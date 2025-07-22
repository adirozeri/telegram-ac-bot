import asyncio
import logging
import os
import platform
import socket
import psutil
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from aioswitcher.api import SwitcherApi
from aioswitcher.api.remotes import SwitcherBreezeRemoteManager
from aioswitcher.device import DeviceType, DeviceState, ThermostatFanLevel, ThermostatMode, ThermostatSwing

from dotenv import load_dotenv
load_dotenv()  # This loads the .env file


# Configure logging for cloud deployment
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration - using environment variables for security

BOT_TOKEN = os.getenv("BOT_TOKEN")
AUTHORIZED_CHAT_IDS = [
    int(os.getenv("CHAT_ID_1")),
    int(os.getenv("CHAT_ID_2"))
]

# Switcher Breeze Configuration - using environment variables
DEVICE_IP = os.getenv("DEVICE_IP")
DEVICE_ID = os.getenv("DEVICE_ID")
DEVICE_KEY = os.getenv("DEVICE_KEY")
TOKEN = os.getenv("SWITCHER_TOKEN")
REMOTE_ID = os.getenv("REMOTE_ID")

DEVICE_TYPE = DeviceType.BREEZE

# Global variables for AC state management
ac_state = {
    "is_on": False,
    "mode": "COOL",
    "temperature": 24,
    "last_updated": None,
    "timer_task": None,
    "timer_end": None
}

# Timers storage
active_timers = {}

class ACController:
    def __init__(self):
        self.remote_manager = SwitcherBreezeRemoteManager()
    
    async def get_status(self):
        """Get AC status from Switcher device"""
        try:
            logger.info(f"Getting AC status from {DEVICE_IP}")
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                state = await api.get_breeze_state()
                logger.info(f"AC status retrieved: {state}")
                
                # Update global state
                global ac_state
                ac_state["is_on"] = state.state.name == "ON"
                ac_state["mode"] = state.mode.name
                ac_state["temperature"] = state.target_temperature
                ac_state["last_updated"] = datetime.now()
                
                return state
        except Exception as e:
            logger.error(f"Error getting AC status: {e}")
            return None
    
    async def control_ac(self, power_state, mode, temperature):
        """Control AC with specified parameters"""
        try:
            logger.info(f"Controlling AC: {power_state}, {mode}, {temperature}C")
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                remote = self.remote_manager.get_remote(REMOTE_ID)
                
                # Map mode strings to enum values
                mode_mapping = {
                    "COOL": ThermostatMode.COOL,
                    "HEAT": ThermostatMode.HEAT,
                    "FAN": ThermostatMode.FAN
                }
                
                await api.control_breeze_device(
                    remote, 
                    DeviceState.ON if power_state else DeviceState.OFF,
                    mode_mapping.get(mode, ThermostatMode.COOL),
                    temperature,
                    ThermostatFanLevel.MEDIUM,
                    ThermostatSwing.OFF
                )
                
                # Update global state
                global ac_state
                ac_state["is_on"] = power_state
                ac_state["mode"] = mode
                ac_state["temperature"] = temperature
                ac_state["last_updated"] = datetime.now()
                
                logger.info(f"AC control successful")
                return True
        except Exception as e:
            logger.error(f"Error controlling AC: {e}")
            return False

