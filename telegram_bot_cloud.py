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

# Global variable for button logic state
buttons_flipped = False

class ACController:
    def __init__(self):
        self.remote_manager = SwitcherBreezeRemoteManager()
    
    async def toggle_ac(self):
        """Send toggle command to AC"""
        try:
            logger.info(f"Sending toggle command to AC at {DEVICE_IP}")
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                remote = self.remote_manager.get_remote(REMOTE_ID)
                
                await api.control_breeze_device(
                    remote, 
                    DeviceState.ON,
                    ThermostatMode.COOL,
                    0,  # Let AC use last temperature setting
                    ThermostatFanLevel.MEDIUM,
                    ThermostatSwing.OFF
                )
                
                logger.info(f"Toggle command sent successfully")
                return True
        except Exception as e:
            logger.error(f"Error sending toggle command: {e}")
            return False
    
    async def turn_on_ac(self):
        """Always turn AC ON"""
        try:
            logger.info(f"Turning AC ON at {DEVICE_IP}")
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                remote = self.remote_manager.get_remote(REMOTE_ID)
                
                await api.control_breeze_device(
                    remote, 
                    DeviceState.ON,
                    ThermostatMode.COOL,
                    0,  # Let AC use last temperature setting
                    ThermostatFanLevel.MEDIUM,
                    ThermostatSwing.OFF
                )
                
                logger.info(f"AC ON command sent successfully")
                return True
        except Exception as e:
            logger.error(f"Error turning AC ON: {e}")
            return False
    
    async def turn_off_ac(self):
        """Always turn AC OFF"""
        try:
            logger.info(f"Turning AC OFF at {DEVICE_IP}")
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                remote = self.remote_manager.get_remote(REMOTE_ID)
                
                await api.control_breeze_device(
                    remote, 
                    DeviceState.OFF
                )
                
                logger.info(f"AC OFF command sent successfully")
                return True
        except Exception as e:
            logger.error(f"Error turning AC OFF: {e}")
            return False
    
    async def flip_switcher_state(self):
        """Flip button logic in the bot (no communication with Switcher)"""
        global buttons_flipped
        buttons_flipped = not buttons_flipped
        logger.info(f"Button logic flipped. Buttons flipped: {buttons_flipped}")
        return True

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
        
        return {
            "deployment": deployment,
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

def get_control_menu():
    """Create AC control menu with on, off, and flip state buttons"""
    keyboard = [
        [
            InlineKeyboardButton("🟢 Turn ON", callback_data="turn_on"),
            InlineKeyboardButton("🔴 Turn OFF", callback_data="turn_off")
        ],
        [InlineKeyboardButton("🔄 Flip AC State", callback_data="flip_state")]
    ]
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
            success = await ac.turn_off_ac()
            command_sent = "OFF"
        else:
            # Send ON command normally
            success = await ac.turn_on_ac()
            command_sent = "ON"
        
        if success:
            message = f"✅ {command_sent} command sent!"
        else:
            message = f"❌ Failed to send {command_sent} command"
        
        await query.edit_message_text(
            message,
            reply_markup=get_control_menu()
        )
    
    elif data == "turn_off":
        await query.edit_message_text("🔴 Sending command...")
        
        # Check if buttons are flipped
        if buttons_flipped:
            # Send ON command when buttons are flipped
            success = await ac.turn_on_ac()
            command_sent = "ON"
        else:
            # Send OFF command normally
            success = await ac.turn_off_ac()
            command_sent = "OFF"
        
        if success:
            message = f"✅ {command_sent} command sent!"
        else:
            message = f"❌ Failed to send {command_sent} command"
        
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