import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from aioswitcher.api import SwitcherApi
from aioswitcher.api.remotes import SwitcherBreezeRemoteManager
from aioswitcher.device import DeviceType, DeviceState, ThermostatFanLevel, ThermostatMode, ThermostatSwing

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot Configuration
BOT_TOKEN = "7749658228:AAHVodV0YEWj-drf5MUGZWob5IG-mU-CSYw"
AUTHORIZED_CHAT_IDS = [999186130, 922682443]  # Jim (@adirozeri) and Paulina (@pau_pau17)

# Switcher Breeze Configuration
DEVICE_TYPE = DeviceType.BREEZE
DEVICE_IP = "192.168.1.126"
DEVICE_ID = "645eb7"
DEVICE_KEY = "03"
TOKEN = "yr60o/WGJZVRCxBd6ywclg=="
REMOTE_ID = "ELEC7009"

class ACController:
    def __init__(self):
        self.remote_manager = SwitcherBreezeRemoteManager()
    
    async def get_status(self):
        """Get AC status"""
        try:
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                state = await api.get_breeze_state()
                return f"AC Status: {state}"
        except Exception as e:
            return f"Error getting status: {str(e)}"
    
    async def turn_on_cooling(self, temperature=24):
        """Turn on AC with cooling"""
        try:
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                remote = self.remote_manager.get_remote(REMOTE_ID)
                await api.control_breeze_device(
                    remote, DeviceState.ON, ThermostatMode.COOL, temperature,
                    ThermostatFanLevel.MEDIUM, ThermostatSwing.OFF
                )
                return f"AC turned ON - Cooling {temperature}C"
        except Exception as e:
            return f"Error turning on AC: {str(e)}"
    
    async def turn_on_heating(self, temperature=22):
        """Turn on AC with heating"""
        try:
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                remote = self.remote_manager.get_remote(REMOTE_ID)
                await api.control_breeze_device(
                    remote, DeviceState.ON, ThermostatMode.HEAT, temperature,
                    ThermostatFanLevel.MEDIUM, ThermostatSwing.OFF
                )
                return f"AC turned ON - Heating {temperature}C"
        except Exception as e:
            return f"Error turning on heating: {str(e)}"
    
    async def turn_off(self):
        """Turn off AC"""
        try:
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                remote = self.remote_manager.get_remote(REMOTE_ID)
                await api.control_breeze_device(
                    remote, DeviceState.OFF, ThermostatMode.COOL, 24,
                    ThermostatFanLevel.MEDIUM, ThermostatSwing.OFF
                )
                return "AC turned OFF"
        except Exception as e:
            return f"Error turning off AC: {str(e)}"
    
    async def fan_only(self):
        """Set AC to fan only mode"""
        try:
            async with SwitcherApi(DEVICE_TYPE, DEVICE_IP, DEVICE_ID, DEVICE_KEY) as api:
                remote = self.remote_manager.get_remote(REMOTE_ID)
                await api.control_breeze_device(
                    remote, DeviceState.ON, ThermostatMode.FAN, 24,
                    ThermostatFanLevel.MEDIUM, ThermostatSwing.OFF
                )
                return "AC set to FAN mode"
        except Exception as e:
            return f"Error setting fan mode: {str(e)}"

# Initialize AC controller
ac = ACController()

# Security check
def check_authorization(update: Update) -> bool:
    """Check if user is authorized"""
    return update.effective_chat.id in AUTHORIZED_CHAT_IDS

# Bot command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    welcome_text = """
AC Controller Bot

Available commands:
• 'on' or /cool - Turn on cooling (24C)
• 'off' or /off - Turn off AC  
• /heat - Turn on heating (22C)
• /fan - Fan only mode
• /status - Check AC status
• /cool 26 - Cool to specific temperature
• /heat 20 - Heat to specific temperature

Just type "on" or "off" for quick control! 
    """
    await update.message.reply_text(welcome_text)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get AC status"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    await update.message.reply_text("Checking AC status...")
    result = await ac.get_status()
    await update.message.reply_text(result)

async def cool_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cool command with optional temperature"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    # Get temperature from command args
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
    
    await update.message.reply_text(f"Turning on cooling to {temp}C...")
    result = await ac.turn_on_cooling(temp)
    await update.message.reply_text(result)

async def heat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Heat command with optional temperature"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    # Get temperature from command args
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
    
    await update.message.reply_text(f"Turning on heating to {temp}C...")
    result = await ac.turn_on_heating(temp)
    await update.message.reply_text(result)

async def off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Turn off AC"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    await update.message.reply_text("Turning off AC...")
    result = await ac.turn_off()
    await update.message.reply_text(result)

async def fan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fan only mode"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    await update.message.reply_text("Setting fan only mode...")
    result = await ac.fan_only()
    await update.message.reply_text(result)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle simple text messages like 'on' and 'off'"""
    if not check_authorization(update):
        await update.message.reply_text("Unauthorized access")
        return
    
    text = update.message.text.lower().strip()
    
    if text in ['on', 'turn on', 'start', 'cool']:
        await update.message.reply_text("Turning on cooling to 24C...")
        result = await ac.turn_on_cooling(24)
        await update.message.reply_text(result)
    
    elif text in ['off', 'turn off', 'stop']:
        await update.message.reply_text("Turning off AC...")
        result = await ac.turn_off()
        await update.message.reply_text(result)
    
    elif text in ['status', 'check']:
        await update.message.reply_text("Checking AC status...")
        result = await ac.get_status()
        await update.message.reply_text(result)
    
    elif text in ['fan', 'fan only']:
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
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("Please set your BOT_TOKEN first!")
        return
    
    if not AUTHORIZED_CHAT_IDS:
        print("Please set your AUTHORIZED_CHAT_IDS first!")
        return
    
    print("Starting AC Controller Bot...")
    print(f"Authorized users: {AUTHORIZED_CHAT_IDS}")
    
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
    print("Bot is running! Send 'on' or 'off' to control your AC")
    print("Authorized users can control the AC")
    application.run_polling()

if __name__ == "__main__":
    main()
    