# plx_parser.py
import xml.etree.ElementTree as ET
from django.core.files.uploadedfile import UploadedFile
import io


def parse_plx_file(file) -> dict:
    """
    Парсит PLX файл и возвращает словарь с данными

    Args:
        file: файл (путь или UploadedFile)

    Returns:
        dict с ключами: direction, faculty, department, year_start, qualifications
    """
    try:
        # Читаем содержимое файла
        if isinstance(file, UploadedFile):
            content = file.read()
            file.seek(0)  # Сбрасываем указатель
        else:
            with open(file, 'rb') as f:
                content = f.read()

        # Парсим XML (PLX это XML с кодировкой utf-16)
        root = ET.fromstring(content.decode('utf-16'))

        # Находим namespace
        ns = {'ds': 'http://tempuri.org/dsMMISDB.xsd'}

        result = {
            'direction': '',
            'direction_code': '',
            'faculty': '',
            'department': '',
            'department_code': '',
            'year_start': '',
            'qualification': '',
            'disciplines': []
        }

        # === Извлекаем данные ООП (образовательная программа) ===
        oop = root.find('.//ds:ООП', ns)
        if oop is not None:
            result['direction_code'] = oop.get('Шифр', '')
            result['direction'] = oop.get('Название', '')
            result['qualification'] = oop.get('Квалификация', '')

        # === Извлекаем данные Плана ===
        plan = root.find('.//ds:Планы', ns)
        if plan is not None:
            result['year_start'] = plan.get('ГодНачалаПодготовки', '')
            result['department_code'] = plan.get('КодПрофКафедры', '')
            result['faculty_code'] = plan.get('КодФакультета', '')

        # === Извлекаем название факультета ===
        faculties = root.findall('.//ds:Факультеты', ns)
        for fac in faculties:
            fac_code = fac.get('Код', '')
            if fac_code == result.get('faculty_code', ''):
                result['faculty'] = fac.get('Факультет', '')
                break

        # === Извлекаем название кафедры ===
        departments = root.findall('.//ds:Кафедры', ns)
        for dept in departments:
            dept_code = dept.get('Код', '')
            if dept_code == result.get('department_code', ''):
                result['department'] = dept.get('Название', '')
                break

        # === Извлекаем дисциплины ===
        plan_rows = root.findall('.//ds:ПланыСтроки', ns)
        for row in plan_rows:
            discipline = row.get('Дисциплина', '')
            code = row.get('ДисциплинаКод', '')
            credits = row.get('ТрудоемкостьКредитов', '')

            if discipline and code:
                result['disciplines'].append({
                    'name': discipline,
                    'code': code,
                    'credits': credits
                })

        return result

    except Exception as e:
        print(f"Ошибка при парсинге PLX: {e}")
        return {
            'direction': '',
            'direction_code': '',
            'faculty': '',
            'department': '',
            'year_start': '',
            'qualification': '',
            'disciplines': [],
            'error': str(e)
        }