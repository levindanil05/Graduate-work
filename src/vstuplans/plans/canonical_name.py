from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DICT_PATH = Path(__file__).resolve().parent / 'data' / 'plx_abbr_dict.yaml'

_STOP_WORDS = frozenset({
    'и', 'в', 'на', 'по', 'с', 'со', 'для', 'из', 'к', 'о', 'об', 'от', 'у', 'а',
    'the', 'of', 'and',
})

_CYRILLIC_RE = re.compile(r'[А-Яа-яЁё]')
_WORD_RE = re.compile(r'[A-Za-zА-Яа-яЁё0-9]+')

_TRANSLIT_TABLE = str.maketrans({
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
    'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
    'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
    'Ф': 'F', 'Х': 'H', 'Ц': 'C', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
    'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
})


def transliterate_ru(text: str) -> str:
    """Кириллица → латиница по стабильному правилу."""
    return (text or '').translate(_TRANSLIT_TABLE)


def normalize_name_key(name: str) -> str:
    return ' '.join((name or '').casefold().split())


def _has_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(text or ''))


def latin_abbr(raw: str) -> str:
    """Нормализует аббревиатуру в латинский токен для имени файла."""
    text = (raw or '').strip()
    if not text:
        return ''
    if _has_cyrillic(text):
        text = transliterate_ru(text)
    # Убрать пробелы/точки внутри аббр., сохранить дефис
    text = re.sub(r'[\s.]+', '', text)
    return text


# E→Э: в аббр. факультетов/кафедр типично ФЭВТ/ФЭУ, не ФеВТ.
_REVERSE_LETTER = {
    'A': 'А', 'B': 'Б', 'V': 'В', 'G': 'Г', 'D': 'Д', 'E': 'Э',
    'Z': 'З', 'I': 'И', 'Y': 'Й', 'K': 'К', 'L': 'Л', 'M': 'М',
    'N': 'Н', 'O': 'О', 'P': 'П', 'R': 'Р', 'S': 'С', 'T': 'Т',
    'U': 'У', 'F': 'Ф', 'H': 'Х', 'C': 'Ц',
}


def cyrillic_abbr_guess(en: str) -> str:
    """Грубая кириллическая форма латинской аббр. для начального ru в словаре."""
    if not en or _has_cyrillic(en):
        return en or ''
    out: list[str] = []
    for ch in en:
        if ch == '-' or ch.isdigit() or ch in '()':
            out.append(ch)
        elif ch.upper() in _REVERSE_LETTER:
            mapped = _REVERSE_LETTER[ch.upper()]
            out.append(mapped if ch.isupper() else mapped.casefold())
        else:
            return ''  # неоднозначно (Zh/Ch/…) — лучше оставить пустым
    return ''.join(out)


def abbreviate_from_name(full_name: str) -> str:
    """Прямолинейная эвристика: инициалы значимых слов + транслит."""
    words = _WORD_RE.findall(full_name or '')
    parts: list[str] = []
    for word in words:
        if word.casefold() in _STOP_WORDS:
            continue
        if word.isupper() and len(word) > 1:
            parts.append(latin_abbr(word))
            continue
        first = word[0]
        parts.append(latin_abbr(first.upper() if first.isalpha() else first))
    return ''.join(parts)


def _register_form(
    section_map: dict[str, dict[str, str]],
    form: str,
    en: str,
    ru: str,
) -> None:
    key = normalize_name_key(form)
    if not key:
        return
    section_map[key] = {'en': en, 'ru': ru}


def _load_section_entries(section_data) -> dict[str, dict[str, str]]:
    """
    Разворачивает секцию словаря в lookup по нормализованной форме.
    Поддерживает:
      - list: [{en, ru, forms: [...]}, ...]  (новый формат)
      - dict: {form: {en, ru}, ...}          (старый плоский формат)
    """
    out: dict[str, dict[str, str]] = {}
    if isinstance(section_data, list):
        for entity in section_data:
            if not isinstance(entity, dict):
                continue
            en = str(entity.get('en') or '').strip()
            ru = str(entity.get('ru') or '').strip()
            forms = entity.get('forms') or []
            if not isinstance(forms, list):
                continue
            for form in forms:
                _register_form(out, str(form), en, ru)
        return out

    if isinstance(section_data, dict):
        for key, value in section_data.items():
            if not isinstance(value, dict):
                continue
            en = str(value.get('en') or '').strip()
            ru = str(value.get('ru') or '').strip()
            forms = value.get('forms')
            if isinstance(forms, list) and forms:
                for form in forms:
                    _register_form(out, str(form), en, ru)
            else:
                _register_form(out, str(key), en, ru)
    return out


