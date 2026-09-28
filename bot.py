import asyncio
import html
import json
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('schedule_bot')

API_TOKEN = os.getenv('BOT_TOKEN')  # НЕ зберігай токен у коді!
if not API_TOKEN:
    raise SystemExit('Задай змінну оточення BOT_TOKEN')

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

KYIV_TZ = ZoneInfo('Europe/Kyiv')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHAT_ID_FILE = os.path.join(BASE_DIR, 'chat_id.json')
SCHEDULE_FILE = os.path.join(BASE_DIR, 'schedule.json')

LESSONS_END_TIMES = {
    1: 9 * 60 + 50,
    2: 11 * 60 + 25,
    3: 13 * 60 + 0,
    4: 14 * 60 + 35,
    5: 16 * 60 + 10,
    6: 17 * 60 + 45,
}

MORNING_MINUTE = 7 * 60 + 30
GRACE = 5  # хвилин "вікна" для надсилання


# ---------- chat id ----------
def load_chat_id():
    env = os.getenv('CHAT_ID')  # найнадійніше в хмарі
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    try:
        if os.path.exists(CHAT_ID_FILE):
            with open(CHAT_ID_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get('chat_id')
    except Exception:
        log.exception('Не вдалося прочитати chat_id')
    return None


def save_chat_id(chat_id):
    try:
        with open(CHAT_ID_FILE, 'w', encoding='utf-8') as f:
            json.dump({'chat_id': chat_id}, f)
    except Exception:
        log.exception('Не вдалося зберегти chat_id')


USER_CHAT_ID = load_chat_id()


def remember_chat(chat_id):
    global USER_CHAT_ID
    if USER_CHAT_ID != chat_id:
        USER_CHAT_ID = chat_id
        save_chat_id(chat_id)
        log.info('chat_id збережено: %s (для хмари задай CHAT_ID у змінних)', chat_id)


def get_chat_id():
    global USER_CHAT_ID
    if not USER_CHAT_ID:
        USER_CHAT_ID = load_chat_id()
    return USER_CHAT_ID


# ---------- погода ----------
def _fetch_weather():
    url = (
        'https://api.open-meteo.com/v1/forecast?latitude=49.8383&longitude=24.0232'
        '&current=temperature_2m,weather_code&timezone=auto'
    )
    r = requests.get(url, timeout=5)
    r.raise_for_status()
    cur = r.json()['current']
    return round(cur['temperature_2m']) - 1, cur['weather_code']


WEATHER_URL = (
    'https://api.open-meteo.com/v1/forecast'
    '?latitude=49.8383&longitude=24.0232'
    '&current=temperature_2m,apparent_temperature,relative_humidity_2m,'
    'weather_code,wind_speed_10m'
    '&hourly=temperature_2m,precipitation_probability,weather_code'
    '&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,'
    'uv_index_max,sunrise,sunset'
    '&wind_speed_unit=ms&timezone=Europe%2FKyiv&forecast_days=1'
)
TEMP_CORRECTION = -1  # твоя поправка до температури, як було в старому коді
HOURLY_SLOTS = (9, 12, 15, 18, 21)


def _t(v):
    return round(v) + TEMP_CORRECTION


def fmt_temp(n):
    return f'+{n}°C' if n > 0 else f'{n}°C'


def describe_code(code):
    if code == 0:
        return '☀️', 'Ясно'
    if code == 1:
        return '🌤', 'Переважно ясно'
    if code == 2:
        return '⛅', 'Мінлива хмарність'
    if code == 3:
        return '☁️', 'Хмарно'
    if code in (45, 48):
        return '🌫', 'Туман'
    if code in (51, 53, 55):
        return '🌦', 'Мряка'
    if code in (56, 57, 66, 67):
        return '🌧', 'Крижаний дощ'
    if code in (61, 63, 65):
        return '🌧', 'Дощ'
    if code in (71, 73, 75, 77, 85, 86):
        return '❄️', 'Сніг'
    if code in (80, 81, 82):
        return '🌦', 'Зливи'
    if code in (95, 96, 99):
        return '⛈', 'Гроза'
    return '🌡', 'Мінлива погода'


def is_rainy(code):
    return 51 <= code <= 67 or 80 <= code <= 82 or code >= 95


def is_snowy(code):
    return code in (71, 73, 75, 77, 85, 86)


def get_weather_data():
    r = requests.get(WEATHER_URL, timeout=8)
    r.raise_for_status()
    j = r.json()
    cur, d, h = j['current'], j['daily'], j['hourly']
    hourly = []
    for i, ts in enumerate(h['time']):
        hourly.append((
            int(ts[11:13]),
            _t(h['temperature_2m'][i]),
            h['precipitation_probability'][i] or 0,
            h['weather_code'][i],
        ))
    return {
        'temp': _t(cur['temperature_2m']),
        'feels': _t(cur['apparent_temperature']),
        'humidity': round(cur['relative_humidity_2m']),
        'wind': cur['wind_speed_10m'],
        'code': cur['weather_code'],
        'tmax': _t(d['temperature_2m_max'][0]),
        'tmin': _t(d['temperature_2m_min'][0]),
        'pop': d['precipitation_probability_max'][0] or 0,
        'uv': d['uv_index_max'][0] or 0,
        'sunrise': d['sunrise'][0][11:16],
        'sunset': d['sunset'][0][11:16],
        'hourly': hourly,
    }


def build_outfit(w):
    feels = w['feels']
    if feels <= -10:
        lines = ['🧥 Зимова куртка, шапка, шарф, рукавиці, теплі черевики']
    elif feels <= 0:
        lines = ['🧥 Зимова куртка, шапка, шарф, рукавиці']
    elif feels <= 7:
        lines = ['🧥 Тепла куртка чи пальто, шапка і шарф за вітру']
    elif feels <= 13:
        lines = ['🧥 Демісезонна куртка, светр чи худі']
    elif feels <= 18:
        lines = ['🧶 Легка куртка чи худі']
    elif feels <= 23:
        lines = ['👕 Футболка і легка кофта про запас']
    else:
        lines = ['👕 Легкий одяг, більше води']

    if w['pop'] >= 50 or is_rainy(w['code']):
        lines.append('☂️ Візьми парасольку, взуття краще непромокаюче')
    elif w['pop'] >= 30:
        lines.append('🌂 Можливий дощ, парасолька не завадить')
    if is_snowy(w['code']):
        lines.append('🥾 Тепле взуття, що не ковзає')
    if w['wind'] >= 8:
        lines.append('💨 Сильний вітер, краще вітрозахисна куртка')
    if w['uv'] >= 6 and w['tmax'] > 10:
        lines.append('🕶 Сонцезахисні окуляри')
    if w['tmax'] - w['tmin'] >= 8:
        lines.append('🧅 Різниця за день велика, вдягайся шарами')
    return lines


def build_weather_text(w):
    emoji, desc = describe_code(w['code'])
    now_hour = datetime.now(KYIV_TZ).hour

    text = (
        f'🌤 <b>Львів зараз</b>\n'
        f"{emoji} {desc}, <b>{fmt_temp(w['temp'])}</b>\n"
        f"🌡 Відчувається як {fmt_temp(w['feels'])} • 💧 {w['humidity']}% • "
        f"💨 {w['wind']:.0f} м/с\n\n"
        f"📊 Сьогодні: від {fmt_temp(w['tmin'])} до {fmt_temp(w['tmax'])}\n"
        f"☔ Ймовірність опадів: {w['pop']}%\n"
        f"🌅 {w['sunrise']} • 🌇 {w['sunset']}\n"
    )

    slots = [x for x in w['hourly'] if x[0] in HOURLY_SLOTS and x[0] > now_hour]
    if slots:
        text += '\n🕒 <b>По годинах:</b>\n<code>'
        for hour, temp, pop, code in slots:
            e, _ = describe_code(code)
            text += f'{hour:02d}:00  {e} {fmt_temp(temp):>5}  ({pop}%)\n'
        text += '</code>'

    text += '\n👕 <b>Що вдягнути:</b>\n' + '\n'.join(build_outfit(w))
    return text


def get_weather_report():
    """Детальний звіт для кнопки/команди «Погода»."""
    try:
        return build_weather_text(get_weather_data())
    except Exception:
        log.exception('Помилка погоди')
        return '🌤 Львів: дані недоступні, спробуй пізніше'


def get_lviv_weather():
    """Короткий варіант (рядок, чи потрібна парасолька), для розкладу."""
    try:
        w = get_weather_data()
        emoji, desc = describe_code(w['code'])
        rain = w['pop'] >= 50 or is_rainy(w['code'])
        return f"{emoji} Львів: {desc}, {fmt_temp(w['temp'])}", rain
    except Exception:
        log.exception('Помилка погоди')
        return '🌤 Львів: дані недоступні', False


def get_morning_weather():
    """Для ранкового зведення: рядок погоди, чи потрібна парасолька, поради з одягу."""
    try:
        w = get_weather_data()
        emoji, desc = describe_code(w['code'])
        line = (
            f"{emoji} Львів: {desc}, {fmt_temp(w['temp'])} "
            f"(сьогодні {fmt_temp(w['tmin'])}…{fmt_temp(w['tmax'])})"
        )
        rain = w['pop'] >= 50 or is_rainy(w['code'])
        return line, rain, '\n'.join(build_outfit(w))
    except Exception:
        log.exception('Помилка погоди')
        return '🌤 Львів: дані недоступні', False, '🎒 Одягайся за погодою'


# ---------- розклад ----------
def get_week_type(target_date=None):
    if target_date is None:
        now = datetime.now(KYIV_TZ)
        target_date = now + timedelta(days=2) if now.weekday() >= 5 else now
    return 'Знаменник' if target_date.isocalendar()[1] % 2 != 0 else 'Чисельник'


get_current_week_type = get_week_type

DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд']


def get_today_short_name():
    return DAYS[datetime.now(KYIV_TZ).weekday()]


def get_tomorrow_short_name():
    return DAYS[(datetime.now(KYIV_TZ).weekday() + 1) % 7]


def load_schedule():
    with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def lessons_for(day_name, week):
    """Фільтрує пари за тижнем і підгрупою (єдине місце замість 3 копій)."""
    result = []
    for l in load_schedule().get(day_name, []):
        w_type = l.get('week_type', '').lower()
        subgroup = l.get('subgroup', '').lower()
        subject = l.get('subject', '').lower()
        details = l.get('details', '').lower()

        if day_name == 'Чт' and 'історія' in subject:
            if 'лекція' in details and week != 'Чисельник':
                continue
            if 'практична' in details and week != 'Знаменник':
                continue

        right_week = (
            week.lower() in w_type
            or 'кож' in w_type
            or 'об' in w_type
            or 'загальн' in w_type
            or not w_type
        )
        right_sub = (
            '2' in subgroup or 'всі' in subgroup or 'вси' in subgroup or not subgroup
        )
        if right_week and right_sub:
            result.append(l)
    result.sort(key=lambda x: int(x['lesson_num']))
    return result


def clean_subject(s):
    return html.escape(s.replace(', частина 1', '').replace(', частина 2', ''))


def get_recommendation(subject, details):
    sub, det = subject.lower(), details.lower()
    if 'фізичне виховання' in sub:
        return '👟 Спортивна форма та взуття'
    if 'програмування' in sub or 'алгоритмізація' in sub:
        return '💻 Ноутбук'
    if 'фізика' in sub:
        return '📐 Калькулятор, зошит для лаб'
    if 'лекція' in det:
        return '📓 Зошит для конспекту'
    if 'практична' in det:
        return '✍️ Практичні матеріали'
    return '🎒 Зошит, ручка'


def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text='📅 Сьогодні', callback_data='day_today')
    builder.button(text='⏭ Завтра', callback_data='day_tomorrow')
    builder.button(text='🌤 Погода', callback_data='weather')
    builder.button(text='📚 Весь розклад', callback_data='schedule_all')
    builder.adjust(2, 2, 1)

    days_builder = InlineKeyboardBuilder()
    for day in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт']:
        days_builder.button(text=day, callback_data=f'day_{day}')
    days_builder.adjust(5)

    builder.attach(days_builder)
    return builder.as_markup()


