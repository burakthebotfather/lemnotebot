import os
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Filter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db import Database
from parser_utils import parse_trigger_and_amount, CHAT_MAP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise RuntimeError('TELEGRAM_TOKEN env var required')
ADMIN_ID = int(os.getenv('ADMIN_ID', '542345855'))
TIMEZONE = os.getenv('TZ', 'Europe/Vienna')

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
db = Database(os.path.join(os.path.dirname(__file__), '..', 'notepad_bot.sqlite'))

class AllowedThreadFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        chat_id = message.chat.id
        thread_id = getattr(message, 'message_thread_id', None)
        if chat_id in CHAT_MAP:
            _, expected_thread = CHAT_MAP[chat_id]
            return expected_thread == thread_id
        return False

@dp.message()
async def handle_message(message: Message):
    # only process messages from allowed chats/threads
    chat_id = message.chat.id
    thread_id = getattr(message, 'message_thread_id', None)
    if chat_id not in CHAT_MAP:
        return
    expected_title, expected_thread = CHAT_MAP[chat_id]
    if expected_thread != thread_id:
        return
    text = (message.text or "").strip()
    if "+" not in text:
        return  # ignore messages without '+'
    # Save for delayed processing (5 minutes)
    now = datetime.utcnow()
    process_after = now + timedelta(minutes=5)
    await db.save_pending_message(
        message_id=message.message_id,
        chat_id=chat_id,
        thread_id=thread_id,
        user_id=message.from_user.id if message.from_user else None,
        text=text,
        timestamp_original=now,
        process_after=process_after
    )
    logger.info("Saved pending message %s from chat %s", message.message_id, chat_id)

async def process_due_messages():
    due = await db.get_due_messages()
    if not due:
        return
    for row in due:
        try:
            text = row['text']
            chat_id = row['chat_id']
            timestamp_original = row['timestamp_original']
            chat_title = CHAT_MAP.get(chat_id, ('Unknown', None))[0]
            amount, trigger_text = parse_trigger_and_amount(text)
            if amount is None:
                # mark processed and continue
                await db.mark_processed(row['id'])
                logger.info('No valid trigger found in message id %s', row['id'])
                continue
            # Update counter and log
            await db.add_to_counter(amount)
            await db.insert_log(amount, trigger_text, chat_title, chat_id, datetime.utcnow())
            S = await db.get_counter()
            # format times to timezone
            try:
                tz = ZoneInfo(TIMEZONE)
                local_dt = timestamp_original.replace(tzinfo=ZoneInfo('UTC')).astimezone(tz)
                time_str = local_dt.strftime('%H:%M, %d.%m.%Y')
            except Exception:
                time_str = timestamp_original.strftime('%H:%M, %d.%m.%Y')
            msg_text = f"{format_money(amount)} BYN\nS = {format_money(S)} BYN\n\n{chat_title}\n{time_str}"
            # send to admin
            await bot.send_message(ADMIN_ID, msg_text)
            logger.info('Sent admin message for pending id %s: %s', row['id'], msg_text.replace('\n',' | '))
        except Exception as e:
            logger.exception('Error processing pending message id %s: %s', row.get('id'), e)
        finally:
            await db.mark_processed(row['id'])

def format_money(x: float) -> str:
    # format with comma decimal separator
    return f"{x:0.2f}".replace('.', ',')

async def daily_report():
    try:
        S = await db.get_counter()
        tz = ZoneInfo(TIMEZONE)
        today = datetime.now(tz).strftime('%d.%m.%Y')
        text = f"{format_money(S)} BYN • {today}"
        await bot.send_message(ADMIN_ID, text)
        logger.info('Sent daily report: %s', text)
        await db.reset_counter()
    except Exception as e:
        logger.exception('Failed to send daily report: %s', e)

async def scheduler_startup():
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(lambda: asyncio.create_task(process_due_messages()), 'interval', seconds=30)
    scheduler.add_job(lambda: asyncio.create_task(daily_report()), CronTrigger(hour=22, minute=5, timezone=TIMEZONE))
    scheduler.start()
    logger.info('Scheduler started')

async def main():
    await db.init_db()
    await scheduler_startup()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == '__main__':
    import uvloop
    uvloop.install()
    asyncio.run(main())
