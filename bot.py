import asyncio
from datetime import datetime, timedelta
import json
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import requests

API_TOKEN = '8654263922:AAFmHBjGczqYKi0h4EvnZwf0EyNiphYxrbc'

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

USER_CHAT_ID = None

LESSONS_END_TIMES = {
    1: 9 * 60 + 50,  # 09:50
    2: 11 * 60 + 25,  # 11:25
    3: 13 * 60 + 0,  # 13:00
    4: 14 * 60 + 35,  # 14:35
    5: 16 * 60 + 10,  # 16:10
    6: 17 * 60 + 45,  # 17:45
}


def get_lviv_weather_full():
  try:
    # Отримуємо погоду для аналізу чи потрібна парасолька
    url = 'https://wttr.in/Lviv?format=%C|%t'
    response = requests.get(url, timeout=5)
    if response.status_code == 200:
      return response.text.strip()
  except Exception:
    pass
  return ''


def get_lviv_weather():
  try:
    url = 'https://wttr.in/Lviv?format=3'
    response = requests.get(url, timeout=5)
    if response.status_code == 200:
      return f'🌤 {response.text.strip()}'
  except Exception:
    pass
  return '⚠️ Погода недоступна'


def get_current_week_type(target_date=None):
  if target_date is None:
    now = datetime.now()
    if now.weekday() >= 5:
      target_date = now + timedelta(days=2)
    else:
      target_date = now

  week_number = target_date.isocalendar()[1]
  return 'Знаменник' if week_number % 2 != 0 else 'Чисельник'


def get_recommendation(subject, details):
  sub_lower = subject.lower()
  det_lower = details.lower()

  if 'фізичне виховання' in sub_lower:
    return '👟 Спортивна форма та взуття'
  elif 'програмування' in sub_lower or 'алгоритмізація' in sub_lower:
    return '💻 Ноутбук'
  elif 'фізика' in sub_lower:
    return '📐 Калькулятор, зошит для лаб'
  elif 'лекція' in det_lower:
    return '📓 Зошит для конспекту'
  elif 'практична' in det_lower:
    return '✍️ Практичні матеріали'
  else:
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


@dp.message(Command('start'))
async def cmd_start(message: types.Message):
  global USER_CHAT_ID
  USER_CHAT_ID = message.chat.id
  current_week = get_current_week_type()
  await message.answer(
      f'🤖 **ПП-14** (2 підгр.) | *{current_week}*\nОбери день 👇',
      reply_markup=get_main_keyboard(),
      parse_mode='Markdown',
  )


@dp.callback_query(F.data == 'weather')
async def cb_weather(callback: types.CallbackQuery):
  await callback.message.answer(get_lviv_weather(), parse_mode='Markdown')
  await callback.answer()


@dp.callback_query(F.data == 'schedule_all')
async def cb_schedule_all(callback: types.CallbackQuery):
  await send_full_schedule(callback.message)
  await callback.answer()


@dp.callback_query(F.data.startswith('day_'))
async def cb_day_select(callback: types.CallbackQuery):
  day_code = callback.data.split('_')[1]
  if day_code == 'today':
    day_name = get_today_short_name()
  elif day_code == 'tomorrow':
    day_name = get_tomorrow_short_name()
  else:
    day_name = day_code

  await send_day_schedule(callback.message, day_name)
  await callback.answer()


@dp.message(Command('weather'))
async def cmd_weather(message: types.Message):
  await message.answer(get_lviv_weather(), parse_mode='Markdown')


@dp.message(Command('today'))
async def cmd_today(message: types.Message):
  global USER_CHAT_ID
  USER_CHAT_ID = message.chat.id
  await send_day_schedule(message, get_today_short_name())


@dp.message(Command('tomorrow'))
async def cmd_tomorrow(message: types.Message):
  global USER_CHAT_ID
  USER_CHAT_ID = message.chat.id
  await send_day_schedule(message, get_tomorrow_short_name())


@dp.message(Command('schedule'))
async def cmd_schedule(message: types.Message):
  await send_full_schedule(message)


def get_today_short_name():
  days_map = {
      'Monday': 'Пн',
      'Tuesday': 'Вт',
      'Wednesday': 'Ср',
      'Thursday': 'Чт',
      'Friday': 'Пт',
      'Saturday': 'Сб',
      'Sunday': 'Нд',
  }
  return days_map.get(datetime.now().strftime('%A'), 'Пн')