# ---------- хендлери ----------
@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    remember_chat(message.chat.id)
    await message.answer(
        f'🤖 <b>ПП-14</b> (2 підгр.) | <i>{get_week_type()}</i>\nОбери день 👇',
        reply_markup=get_main_keyboard(),
        parse_mode='HTML',
    )


@dp.callback_query(F.data == 'weather')
async def cb_weather(callback: types.CallbackQuery):
    text = await asyncio.to_thread(get_weather_report)
    await callback.message.answer(
        text, reply_markup=get_main_keyboard(), parse_mode='HTML'
    )
    await callback.answer()


@dp.message(Command('weather'))
async def cmd_weather(message: types.Message):
    text = await asyncio.to_thread(get_weather_report)
    await message.answer(
        text, reply_markup=get_main_keyboard(), parse_mode='HTML'
    )


@dp.callback_query(F.data == 'schedule_all')
async def cb_schedule_all(callback: types.CallbackQuery):
    remember_chat(callback.message.chat.id)
    await send_full_schedule(callback.message)
    await callback.answer()


@dp.callback_query(F.data.startswith('day_'))
async def cb_day_select(callback: types.CallbackQuery):
    remember_chat(callback.message.chat.id)
    code = callback.data.split('_')[1]
    if code == 'today':
        day = get_today_short_name()
    elif code == 'tomorrow':
        day = get_tomorrow_short_name()
    else:
        day = code
    await send_day_schedule(callback.message, day)
    await callback.answer()




