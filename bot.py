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


SUCCESS_THOUGHTS = [
    "🌱 Каждый такой день укрепляет привычку.",
    "🧱 Маленькие шаги постепенно складываются в большие изменения.",
    "💪 Сегодня удалось сохранить курс.",
    "🚀 Ещё один день пошёл в твою пользу.",
    "🌿 Привычка становится крепче через повторение.",
    "🎯 Сегодняшний выбор имеет значение.",
    "🔥 Серия продолжает расти.",
    "⭐ Это хороший вклад в себя.",
    "👏 Ритм сохраняется. Продолжаем.",
    "🌤 Ещё один спокойный шаг вперёд.",
]

HARD_DAY_THOUGHTS = [
    "Сегодня было непросто, но день всё равно сохранён.",
    "Не самый лёгкий день, но это не отменяет весь путь.",
    "Сегодня было больше сопротивления. Завтра будет новая попытка.",
    "Сложные дни тоже часть процесса.",
    "Главное — не застрять в этом дне и продолжить дальше.",
]

SMOKED_SUPPORT_PHRASES = [
    "Сегодня получилось не так, как хотелось. Это не отменяет весь путь.",
    "Один день не определяет результат. Завтра можно начать новую серию.",
    "Такое бывает. Важно не застрять в этом дне и продолжить завтра.",
    "Срыв — это не конец. Это просто точка, от которой можно оттолкнуться.",
    "Сегодня был непростой день. Всё ещё впереди.",
]

SLEEP_YES_PHRASES = [
    "😴 Сон сегодня поддержал восстановление.",
    "🌙 Хороший сон — сильная база для следующего дня.",
    "💤 Восстановление сегодня пошло в плюс.",
]

SLEEP_NO_PHRASES = [
    "😴 Сегодня сна было маловато. Завтра стоит дать себе больше восстановления.",
    "🌙 Недосып может усиливать тягу. Завтра лучше уделить сну больше внимания.",
    "💤 Сон сегодня просел. Это не провал, но хороший сигнал на завтра.",
]

WATER_YES_PHRASES = [
    "💧 С водой сегодня порядок.",
    "🚰 Водный баланс сегодня пошёл в плюс.",
    "💦 Хорошо, что про воду не забыли.",
]

WATER_NO_PHRASES = [
    "💧 Завтра можно начать хотя бы с одного дополнительного стакана воды.",
    "🚰 Воду легко забыть, но она заметно влияет на самочувствие.",
    "💦 Сегодня воды было мало. Завтра можно сделать лучше.",
]

FOOD_YES_PHRASES = [
    "🍽 Питание сегодня поддержало энергию.",
    "🥗 С едой сегодня получилось ровнее.",
    "🍲 Хорошая база для самочувствия.",
]

FOOD_NO_PHRASES = [
    "🍽 Завтра стоит найти время хотя бы на один нормальный приём пищи.",
    "🥗 Питание сегодня просело. Это не критично, но лучше не запускать.",
    "🍲 Завтра можно сделать день ровнее по еде.",
]

REST_YES_PHRASES = [
    "🛌 Отдых сегодня помог восстановиться.",
    "🌿 Хорошо, что было время на восстановление.",
    "🔋 Отдых — это часть прогресса.",
]

REST_NO_PHRASES = [
    "🛌 Завтра попробуй выделить хотя бы немного времени для себя.",
    "🔋 Сегодня было мало восстановления. Это стоит поправить.",
    "🌿 Отдых тоже часть прогресса. Не забывай про него.",
]

