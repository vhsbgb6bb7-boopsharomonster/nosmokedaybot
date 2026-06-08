import os
import asyncio
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application


TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_URL = "https://nosmokedaybot.onrender.com/webhook"

DB_NAME = "smoke_tracker.db"
DEFAULT_TIME = "14:00"
DEFAULT_TIMEZONE = "Asia/Vladivostok"

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


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
            food INTEGER,
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

        try:
            conn.execute("ALTER TABLE daily_logs ADD COLUMN food INTEGER")
        except sqlite3.OperationalError:
            pass


def ensure_user(user_id: int):
    with get_db() as conn:
        conn.execute("""
        INSERT OR IGNORE INTO users(user_id, reminder_time, timezone)
        VALUES (?, ?, ?)
        """, (user_id, DEFAULT_TIME, DEFAULT_TIMEZONE))


def get_today(user_id: int):
    with get_db() as conn:
        row = conn.execute("""
        SELECT timezone
        FROM users
        WHERE user_id = ?
        """, (user_id,)).fetchone()

    timezone = row[0] if row else DEFAULT_TIMEZONE
    return datetime.now(ZoneInfo(timezone)).date().isoformat()


def update_log(user_id: int, field: str, value: int):
    allowed_fields = {
        "smoked",
        "sleep",
        "water",
        "food",
        "rest",
        "craving",
        "completed"
    }

    if field not in allowed_fields:
        return

    today = get_today(user_id)

    with get_db() as conn:
        conn.execute("""
        INSERT OR IGNORE INTO daily_logs(user_id, date)
        VALUES (?, ?)
        """, (user_id, today))

        conn.execute(
            f"""
            UPDATE daily_logs
            SET {field} = ?
            WHERE user_id = ?
            AND date = ?
            """,
            (value, user_id, today)
        )


def calculate_streak(user_id: int):
    with get_db() as conn:
        rows = conn.execute("""
        SELECT date, smoked
        FROM daily_logs
        WHERE user_id = ?
        ORDER BY date DESC
        """, (user_id,)).fetchall()

    logs = {row[0]: row for row in rows}
    streak = 0
    current_date = datetime.fromisoformat(get_today(user_id)).date()

    while True:
        key = current_date.isoformat()
        row = logs.get(key)

        if not row:
            break

        _, smoked = row

        if smoked == 0:
            streak += 1
            current_date -= timedelta(days=1)
        else:
            break

    with get_db() as conn:
        row = conn.execute("""
        SELECT best_streak
        FROM users
        WHERE user_id = ?
        """, (user_id,)).fetchone()

        old_best = row[0] if row else 0
        new_best = max(old_best, streak)

        conn.execute("""
        UPDATE users
        SET current_streak = ?,
            best_streak = ?
        WHERE user_id = ?
        """, (streak, new_best, user_id))

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
        "🌬 Люба, был сегодня кальян?",
        reply_markup=yes_no_keyboard("smoked")
    )


@router.message(Command("start"))
async def start(message: Message):
    ensure_user(message.from_user.id)

    await message.answer(
        "👋 Люба, привет.\n\n"
        "Я буду помогать тебе отслеживать дни без кальяна.\n\n"
        "Команды:\n"
        "/today — отметить день без кальяна\n"
        "/stats — статистика"
    )


@router.message(Command("today"))
async def today(message: Message):
    ensure_user(message.from_user.id)
    await ask_smoked(message.from_user.id)


@router.message(Command("stats"))
async def stats(message: Message):
    ensure_user(message.from_user.id)

    streak, best = calculate_streak(message.from_user.id)

    await message.answer(
        f"📊 Статистика Любы\n\n"
        f"🌬 Сейчас без кальяна: {streak} дн.\n"
        f"🏆 Лучший результат: {best} дн."
    )


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
        "Сегодня отмечен день с кальяном.\n\n"
        "Люба, ничего страшного.\n"
        "Завтра продолжаем 💪"
    )

    await callback.answer()


@router.callback_query(F.data == "smoked:no")
async def smoked_no(callback: CallbackQuery):
    user_id = callback.from_user.id

    update_log(user_id, "smoked", 0)

    await callback.message.edit_text(
        "✨ Отлично.\n\n"
        "Люба, ты выспалась?",
        reply_markup=yes_no_keyboard("sleep")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("sleep:"))
async def sleep_answer(callback: CallbackQuery):
    value = 1 if callback.data.endswith("yes") else 0
    update_log(callback.from_user.id, "sleep", value)

    await callback.message.edit_text(
        "💧 Ты выпила достаточно воды?",
        reply_markup=yes_no_keyboard("water")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("water:"))
async def water_answer(callback: CallbackQuery):
    value = 1 if callback.data.endswith("yes") else 0
    update_log(callback.from_user.id, "water", value)

    await callback.message.edit_text(
        "🍽 Ты нормально поела?",
        reply_markup=yes_no_keyboard("food")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("food:"))
async def food_answer(callback: CallbackQuery):
    value = 1 if callback.data.endswith("yes") else 0
    update_log(callback.from_user.id, "food", value)

    await callback.message.edit_text(
        "🛌 У тебя был нормальный отдых?",
        reply_markup=yes_no_keyboard("rest")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("rest:"))
async def rest_answer(callback: CallbackQuery):
    value = 1 if callback.data.endswith("yes") else 0
    update_log(callback.from_user.id, "rest", value)

    await callback.message.edit_text(
        "🔥 Было сильное желание кальяна?",
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
        f"Люба, сегодня ты справилась 🌬\n\n"
        f"🌬 Текущая серия: {streak} дн.\n"
        f"🏆 Лучший результат: {best} дн."
    )

    await callback.answer()


async def check_reminders():
    with get_db() as conn:
        users = conn.execute("""
        SELECT user_id, reminder_time, timezone
        FROM users
        """).fetchall()

    for user_id, reminder_time, timezone in users:
        now = datetime.now(ZoneInfo(timezone))
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
            """, (user_id, today)).fetchone()

            if already_sent:
                continue

            conn.execute("""
            INSERT INTO reminders_sent(user_id, date)
            VALUES (?, ?)
            """, (user_id, today))

        try:
            await ask_smoked(user_id)
            print(f"Reminder sent to {user_id} at {current_time}")
        except Exception as e:
            print(f"Reminder send error for {user_id}: {e}")


async def reminder_loop():
    while True:
        try:
            await check_reminders()
        except Exception as e:
            print("Reminder loop error:", e)

        await asyncio.sleep(30)


async def on_startup(bot: Bot):
    init_db()
    await bot.set_webhook(WEBHOOK_URL)

    asyncio.create_task(reminder_loop())

    print("BOT STARTED")


async def health(request):
    try:
        await check_reminders()
    except Exception as e:
        print("Health reminder error:", e)

    return web.Response(text="Bot is running")


def main():
    dp.startup.register(on_startup)

    app = web.Application()
    app.router.add_get("/", health)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    ).register(app, path="/webhook")

    setup_application(app, dp, bot=bot)

    web.run_app(
        app,
        host="0.0.0.0",
        port=PORT
    )


if __name__ == "__main__":
    main()