@dp.message(Command('today'))
async def cmd_today(message: types.Message):
    remember_chat(message.chat.id)
    await send_day_schedule(message, get_today_short_name())


@dp.message(Command('tomorrow'))
async def cmd_tomorrow(message: types.Message):
    remember_chat(message.chat.id)
    await send_day_schedule(message, get_tomorrow_short_name())


@dp.message(Command('schedule'))
async def cmd_schedule(message: types.Message):
    remember_chat(message.chat.id)
    await send_full_schedule(message)


async def send_day_schedule(message: types.Message, day_name: str):
    try:
        week = get_week_type()
        response = f'📌 <b>{day_name}</b> • <i>{week}</i>\n'
        if day_name == get_today_short_name():
            weather, _ = await asyncio.to_thread(get_lviv_weather)
            response = f'{weather}\n\n' + response

        if day_name in ('Сб', 'Нд'):
            response += '\n🎉 Вихідний!'
        else:
            lessons = lessons_for(day_name, week)
            if not lessons:
                response += '\n🎉 Пар немає!'
            for l in lessons:
                response += (
                    f"\n🔹 <b>{l['lesson_num']}. {clean_subject(l['subject'])}</b>\n"
                    f"   <code>{html.escape(l['details'])}</code>\n"
                )
        await message.answer(
            response, reply_markup=get_main_keyboard(), parse_mode='HTML'
        )
    except FileNotFoundError:
        await message.answer('⚠️ Файл розкладу не знайдено!')


