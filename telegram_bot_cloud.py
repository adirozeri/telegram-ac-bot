import asyncio
import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from aioswitcher.api import SwitcherApi
from aioswitcher.api.remotes import SwitcherBreezeRemoteManager
from aioswitcher.device import DeviceType, DeviceState, ThermostatFanLevel, ThermostatMode, ThermostatSwing

# Configure logging for cloud deployment
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration - using environment variables for security
BOT_TOKEN = os.getenv("BOT_TOKEN", "7749658228:AAHVodV0YEWj-drf5MUGZWob5IG-mU-CSYw")
AUTHORIZED_CHAT_IDS = [
    int(os.getenv("CHAT_ID_1", "999186130")),
    int(os.getenv("CHAT_ID_2", "922682443"))
]

# Switcher Breeze Configuration - using environment variables
# IMPORTANT: Replace YOUR_PUBLIC_IP_HERE with your actual public IP from whatismyipaddress.com
DEVICE_IP = os.getenv("DEVICE_IP", "46.120.215.94")  # Your public IP goes here
DEVICE_ID = os.getenv("DEVICE_ID", "645eb7")
DEVICE_KEY = os.getenv("DEVICE_KEY", "03")
TOKEN = os.getenv("SWITCHER_TOKEN", "yr60o/WGJZVRCxBd6ywclg==")
REMOTE_ID = os.getenv("REMOTE_ID", "ELEC7009")

DEVICE_TYPE = DeviceType.BREEZE

class ACController:
    def __init__(self):
        self.remote_manager = SwitcherBreezeRemoteManager()
    
    async def get_status(self):
        """Get AC status"""
        try:
            logger.info(f"Getting AC status from {DEVICE_IP}")
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                state = await api.get_breeze_state()
                logger.info(f"AC status retrieved: {state}")
                return f"AC Status: {state}"
        except Exception as e:
            logger.error(f"Error getting AC status: {e}")
            return f"Error getting status: {str(e)}"
    
    async def turn_on_cooling(self, temperature=24):
        """Turn on AC with cooling"""
        try:
            logger.info(f"Turning on AC cooling to {temperature}C")
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                remote = self.remote_manager.get_remote(REMOTE_ID)
                await api.control_breeze_device(
                    remote, DeviceState.ON, ThermostatMode.COOL, temperature,
                    ThermostatFanLevel.MEDIUM, ThermostatSwing.OFF
                )
                logger.info(f"AC turned ON - Cooling {temperature}C")
                return f"AC turned ON - Cooling {temperature}C"
        except Exception as e:
            logger.error(f"Error turning on AC cooling: {e}")
            return f"Error turning on AC: {str(e)}"
    
    async def turn_on_heating(self, temperature=22):
        """Turn on AC with heating"""
        try:
            logger.info(f"Turning on AC heating to {temperature}C")
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                remote = self.remote_manager.get_remote(REMOTE_ID)
                await api.control_breeze_device(
                    remote, DeviceState.ON, ThermostatMode.HEAT, temperature,
                    ThermostatFanLevel.MEDIUM, ThermostatSwing.OFF
                )
                logger.info(f"AC turned ON - Heating {temperature}C")
                return f"AC turned ON - Heating {temperature}C"
        except Exception as e:
            logger.error(f"Error turning on AC heating: {e}")
            return f"Error turning on heating: {str(e)}"
    
    async def turn_off(self):
        """Turn off AC"""
        try:
            logger.info("Turning off AC")
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                remote = self.remote_manager.get_remote(REMOTE_ID)
                await api.control_breeze_device(
                    remote, DeviceState.OFF, ThermostatMode.COOL, 24,
                    ThermostatFanLevel.MEDIUM, ThermostatSwing.OFF
                )
                logger.info("AC turned OFF")
                return "AC turned OFF"
        except Exception as e:
            logger.error(f"Error turning off AC: {e}")
            return f"Error turning off AC: {str(e)}"
    
    async def fan_only(self):
        """Set AC to fan only mode"""
        try:
            logger.info("Setting AC to fan only mode")
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                remote = self.remote_manager.get_remote(REMOTE_ID)
                await api.control_breeze_device(
                    remote, DeviceState.ON, ThermostatMode.FAN, 24,
                    ThermostatFanLevel.MEDIUM, ThermostatSwing.OFF
                )
                logger.info("AC set to FAN mode")
                return "AC set to FAN mode"
        except Exception as e:
            logger.error(f"Error setting fan mode: {e}")
            return f"Error setting fan mode: {str(e)}"

# Initialize AC controller
ac = ACController()

# Security check
def check_authorization(update: Update) -> bool:
    """Check if user is authorized"""
    user_id = update.effective_chat.id
    authorized = user_id in AUTHORIZED_CHAT_IDS
    if not authorized:
        logger.warning(f"Unauthorized access attempt from user ID: {user_id}")
    return authorized

# Bot command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    logger.info(f"Start command from authorized user: {update.effective_chat.id}")
    welcome_text = """
AC Controller Bot - Cloud Version

Available commands:
• 'on' or /cool - Turn on cooling (24C)
• 'off' or /off - Turn off AC  
• /heat - Turn on heating (22C)
• /fan - Fan only mode
• /status - Check AC status
• /cool 26 - Cool to specific temperature
• /heat 20 - Heat to specific temperature

Just type "on" or "off" for quick control! 

Running 24/7 in the cloud!
    """
    await update.message.reply_text(welcome_text)