# Initialize AC controller
ac = ACController()

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
        
        # Get IP address
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
        except:
            local_ip = "Unknown"
        
        # Get system stats
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        return {
            "deployment": deployment,
            "hostname": hostname,
            "local_ip": local_ip,
            "platform": platform.system(),
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "python_version": platform.python_version(),
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

def get_main_menu():
    """Create main menu keyboard"""
    global ac_state
    
    # Toggle button changes based on current state
    if ac_state["is_on"]:
        toggle_button = InlineKeyboardButton("❄️ Turn OFF", callback_data="toggle_power")
    else:
        toggle_button = InlineKeyboardButton("🔥 Turn ON", callback_data="toggle_power")
    
    keyboard = [
        [toggle_button],
        [
            InlineKeyboardButton("🌡️ Set Temperature", callback_data="set_temp"),
            InlineKeyboardButton("📊 Status", callback_data="status")
        ],
        [
            InlineKeyboardButton("⏱️ Set Timer", callback_data="set_timer"),
            InlineKeyboardButton("🔄 Refresh Menu", callback_data="refresh")
        ],
        [
            InlineKeyboardButton("📍 Set State", callback_data="set_state")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_temperature_menu():
    """Create temperature selection menu"""
    keyboard = []
    # Create temperature buttons in rows of 3
    temps = list(range(16, 31))  # 16-30°C
    for i in range(0, len(temps), 3):
        row = []
        for temp in temps[i:i+3]:
            row.append(InlineKeyboardButton(f"{temp}°C", callback_data=f"temp_{temp}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_state_menu():
    """Create state setting menu"""
    keyboard = [
        [
            InlineKeyboardButton("🟢 AC is ON", callback_data="manual_state_on"),
            InlineKeyboardButton("🔴 AC is OFF", callback_data="manual_state_off")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_timer_menu():
    """Create timer selection menu"""
    keyboard = [
        [
            InlineKeyboardButton("5 min", callback_data="timer_5"),
            InlineKeyboardButton("10 min", callback_data="timer_10"),
            InlineKeyboardButton("15 min", callback_data="timer_15")
        ],
        [
            InlineKeyboardButton("30 min", callback_data="timer_30"),
            InlineKeyboardButton("1 hour", callback_data="timer_60"),
            InlineKeyboardButton("2 hours", callback_data="timer_120")
        ],
        [
            InlineKeyboardButton("❌ Cancel Timer", callback_data="cancel_timer"),
            InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_status_message():
    """Format AC status message"""
    global ac_state
    
    status_emoji = "🟢 ON" if ac_state["is_on"] else "🔴 OFF"
    
    timer_info = ""
    if ac_state["timer_end"]:
        remaining = ac_state["timer_end"] - datetime.now()
        if remaining.total_seconds() > 0:
            minutes = int(remaining.total_seconds() / 60)
            timer_info = f"\n⏰ Timer: {minutes} min remaining"
        else:
            timer_info = "\n⏰ Timer: Expired"
    
    last_update = "Never" if not ac_state["last_updated"] else ac_state["last_updated"].strftime("%H:%M:%S")
    
    return f"""🌡️ **AC Status**

**Power:** {status_emoji}
**Mode:** {ac_state["mode"]}
**Temperature:** {ac_state["temperature"]}°C
**Last Updated:** {last_update}{timer_info}

Use the menu below to control your AC:"""

async def set_ac_timer(chat_id, minutes, context):
    """Set a timer to turn off AC"""
    global ac_state, active_timers
    
    # Cancel existing timer if any
    if ac_state["timer_task"]:
        ac_state["timer_task"].cancel()
    
    # Set new timer
    ac_state["timer_end"] = datetime.now() + timedelta(minutes=minutes)
    
    async def timer_callback():
        await asyncio.sleep(minutes * 60)
        # Turn off AC
        success = await ac.control_ac(False, "COOL", 24)
        if success:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏰ Timer expired! AC turned OFF after {minutes} minutes."
            )
            ac_state["timer_task"] = None
            ac_state["timer_end"] = None
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Timer expired but failed to turn OFF AC. Please check manually."
            )
    
    ac_state["timer_task"] = asyncio.create_task(timer_callback())

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command with main menu"""
    if not check_authorization(update):
        await update.message.reply_text("❌ Unauthorized access")
        return
    
    logger.info(f"Start command from authorized user: {update.effective_chat.id}")
    
    welcome_text = f"""🤖 **AC Controller Bot**

{format_status_message()}"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu(),
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
**Hostname:** {info.get('hostname', 'Unknown')}
**Local IP:** {info.get('local_ip', 'Unknown')}
**Platform:** {info.get('platform', 'Unknown')}
**CPU Usage:** {info.get('cpu_percent', 0):.1f}%
**Memory Usage:** {info.get('memory_percent', 0):.1f}%
**Python Version:** {info.get('python_version', 'Unknown')}
**Started:** {info.get('start_time', 'Unknown')}
**Device IP:** {DEVICE_IP}
**Device ID:** {DEVICE_ID}
"""
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks"""
    if not check_authorization(update):
        await update.callback_query.answer("❌ Unauthorized access")
        return
    
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "toggle_power":
        # Toggle AC power based on current state
        if ac_state["is_on"]:
            # AC is currently ON, so turn it OFF
            await query.edit_message_text("🔄 Turning AC OFF...")
            success = await ac.control_ac(False, "COOL", ac_state["temperature"])
            if success:
                message = f"✅ AC turned OFF successfully!\n\n{format_status_message()}"
            else:
                message = f"❌ Failed to turn OFF AC\n\n{format_status_message()}"
        else:
            # AC is currently OFF, so turn it ON
            await query.edit_message_text("🔄 Turning AC ON...")
            success = await ac.control_ac(True, "COOL", ac_state["temperature"])
            if success:
                message = f"✅ AC turned ON successfully!\n\n{format_status_message()}"
            else:
                message = f"❌ Failed to turn ON AC\n\n{format_status_message()}"
        
        await query.edit_message_text(message, reply_markup=get_main_menu(), parse_mode='Markdown')
    
    elif data == "set_state":
        await query.edit_message_text(
            "📍 Manually set AC state in bot memory:\n\n(Use this to correct the bot's state when it gets out of sync with the actual AC)",
            reply_markup=get_state_menu()
        )
    
    elif data == "manual_state_on":
        # Manually set AC state to ON in bot memory only
        ac_state["is_on"] = True
        ac_state["last_updated"] = datetime.now()
        message = f"✅ Bot state set to ON manually\n\n{format_status_message()}"
        await query.edit_message_text(message, reply_markup=get_main_menu(), parse_mode='Markdown')
    
    elif data == "manual_state_off":
        # Manually set AC state to OFF in bot memory only
        ac_state["is_on"] = False
        ac_state["last_updated"] = datetime.now()
        message = f"✅ Bot state set to OFF manually\n\n{format_status_message()}"
        await query.edit_message_text(message, reply_markup=get_main_menu(), parse_mode='Markdown')
    
    elif data == "set_temp":
        await query.edit_message_text(
            "🌡️ Select temperature:",
            reply_markup=get_temperature_menu()
        )
    
    elif data.startswith("temp_"):
        temp = int(data.split("_")[1])
        await query.edit_message_text(f"🔄 Setting temperature to {temp}°C...")
        # Turn on AC with selected temperature
        success = await ac.control_ac(True, "COOL", temp)
        if success:
            message = f"✅ AC set to {temp}°C!\n\n{format_status_message()}"
        else:
            message = f"❌ Failed to set temperature\n\n{format_status_message()}"
        await query.edit_message_text(message, reply_markup=get_main_menu(), parse_mode='Markdown')
    
    elif data == "status":
        # Refresh status from device
        await query.edit_message_text("🔄 Getting AC status...")
        device_state = await ac.get_status()
        if device_state:
            message = f"📊 Status refreshed from device\n\n{format_status_message()}"
        else:
            message = f"❌ Failed to get status from device\n\n{format_status_message()}"
        await query.edit_message_text(message, reply_markup=get_main_menu(), parse_mode='Markdown')
    
    elif data == "set_timer":
        await query.edit_message_text(
            "⏱️ Set timer to turn OFF AC:",
            reply_markup=get_timer_menu()
        )
    
    elif data.startswith("timer_"):
        minutes = int(data.split("_")[1])
        await set_ac_timer(query.message.chat_id, minutes, context)
        message = f"⏰ Timer set for {minutes} minutes!\n\n{format_status_message()}"
        await query.edit_message_text(message, reply_markup=get_main_menu(), parse_mode='Markdown')
    
    elif data == "cancel_timer":
        if ac_state["timer_task"]:
            ac_state["timer_task"].cancel()
            ac_state["timer_task"] = None
            ac_state["timer_end"] = None
            message = f"⏰ Timer cancelled!\n\n{format_status_message()}"
        else:
            message = f"⏰ No active timer to cancel\n\n{format_status_message()}"
        await query.edit_message_text(message, reply_markup=get_main_menu(), parse_mode='Markdown')
    
    elif data == "refresh" or data == "back_to_main":
        message = format_status_message()
        await query.edit_message_text(message, reply_markup=get_main_menu(), parse_mode='Markdown')

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages by showing menu"""
    if not check_authorization(update):
        await update.message.reply_text("❌ Unauthorized access")
        return
    
    # Always respond with the menu
    message = f"🤖 Use the menu below to control your AC:\n\n{format_status_message()}"
    await update.message.reply_text(
        message,
        reply_markup=get_main_menu(),
        parse_mode='Markdown'
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
**Platform:** {info.get('platform', 'Unknown')}
**Python:** {info.get('python_version', 'Unknown')}
**CPU:** {info.get('cpu_percent', 0):.1f}%
**Memory:** {info.get('memory_percent', 0):.1f}%

Bot is ready to control your AC! 🌡️

{format_status_message()}"""
    
    for chat_id in AUTHORIZED_CHAT_IDS:
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=startup_message,
                parse_mode='Markdown',
                reply_markup=get_main_menu()
            )
            logger.info(f"Startup notification sent to {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send startup notification to {chat_id}: {e}")

async def post_init(application):
    """Called after the bot starts - send startup notification"""
    await send_startup_notification(application)

def main():
    """Start the bot"""
    logger.info("=== STARTING ENHANCED TELEGRAM AC CONTROLLER BOT ===")
    
    if DEVICE_IP == "YOUR_PUBLIC_IP_HERE":
        logger.error("ERROR: Please replace YOUR_PUBLIC_IP_HERE with your actual public IP!")
        return
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("where", where_command))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_error_handler(error_handler)
    
    # Start bot
    logger.info("Bot is running with enhanced menu interface!")
    
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