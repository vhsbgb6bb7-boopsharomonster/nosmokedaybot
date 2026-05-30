import asyncio
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

TOKEN = "8525547515:AAFyQG25LcqcUYiE45OMZ_8qAKmR6Gpv1nI"

DB_NAME = "smoke_tracker.db"

DEFAULT_TIME = "14:00"
DEFAULT_TIMEZONE = "Asia/Vladivostok"

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

dp.include_router(router)


# =========================
# DATABASE
# =========================

def get_db():
    return sqlite3.connect(DB_NAME)


def init_db():
    with get_db() as conn:

        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            reminder_time TEXT DEFAULT '14:00',
            timezone TEXT DEFAULT 'Asia/Vladivostok',
            current_streak INTEGER DEFAULT 0,
            best_streak INTEGER DEFAULT 0
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_logs (
            user_id INTEGER,
            date TEXT,
            smoked INTEGER,
            sleep INTEGER,
            water INTEGER,
            rest INTEGER,
            craving INTEGER,
            completed INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders_sent (
            user_id INTEGER,
            date TEXT,
            PRIMARY KEY (user_id, date)
        )
        """)


# =========================
# HELPERS
# =========================

def ensure_user(user_id: int):
    with get_db() as conn:
        conn.execute("""
        INSERT OR IGNORE INTO users (
            user_id,
            reminder_time,
            timezone
        )
        VALUES (?, ?, ?)
        """, (
            user_id,
            DEFAULT_TIME,
            DEFAULT_TIMEZONE
        ))


def get_today(user_id: int):
    with get_db() as conn:
        row = conn.execute("""
        SELECT timezone
        FROM users
        WHERE user_id = ?
        """, (user_id,)).fetchone()

    timezone = row[0] if row else DEFAULT_TIMEZONE

    return datetime.now(
        ZoneInfo(timezone)
    ).date().isoformat()


def update_log(user_id: int, field: str, value: int):
    today = get_today(user_id)

    with get_db() as conn:

        conn.execute("""
        INSERT OR IGNORE INTO daily_logs (
            user_id,
            date
        )
        VALUES (?, ?)
        """, (user_id, today))

        conn.execute(
            f"""
            UPDATE daily_logs
            SET {field} = ?
            WHERE user_id = ? AND date = ?
            """,
            (value, user_id, today)
        )


def calculate_streak(user_id: int):

    with get_db() as conn:
        rows = conn.execute("""
        SELECT date, smoked, completed
        FROM daily_logs
        WHERE user_id = ?
        ORDER BY date DESC
        """, (user_id,)).fetchall()

    logs = {row[0]: row for row in rows}

    streak = 0

    current_date = datetime.fromisoformat(
        get_today(user_id)
    ).date()

    while True:

        key = current_date.isoformat()

        row = logs.get(key)

        if not row:
            break

        _, smoked, completed = row

        if smoked == 0 and completed == 1:
            streak += 1
            current_date -= timedelta(days=1)
        else:
            break

    with get_db() as conn:

        best_streak = conn.execute("""
        SELECT best_streak
        FROM users
        WHERE user_id = ?
        """, (user_id,)).fetchone()[0]

        new_best = max(best_streak, streak)

        conn.execute("""
        UPDATE users
        SET current_streak = ?,
            best_streak = ?
        WHERE user_id = ?
        """, (
            streak,
            new_best,
            user_id
        ))

    return streak, new_best


def yes_no_keyboard(prefix: str):

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да",
                    callback_data=f"{prefix}:yes"
                ),
                InlineKeyboardButton(
                    text="Нет",
                    callback_data=f"{prefix}:no"
                )
            ]
        ]
    )


async def ask_smoked(user_id: int):

    await bot.send_message(
        user_id,
        "🚬 Курил сегодня?",
        reply_markup=yes_no_keyboard("smoked")
    )


# =========================
# COMMANDS
# =========================

@router.message(Command("start"))
async def start(message: Message):

    ensure_user(message.from_user.id)

    await message.answer(
        "👋 Добро пожаловать.\n\n"
        "Я буду помогать тебе отслеживать "
        "дни без курения.\n\n"
        "Команды:\n"
        "/today — отметить день\n"
        "/stats — статистика\n"
        "/time 14:00 — изменить время"
    )


@router.message(Command("today"))
async def today(message: Message):

    ensure_user(message.from_user.id)

    await ask_smoked(message.from_user.id)


@router.message(Command("stats"))
async def stats(message: Message):

    ensure_user(message.from_user.id)

    with get_db() as conn:

        row = conn.execute("""
        SELECT current_streak,
               best_streak,
               reminder_time,
               timezone
        FROM users
        WHERE user_id = ?
        """, (message.from_user.id,)).fetchone()

    current_streak, best_streak, reminder_time, timezone = row

    await message.answer(
        f"📊 Статистика\n\n"
        f"🚭 Сейчас без курения: {current_streak} дн.\n"
        f"🏆 Лучший результат: {best_streak} дн.\n"
        f"⏰ Напоминание: {reminder_time}\n"
        f"🌍 Часовой пояс: {timezone}"
    )


@router.message(Command("time"))
async def set_time(message: Message):

    ensure_user(message.from_user.id)

    parts = message.text.split()

    if len(parts) != 2:
        await message.answer(
            "Используй так:\n"
            "/time 14:00"
        )
        return

    new_time = parts[1]

    try:
        datetime.strptime(new_time, "%H:%M")
    except:
        await message.answer(
            "Неверный формат времени.\n"
            "Пример:\n"
            "/time 14:00"
        )
        return

    with get_db() as conn:

        conn.execute("""
        UPDATE users
        SET reminder_time = ?
        WHERE user_id = ?
        """, (
            new_time,
            message.from_user.id
        ))

    await message.answer(
        f"✅ Время обновлено: {new_time}"
    )


# =========================
# CALLBACKS
# =========================

@router.callback_query(F.data == "smoked:yes")
async def smoked_yes(callback: CallbackQuery):

    user_id = callback.from_user.id

    update_log(user_id, "smoked", 1)
    update_log(user_id, "completed", 1)

    with get_db() as conn:

        conn.execute("""
        UPDATE users
        SET current_streak = 0
        WHERE user_id = ?
        """, (user_id,))

    await callback.message.edit_text(
        "😔 День отмечен как день с курением.\n\n"
        "Не страшно. Продолжаем дальше."
    )

    await callback.answer()


@router.callback_query(F.data == "smoked:no")
async def smoked_no(callback: CallbackQuery):

    user_id = callback.from_user.id

    update_log(user_id, "smoked", 0)

    await callback.message.edit_text(
        "😴 Выспался сегодня?",
        reply_markup=yes_no_keyboard("sleep")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("sleep:"))
async def sleep_answer(callback: CallbackQuery):

    value = 1 if callback.data.endswith("yes") else 0

    update_log(callback.from_user.id, "sleep", value)

    await callback.message.edit_text(
        "💧 Выпил достаточно воды?",
        reply_markup=yes_no_keyboard("water")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("water:"))
async def water_answer(callback: CallbackQuery):

    value = 1 if callback.data.endswith("yes") else 0

    update_log(callback.from_user.id, "water", value)

    await callback.message.edit_text(
        "🛌 Был отдых сегодня?",
        reply_markup=yes_no_keyboard("rest")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("rest:"))
async def rest_answer(callback: CallbackQuery):

    value = 1 if callback.data.endswith("yes") else 0

    update_log(callback.from_user.id, "rest", value)

    await callback.message.edit_text(
        "🔥 Было сильное желание закурить?",
        reply_markup=yes_no_keyboard("craving")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("craving:"))
async def craving_answer(callback: CallbackQuery):

    value = 1 if callback.data.endswith("yes") else 0

    user_id = callback.from_user.id

    update_log(user_id, "craving", value)
    update_log(user_id, "completed", 1)

    streak, best = calculate_streak(user_id)

    await callback.message.edit_text(
        f"✅ День сохранён.\n\n"
        f"🚭 Текущая серия: {streak} дн.\n"
        f"🏆 Лучший результат: {best} дн."
    )

    await callback.answer()


# =========================
# REMINDER LOOP
# =========================

async def reminder_loop():

    while True:

        with get_db() as conn:

            users = conn.execute("""
            SELECT user_id,
                   reminder_time,
                   timezone
            FROM users
            """).fetchall()

        for user_id, reminder_time, timezone in users:

            now = datetime.now(
                ZoneInfo(timezone)
            )

            current_time = now.strftime("%H:%M")

            today = now.date().isoformat()

            if current_time != reminder_time:
                continue

            with get_db() as conn:

                already_sent = conn.execute("""
                SELECT 1
                FROM reminders_sent
                WHERE user_id = ?
                AND date = ?
                """, (
                    user_id,
                    today
                )).fetchone()

                if already_sent:
                    continue

                conn.execute("""
                INSERT INTO reminders_sent (
                    user_id,
                    date
                )
                VALUES (?, ?)
                """, (
                    user_id,
                    today
                ))

            try:
                await ask_smoked(user_id)
            except:
                pass

        await asyncio.sleep(30)


# =========================
# MAIN
# =========================

async def main():

    init_db()

    asyncio.create_task(
        reminder_loop()
    )

    print("BOT STARTED")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