def get_tomorrow_short_name():
  days_map = {
      'Monday': 'Вт',
      'Tuesday': 'Ср',
      'Wednesday': 'Чт',
      'Thursday': 'Пт',
      'Friday': 'Сб',
      'Saturday': 'Нд',
      'Sunday': 'Пн',
  }
  return days_map.get(datetime.now().strftime('%A'), 'Пн')


async def send_day_schedule(message: types.Message, day_name: str):
  try:
    with open('schedule.json', 'r', encoding='utf-8') as f:
      schedule = json.load(f)

    current_week = get_current_week_type()
    lessons = schedule.get(day_name, [])
    weather = (
        get_lviv_weather() if day_name == get_today_short_name() else ''
    )

    response = f'📌 **{day_name}** • *{current_week}*\n'
    if weather:
      response = f'{weather}\n\n' + response

    if day_name in ['Сб', 'Нд']:
      response += '\n🎉 Вихідний!'
      await message.answer(
          response, reply_markup=get_main_keyboard(), parse_mode='Markdown'
      )
      return

    filtered_lessons = []
    for l in lessons:
      w_type = l.get('week_type', '').lower()
      subgroup = l.get('subgroup', '').lower()
      subject = l.get('subject', '').lower()
      details = l.get('details', '').lower()

      if day_name == 'Чт' and 'історія' in subject:
        if 'лекція' in details and current_week != 'Чисельник':
          continue
        if 'практична' in details and current_week != 'Знаменник':
          continue

      is_right_week = (
          current_week.lower() in w_type
          or 'кож' in w_type
          or 'об' in w_type
          or 'загальн' in w_type
          or not w_type
      )
      is_right_subgroup = (
          '2' in subgroup
          or 'всі' in subgroup
          or 'вси' in subgroup
          or not subgroup
      )

      if is_right_week and is_right_subgroup:
        filtered_lessons.append(l)

    if not filtered_lessons:
      response += '\n🎉 Пар немає!'
    else:
      for l in filtered_lessons:
        subj = l['subject'].replace(', частина 1', '').replace(
            ', частина 2', ''
        )
        # Виводимо ультра-чисто без підказок у щоденному перегляді
        response += (
            f"\n🔹 **{l['lesson_num']}. {subj}**\n"
            f"   `{l['details']}`\n"
        )

    await message.answer(
        response, reply_markup=get_main_keyboard(), parse_mode='Markdown'
    )
  except FileNotFoundError:
    await message.answer('⚠️ Файл розкладу не знайдено!')


async def send_full_schedule(message: types.Message):
  try:
    with open('schedule.json', 'r', encoding='utf-8') as f:
      schedule = json.load(f)
    response = '📚 **Розклад (ПП-14):**\n'
    for day, lessons in schedule.items():
      day_lessons = [
          l
          for l in lessons
          if '2' in l.get('subgroup', '').lower()
          or 'всі' in l.get('subgroup', '').lower()
          or not l.get('subgroup')
      ]
      if day_lessons:
        response += f'\n🔸 **{day}**:\n'
        for l in day_lessons:
          subj = l['subject'].replace(', частина 1', '')
          response += f" • {l['lesson_num']}. {subj} ({l['details']})\n"

    if len(response) > 4000:
      for x in range(0, len(response), 4000):
        await message.answer(response[x : x + 4000], parse_mode='Markdown')
    else:
      await message.answer(
          response, reply_markup=get_main_keyboard(), parse_mode='Markdown'
      )
  except FileNotFoundError:
    await message.answer('⚠️ Файл розкладу не знайдено!')


