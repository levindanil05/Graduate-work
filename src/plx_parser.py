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


_MSDATA_NS = 'urn:schemas-microsoft-com:xml-msdata'
_ROW_ORDER_ATTR = f'{{{_MSDATA_NS}}}rowOrder'


def _nsmap_from_root(root: ET.Element) -> dict:
    """
    Возвращает namespace map для поиска, извлекая namespace из тега корня
    вида {namespace}MMISDB или без namespace.
    """
    if root.tag.startswith("{") and "}" in root.tag:
        ns_uri = root.tag.split("}", 1)[0][1:]
        return {"ds": ns_uri}
    return {"ds": "http://tempuri.org/dsMMISDB.xsd"}


def _row_order(element: ET.Element) -> int:
    raw = element.get(_ROW_ORDER_ATTR) or element.get('rowOrder') or '0'
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _extract_profiles(root: ET.Element, ns: dict) -> list[str]:
    """Профили ООП с Используется=true, по возрастанию msdata:rowOrder."""
    candidates: list[tuple[int, str]] = []
    for oop in root.findall('.//ds:ООП', ns):
        if (oop.get('Используется') or '').strip().lower() != 'true':
            continue
        name = (oop.get('Название') or '').strip()
        if not name:
            continue
        candidates.append((_row_order(oop), name))
    candidates.sort(key=lambda item: item[0])
    return [name for _, name in candidates]


def _empty_result(**extra) -> dict:
    return {
        'direction': '',
        'direction_code': '',
        'faculty': '',
        'faculty_code': '',
        'department': '',
        'department_code': '',
        'year_start': '',
        'qualification': '',
        'profiles': [],
        'profile': '',
        'disciplines': [],
        **extra,
    }


def parse_plx_file(file) -> dict:
    """
    Парсит PLX файл и возвращает словарь с данными

    Args:
        file: файл (путь или UploadedFile)

    Returns:
        dict с ключами: direction, faculty, department, year_start, qualification,
        profiles, profile, disciplines
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

        result = _empty_result()

        # === Извлекаем данные ООП (образовательная программа) ===
        oop = root.find('.//ds:ООП', ns)
        if oop is not None:
            result['direction_code'] = oop.get('Шифр', '')
            result['direction'] = oop.get('Название', '')
            result['qualification'] = oop.get('Квалификация', '')

        profiles = _extract_profiles(root, ns)
        result['profiles'] = profiles
        result['profile'] = profiles[0] if profiles else ''

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
        return _empty_result(error=str(e))
