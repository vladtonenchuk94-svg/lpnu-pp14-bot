from bs4 import BeautifulSoup
import json
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Змінили параметри семестру на актуальні, щоб підтягувався правильний розклад
url = 'https://student.lpnu.ua/students_schedule?studygroup_abbrname=%D0%9F%D0%9F-14&semestr=1&semestrduration=1'

headers = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,'
        ' like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
}

print('Збираю розклад для збереження у файл...')
response = requests.get(url, headers=headers, verify=False)

schedule_data = {}

if response.status_code == 200:
  soup = BeautifulSoup(response.text, 'html.parser')
  days_headers = soup.find_all('span', class_='view-grouping-header')

  for header in days_headers:
    day_name = header.get_text(strip=True)
    schedule_data[day_name] = []

    elements_in_day = []
    for sibling in header.find_next_siblings():
      if (
          sibling.name == 'span'
          and 'view-grouping-header' in sibling.get('class', [])
      ):
        break
      elements_in_day.append(sibling)

    current_lesson_num = '?'

    for elem in elements_in_day:
      if elem.name == 'h3':
        current_lesson_num = elem.get_text(strip=True)
      else:
        schedules = []
        if elem.name == 'div' and 'stud_schedule' in elem.get('class', []):
          schedules.append(elem)
        else:
          schedules = elem.find_all('div', class_='stud_schedule')

        for lesson in schedules:
          contents = lesson.find_all('div', class_='group_content')
          total_contents = len(contents)

          for index, content in enumerate(contents):
            week_type = 'Загальний тиждень'
            subgroup = 'Всі підгрупи'

            current = content
            found_subgroup = False
            while current and current != lesson:
              elem_id = current.get('id', '')
              elem_classes = ' '.join(current.get('class', []))
              full_attr = f'{elem_id} {elem_classes}'.lower()

              if 'chisl' in full_attr:
                week_type = 'Чисельник'
              elif 'znam' in full_attr:
                week_type = 'Знаменник'

              if 'sub_1' in full_attr:
                subgroup = '1-а підгрупа'
                found_subgroup = True
              elif 'sub_2' in full_attr:
                subgroup = '2-а підгрупа'
                found_subgroup = True

              current = current.parent

            if not found_subgroup and total_contents == 2:
              if index == 0:
                subgroup = '1-а підгрупа'
              elif index == 1:
                subgroup = '2-а підгрупа'

            text_lines = [
                line.strip()
                for line in content.get_text(separator='\n').split('\n')
                if line.strip()
            ]
            if text_lines:
              subject = text_lines[0]
              details = (
                  text_lines[1] if len(text_lines) > 1 else 'Деталі відсутні'
              )

              # Додаємо пару у структуру дня без жорстких костилів
              schedule_data[day_name].append({
                  'lesson_num': current_lesson_num,
                  'week_type': week_type,
                  'subgroup': subgroup,
                  'subject': subject,
                  'details': details,
              })

  # Зберігаємо оновлену інформацію у файл
  with open('schedule.json', 'w', encoding='utf-8') as f:
    json.dump(schedule_data, f, ensure_ascii=False, indent=4)

  print('Успіх! Актуальний розклад збережено у файл "schedule.json".')
else:
  print('Помилка завантаження:', response.status_code)