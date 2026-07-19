from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from django.core.files.uploadedfile import UploadedFile

# plx_parser.py


_XML_ENCODING_RE = re.compile(br'encoding=[\'"](?P<enc>[^\'"]+)[\'"]', re.IGNORECASE)

_FORM_CODE_TO_EN = {
    '1': 'O',
    '2': 'Z',
    '3': 'V',
}

_PROGRAM_CODE_TO_KIND = {
    '3': 'A',
    '4': 'P',
}

# Профиль / программа в Титул (в кавычках или до конца строки; ru/en)
_TITLE_PROFILE_RE = re.compile(
    r'(?:'
    r'(?:по\s+)?профил\w*(?:\s+подготовки)?|Программа|Profile|Program'
    r')\s*[-–—:]?\s*'
    r'(?:[«"\']([^»"\']+)[»"\']|([^\r\n]+))',
    re.IGNORECASE,
)

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


def _extract_used_profiles(root: ET.Element, ns: dict) -> list[dict]:
    """Профили ООП с Используется=true, по возрастанию msdata:rowOrder."""
    candidates: list[tuple[int, dict]] = []
    for oop in root.findall('.//ds:ООП', ns):
        if (oop.get('Используется') or '').strip().lower() != 'true':
            continue
        name = (oop.get('Название') or '').strip()
        if not name:
            continue
        candidates.append((
            _row_order(oop),
            {
                'name': name,
                'prefix': (oop.get('Префикс') or '').strip(),
            },
        ))
    candidates.sort(key=lambda item: item[0])
    return [row for _, row in candidates]


def _profile_from_title(title: str) -> str:
    if not title:
        return ''
    m = _TITLE_PROFILE_RE.search(title)
    if not m:
        return ''
    return (m.group(1) or m.group(2) or '').strip()


def _oop_by_code(root: ET.Element, ns: dict, code: str) -> ET.Element | None:
    if not code:
        return None
    for oop in root.findall('.//ds:ООП', ns):
        if (oop.get('Код') or '').strip() == code:
            return oop
    return None


def _find_direction_oop(root: ET.Element, ns: dict) -> ET.Element | None:
    """Корневое направление: ООП с шифром и Используется!=true, иначе первый с шифром."""
    fallback = None
    for oop in root.findall('.//ds:ООП', ns):
        code = (oop.get('Шифр') or '').strip()
        if not code:
            continue
        used = (oop.get('Используется') or '').strip().lower()
        if used != 'true':
            return oop
        if fallback is None:
            fallback = oop
    return fallback


def _lookup_by_code(elements, code: str, code_attr: str = 'Код'):
    for el in elements:
        if el.get(code_attr, '') == code:
            return el
    return None


def _bool_attr(raw: str | None) -> bool | None:
    if raw is None or raw == '':
        return None
    return raw.strip().lower() == 'true'


def _derive_term_code(is_shortened: bool | None, study_years: str) -> str:
    if is_shortened is False:
        return 'NOR'
    if is_shortened is not True:
        return ''
    years = (study_years or '').strip()
    if years == '2':
        return '2VO'
    return 'SOKR'


def _derive_program_kind(
    program_code: str,
    program_name: str,
    education_plan_kind: str,
    direction_code: str,
    title: str = '',
    oop_program_code: str = '',
) -> str:
    kind = education_plan_kind.casefold()
    if 'специалитет' in kind:
        return '-'
    parts = (direction_code or '').split('.')
    if len(parts) >= 2 and parts[1] == '05':
        return '-'

    for code in ((program_code or '').strip(), (oop_program_code or '').strip()):
        mapped = _PROGRAM_CODE_TO_KIND.get(code)
        if mapped:
            return mapped

    blob = f'{program_name} {title}'.casefold()
    if 'прикладн' in blob:
        return 'P'
    if 'академич' in blob:
        return 'A'
    return ''


def _empty_result(**extra) -> dict:
    return {
        'direction': '',
        'direction_code': '',
        'faculty': '',
        'faculty_code': '',
        'faculty_abbr_raw': '',
        'department': '',
        'department_code': '',
        'department_abbr_raw': '',
        'year_start': '',
        'qualification': '',
        'profiles': [],
        'profile': '',
        'profile_prefix_raw': '',
        'study_form_code': '',
        'study_form': '',
        'study_form_en': '',
        'program_code': '',
        'program_name': '',
        'program_kind': '',
        'is_shortened': None,
        'study_years': '',
        'term_code': '',
        'education_level_code': '',
        'education_level': '',
        'education_plan_kind': '',
        'title': '',
        'source_filename': '',
        'disciplines': [],
        **extra,
    }


