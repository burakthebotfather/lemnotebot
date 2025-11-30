import os
import re
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.enums import ParseMode

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


# ------------------------------------------------------
#                      CONFIG
# ------------------------------------------------------

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = 542345855  # ID администратора для отчётов

bot = Bot(TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

DB = "database.sqlite"


# ------------------------------------------------------
#                    TRIGGER VALUES
# ------------------------------------------------------

TRIGGERS = {
    "+": 2.56,
    "+ мк": 2.39,
    "+ мк синяя": 4.05,
    "+ мк красная": 5.71,
    "+ мк оранжевая": 6.37,
    "+ мк салатовая": 8.03,
    "+ мк коричневая": 8.69,
    "+ мк светло-серая": 10.35,
    "+ мк розовая": 11.01,
    "+ мк темно-серая": 12.67,
    "+ мк голубая": 13.33,
}

GAB_VALUE = 2.89


# ------------------------------------------------------
#                     CHAT MAP
# ------------------------------------------------------

CHAT_MAP = {
    -1002079167705: ("A. Mousse Art Bakery - Белинского, 23", 48),
    -1002936236597: ("B. Millionroz.by - Тимирязева, 67", 3),
    -1002423500927: ("E. Flovi.Studio - Тимирязева, 65Б", 2),
    -1003117964688: ("F. Flowers Titan - Мележа, 1", 5),
    -1002864795738: ("G. Цветы Мира - Академическая, 6", 3),
    -1002535060344: ("H. Kudesnica.by - Старовиленский тракт, 10", 5),
    -1002477650634: ("I. Cvetok.by - Восточная, 41", 3),
    -1003204457764: ("J. Jungle.by - Неманская, 2", 4),
    -1002660511483: ("K. Pastel Flowers - Сурганова, 31", 3),
    -1002360529455: ("333. ТЕСТ БОТОВ - 1-й Нагатинский пр-д", 0),
    -1002538985387: ("L. Lamour.by - Кропоткина, 84", 3),
}


# ------------------------------------------------------
#                     DB INIT
# ------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message_id INTEGER,
            thread_id INTEGER,
            text TEXT,
            created_ts INTEGER,
            to_process_ts INTEGER,
            processed INTEGER DEFAULT 0
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS earnings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            total REAL
        )
        """
    )

    # Ensure single counter row
    c.execute("INSERT OR IGNORE INTO earnings (id, total) VALUES (1, 0)")

    conn.commit()
    conn.close()


# ------------------------------------------------------
#               TRIGGER PARSER
# ------------------------------------------------------

def parse_trigger(text: str) -> float | None:
    t = text.lower().strip()

    # GAB
    if "габ" in t:
        match = re.search(r"(\d*)\s*габ", t)
        if match:
            num = match.group(1)
            return int(num) * GAB_VALUE if num.isdigit() else GAB_VALUE

    # "+" triggers
    for trig, val in sorted(TRIGGERS.items(), key=lambda x: -len(x[0])):
        if t.startswith(trig):
            return val

    return None


# ------------------------------------------------------
#                STORE INCOMING MESSAGE
# ------------------------------------------------------

async def store_message(message: Message):
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    # Filter: chat not registered
    if chat_id not in CHAT_MAP:
        return

    # Filter: wrong thread
    if thread_id != CHAT_MAP[chat_id][1]:
        return

    text = message.text or ""
    if "+" not in text:
        return

    now = int(datetime.utcnow().timestamp())
    process_ts = now + 300  # process after 5 minutes

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute(
        """
        INSERT INTO queue (chat_id, message_id, thread_id, text, created_ts, to_process_ts)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (chat_id, message.message_id, thread_id, text, now, process_ts)
    )

    conn.commit()
    conn.close()


# ------------------------------------------------------
#                PROCESS QUEUE
# ------------------------------------------------------

async def process_queue():
    now = int(datetime.utcnow().timestamp())
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute(
        """
        SELECT id, chat_id, message_id, thread_id, text, created_ts
        FROM queue
        WHERE processed = 0 AND to_process_ts <= ?
        """,
        (now,)
    )

    rows = c.fetchall()

    for row in rows:
        q_id, chat_id, msg_id, thread_id, text, ts = row

        # Extract part after "+"
        try:
            part = text[text.index("+"):].strip()
        except ValueError:
            c.execute("UPDATE queue SET processed = 1 WHERE id = ?", (q_id,))
            conn.commit()
            continue

        amount = parse_trigger(part)
        if amount is None:
            c.execute("UPDATE queue SET processed = 1 WHERE id = ?", (q_id,))
            conn.commit()
            continue

        # Load current total
        c.execute("SELECT total FROM earnings WHERE id = 1")
        total = c.fetchone()[0]

        new_total = round(total + amount, 2)

        c.execute("UPDATE earnings SET total = ? WHERE id = 1", (new_total,))

        # Formatting the outgoing message
        org_name = CHAT_MAP[chat_id][0]
        dt = datetime.fromtimestamp(ts)
        date_str = dt.strftime("%H:%M, %d.%m.%Y")

        msg = (
            f"+{amount:.2f} BYN\n"
            f"S = {new_total:.2f} BYN\n\n"
            f"{org_name}\n"
            f"{date_str}"
        )

        # Try sending the result
        try:
            await bot.send_message(ADMIN_ID, msg)
        except Exception as e:
            print("Error sending:", e)

        # Mark row as processed
        c.execute("UPDATE queue SET processed = 1 WHERE id = ?", (q_id,))
        conn.commit()

    conn.close()


# ------------------------------------------------------
#                DAILY REPORT
# ------------------------------------------------------

async def daily_report():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("SELECT total FROM earnings WHERE id = 1")
    total = c.fetchone()[0]

    date_str = datetime.now().strftime("%d.%m.%Y")

    await bot.send_message(ADMIN_ID, f"{total:.2f} BYN • {date_str}")

    # Reset counter
    c.execute("UPDATE earnings SET total = 0 WHERE id = 1")
    conn.commit()
    conn.close()


# ------------------------------------------------------
#                HANDLERS
# ------------------------------------------------------

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Bot is running!")


@dp.message(F.text)
async def on_message(message: Message):
    await store_message(message)


# ------------------------------------------------------
#                MAIN APP
# ------------------------------------------------------

async def main():
    init_db()

    scheduler = AsyncIOScheduler(timezone="Europe/Vienna")

    # Check queue every 20 sec
    scheduler.add_job(process_queue, "interval", seconds=20)

    # Daily report @ 22:05
    scheduler.add_job(daily_report, CronTrigger(hour=22, minute=5))

    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
