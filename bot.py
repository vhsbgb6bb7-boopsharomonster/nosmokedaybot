import os
import asyncio
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import web

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application


TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_URL = "https://nosmokedaybot.onrender.com/webhook"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

DEFAULT_TIME = "23:00"
DEFAULT_TIMEZONE = "Europe/Moscow"

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


SUCCESS_PHRASES = [
    "🌱 Ещё один шаг в правильную сторону.",
    "🔥 Серия продолжается.",
    "💪 Хорошая работа. Регулярность решает.",
    "🚀 Сегодня ты снова выбрал себя.",
    "🌿 Маленькие действия складываются в большие изменения.",
    "⭐ Такой день точно идёт в плюс.",
    "🧱 Ещё один кирпичик в новую привычку.",
    "👏 Отличный темп. Продолжаем.",
    "🌤 Сегодня хороший вклад в будущего себя.",
    "🎯 День отмечен не зря.",
]

SMOKED_SUPPORT_PHRASES = [
    "Сегодня получилось не так, как хотелось. Это не отменяет весь путь.",
    "Один день не определяет результат. Завтра можно начать новую серию.",
    "Такое бывает. Важно не застрять в этом дне и продолжить завтра.",
    "Срыв — это не конец. Это просто точка, от которой можно оттолкнуться.",
    "Ничего страшного. Завтра будет новый шанс.",
]

SLEEP_YES_PHRASES = [
    "😴 Отлично. Хороший сон помогает держать курс.",
    "🌙 Сон — мощная поддержка для силы воли.",
    "💤 Хорошее восстановление сегодня в плюс.",
]

SLEEP_NO_PHRASES = [
    "😴 Сегодня сна было маловато. Завтра попробуй дать себе больше восстановления.",
    "🌙 Недосып может усиливать тягу. Завтра стоит чуть больше внимания уделить сну.",
    "💤 Не лучший день по сну. Ничего страшного, завтра можно исправить.",
]

WATER_YES_PHRASES = [
    "💧 Отлично. Организм скажет спасибо.",
    "🚰 Хорошо. Вода — простая привычка, которая реально помогает.",
    "💦 Нормальный водный баланс — уже плюс к дню.",
]

WATER_NO_PHRASES = [
    "💧 Завтра попробуй начать хотя бы с одного дополнительного стакана воды.",
    "🚰 Воду легко забыть, но она сильно влияет на самочувствие.",
    "💦 Сегодня воды было мало. Завтра можно сделать лучше.",
]

FOOD_YES_PHRASES = [
    "🍽 Отлично. Нормальное питание помогает держать энергию.",
    "🥗 Хорошо. Стабильная еда — меньше лишнего стресса для организма.",
    "🍲 Это важная база для хорошего самочувствия.",
]

FOOD_NO_PHRASES = [
    "🍽 Завтра постарайся найти время хотя бы на один нормальный приём пищи.",
    "🥗 Питание сегодня просело. Это не критично, но лучше не запускать.",
    "🍲 Завтра можно сделать день ровнее по еде.",
]

REST_YES_PHRASES = [
    "🛌 Отлично. Отдых — это восстановление, а не слабость.",
    "🌿 Хорошо. Без отдыха сложно держать длинную серию.",
    "🔋 Нормальный отдых помогает не перегореть.",
]

REST_NO_PHRASES = [
    "🛌 Завтра попробуй выделить хотя бы немного времени для себя.",
    "🔋 Похоже, сегодня было мало восстановления. Это стоит поправить.",
    "🌿 Отдых тоже часть прогресса. Не забывай про него.",
]

CRAVING_YES_PHRASES = [
    "🔥 Сегодня было непросто, но ты всё равно дошёл до конца опроса.",
    "🔥 Тяга была — значит день был сложнее. Тем ценнее результат.",
    "🔥 Хорошо, что ты это отметил. Такие данные потом помогут лучше понять себя.",
]

CRAVING_NO_PHRASES = [
    "🔥 Отлично. Сегодня тяга почти не мешала.",
    "😌 Хороший знак. День прошёл спокойнее.",
    "🌿 Отлично. Чем меньше тяги, тем легче закрепляется привычка.",
]


def headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="✅ Отметить день"),
                KeyboardButton(text="📊 Статистика"),
            ]
        ],
        resize_keyboard=True
    )