def parse_plx_file(file) -> dict:
    """
    Парсит PLX файл и возвращает словарь с данными

    Args:
        file: файл (путь или UploadedFile)

    Returns:
        dict с метаданными плана (направление, форма, срок, подразделения, профили, …)
    """
    try:
        if isinstance(file, UploadedFile):
            content = file.read()
            file.seek(0)
        else:
            with open(file, 'rb') as f:
                content = f.read()

        xml_text = _decode_xml_bytes(content)
        root = ET.fromstring(xml_text)
        ns = _nsmap_from_root(root)

        result = _empty_result()

        oop = _find_direction_oop(root, ns)
        oop_program_code = ''
        if oop is not None:
            result['direction_code'] = (oop.get('Шифр') or '').strip()
            result['direction'] = (oop.get('Название') or '').strip()
            result['qualification'] = (oop.get('Квалификация') or '').strip()
            oop_program_code = (oop.get('ПрограммаПодготовки') or '').strip()

        plan = root.find('.//ds:Планы', ns)
        if plan is not None:
            result['year_start'] = (plan.get('ГодНачалаПодготовки') or '').strip()
            result['department_code'] = (plan.get('КодПрофКафедры') or '').strip()
            result['faculty_code'] = (plan.get('КодФакультета') or '').strip()
            result['study_form_code'] = (plan.get('КодФормыОбучения') or '').strip()
            result['program_code'] = (plan.get('КодПрограммы') or '').strip()
            result['education_level_code'] = (plan.get('КодУровняОбразования') or '').strip()
            result['study_years'] = (plan.get('СрокОбучения') or '').strip()
            result['is_shortened'] = _bool_attr(plan.get('Сокращённое'))
            result['title'] = (plan.get('Титул') or '').strip()
            # Только для исследования/отчётов; в build_canonical_name не используется.
            result['source_filename'] = (plan.get('ИмяФайла') or '').strip()
            plan_qual = (plan.get('Квалификация') or '').strip()
            if plan_qual and not result['qualification'].isalpha():
                # В ООП часто код («2»), в Планы — текст («бакалавр»)
                if any(ch.isalpha() for ch in plan_qual):
                    result['qualification'] = plan_qual

        # 1) ООП с Используется=true; 2) КодАктивногоООП; 3) Титул
        used_profiles = _extract_used_profiles(root, ns)
        if used_profiles:
            result['profiles'] = [row['name'] for row in used_profiles]
            result['profile'] = used_profiles[0]['name']
            result['profile_prefix_raw'] = used_profiles[0]['prefix']
        else:
            active_code = ''
            if plan is not None:
                active_code = (plan.get('КодАктивногоООП') or '').strip()
            active_oop = _oop_by_code(root, ns, active_code)
            if active_oop is not None:
                active_name = (active_oop.get('Название') or '').strip()
                if active_name and active_name.casefold() != result['direction'].casefold():
                    result['profile'] = active_name
                    result['profiles'] = [active_name]
                    result['profile_prefix_raw'] = (active_oop.get('Префикс') or '').strip()
            if not result['profile']:
                from_title = _profile_from_title(result['title'])
                if from_title:
                    result['profile'] = from_title
                    result['profiles'] = [from_title]

        form_el = _lookup_by_code(
            root.findall('.//ds:ФормаОбучения', ns),
            result['study_form_code'],
        )
        if form_el is not None:
            result['study_form'] = (form_el.get('ФормаОбучения') or '').strip()
        result['study_form_en'] = _FORM_CODE_TO_EN.get(result['study_form_code'], '')

        prog_el = _lookup_by_code(
            root.findall('.//ds:ПрограммаПодготовки', ns),
            result['program_code'],
        )
        if prog_el is not None:
            result['program_name'] = (prog_el.get('Наименование') or '').strip()

        level_el = _lookup_by_code(
            root.findall('.//ds:Уровень_образования', ns),
            result['education_level_code'],
            code_attr='Код_записи',
        )
        if level_el is not None:
            result['education_level'] = (level_el.get('Уровень') or '').strip()
            result['education_plan_kind'] = (level_el.get('ВидПлана') or '').strip()

        result['term_code'] = _derive_term_code(result['is_shortened'], result['study_years'])
        # Имя файла (диск / ИмяФайла) для построения вида A/P не используем.
        result['program_kind'] = _derive_program_kind(
            result['program_code'],
            result['program_name'],
            result['education_plan_kind'],
            result['direction_code'],
            title=result['title'],
            oop_program_code=oop_program_code,
        )

        fac = _lookup_by_code(
            root.findall('.//ds:Факультеты', ns),
            result['faculty_code'],
        )
        if fac is not None:
            result['faculty'] = (fac.get('Факультет') or '').strip()
            result['faculty_abbr_raw'] = (
                (fac.get('Сокращение') or '').strip()
                or (fac.get('Псевдоним') or '').strip()
            )

        dept = _lookup_by_code(
            root.findall('.//ds:Кафедры', ns),
            result['department_code'],
        )
        if dept is not None:
            result['department'] = (dept.get('Название') or '').strip()
            result['department_abbr_raw'] = (dept.get('Сокращение') or '').strip()

        for row in root.findall('.//ds:ПланыСтроки', ns):
            discipline = row.get('Дисциплина', '')
            code = row.get('ДисциплинаКод', '')
            credits = row.get('ТрудоемкостьКредитов', '')
            if discipline and code:
                result['disciplines'].append({
                    'name': discipline,
                    'code': code,
                    'credits': credits,
                })

        return result

    except Exception as e:
        return _empty_result(error=str(e))
