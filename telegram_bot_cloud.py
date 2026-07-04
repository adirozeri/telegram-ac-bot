"""
Simplified Telegram AC Controller Bot - Toggle Only
Load environment variables FIRST before anything else
"""

# CRITICAL: Load environment variables BEFORE any other imports
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file immediately - before any other operations
script_dir = Path(__file__).parent
env_path = script_dir / '.env'
load_dotenv(env_path, override=True)

# Verify critical variables are loaded
bot_token = os.getenv("BOT_TOKEN")
if not bot_token:
    print("❌ ERROR: BOT_TOKEN not found in environment variables!")
    print("Please check your .env file exists and contains BOT_TOKEN=your_token_here")
    exit(1)

# Now import everything else
import asyncio
import logging
import platform
import socket
import psutil
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from aioswitcher.api import SwitcherApi
from aioswitcher.api.remotes import SwitcherBreezeRemoteManager
from aioswitcher.bridge import SwitcherBridge
from aioswitcher.device import DeviceType, DeviceState, ThermostatFanLevel, ThermostatMode, ThermostatSwing

# Configure logging properly to prevent token exposure
def setup_logging():
    """Configure logging with security considerations"""
    # Main application logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(),  # Console output
            # Uncomment for file logging:
            # logging.FileHandler('/home/pi/telegram-ac-bot/bot.log', mode='a')
        ]
    )
    
    # Silence noisy third-party libraries to prevent token exposure
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aioswitcher").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

# Setup logging and get main logger
logger = setup_logging()

# Bot Configuration - using environment variables for security
BOT_TOKEN = bot_token  # Use the verified token from above

# Handle missing environment variables gracefully
try:
    AUTHORIZED_CHAT_IDS = [
        int(os.getenv("CHAT_ID_1")),
        int(os.getenv("CHAT_ID_2"))
    ]
except (TypeError, ValueError) as e:
    logger.error(f"Error reading CHAT_ID environment variables: {e}")
    logger.error("Please ensure CHAT_ID_1 and CHAT_ID_2 are set in your .env file or environment variables")
    exit(1)

# Switcher Breeze Configuration - using environment variables
DEVICE_IP = os.getenv("DEVICE_IP")
DEVICE_ID = os.getenv("DEVICE_ID")
DEVICE_KEY = os.getenv("DEVICE_KEY")
TOKEN = os.getenv("SWITCHER_TOKEN")
REMOTE_ID = os.getenv("REMOTE_ID")

# Verify all required variables are loaded
required_vars = {
    'DEVICE_IP': DEVICE_IP,
    'DEVICE_ID': DEVICE_ID,
    'DEVICE_KEY': DEVICE_KEY,
    'SWITCHER_TOKEN': TOKEN,
    'REMOTE_ID': REMOTE_ID
}

missing_vars = [key for key, value in required_vars.items() if not value]
if missing_vars:
    logger.error(f"Missing required environment variables: {missing_vars}")
    logger.error("Please check your .env file contains all required variables")
    exit(1)

DEVICE_TYPE = DeviceType.BREEZE

# Reliability tuning
# NOTE: the Breeze broadcasts its presence only every ~20-30s, so the discovery
# window must be long enough to catch at least one broadcast. Discovery only runs
# when the cached/last-known IP fails, so this slow path is the rare case.
DISCOVERY_TIMEOUT = 35     # seconds to listen for the device's UDP broadcast
COMMAND_TIMEOUT = 12       # seconds for a full login+control round-trip
MAX_ATTEMPTS = 2           # command attempts before giving up (re-discovers between tries)

# Global variable for button logic state
buttons_flipped = False