def pick(items):
    return random.choice(items)


def yes_no_keyboard(prefix: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да", callback_data=f"{prefix}:yes"),
                InlineKeyboardButton(text="Нет", callback_data=f"{prefix}:no"),
            ]
        ]
    )


async def supabase_get(table, params=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}{params}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers()) as resp:
            if resp.status >= 400:
                text = await resp.text()
                print("SUPABASE GET ERROR:", resp.status, text, flush=True)
                return []

            return await resp.json()


async def supabase_post(table, data, upsert=False, conflict=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    custom_headers = headers()

    if upsert:
        custom_headers["Prefer"] = "resolution=merge-duplicates,return=representation"

        if conflict:
            url += f"?on_conflict={conflict}"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=custom_headers, json=data) as resp:
            if resp.status >= 400:
                text = await resp.text()
                print("SUPABASE POST ERROR:", resp.status, text, flush=True)
                return None

            return await resp.json()


async def ensure_user(user_id: int):
    await supabase_post(
        "users",
        {
            "user_id": user_id,
            "reminder_time": DEFAULT_TIME,
            "timezone": DEFAULT_TIMEZONE,
        },
        upsert=True,
        conflict="user_id",
    )


async def get_user(user_id: int):
    rows = await supabase_get(
        "users",
        f"?user_id=eq.{user_id}&select=*"
    )

    if rows:
        return rows[0]

    await ensure_user(user_id)

    rows = await supabase_get(
        "users",
        f"?user_id=eq.{user_id}&select=*"
    )

    return rows[0]


async def get_today(user_id: int):
    user = await get_user(user_id)
    timezone = user.get("timezone") or DEFAULT_TIMEZONE

    return datetime.now(
        ZoneInfo(timezone)
    ).date().isoformat()


async def get_today_log(user_id: int):
    today = await get_today(user_id)

    rows = await supabase_get(
        "daily_logs",
        f"?user_id=eq.{user_id}&date=eq.{today}&select=*"
    )

    return rows[0] if rows else None


async def update_log(user_id: int, field: str, value: int):
    allowed_fields = {
        "smoked",
        "sleep",
        "water",
        "food",
        "rest",
        "craving",
        "completed",
    }

    if field not in allowed_fields:
        return

    today = await get_today(user_id)

    await supabase_post(
        "daily_logs",
        {
            "user_id": user_id,
            "date": today,
            field: value,
        },
        upsert=True,
        conflict="user_id,date",
    )


async def was_reminder_sent(user_id: int):
    today = await get_today(user_id)

    rows = await supabase_get(
        "reminders_sent",
        f"?user_id=eq.{user_id}&date=eq.{today}&reminder_type=eq.smoke&select=*"
    )

    return bool(rows)


async def mark_reminder_sent(user_id: int):
    today = await get_today(user_id)

    await supabase_post(
        "reminders_sent",
        {
            "user_id": user_id,
            "date": today,
            "reminder_type": "smoke",
        },
        upsert=True,
        conflict="user_id,date,reminder_type",
    )


async def calculate_streak(user_id: int):
    rows = await supabase_get(
        "daily_logs",
        f"?user_id=eq.{user_id}&select=date,smoked&order=date.desc"
    )

    logs = {row["date"]: row for row in rows}

    streak = 0
    today = await get_today(user_id)
    current_date = datetime.fromisoformat(today).date()

    while True:
        key = current_date.isoformat()
        row = logs.get(key)

        if not row:
            break

        smoked = row.get("smoked")

        if smoked is None:
            current_date -= timedelta(days=1)
            continue

        if smoked == 0:
            streak += 1
            current_date -= timedelta(days=1)
            continue

        break

    return streak


async def calculate_best_streak(user_id: int, exclude_today=False):
    today = await get_today(user_id)

    rows = await supabase_get(
        "daily_logs",
        f"?user_id=eq.{user_id}&select=date,smoked&order=date.asc"
    )

    best = 0
    current = 0

    for row in rows:
        if exclude_today and row.get("date") == today:
            continue

        smoked = row.get("smoked")

        if smoked == 0:
            current += 1
            best = max(best, current)

        elif smoked == 1:
            current = 0

    return best


