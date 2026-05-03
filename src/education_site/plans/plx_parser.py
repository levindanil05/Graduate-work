from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from django.core.files.uploadedfile import UploadedFile

# plx_parser.py


_XML_ENCODING_RE = re.compile(br'encoding=[\'"](?P<enc>[^\'"]+)[\'"]', re.IGNORECASE)


def _decode_xml_bytes(content: bytes) -> str:
    """
    Декодирует XML-байты, пытаясь корректно определить кодировку.
    PLX часто бывает UTF-16 (LE/BE) с BOM, но на практике встречаются и другие варианты.
    """
    m = _XML_ENCODING_RE.search(content[:200])
    if m:
        declared = m.group("enc").decode("ascii", errors="ignore").strip()
        if declared:
            try:
                return content.decode(declared)
            except Exception:
                pass

    # BOM-aware: python сам поймёт utf-16/utf-8-sig при наличии BOM
    for enc in ("utf-16", "utf-8-sig", "utf-16-le", "utf-16-be", "utf-8", "cp1251"):
        try:
            return content.decode(enc)
        except Exception:
            continue

    # Последняя попытка — без падения
    return content.decode("utf-8", errors="replace")


def _nsmap_from_root(root: ET.Element) -> dict:
    """
    Возвращает namespace map для поиска, извлекая namespace из тега корня
    вида {namespace}MMISDB или без namespace.
    """
    if root.tag.startswith("{") and "}" in root.tag:
        ns_uri = root.tag.split("}", 1)[0][1:]
        return {"ds": ns_uri}
    return {"ds": "http://tempuri.org/dsMMISDB.xsd"}


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

        xml_text = _decode_xml_bytes(content)
        root = ET.fromstring(xml_text)
        ns = _nsmap_from_root(root)

        result = {
            'direction': '',
            'direction_code': '',
            'faculty': '',
            'faculty_code': '',
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
        return {
            'direction': '',
            'direction_code': '',
            'faculty': '',
            'faculty_code': '',
            'department': '',
            'department_code': '',
            'year_start': '',
            'qualification': '',
            'disciplines': [],
            'error': str(e)
        }
