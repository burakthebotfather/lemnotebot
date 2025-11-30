import aiosqlite
from datetime import datetime

CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS pending_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    chat_id INTEGER,
    thread_id INTEGER,
    user_id INTEGER,
    text TEXT,
    timestamp_original TEXT,
    process_after TEXT,
    processed INTEGER DEFAULT 0
);
"""

CREATE_LOG = """
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL,
    trigger_text TEXT,
    chat_title TEXT,
    chat_id INTEGER,
    time TEXT
);
"""

CREATE_COUNTER = """
CREATE TABLE IF NOT EXISTS counter (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    amount REAL DEFAULT 0,
    updated_at TEXT
);
"""

class Database:
    def __init__(self, path='notepad_bot.sqlite'):
        self.path = path
        self.conn = None

    async def init_db(self):
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.execute(CREATE_MESSAGES)
        await self.conn.execute(CREATE_LOG)
        await self.conn.execute(CREATE_COUNTER)
        await self.conn.commit()
        cur = await self.conn.execute('SELECT COUNT(*) FROM counter')
        cnt = (await cur.fetchone())[0]
        if cnt == 0:
            await self.conn.execute('INSERT INTO counter (id, amount, updated_at) VALUES (1, 0, ?)', (datetime.utcnow().isoformat(),))
            await self.conn.commit()

    async def save_pending_message(self, message_id, chat_id, thread_id, user_id, text, timestamp_original, process_after):
        await self.conn.execute('INSERT INTO pending_messages (message_id, chat_id, thread_id, user_id, text, timestamp_original, process_after) VALUES (?, ?, ?, ?, ?, ?, ?)', (message_id, chat_id, thread_id, user_id, text, timestamp_original.isoformat(), process_after.isoformat()))
        await self.conn.commit()

    async def get_due_messages(self):
        cur = await self.conn.execute('SELECT id, message_id, chat_id, thread_id, user_id, text, timestamp_original FROM pending_messages WHERE processed = 0 AND process_after <= ?', (datetime.utcnow().isoformat(),))
        rows = await cur.fetchall()
        res = []
        for r in rows:
            res.append({
                'id': r[0],
                'message_id': r[1],
                'chat_id': r[2],
                'thread_id': r[3],
                'user_id': r[4],
                'text': r[5],
                'timestamp_original': datetime.fromisoformat(r[6])
            })
        return res

    async def mark_processed(self, id_):
        await self.conn.execute('UPDATE pending_messages SET processed = 1 WHERE id = ?', (id_,))
        await self.conn.commit()

    async def add_to_counter(self, amount: float):
        cur = await self.conn.execute('SELECT amount FROM counter WHERE id = 1')
        row = await cur.fetchone()
        current = row[0] if row else 0.0
        new = current + amount
        await self.conn.execute('UPDATE counter SET amount = ?, updated_at = ? WHERE id = 1', (new, datetime.utcnow().isoformat()))
        await self.conn.commit()

    async def get_counter(self) -> float:
        cur = await self.conn.execute('SELECT amount FROM counter WHERE id = 1')
        row = await cur.fetchone()
        return float(row[0]) if row else 0.0

    async def reset_counter(self):
        await self.conn.execute('UPDATE counter SET amount = 0, updated_at = ? WHERE id = 1', (datetime.utcnow().isoformat(),))
        await self.conn.commit()

    async def insert_log(self, amount, trigger_text, chat_title, chat_id, time: datetime):
        await self.conn.execute('INSERT INTO logs (amount, trigger_text, chat_title, chat_id, time) VALUES (?, ?, ?, ?, ?)', (amount, trigger_text, chat_title, chat_id, time.isoformat()))
        await self.conn.commit()