async def get_path_event(user_id: int):
    rows = await supabase_get(
        "daily_logs",
        f"?user_id=eq.{user_id}&select=date&order=date.asc&limit=1"
    )

    if not rows:
        return ""

    first_date = datetime.fromisoformat(rows[0]["date"]).date()
    today = datetime.fromisoformat(await get_today(user_id)).date()
    days = (today - first_date).days

    events = {
        7: "🎉 Сегодня ровно неделя с твоего первого дня.",
        30: "🎉 Сегодня ровно месяц с твоего первого дня.",
        100: "🎉 Сегодня уже 100 дней с начала твоего пути.",
        180: "🚀 Сегодня прошло полгода с начала твоего пути.",
        365: "👑 Сегодня ровно год с начала твоего пути.",
    }

    return events.get(days, "")


def milestone_message(streak: int):
    milestones = {
        1: "🎉 Первый шаг сделан.",
        3: "🥉 Уже три дня подряд. Хорошее начало.",
        7: "🥈 Первая неделя позади. Это уже серьёзный шаг.",
        14: "🥇 Две недели подряд. Привычка становится крепче.",
        30: "💎 Первый месяц. Это сильный результат.",
        180: "🚀 Полгода. Очень мощная серия.",
        365: "👑 Год. Это уже настоящая легенда.",
    }

    return milestones.get(streak, "")


async def ask_smoked(user_id: int):
    await bot.send_message(
        user_id,
        "🚬 Сегодня было курение?",
        reply_markup=yes_no_keyboard("smoked")
    )


async def send_stats(message: Message):
    user_id = message.from_user.id

    await ensure_user(user_id)

    streak = await calculate_streak(user_id)
    best = await calculate_best_streak(user_id)
    path_event = await get_path_event(user_id)

    text = (
        f"📊 Статистика\n\n"
        f"🚭 Сейчас без курения: {streak} дн.\n"
        f"🏆 Лучший результат: {best} дн."
    )

    if path_event:
        text += f"\n\n{path_event}"

    await message.answer(
        text,
        reply_markup=main_menu()
    )


@router.message(Command("start"))
async def start(message: Message):
    await ensure_user(message.from_user.id)

    await message.answer(
        "👋 Привет.\n\n"
        "Я помогу отслеживать дни без курения "
        "и формировать полезные привычки.\n\n"
        "Сильная жизнь начинается с сильных привычек.\n\n"
        "Можно пользоваться кнопками ниже:",
        reply_markup=main_menu()
    )


@router.message(Command("today"))
async def today(message: Message):
    await ensure_user(message.from_user.id)
    await ask_smoked(message.from_user.id)


@router.message(Command("stats"))
async def stats(message: Message):
    await send_stats(message)


@router.message(F.text == "✅ Отметить день")
async def today_button(message: Message):
    await ensure_user(message.from_user.id)
    await ask_smoked(message.from_user.id)


@router.message(F.text == "📊 Статистика")
async def stats_button(message: Message):
    await send_stats(message)


@router.callback_query(F.data == "smoked:yes")
async def smoked_yes(callback: CallbackQuery):
    user_id = callback.from_user.id

    await update_log(user_id, "smoked", 1)
    await update_log(user_id, "completed", 1)

    await callback.message.edit_text(
        f"Сегодня отмечен день с курением.\n\n"
        f"{pick(SMOKED_SUPPORT_PHRASES)}\n\n"
        f"Завтра продолжаем 💪"
    )

    await callback.answer()


@router.callback_query(F.data == "smoked:no")
async def smoked_no(callback: CallbackQuery):
    user_id = callback.from_user.id

    await update_log(user_id, "smoked", 0)

    await callback.message.edit_text(
        f"{pick(SUCCESS_PHRASES)}\n\n"
        f"😴 Как сегодня со сном? Удалось выспаться?",
        reply_markup=yes_no_keyboard("sleep")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("sleep:"))
async def sleep_answer(callback: CallbackQuery):
    value = 1 if callback.data.endswith("yes") else 0

    await update_log(
        callback.from_user.id,
        "sleep",
        value
    )

    phrase = pick(SLEEP_YES_PHRASES if value else SLEEP_NO_PHRASES)

    await callback.message.edit_text(
        f"{phrase}\n\n"
        f"💧 Как сегодня с водой? Получилось выпить достаточно?",
        reply_markup=yes_no_keyboard("water")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("water:"))