async def send_full_schedule(message: types.Message):
    try:
        schedule = load_schedule()
    except FileNotFoundError:
        await message.answer('⚠️ Файл розкладу не знайдено!')
        return

    parts = ['📚 <b>Розклад (ПП-14):</b>\n']
    for day, lessons in schedule.items():
        day_lessons = [
            l
            for l in lessons
            if '2' in l.get('subgroup', '').lower()
            or 'всі' in l.get('subgroup', '').lower()
            or not l.get('subgroup')
        ]
        if day_lessons:
            block = f'\n🔸 <b>{html.escape(day)}</b>:\n'
            for l in day_lessons:
                block += (
                    f" • {l['lesson_num']}. {clean_subject(l['subject'])}"
                    f" ({html.escape(l['details'])})\n"
                )
            parts.append(block)

    # ділимо по блоках, щоб не ламати HTML-теги
    chunk = ''
    chunks = []
    for p in parts:
        if len(chunk) + len(p) > 3500:
            chunks.append(chunk)
            chunk = ''
        chunk += p
    chunks.append(chunk)
    for i, c in enumerate(chunks):
        await message.answer(
            c,
            reply_markup=get_main_keyboard() if i == len(chunks) - 1 else None,
            parse_mode='HTML',
        )


# ---------- фонові задачі ----------
async def morning_briefing_task():
    sent_dates = set()
    while True:
        try:
            await asyncio.sleep(20)
            chat_id = get_chat_id()
            if not chat_id:
                continue

            now = datetime.now(KYIV_TZ)
            today = now.strftime('%Y-%m-%d')
            cur = now.hour * 60 + now.minute

            if today in sent_dates or not (MORNING_MINUTE <= cur < MORNING_MINUTE + GRACE):
                continue
            if now.weekday() >= 5:
                continue

            day = get_today_short_name()
            week = get_week_type()
            weather_msg, rain, outfit = await asyncio.to_thread(get_morning_weather)

            try:
                recs = {
                    get_recommendation(l['subject'], l['details'])
                    for l in lessons_for(day, week)
                }
            except Exception:
                log.exception('Помилка розкладу у ранковому зведенні')
                recs = set()
            advice = ', '.join(sorted(recs)) if recs else '🎒 Зошит, ручка'

            umbrella = (
                '☂️ Обов’язково візьми парасольку (є дощ)!'
                if rain
                else '☀️ Парасолька поки не потрібна.'
            )
            msg = (
                f'🌅 <b>Доброго ранку! Ранкове зведення</b> ({day}, <i>{week}</i>)\n\n'
                f'{weather_msg}\n{umbrella}\n\n'
                f'👕 <b>Що вдягнути:</b>\n{outfit}\n\n'
                f'💡 <b>Що взяти на пари сьогодні:</b>\n• {advice}'
            )
            await bot.send_message(
                chat_id, msg, reply_markup=get_main_keyboard(), parse_mode='HTML'
            )
            sent_dates.add(today)  # позначаємо тільки після успішної відправки
            log.info('Ранкове зведення надіслано')
        except Exception:
            log.exception('Помилка morning_briefing_task')


