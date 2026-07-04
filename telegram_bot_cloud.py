"""Telegram AC bot — remote ON / OFF / Flip.

The free remote control for when you're away from home. Shares the app/ logic
and the SQLite DB with the web dashboard (which owns the auto-cycle and
analytics). Every ON/OFF is logged to the DB with source='telegram'; Flip is a
shared DB setting so the bot and dashboard agree.
"""
import logging
import os
import socket
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)

from app import config, db
from app.ac import ACController
from app.commands import set_ac, toggle_flip


def setup_logging():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
    )
    for noisy in ("httpx", "telegram", "urllib3", "aioswitcher"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger(__name__)


logger = setup_logging()

ac = ACController()


def get_system_info():
    """System info for the startup / status messages."""
    try:
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
            "host_ip": host_ip,
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        return {"deployment": "Unknown", "error": str(e)}


def check_authorization(update: Update) -> bool:
    user_id = update.effective_chat.id
    authorized = user_id in config.AUTHORIZED_CHAT_IDS
    if not authorized:
        logger.warning(f"Unauthorized access attempt from user ID: {user_id}")
    return authorized


def get_control_menu():
    """AC control menu: ON, OFF, Flip (auto-cycle lives in the web dashboard)."""
    keyboard = [
        [
            InlineKeyboardButton("🟢 Turn ON", callback_data="turn_on"),
            InlineKeyboardButton("🔴 Turn OFF", callback_data="turn_off"),
        ],
        [InlineKeyboardButton("🔄 Flip AC State", callback_data="flip_state")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_authorization(update):
        await update.message.reply_text("❌ Unauthorized access")
        return
    logger.info(f"Start command from authorized user: {update.effective_chat.id}")
    await update.message.reply_text(
        "🤖 **AC Controller Bot**\n\nUse the buttons below to control your AC:",
        reply_markup=get_control_menu(),
        parse_mode="Markdown",
    )


async def where_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_authorization(update):
        await update.message.reply_text("❌ Unauthorized access")
        return
    info = get_system_info()
    message = f"""🖥️ **System Information**

**Deployment:** {info['deployment']}
**Started:** {info.get('start_time', 'Unknown')}
**Bot IP:** {info.get('host_ip', 'Unknown')}
**Device IP:** {config.DEVICE_IP}
**Device ID:** {config.DEVICE_ID}
"""
    await update.message.reply_text(message, parse_mode="Markdown")


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_authorization(update):
        await update.callback_query.answer("❌ Unauthorized access")
        return

    query = update.callback_query
    await query.answer()
    data = query.data

    if data in ("turn_on", "turn_off"):
        intent_on = data == "turn_on"
        label = "ON" if intent_on else "OFF"
        await query.edit_message_text(f"{'🟢' if intent_on else '🔴'} Sending command...")
        ok, err = await set_ac(ac, intent_on, source="telegram")
        message = f"✅ {label} command sent!" if ok else f"❌ Failed to send {label} command\n({err})"
        await query.edit_message_text(message, reply_markup=get_control_menu())

    elif data == "flip_state":
        flipped = toggle_flip(source="telegram")
        on_sends = "OFF" if flipped else "ON"
        off_sends = "ON" if flipped else "OFF"
        message = (
            f"✅ Button logic flipped!\n\n"
            f"🟢 ON button now sends: {on_sends}\n"
            f"🔴 OFF button now sends: {off_sends}"
        )
        await query.edit_message_text(message, reply_markup=get_control_menu())


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_authorization(update):
        await update.message.reply_text("❌ Unauthorized access")
        return
    await update.message.reply_text(
        "🤖 Use the buttons below to control your AC:", reply_markup=get_control_menu()
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")


async def send_startup_notification(application):
    info = get_system_info()
    startup_message = f"""🚀 **AC Bot Started!**

**Time:** {info['start_time']}
**Running on:** {info['deployment']}
**Bot IP:** {info['host_ip']}

Bot is ready to control your AC! 🌡️"""
    for chat_id in config.AUTHORIZED_CHAT_IDS:
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=startup_message,
                parse_mode="Markdown",
                reply_markup=get_control_menu(),
            )
            logger.info(f"Startup notification sent to {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send startup notification to {chat_id}: {e}")


async def post_init(application):
    await send_startup_notification(application)


def main():
    logger.info("=== STARTING TELEGRAM AC BOT (remote ON/OFF/Flip) ===")
    config.validate_device()
    config.validate_telegram()
    db.init_db()

    application = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("where", where_command))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_error_handler(error_handler)

    logger.info("Bot is running with remote ON / OFF / Flip interface!")

    port = int(os.environ.get("PORT", 0))
    if port:
        render_url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("RENDER_SERVICE_URL")
        if not render_url:
            logger.error("ERROR: RENDER_EXTERNAL_URL environment variable not set!")
            return
        webhook_url = (
            f"https://{render_url}/webhook"
            if not render_url.startswith("https://")
            else f"{render_url}/webhook"
        )
        logger.info(f"Starting webhook mode: {webhook_url}")
        application.run_webhook(listen="0.0.0.0", port=port, url_path="webhook", webhook_url=webhook_url)
    else:
        logger.info("Starting polling mode for local testing")
        application.run_polling()


if __name__ == "__main__":
    main()