class ACController:
    def __init__(self):
        self.remote_manager = SwitcherBreezeRemoteManager()
        # Last-known IP. DEVICE_IP from .env is only a starting hint, not the
        # source of truth — the device is located by DEVICE_ID via discovery.
        self._ip = DEVICE_IP or None
        self._key = DEVICE_KEY

    async def discover(self, timeout=DISCOVERY_TIMEOUT):
        """Find the device's current IP by listening for its UDP broadcast.

        Switcher devices get DHCP addresses that drift, so we match on the stable
        DEVICE_ID rather than a hardcoded IP. Returns the IP, or None on timeout.
        """
        loop = asyncio.get_event_loop()
        found = loop.create_future()

        def on_device(device):
            if device.device_id == DEVICE_ID and not found.done():
                found.set_result(device)

        try:
            async with SwitcherBridge(on_device):
                device = await asyncio.wait_for(found, timeout)
            self._ip = device.ip_address
            if getattr(device, "device_key", None):
                self._key = device.device_key
            logger.info(f"Discovered device {DEVICE_ID} at {self._ip}")
            return self._ip
        except asyncio.TimeoutError:
            logger.warning(f"Discovery timed out after {timeout}s (device {DEVICE_ID} not heard on LAN)")
            return None
        except Exception as e:
            logger.error(f"Discovery error: {e}")
            return None

    async def _send(self, *args, label="command"):
        """Send a Breeze control command, (re)discovering the IP and retrying.

        Returns (ok: bool, error: str|None) so callers can surface a real reason.
        """
        last_err = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if not self._ip:
                await self.discover()
            if not self._ip:
                last_err = "device not found on the network"
                continue
            try:
                async with asyncio.timeout(COMMAND_TIMEOUT):
                    async with SwitcherApi(DEVICE_TYPE, self._ip, DEVICE_ID, self._key, token=TOKEN) as api:
                        remote = self.remote_manager.get_remote(REMOTE_ID)
                        await api.control_breeze_device(remote, *args)
                logger.info(f"{label} sent successfully to {self._ip}")
                return True, None
            except (asyncio.TimeoutError, OSError) as e:
                last_err = f"{type(e).__name__}: {e}"
                logger.warning(f"{label} attempt {attempt}/{MAX_ATTEMPTS} failed ({last_err}); re-discovering")
                self._ip = None  # force fresh discovery on the next attempt
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                logger.error(f"{label} attempt {attempt}/{MAX_ATTEMPTS} error: {last_err}")
                self._ip = None
        return False, last_err

    async def turn_on_ac(self):
        """Send an explicit ON command (COOL, last temperature, medium fan)."""
        return await self._send(
            DeviceState.ON, ThermostatMode.COOL, 0,
            ThermostatFanLevel.MEDIUM, ThermostatSwing.OFF,
            label="ON",
        )

    async def turn_off_ac(self):
        """Send an explicit OFF command."""
        return await self._send(DeviceState.OFF, label="OFF")

    async def flip_switcher_state(self):
        """Flip the bot's button logic (no communication with the device).

        The Switcher Breeze is an IR blaster whose reported state can't be
        trusted, so this manual override lets the user correct which physical
        action the ON/OFF buttons actually produce.
        """
        global buttons_flipped
        buttons_flipped = not buttons_flipped
        logger.info(f"Button logic flipped. Buttons flipped: {buttons_flipped}")
        return True


class CycleManager:
    """Runs an ON/OFF duty cycle: hold ON for on_min, then OFF for off_min, repeat.

    Drives the AC with explicit ON/OFF commands (never relies on device state),
    starting with ON. Held in memory only — a bot restart clears any active cycle.
    """

    def __init__(self, controller):
        self.ac = controller
        self.task = None
        self.on_min = None
        self.off_min = None

    @property
    def running(self):
        return self.task is not None and not self.task.done()

    def start(self, on_min, off_min, bot, chat_id):
        self.stop()
        self.on_min, self.off_min = on_min, off_min
        self.task = asyncio.create_task(self._run(on_min, off_min, bot, chat_id))

    def stop(self):
        if self.task and not self.task.done():
            self.task.cancel()
        self.task = None
        self.on_min = self.off_min = None

    async def _run(self, on_min, off_min, bot, chat_id):
        intend_on = True  # start with ON
        try:
            while True:
                # Honour the same flip the manual buttons use, so the cycle's
                # "ON" produces the same physical action as the 🟢 button.
                if intend_on ^ buttons_flipped:
                    ok, err = await self.ac.turn_on_ac()
                else:
                    ok, err = await self.ac.turn_off_ac()

                label = "ON" if intend_on else "OFF"
                hold = on_min if intend_on else off_min
                logger.info(f"Cycle tick: {label} (ok={ok}) holding {hold} min")
                try:
                    if ok:
                        text = f"🔁 Cycle: AC {label} — holding {hold} min"
                    else:
                        text = f"🔁 Cycle: {label} command failed ({err}) — holding {hold} min"
                    await bot.send_message(chat_id=chat_id, text=text)
                except Exception as e:
                    logger.error(f"Cycle notify failed: {e}")

                await asyncio.sleep(hold * 60)
                intend_on = not intend_on
        except asyncio.CancelledError:
            logger.info("Cycle stopped")
            raise