async def schedule_checker():
    sent = set()
    while True:
        try:
            await asyncio.sleep(20)
            chat_id = get_chat_id()
            if not chat_id:
                continue

            now = datetime.now(KYIV_TZ)
            today = now.strftime('%Y-%m-%d')
            sent = {k for k in sent if k.startswith(today)}
            if now.weekday() >= 5:
                continue

            cur = now.hour * 60 + now.minute
            day = get_today_short_name()
            week = get_week_type()
            lessons = lessons_for(day, week)
            if not lessons:
                continue
            nums = [int(l['lesson_num']) for l in lessons]

            for n, end in LESSONS_END_TIMES.items():
                target = end - 15
                if not (target <= cur < target + GRACE):
                    continue
                if n not in nums:  # зараз пари немає — нагадування не треба
                    continue
                key = f'{today}_lesson_{n}'
                if key in sent:
                    continue

                nxt = next((l for l in lessons if int(l['lesson_num']) > n), None)
                if nxt:
                    msg = (
                        f'⏰ <b>За 15 хв перерва!</b>\n'
                        f"👉 <b>{nxt['lesson_num']} пара:</b> {clean_subject(nxt['subject'])}\n"
                        f"📍 {html.escape(nxt['details'])}"
                    )
                else:
                    msg = '⏰ <b>За 15 хв кінець пари!</b> На сьогодні все! 🎉'

                try:
                    await bot.send_message(
                        chat_id, msg, reply_markup=get_main_keyboard(), parse_mode='HTML'
                    )
                    sent.add(key)
                    log.info('Нагадування %s надіслано', key)
                except Exception:
                    log.exception('Не вдалося надіслати нагадування')
        except Exception:
            log.exception('Помилка schedule_checker')


async def main():
    log.info('Бот запущено. chat_id=%s, час Києва: %s', get_chat_id(), datetime.now(KYIV_TZ))
    tasks = [
        asyncio.create_task(schedule_checker()),
        asyncio.create_task(morning_briefing_task()),
    ]
    try:
        await dp.start_polling(bot)
    finally:
        for t in tasks:
            t.cancel()


if __name__ == '__main__':
    asyncio.run(main())