async def morning_briefing_task():
  global USER_CHAT_ID
  sent_today = False

  while True:
    await asyncio.sleep(30)
    if not USER_CHAT_ID:
      continue

    now = datetime.now()
    # Рівно о 07:30 ранку
    if now.hour == 7 and now.minute == 30:
      today_str = now.strftime('%Y-%m-%d')
      if not sent_today:
        sent_today = True

        current_day_str = get_today_short_name()
        current_week = get_current_week_type()

        if current_day_str in ['Сб', 'Нд']:
          continue

        # Аналіз погоди для парасольки
        weather_raw = get_lviv_weather_full().lower()
        umbrella_needed = any(
            w in weather_raw for w in ['rain', 'drizzle', 'дощ', 'злива']
        )

        weather_msg = get_lviv_weather()

        # Збираємо поради на день
        try:
          with open('schedule.json', 'r', encoding='utf-8') as f:
            schedule = json.load(f)

          raw_lessons = schedule.get(current_day_str, [])
          recommendations = set()
          for l in raw_lessons:
            w_type = l.get('week_type', '').lower()
            subgroup = l.get('subgroup', '').lower()
            subject = l.get('subject', '').lower()
            details = l.get('details', '').lower()

            if current_day_str == 'Чт' and 'історія' in subject:
              if 'лекція' in details and current_week != 'Чисельник':
                continue
              if 'практична' in details and current_week != 'Знаменник':
                continue

            is_right_week = (
                current_week.lower() in w_type
                or 'кож' in w_type
                or 'об' in w_type
                or 'загальн' in w_type
                or not w_type
            )
            is_right_subgroup = (
                '2' in subgroup
                or 'всі' in subgroup
                or 'вси' in subgroup
                or not subgroup
            )

            if is_right_week and is_right_subgroup:
              rec = get_recommendation(l['subject'], l['details'])
              recommendations.add(rec)

          advice_text = (
              ', '.join(recommendations)
              if recommendations
              else '🎒 Зошит, ручка'
          )
        except Exception:
          advice_text = '🎒 Зошит, ручка'

        umbrella_text = (
            '☂️ Обов’язково візьми парасольку (є дощ)!'
            if umbrella_needed
            else '☀️ Парасолька поки не потрібна.'
        )

        msg = (
            f'🌅 **Доброго ранку! Ранкове зведення** ({current_day_str},'
            f' *{current_week}*)\n\n'
            f'{weather_msg}\n'
            f'{umbrella_text}\n\n'
            f'💡 **Що взяти на пари сьогодні:**\n'
            f'• {advice_text}'
        )

        await bot.send_message(
            USER_CHAT_ID,
            msg,
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown',
        )
    else:
      # Скидаємо прапорець наступного дня
      if now.hour == 8:
        sent_today = False


async def schedule_checker():
  global USER_CHAT_ID
  sent_notifications = set()

  while True:
    await asyncio.sleep(30)
    if not USER_CHAT_ID:
      continue

    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    current_day_str = get_today_short_name()
    current_week = get_current_week_type()

    if current_day_str in ['Сб', 'Нд']:
      continue

    for lesson_num_int, end_time in LESSONS_END_TIMES.items():
      target_time = end_time - 15

      if current_minutes == target_time:
        notif_key = f"{now.strftime('%Y-%m-%d')}_lesson_{lesson_num_int}"

        if notif_key not in sent_notifications:
          sent_notifications.add(notif_key)

          try:
            with open('schedule.json', 'r', encoding='utf-8') as f:
              schedule = json.load(f)

            raw_lessons = schedule.get(current_day_str, [])
            lessons = []
            for l in raw_lessons:
              w_type = l.get('week_type', '').lower()
              subgroup = l.get('subgroup', '').lower()
              subject = l.get('subject', '').lower()
              details = l.get('details', '').lower()

              if current_day_str == 'Чт' and 'історія' in subject:
                if 'лекція' in details and current_week != 'Чисельник':
                  continue
                if 'практична' in details and current_week != 'Знаменник':
                  continue

              is_right_week = (
                  current_week.lower() in w_type
                  or 'кож' in w_type
                  or 'об' in w_type
                  or 'загальн' in w_type
                  or not w_type
              )
              is_right_subgroup = (
                  '2' in subgroup
                  or 'всі' in subgroup
                  or 'вси' in subgroup
                  or not subgroup
              )

              if is_right_week and is_right_subgroup:
                lessons.append(l)

            next_lesson_num = str(lesson_num_int + 1)
            next_lesson = None
            for l in lessons:
              if str(l['lesson_num']) == next_lesson_num:
                next_lesson = l
                break

            if next_lesson:
              subj = next_lesson['subject'].replace(', частина 1', '')
              msg = (
                  f'⏰ **За 15 хв перерва!**\n'
                  f"👉 **{next_lesson['lesson_num']} пара:** {subj}\n"
                  f"📍 {next_lesson['details']}"
              )
            else:
              msg = '⏰ **За 15 хв кінець пари!** На сьогодні все! 🎉'

            await bot.send_message(
                USER_CHAT_ID,
                msg,
                reply_markup=get_main_keyboard(),
                parse_mode='Markdown',
            )

          except Exception as e:
            print(f'Помилка у фоновому нагадуванні: {e}')


async def main():
  print('Бот успішно запущено з ранковим зведенням о 07:30!')
  asyncio.create_task(schedule_checker())
  asyncio.create_task(morning_briefing_task())
  await dp.start_polling(bot)


if __name__ == '__main__':
  asyncio.run(main())