async def water_answer(callback: CallbackQuery):
    value = 1 if callback.data.endswith("yes") else 0

    await update_log(
        callback.from_user.id,
        "water",
        value
    )

    phrase = pick(WATER_YES_PHRASES if value else WATER_NO_PHRASES)

    await callback.message.edit_text(
        f"{phrase}\n\n"
        f"🍽 Как сегодня с питанием? Получилось нормально поесть?",
        reply_markup=yes_no_keyboard("food")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("food:"))
async def food_answer(callback: CallbackQuery):
    value = 1 if callback.data.endswith("yes") else 0

    await update_log(
        callback.from_user.id,
        "food",
        value
    )

    phrase = pick(FOOD_YES_PHRASES if value else FOOD_NO_PHRASES)

    await callback.message.edit_text(
        f"{phrase}\n\n"
        f"🛌 Был ли сегодня нормальный отдых?",
        reply_markup=yes_no_keyboard("rest")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("rest:"))
async def rest_answer(callback: CallbackQuery):
    value = 1 if callback.data.endswith("yes") else 0

    await update_log(
        callback.from_user.id,
        "rest",
        value
    )

    phrase = pick(REST_YES_PHRASES if value else REST_NO_PHRASES)

    await callback.message.edit_text(
        f"{phrase}\n\n"
        f"🔥 Было сильное желание закурить?",
        reply_markup=yes_no_keyboard("craving")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("craving:"))
async def craving_answer(callback: CallbackQuery):
    value = 1 if callback.data.endswith("yes") else 0
    user_id = callback.from_user.id

    previous_log = await get_today_log(user_id)
    already_completed = bool(previous_log and previous_log.get("completed") == 1)

    await update_log(user_id, "craving", value)
    await update_log(user_id, "completed", 1)

    streak = await calculate_streak(user_id)
    old_best = await calculate_best_streak(user_id, exclude_today=True)
    best = max(streak, old_best)

    phrase = pick(CRAVING_YES_PHRASES if value else CRAVING_NO_PHRASES)
    milestone = milestone_message(streak) if not already_completed else ""
    new_record = streak > old_best and streak > 1 and not already_completed

    text = (
        f"✅ День сохранён.\n\n"
        f"{phrase}\n\n"
        f"{pick(SUCCESS_PHRASES)}\n\n"
        f"🔥 Текущая серия: {streak} дн.\n"
        f"🏆 Лучший результат: {best} дн."
    )

    if new_record:
        text += f"\n\n🎉 Новый личный рекорд: {streak} дн."

    if milestone:
        text += f"\n\n{milestone}"

    await callback.message.edit_text(text)

    await callback.answer()


async def check_reminders():
    users = await supabase_get(
        "users",
        "?select=user_id,reminder_time,timezone"
    )

    for user in users:
        user_id = user["user_id"]
        reminder_time = user.get("reminder_time") or DEFAULT_TIME
        timezone = user.get("timezone") or DEFAULT_TIMEZONE

        now = datetime.now(ZoneInfo(timezone))
        current_time = now.strftime("%H:%M")

        if current_time < reminder_time:
            continue

        already_sent = await was_reminder_sent(user_id)

        if already_sent:
            continue

        try:
            await ask_smoked(user_id)
            await mark_reminder_sent(user_id)

            print(
                f"Reminder sent to {user_id} at {current_time}",
                flush=True
            )

        except Exception as e:
            print(
                f"Reminder send error for {user_id}: {e}",
                flush=True
            )


async def reminder_loop():
    while True:
        try:
            await check_reminders()

        except Exception as e:
            print("Reminder loop error:", e, flush=True)

        await asyncio.sleep(30)


async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)

    asyncio.create_task(
        reminder_loop()
    )

    print("BOT STARTED", flush=True)


async def health(request):
    return web.Response(
        text="Bot is running"
    )


def main():
    dp.startup.register(
        on_startup
    )

    app = web.Application()

    app.router.add_get(
        "/",
        health
    )

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    ).register(
        app,
        path="/webhook"
    )

    setup_application(
        app,
        dp,
        bot=bot
    )

    web.run_app(
        app,
        host="0.0.0.0",
        port=PORT
    )


if __name__ == "__main__":
    main()