@lru_cache(maxsize=1)
def load_abbr_dict(path: str | None = None) -> dict[str, dict[str, dict[str, str]]]:
    """
    Загружает YAML-словарь.
    Возвращает {section: {normalized_full_name: {en, ru}}}.
    """
    dict_path = Path(path) if path else _DICT_PATH
    if not dict_path.is_file():
        return {'faculty': {}, 'department': {}, 'profile': {}}

    with dict_path.open(encoding='utf-8') as fh:
        raw = yaml.safe_load(fh) or {}

    result: dict[str, dict[str, dict[str, str]]] = {
        'faculty': {},
        'department': {},
        'profile': {},
    }
    for section in result:
        result[section] = _load_section_entries(raw.get(section) or {})
    return result


def reload_abbr_dict(path: str | None = None) -> dict[str, dict[str, dict[str, str]]]:
    load_abbr_dict.cache_clear()
    return load_abbr_dict(path)


def resolve_abbr(
    section: str,
    full_name: str,
    raw_abbr: str = '',
    *,
    dict_data: dict | None = None,
) -> dict[str, str]:
    """
    Единый резолвер для faculty / department / profile.
    Возвращает {en, ru}.
    """
    data = dict_data if dict_data is not None else load_abbr_dict()
    section_map = data.get(section) or {}
    entry = section_map.get(normalize_name_key(full_name), {})

    raw = (raw_abbr or '').strip()
    raw_en = latin_abbr(raw) if raw else ''
    raw_ru = raw if raw and _has_cyrillic(raw) else ''

    # YAML переопределяет сырое поле (правка en/ru должна сразу применяться).
    en = (entry.get('en') or '') or raw_en or abbreviate_from_name(full_name)
    ru = (entry.get('ru') or '') or raw_ru or (full_name or '').strip()
    return {'en': en, 'ru': ru}


def enrich_meta_with_abbrs(meta: dict[str, Any], *, dict_data: dict | None = None) -> dict[str, Any]:
    """Добавляет пары *_abbr_en / *_abbr_ru в копию meta."""
    out = dict(meta)
    fac = resolve_abbr(
        'faculty',
        out.get('faculty', ''),
        out.get('faculty_abbr_raw', ''),
        dict_data=dict_data,
    )
    dept = resolve_abbr(
        'department',
        out.get('department', ''),
        out.get('department_abbr_raw', ''),
        dict_data=dict_data,
    )
    prof = resolve_abbr(
        'profile',
        out.get('profile', ''),
        out.get('profile_prefix_raw', ''),
        dict_data=dict_data,
    )
    out['faculty_abbr_en'] = fac['en']
    out['faculty_abbr_ru'] = fac['ru']
    out['department_abbr_en'] = dept['en']
    out['department_abbr_ru'] = dept['ru']
    out['profile_abbr_en'] = prof['en']
    out['profile_abbr_ru'] = prof['ru']
    return out


def build_canonical_name(meta: dict[str, Any], *, dict_data: dict | None = None) -> str:
    """
    Собирает каноническое имя файла из метаданных (токены en).
    Ucheb_plan_{code}_{A|P|-}_{profile}_{O|Z|V}_{NOR|SOKR|2VO}_{fac}_{dept}_{year}.plx
    """
    enriched = enrich_meta_with_abbrs(meta, dict_data=dict_data)

    code = (enriched.get('direction_code') or '').strip()
    # Если вида нет в метаданных — A (в корпусе большинство таких планов академические).
    kind = (enriched.get('program_kind') or '').strip() or 'A'
    profile = (enriched.get('profile_abbr_en') or '').strip()
    form = (enriched.get('study_form_en') or '').strip()
    term = (enriched.get('term_code') or '').strip()
    faculty = (enriched.get('faculty_abbr_en') or '').strip()
    department = (enriched.get('department_abbr_en') or '').strip()
    year = str(enriched.get('year_start') or '').strip()

    parts = [
        'Ucheb_plan',
        code,
        kind,
        profile,
        form,
        term,
        faculty,
        department,
        year,
    ]
    if not all([code, profile, form, term, faculty, department, year]):
        # Собираем как есть — eval покажет провалы по компонентам
        pass
    return '_'.join(parts) + '.plx'


def display_abbr(section: str, full_name: str, abbr_ru: str = '', abbr_en: str = '') -> str:
    """Подпись для UI: ru, иначе полное имя (не en)."""
    if abbr_ru:
        return abbr_ru
    if full_name:
        return full_name
    return abbr_en or ''