async def get_status(self):
        """Get AC status"""
        try:
            logger.info(f"Getting AC status from {DEVICE_IP}")
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                state = await api.get_breeze_state()
                logger.info(f"AC status retrieved: {state}")
                
                # Format the response in a user-friendly way
                status_text = f"""🌡️ **AC Status**
                
**Power:** {"🟢 ON" if state.state.name == "ON" else "🔴 OFF"}
**Mode:** {state.mode.name.title()}
**Current Temp:** {state.temperature}°C
**Target Temp:** {state.target_temperature}°C
**Fan Level:** {state.fan_level.name.title()}
**Swing:** {state.swing.name.title()}
**Remote ID:** {state.remote_id}
                """
                
                return status_text
        except Exception as e:
            logger.error(f"Error getting AC status: {e}")
            return f"❌ Error getting status: {str(e)}"


async def cool_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cool command with optional temperature"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    temp = 24  # default
    if context.args:
        try:
            temp = int(context.args[0])
            if not (16 <= temp <= 30):
                await update.message.reply_text("Temperature must be between 16-30C")
                return
        except ValueError:
            await update.message.reply_text("Invalid temperature")
            return
    
    logger.info(f"Cool command ({temp}C) from user: {update.effective_chat.id}")
    await update.message.reply_text(f"Turning on cooling to {temp}C...")
    result = await ac.turn_on_cooling(temp)
    await update.message.reply_text(result)

async def heat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Heat command with optional temperature"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    temp = 22  # default
    if context.args:
        try:
            temp = int(context.args[0])
            if not (16 <= temp <= 30):
                await update.message.reply_text("Temperature must be between 16-30C")
                return
        except ValueError:
            await update.message.reply_text("Invalid temperature")
            return
    
    logger.info(f"Heat command ({temp}C) from user: {update.effective_chat.id}")
    await update.message.reply_text(f"Turning on heating to {temp}C...")
    result = await ac.turn_on_heating(temp)
    await update.message.reply_text(result)

async def off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Turn off AC"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    logger.info(f"Off command from user: {update.effective_chat.id}")
    await update.message.reply_text("Turning off AC...")
    result = await ac.turn_off()
    await update.message.reply_text(result)

async def fan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fan only mode"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    logger.info(f"Fan command from user: {update.effective_chat.id}")
    await update.message.reply_text("Setting fan only mode...")
    result = await ac.fan_only()
    await update.message.reply_text(result)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle simple text messages like 'on' and 'off'"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    text = update.message.text.lower().strip()
    user_id = update.effective_chat.id
    
    if text in ['on', 'turn on', 'start', 'cool']:
        logger.info(f"Text 'on' command from user: {user_id}")
        await update.message.reply_text("Turning on cooling to 24C...")
        result = await ac.turn_on_cooling(24)
        await update.message.reply_text(result)
    
    elif text in ['off', 'turn off', 'stop']:
        logger.info(f"Text 'off' command from user: {user_id}")
        await update.message.reply_text("Turning off AC...")
        result = await ac.turn_off()
        await update.message.reply_text(result)
    
    elif text in ['status', 'check']:
        logger.info(f"Text 'status' command from user: {user_id}")
        await update.message.reply_text("Checking AC status...")
        result = await ac.get_status()
        await update.message.reply_text(result)
    
    elif text in ['fan', 'fan only']:
        logger.info(f"Text 'fan' command from user: {user_id}")
        await update.message.reply_text("Setting fan only mode...")
        result = await ac.fan_only()
        await update.message.reply_text(result)
    
    else:
        await update.message.reply_text(
            "I don't understand. Try:\n"
            "• 'on' or 'off'\n"
            "• /cool or /heat\n"
            "• /status for AC status"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot"""
    logger.info("=== STARTING TELEGRAM AC CONTROLLER BOT ===")
    logger.info(f"Bot Token: {BOT_TOKEN[:10]}...")
    logger.info(f"Authorized users: {AUTHORIZED_CHAT_IDS}")
    logger.info(f"Device IP: {DEVICE_IP}")
    logger.info(f"Device ID: {DEVICE_ID}")
    logger.info(f"Remote ID: {REMOTE_ID}")
    
    if DEVICE_IP == "YOUR_PUBLIC_IP_HERE":
        logger.error("ERROR: Please replace YOUR_PUBLIC_IP_HERE with your actual public IP!")
        logger.error("Get your public IP from: https://whatismyipaddress.com/")
        return
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("cool", cool_command))
    application.add_handler(CommandHandler("heat", heat_command))
    application.add_handler(CommandHandler("off", off_command))
    application.add_handler(CommandHandler("fan", fan_command))
    
    # Handle simple text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    logger.info("Bot is running! Listening for commands...")
    logger.info("=== BOT READY FOR CLOUD DEPLOYMENT ===")
    
    # Use webhook for cloud deployment (if PORT is set) or polling for local testing
    port = int(os.environ.get("PORT", 0))
    if port:
        # Get the webhook URL - try multiple environment variables
        render_url = os.environ.get('RENDER_EXTERNAL_URL') or os.environ.get('RENDER_SERVICE_URL')
        
        if not render_url:
            logger.error("ERROR: RENDER_EXTERNAL_URL environment variable not set!")
            logger.error("Please set RENDER_EXTERNAL_URL to your Render app URL in the dashboard")
            logger.error("Example: telegram-ac-bot-xyz.onrender.com")
            return
        
        # Handle URLs that may or may not include https://
        if render_url.startswith('https://'):
            webhook_url = f"{render_url}/webhook"
        else:
                webhook_url = f"https://{render_url}/webhook"
        
        logger.info(f"Raw RENDER_EXTERNAL_URL: '{render_url}'")
        logger.info(f"Final webhook URL: '{webhook_url}'")
        
        # Cloud deployment with webhook
        logger.info(f"Starting webhook mode on port {port}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=webhook_url
        )
    else:
        # Local testing with polling
        logger.info("Starting polling mode for local testing")
        application.run_polling()




if __name__ == "__main__":
    main()