ENDING_PHRASES = [
    "Продолжаем завтра.",
    "Следующий день уже ждёт.",
    "Спасибо, что уделил сегодня время себе.",
    "Двигаемся дальше.",
    "Завтра будет новый шаг.",
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


async def supabase_patch(table, params, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}{params}"

    async with aiohttp.ClientSession() as session:
        async with session.patch(url, headers=headers(), json=data) as resp:
            if resp.status >= 400:
                text = await resp.text()
                print("SUPABASE PATCH ERROR:", resp.status, text, flush=True)
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
    rows = await supabase_get("users", f"?user_id=eq.{user_id}&select=*")

    if rows:
        return rows[0]

    await ensure_user(user_id)
    

    rows = await supabase_get("users", f"?user_id=eq.{user_id}&select=*")
    return rows[0]


async def get_today(user_id: int):
    user = await get_user(user_id)
    timezone = user.get("timezone") or DEFAULT_TIMEZONE
    return datetime.now(ZoneInfo(timezone)).date().isoformat()


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
        "willpower_delta",
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


def calculate_willpower_delta(log):
    if not log:
        return 0

    smoked = log.get("smoked")

    if smoked == 1:
        return -10

    sleep = log.get("sleep")
    water = log.get("water")
    food = log.get("food")
    rest = log.get("rest")
    craving = log.get("craving")

    points = 10

    if sleep == 1:
        points += 2
    elif sleep == 0:
        points -= 1

    if water == 1:
        points += 2
    elif water == 0:
        points -= 1

    if food == 1:
        points += 2
    elif food == 0:
        points -= 1

    if rest == 1:
        points += 2
    elif rest == 0:
        points -= 1

    if craving == 1:
        points += 3

    return points


def visible_day_points(log, delta):
    if not log:
        return 0

    if log.get("smoked") == 1:
        return 0

    return max(0, delta)


def format_day_points(points: int):
    if points > 0:
        return f"+{points}"

    return "0"


async def apply_willpower_points(user_id: int):
    user = await get_user(user_id)
    today_log = await get_today_log(user_id)

    if not today_log:
        return 0, user.get("willpower_points") or 0, 0

    old_delta = today_log.get("willpower_delta") or 0
    new_delta = calculate_willpower_delta(today_log)

    current_total = user.get("willpower_points") or 0
    updated_total = current_total - old_delta + new_delta

    if updated_total < 0:
        updated_total = 0

    await update_log(user_id, "willpower_delta", new_delta)

    await supabase_patch(
        "users",
        f"?user_id=eq.{user_id}",
        {"willpower_points": updated_total}
    )

    shown_delta = visible_day_points(today_log, new_delta)

    return new_delta, updated_total, shown_delta


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


def next_goal_text(streak: int):
    if streak == 0:
        return "🎯 Следующая цель: 🥈 7 дней\nНачинаем новую серию."

    goals = [
        (3, "🥉 3 дня"),
        (7, "🥈 7 дней"),
        (14, "🥇 14 дней"),
        (30, "💎 30 дней"),
        (180, "🚀 6 месяцев"),
        (365, "👑 365 дней"),
    ]

    for days, title in goals:
        if streak < days:
            left = days - streak
            return f"🎯 Следующая цель: {title}\nОсталось: {left} дн."

    return "🎯 Следующая цель: 🔥 1000 дней\nПуть продолжается."


def milestone_message(streak: int):
    milestones = {
        1: "🎉 Первый шаг сделан.",
        3: "🥉 Уже три дня подряд.",
        7: "🥈 Первая неделя позади.",
        14: "🥇 Две недели подряд.",
        30: "💎 Первый месяц.",
        180: "🚀 Полгода.",
        365: "👑 Год.",
    }

    return milestones.get(streak, "")


def day_summary(log):
    smoked = log.get("smoked")
    sleep = log.get("sleep")
    water = log.get("water")
    food = log.get("food")
    rest = log.get("rest")
    craving = log.get("craving")

    lines = [
        "📅 Итог дня",
        "",
        f"🚭 Курение: {'✅ нет' if smoked == 0 else '❌ было'}",
        f"😴 Сон: {'✅' if sleep == 1 else '❌'}",
        f"💧 Вода: {'✅' if water == 1 else '❌'}",
        f"🍽 Питание: {'✅' if food == 1 else '❌'}",
        f"🛌 Отдых: {'✅' if rest == 1 else '❌'}",
    ]

    if smoked == 0:
        lines.append(f"🔥 Тяга: {'была' if craving == 1 else 'почти не мешала'}")

    return "\n".join(lines)


def get_context_thought(log):
    smoked = log.get("smoked")
    sleep = log.get("sleep")
    water = log.get("water")
    food = log.get("food")
    rest = log.get("rest")
    craving = log.get("craving")

    if smoked == 1:
        return pick(SMOKED_SUPPORT_PHRASES)

    problems = 0

    for value in [sleep, water, food, rest]:
        if value == 0:
            problems += 1

    if craving == 1:
        problems += 1

    if problems >= 3:
        return pick(HARD_DAY_THOUGHTS)

    if craving == 1:
        return "Сегодня была тяга, но серию удалось сохранить."

    if problems == 0:
        return "Сегодня день получился довольно ровным."

    return pick(SUCCESS_THOUGHTS)


def get_tomorrow_advice(log):
    smoked = log.get("smoked")
    sleep = log.get("sleep")
    water = log.get("water")
    food = log.get("food")
    rest = log.get("rest")
    craving = log.get("craving")

    advice = []

    if smoked == 1:
        advice.append("🚭 начать новую серию")
    if sleep == 0:
        advice.append("😴 дать себе больше сна")
    if water == 0:
        advice.append("💧 выпить больше воды")
    if food == 0:
        advice.append("🍽 поесть чуть ровнее")
    if rest == 0:
        advice.append("🛌 выделить время на отдых")
    if smoked == 0 and craving == 1:
        advice.append("🔥 заранее подготовить замену моменту тяги")

    if not advice:
        return "Завтра можно просто сохранить этот ритм."

    if len(advice) == 1:
        return f"Завтра стоит обратить внимание на это: {advice[0]}."

    return "Завтра стоит обратить внимание:\n" + "\n".join(f"— {item}" for item in advice[:3])


async def ask_smoked(user_id: int):
    await bot.send_message(
        user_id,
        "🚬 Сегодня было курение?",
        reply_markup=yes_no_keyboard("smoked")
    )

async def send_week_report(message: Message):
    user_id = message.from_user.id

    await ensure_user(user_id)
    
    streak = await calculate_streak(user_id)
    best = await calculate_best_streak(user_id)

    user = await get_user(user_id)
    timezone = user.get("timezone") or DEFAULT_TIMEZONE

    today = datetime.now(ZoneInfo(timezone)).date()
    start_date = today - timedelta(days=6)

    rows = await supabase_get(
        "daily_logs",
        (
            f"?user_id=eq.{user_id}"
            f"&date=gte.{start_date.isoformat()}"
            f"&date=lte.{today.isoformat()}"
            f"&select=*"
            f"&order=date.asc"
        )
    )

    completed_logs = [
        row for row in rows
        if row.get("completed") == 1
    ]

    smoke_free_days = sum(
        1 for row in completed_logs
        if row.get("smoked") == 0
    )

    smoked_days = sum(
        1 for row in completed_logs
        if row.get("smoked") == 1
    )

    sleep_good = sum(
        1 for row in completed_logs
        if row.get("sleep") == 1
    )

    water_good = sum(
        1 for row in completed_logs
        if row.get("water") == 1
    )

    food_good = sum(
        1 for row in completed_logs
        if row.get("food") == 1
    )

    rest_good = sum(
        1 for row in completed_logs
        if row.get("rest") == 1
    )

    smoking_spent = sum(
        row.get("smoking_spent") or 0
        for row in completed_logs
    )

    week_points = sum(
        visible_day_points(
            row,
            row.get("willpower_delta") or 0
        )
        for row in completed_logs
    )

    completed_count = len(completed_logs)

    habits = {
        "сон": sleep_good,
        "вода": water_good,
        "питание": food_good,
        "отдых": rest_good,
    }

    if completed_logs:
        min_value = min(habits.values())

        weakest_habits = [
            name
            for name, value in habits.items()
            if value == min_value
        ]

        if len(weakest_habits) == 1:
            weakest_text = weakest_habits[0]

        elif len(weakest_habits) == 2:
            weakest_text = " и ".join(weakest_habits)

        else:
            weakest_text = (
                ", ".join(weakest_habits[:-1])
                + " и "
                + weakest_habits[-1]
            )

    else:
        weakest_text = None

    if completed_count == 0:
        conclusion = (
            "Пока недостаточно данных для вывода. "
            "Отмечай дни, и здесь появится анализ недели."
        )

    elif smoke_free_days == completed_count:
        conclusion = (
            "Неделя идёт без курения. "
            "Главное — сохранить этот ритм."
        )

    elif smoke_free_days > smoked_days:
        conclusion = (
            f"Большая часть отмеченных дней прошла без курения. "
            f"Зона внимания — {weakest_text}."
        )

    else:
        conclusion = (
            f"Неделя получилась непростой. "
            f"На следующей неделе стоит обратить внимание на: "
            f"{weakest_text}."
        )

    text = (
        f"📅 Отчёт за 7 дней\n\n"
        f"🚭 Без курения: {smoke_free_days} дн.\n"
        f"🚬 С курением: {smoked_days} дн.\n\n"
        f"🔥 Текущая серия: {streak} дн.\n"
        f"🏆 Лучший результат: {best} дн.\n\n"
        f"💪 Очки воли за неделю: {week_points}\n"
        f"💸 Потрачено на сигареты: {smoking_spent} ₽\n\n"
        f"😴 Сон: {sleep_good}/{completed_count}\n"
        f"💧 Вода: {water_good}/{completed_count}\n"
        f"🍽 Питание: {food_good}/{completed_count}\n"
        f"🛌 Отдых: {rest_good}/{completed_count}\n\n"
        f"💬 {conclusion}"
    )

    await message.answer(
        text,
        reply_markup=main_menu()
    )

async def send_stats(message: Message):
    user_id = message.from_user.id

    await ensure_user(user_id)

    user = await get_user(user_id)
    streak = await calculate_streak(user_id)
    best = await calculate_best_streak(user_id)
    willpower = user.get("willpower_points") or 0

    text = (
        f"📊 Статистика\n\n"
        f"🚭 Сейчас без курения: {streak} дн.\n"
        f"🏆 Лучший результат: {best} дн.\n"
        f"💪 Очки воли: {willpower}\n\n"
        f"{next_goal_text(streak)}"
    )

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

@router.message(Command("week"))
async def week(message: Message):
    await send_week_report(message)

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

    await callback.message.edit_text(
        "Сегодня отмечен день с курением.\n\n"
        f"{pick(SMOKED_SUPPORT_PHRASES)}\n\n"
        "😴 Как сегодня со сном? Удалось выспаться?",
        reply_markup=yes_no_keyboard("sleep")
    )

    await callback.answer()


@router.callback_query(F.data == "smoked:no")
async def smoked_no(callback: CallbackQuery):
    user_id = callback.from_user.id

    await update_log(user_id, "smoked", 0)

    await callback.message.edit_text(
        f"{pick(SUCCESS_THOUGHTS)}\n\n"
        f"😴 Как сегодня со сном? Удалось выспаться?",
        reply_markup=yes_no_keyboard("sleep")
    )

    await callback.answer()


@router.callback_query(F.data.startswith("sleep:"))
async def sleep_answer(callback: CallbackQuery):
    value = 1 if callback.data.endswith("yes") else 0

    await update_log(callback.from_user.id, "sleep", value)

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

    await update_log(callback.from_user.id, "water", value)

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

    await update_log(callback.from_user.id, "food", value)

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
    user_id = callback.from_user.id

    await update_log(user_id, "rest", value)
    await update_log(user_id, "completed", 1)

    today_log = await get_today_log(user_id)

    _, total, shown_delta = await apply_willpower_points(user_id)

    today_log = await get_today_log(user_id)

    streak = await calculate_streak(user_id)
    old_best = await calculate_best_streak(user_id, exclude_today=True)
    best = max(streak, old_best)

    already_completed = False
    milestone = milestone_message(streak) if not already_completed else ""
    new_record = streak > old_best and streak > 1 and not already_completed
    day_points = format_day_points(shown_delta)

    text = (
        f"✅ День сохранён.\n\n"
        f"{day_summary(today_log)}\n\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"{get_context_thought(today_log)}\n\n"
        f"{get_tomorrow_advice(today_log)}\n\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"💪 Очки воли за день: {day_points}\n"
        f"Всего: {total}\n\n"
        f"🔥 Серия — {streak} дн.\n"
        f"🏆 Рекорд — {best} дн.\n\n"
        f"{next_goal_text(streak)}"
    )

    if new_record:
        text += f"\n\n🎉 Новый личный рекорд — {streak} дн."

    if milestone:
        text += f"\n\n{milestone}"

    text += f"\n\n{pick(ENDING_PHRASES)}"

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

            print(f"Reminder sent to {user_id} at {current_time}", flush=True)

        except Exception as e:
            print(f"Reminder send error for {user_id}: {e}", flush=True)


async def reminder_loop():
    while True:
        try:
            await check_reminders()

        except Exception as e:
            print("Reminder loop error:", e, flush=True)

        await asyncio.sleep(30)


async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)

    asyncio.create_task(reminder_loop())

    print("BOT STARTED", flush=True)


async def health(request):
    return web.Response(text="Bot is running")


def main():
    dp.startup.register(on_startup)

    app = web.Application()

    app.router.add_get("/", health)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    ).register(
        app,
        path="/webhook"
    )

    setup_application(app, dp, bot=bot)

    web.run_app(
        app,
        host="0.0.0.0",
        port=PORT
    )


if __name__ == "__main__":
    main()
