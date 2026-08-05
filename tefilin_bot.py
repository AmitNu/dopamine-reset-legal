import asyncio
import logging
import os
from datetime import datetime, time

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")

# In-memory state: chat_id -> {confirmed: bool, reminder_job: job}
user_state: dict[int, dict] = {}


def done_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ הנחתי תפילין!", callback_data="done")]]
    )


async def send_reminder(app: Application, chat_id: int):
    state = user_state.setdefault(chat_id, {"confirmed": False})
    if state.get("confirmed"):
        return

    await app.bot.send_message(
        chat_id=chat_id,
        text=(
            "🔔 *תזכורת יומית – תפילין!*\n\n"
            "הגיע הזמן להניח תפילין ✡️\n"
            "לחץ על הכפתור כשתסיים."
        ),
        parse_mode="Markdown",
        reply_markup=done_keyboard(),
    )


async def schedule_daily_reminder(app: Application, chat_id: int, scheduler: AsyncIOScheduler):
    job_id = f"reminder_{chat_id}"
    if scheduler.get_job(job_id):
        return  # already scheduled

    # Reset confirmation each day at midnight Israel time
    async def reset_and_remind():
        user_state[chat_id] = {"confirmed": False}
        await send_reminder(app, chat_id)

    # Daily at 09:00 Israel time
    scheduler.add_job(
        reset_and_remind,
        trigger="cron",
        hour=9,
        minute=0,
        timezone=ISRAEL_TZ,
        id=job_id,
        replace_existing=True,
    )

    # Follow-up reminders every 30 minutes if not yet confirmed
    followup_id = f"followup_{chat_id}"

    async def followup():
        state = user_state.get(chat_id, {})
        if not state.get("confirmed"):
            await send_reminder(app, chat_id)

    scheduler.add_job(
        followup,
        trigger="cron",
        minute="*/30",
        timezone=ISRAEL_TZ,
        id=followup_id,
        replace_existing=True,
    )

    logger.info("Scheduled reminders for chat_id=%s", chat_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    scheduler: AsyncIOScheduler = context.bot_data["scheduler"]
    app: Application = context.application

    user_state[chat_id] = {"confirmed": False}
    await schedule_daily_reminder(app, chat_id, scheduler)

    await update.message.reply_text(
        "✡️ *בוט תפילין הופעל!*\n\n"
        "אני אשלח לך תזכורת כל יום ב-09:00 להניח תפילין.\n"
        "אם לא תלחץ ✅, אחזור ואתזכיר כל 30 דקות.\n\n"
        "ב״ה תצליח בכל יום! 🙏",
        parse_mode="Markdown",
    )


async def done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("כל הכבוד! 🎉")
    chat_id = query.message.chat_id

    user_state[chat_id] = {"confirmed": True}

    await query.edit_message_text(
        "✅ *מצוין! הנחת תפילין היום!*\n\nיישר כח! לא אטריד אותך יותר להיום. 🙏",
        parse_mode="Markdown",
    )
    logger.info("chat_id=%s confirmed tefilin for today", chat_id)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = user_state.get(chat_id)
    if not state:
        await update.message.reply_text(
            "לא רשום עדיין. שלח /start להתחיל."
        )
        return
    if state.get("confirmed"):
        await update.message.reply_text("✅ כבר הנחת תפילין היום!")
    else:
        await update.message.reply_text(
            "⏳ עדיין לא הנחת תפילין היום.",
            reply_markup=done_keyboard(),
        )


async def post_init(application: Application):
    scheduler: AsyncIOScheduler = application.bot_data["scheduler"]
    scheduler.start()
    logger.info("Scheduler started")


async def post_shutdown(application: Application):
    scheduler: AsyncIOScheduler = application.bot_data["scheduler"]
    scheduler.shutdown(wait=False)


def main():
    scheduler = AsyncIOScheduler(timezone=ISRAEL_TZ)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["scheduler"] = scheduler

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CallbackQueryHandler(done_callback, pattern="^done$"))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