# Initialize AC controller and cycle manager
ac = ACController()
cycle = CycleManager(ac)

def get_system_info():
    """Get system information for monitoring"""
    try:
        # Determine deployment type
        if os.getenv("RENDER"):
            deployment = "🌐 Render Cloud"
        elif os.getenv("RAILWAY_PROJECT_ID"):
            deployment = "🚂 Railway"
        elif os.getenv("HEROKU_APP_NAME"):
            deployment = "🟣 Heroku"
        elif os.path.exists("/home/pi"):
            deployment = "🥧 Raspberry Pi"
        else:
            deployment = "💻 Local Computer"
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            host_ip = s.getsockname()[0]
            s.close()
        except Exception:
            host_ip = "Unknown"

        return {
            "deployment": deployment,
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "host_ip": host_ip
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        return {"deployment": "Unknown", "error": str(e)}

def check_authorization(update: Update) -> bool:
    """Check if user is authorized"""
    user_id = update.effective_chat.id
    authorized = user_id in AUTHORIZED_CHAT_IDS
    if not authorized:
        logger.warning(f"Unauthorized access attempt from user ID: {user_id}")
    return authorized

CYCLE_PRESETS = [5, 10, 15, 30, 60]  # minutes

def get_control_menu():
    """Create AC control menu with on, off, flip, and auto-cycle buttons"""
    keyboard = [
        [
            InlineKeyboardButton("🟢 Turn ON", callback_data="turn_on"),
            InlineKeyboardButton("🔴 Turn OFF", callback_data="turn_off")
        ],
        [InlineKeyboardButton("🔄 Flip AC State", callback_data="flip_state")]
    ]
    if cycle.running:
        keyboard.append([InlineKeyboardButton(
            f"🛑 Stop Cycle ({cycle.on_min}m on / {cycle.off_min}m off)",
            callback_data="cycle_stop")])
    else:
        keyboard.append([InlineKeyboardButton("🔁 Auto Cycle", callback_data="cycle_menu")])
    return InlineKeyboardMarkup(keyboard)

def _preset_rows(callback_prefix):
    """Build rows of preset-minute buttons, 3 per row, with the given callback prefix."""
    buttons = [InlineKeyboardButton(f"{m} min", callback_data=f"{callback_prefix}{m}") for m in CYCLE_PRESETS]
    return [buttons[i:i + 3] for i in range(0, len(buttons), 3)]

def get_cycle_on_menu():
    """Step 1: choose how long the AC stays ON each cycle."""
    keyboard = _preset_rows("cycleon_")
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_cycle_off_menu(on_min):
    """Step 2: choose how long the AC stays OFF (on_min carried in callback data)."""
    keyboard = _preset_rows(f"cyclego_{on_min}_")
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="cycle_menu")])
    return InlineKeyboardMarkup(keyboard)

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command with toggle menu"""
    if not check_authorization(update):
        await update.message.reply_text("❌ Unauthorized access")
        return
    
    logger.info(f"Start command from authorized user: {update.effective_chat.id}")
    
    welcome_text = "🤖 **AC Controller Bot**\n\nUse the buttons below to control your AC:"
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_control_menu(),
        parse_mode='Markdown'
    )

async def where_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show system information"""
    if not check_authorization(update):
        await update.message.reply_text("❌ Unauthorized access")
        return
    
    info = get_system_info()
    
    message = f"""🖥️ **System Information**

**Deployment:** {info['deployment']}
**Started:** {info.get('start_time', 'Unknown')}
**Device IP:** {DEVICE_IP}
**Device ID:** {DEVICE_ID}
"""
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks"""
    global buttons_flipped
    
    if not check_authorization(update):
        await update.callback_query.answer("❌ Unauthorized access")
        return
    
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "turn_on":
        await query.edit_message_text("🟢 Sending command...")
        
        # Check if buttons are flipped
        if buttons_flipped:
            # Send OFF command when buttons are flipped
            ok, err = await ac.turn_off_ac()
            command_sent = "OFF"
        else:
            # Send ON command normally
            ok, err = await ac.turn_on_ac()
            command_sent = "ON"

        if ok:
            message = f"✅ {command_sent} command sent!"
        else:
            message = f"❌ Failed to send {command_sent} command\n({err})"

        await query.edit_message_text(
            message,
            reply_markup=get_control_menu()
        )

    elif data == "turn_off":
        await query.edit_message_text("🔴 Sending command...")
        
        # Check if buttons are flipped
        if buttons_flipped:
            # Send ON command when buttons are flipped
            ok, err = await ac.turn_on_ac()
            command_sent = "ON"
        else:
            # Send OFF command normally
            ok, err = await ac.turn_off_ac()
            command_sent = "OFF"

        if ok:
            message = f"✅ {command_sent} command sent!"
        else:
            message = f"❌ Failed to send {command_sent} command\n({err})"

        await query.edit_message_text(
            message,
            reply_markup=get_control_menu()
        )

    elif data == "flip_state":
        success = await ac.flip_switcher_state()
        
        if success:
            flip_status = "ON" if buttons_flipped else "OFF"
            message = f"✅ Button logic flipped!\n\n🟢 ON button now sends: {flip_status}\n🔴 OFF button now sends: {'OFF' if buttons_flipped else 'ON'}"
        else:
            message = "❌ Failed to flip button logic"
        
        await query.edit_message_text(
            message,
            reply_markup=get_control_menu()
        )

    elif data == "cycle_menu":
        await query.edit_message_text(
            "🔁 *Auto Cycle* — step 1 of 2\n\nHow long should the AC stay *ON* each cycle?",
            reply_markup=get_cycle_on_menu(),
            parse_mode='Markdown'
        )

    elif data == "back_to_main":
        await query.edit_message_text(
            "🤖 Use the buttons below to control your AC:",
            reply_markup=get_control_menu()
        )

    elif data == "cycle_stop":
        cycle.stop()
        await query.edit_message_text(
            "🛑 Auto Cycle stopped.",
            reply_markup=get_control_menu()
        )

    elif data.startswith("cycleon_"):
        on_min = int(data.split("_")[1])
        await query.edit_message_text(
            f"🔁 *Auto Cycle* — step 2 of 2\n\n🟢 ON = *{on_min} min*.\nNow how long should the AC stay *OFF*?",
            reply_markup=get_cycle_off_menu(on_min),
            parse_mode='Markdown'
        )

    elif data.startswith("cyclego_"):
        _, on_s, off_s = data.split("_")
        on_min, off_min = int(on_s), int(off_s)
        cycle.start(on_min, off_min, context.bot, update.effective_chat.id)
        await query.edit_message_text(
            f"🔁 Auto Cycle started:\n🟢 ON for {on_min} min → 🔴 OFF for {off_min} min → repeat.\n\nSending ON now…",
            reply_markup=get_control_menu()
        )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages by showing menu"""
    if not check_authorization(update):
        await update.message.reply_text("❌ Unauthorized access")
        return
    
    # Always respond with the control menu
    message = "🤖 Use the buttons below to control your AC:"
    await update.message.reply_text(
        message,
        reply_markup=get_control_menu()
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

async def send_startup_notification(application):
    """Send startup notification to authorized users"""
    info = get_system_info()
    
    startup_message = f"""🚀 **AC Bot Started!**

**Time:** {info['start_time']}
**Running on:** {info['deployment']}
**Bot IP:** {info['host_ip']}

Bot is ready to control your AC! 🌡️"""
    
    for chat_id in AUTHORIZED_CHAT_IDS:
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=startup_message,
                parse_mode='Markdown',
                reply_markup=get_control_menu()
            )
            logger.info(f"Startup notification sent to {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send startup notification to {chat_id}: {e}")

async def post_init(application):
    """Called after the bot starts - send startup notification"""
    await send_startup_notification(application)

def main():
    """Start the bot"""
    logger.info("=== STARTING SIMPLIFIED TELEGRAM AC TOGGLE BOT ===")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("where", where_command))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_error_handler(error_handler)

    # Start bot
    logger.info("Bot is running with simple toggle interface!")
    
    port = int(os.environ.get("PORT", 0))
    if port:
        render_url = os.environ.get('RENDER_EXTERNAL_URL') or os.environ.get('RENDER_SERVICE_URL')
        if not render_url:
            logger.error("ERROR: RENDER_EXTERNAL_URL environment variable not set!")
            return
        
        webhook_url = f"https://{render_url}/webhook" if not render_url.startswith('https://') else f"{render_url}/webhook"
        logger.info(f"Starting webhook mode: {webhook_url}")
        
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=webhook_url
        )
    else:
        logger.info("Starting polling mode for local testing")
        application.run_polling()

if __name__ == "__main__":
    main()