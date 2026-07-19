#!/usr/bin/env python3
"""Исследование и оценка канонических имён PLX по корпусу userfiles.

Построение имени идёт только из метаданных XML (не из имени на диске и не из
атрибута ИмяФайла). Имена файлов в userfiles — эталон для eval и источник
для обучения словаря аббревиатур (build-dict).

Режимы:
  census      — частоты полей Планы / справочников
  build-dict  — собрать YAML-словарь аббр. (включая n=1)
  eval        — покрытие build_canonical_name vs имена файлов (>90%)

Примеры:
  python scripts/plx_canonical_research.py eval
  python scripts/plx_canonical_research.py build-dict
  python scripts/plx_canonical_research.py all --dir userfiles
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / 'src'
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(SRC / 'education_site'))

from plans.canonical_name import (  # noqa: E402
    build_canonical_name,
    cyrillic_abbr_guess,
    latin_abbr,
    load_abbr_dict,
    reload_abbr_dict,
)

from plx_parser import parse_plx_file  # noqa: E402

DEFAULT_DIR = REPO_ROOT / 'userfiles'
DEFAULT_DICT = SRC / 'education_site' / 'plans' / 'data' / 'plx_abbr_dict.yaml'
COVERAGE_THRESHOLD = 0.90

# Ucheb_plan_{code}_{AP}_{profile}_{form}_{term}_{fac}_{dept}_{year}[suffix].plx
_FILENAME_RE = re.compile(
    r'^Ucheb_plan_'
    r'(?P<code>\d+[.\s]\d+[.\s]\d+)_'
    r'(?P<ap>[APАП\-])_'
    r'(?P<profile>[^_]+)_'
    r'(?P<form>[OZVО])_'
    r'(?P<term>[A-Z0-9]+)_'
    r'(?P<fac>[A-Za-zА-Яа-яЁё()]+)_'
    r'(?P<dept>[A-Za-zА-Яа-яЁё]+)'
    r'(?:_(?P<dept2>[A-Za-zА-Яа-яЁё]+))?'
    r'_(?P<year>\d{4})'
    r'(?P<suffix>.*?)'
    r'(?:\.plx)?\.plx$',
    re.IGNORECASE,
)


def iter_plx_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob('*.plx') if p.is_file())


def normalize_expected_name(filename: str) -> str:
    """Нормализует эталон: срезает суффиксы после года, схлопывает .plx.plx."""
    parts = parse_filename_parts(filename)
    if not parts:
        name = Path(filename).name
        while name.lower().endswith('.plx.plx'):
            name = name[:-4]
        return name.lower()
    rebuilt = (
        f"Ucheb_plan_{parts['code']}_{parts['ap']}_{parts['profile']}_"
        f"{parts['form']}_{parts['term']}_{parts['fac']}_{parts['dept']}_{parts['year']}.plx"
    )
    return rebuilt.lower()


def parse_filename_parts(filename: str) -> dict | None:
    m = _FILENAME_RE.match(Path(filename).name)
    if not m:
        return None
    dept = m.group('dept')
    if m.group('dept2'):
        dept = f"{m.group('dept')}_{m.group('dept2')}"
    ap = m.group('ap')
    if ap in 'Аа':
        ap = 'A'
    elif ap in 'Пп':
        ap = 'P'
    form = m.group('form')
    if form == 'О':
        form = 'O'
    return {
        'code': m.group('code').replace(' ', '.'),
        'ap': ap,
        'profile': latin_abbr(m.group('profile')),
        'form': form,
        'term': m.group('term').upper(),
        'fac': latin_abbr(m.group('fac')),
        'dept': latin_abbr(dept),
        'year': m.group('year'),
    }


def cmd_census(files: list[Path]) -> int:
    plan_keys: Counter = Counter()
    program_codes: Counter = Counter()
    form_codes: Counter = Counter()
    level_codes: Counter = Counter()
    terms: Counter = Counter()
    sokr_years: Counter = Counter()
    fac_abbr_filled = 0
    dept_abbr_filled = 0
    prefix_filled = 0
    imya_eq = 0
    imya_ne = 0
    errors = 0

    for path in files:
        data = parse_plx_file(str(path))
        if data.get('error'):
            errors += 1
            continue
        # Re-parse plan attrs via light touch: use already extracted
        program_codes[data.get('program_code') or ''] += 1
        form_codes[data.get('study_form_code') or ''] += 1
        level_codes[data.get('education_level_code') or ''] += 1
        terms[data.get('term_code') or ''] += 1
        sokr_years[(data.get('is_shortened'), data.get('study_years') or '')] += 1
        if data.get('faculty_abbr_raw'):
            fac_abbr_filled += 1
        if data.get('department_abbr_raw'):
            dept_abbr_filled += 1
        if data.get('profile_prefix_raw'):
            prefix_filled += 1
        src = Path(data.get('source_filename') or '').name
        if src:
            if src.lower() == path.name.lower():
                imya_eq += 1
            else:
                imya_ne += 1

    n = len(files)
    print(f'files={n} errors={errors}')
    print('program_code:', dict(program_codes.most_common()))
    print('study_form_code:', dict(form_codes.most_common()))
    print('education_level_code:', dict(level_codes.most_common()))
    print('term_code:', dict(terms.most_common()))
    print('is_shortened,study_years:', dict(sokr_years.most_common(12)))
    print(f'faculty_abbr_raw filled: {fac_abbr_filled}/{n}')
    print(f'department_abbr_raw filled: {dept_abbr_filled}/{n}')
    print(f'profile_prefix_raw filled: {prefix_filled}/{n}')
    print(f'ИмяФайла == disk: {imya_eq}; != {imya_ne}')
    return 0


def _majority(counter: Counter) -> tuple[str, int]:
    if not counter:
        return '', 0
    item, count = counter.most_common(1)[0]
    return item, count


def cmd_build_dict(files: list[Path], out_path: Path) -> int:
    # name -> Counter(en), and separately ru candidates
    fac_en: dict[str, Counter] = defaultdict(Counter)
    dept_en: dict[str, Counter] = defaultdict(Counter)
    prof_en: dict[str, Counter] = defaultdict(Counter)
    fac_ru: dict[str, Counter] = defaultdict(Counter)
    dept_ru: dict[str, Counter] = defaultdict(Counter)
    prof_ru: dict[str, Counter] = defaultdict(Counter)
    conflicts: list[str] = []
    parsed = 0

    for path in files:
        parts = parse_filename_parts(path.name)
        if not parts:
            continue
        data = parse_plx_file(str(path))
        if data.get('error'):
            continue
        parsed += 1

        fac_name = (data.get('faculty') or '').strip()
        dept_name = (data.get('department') or '').strip()
        prof_name = (data.get('profile') or '').strip()

        if fac_name:
            fac_en[fac_name][parts['fac']] += 1
            raw = data.get('faculty_abbr_raw') or ''
            if raw:
                fac_ru[fac_name][raw] += 1
        if dept_name:
            dept_en[dept_name][parts['dept']] += 1
            raw = data.get('department_abbr_raw') or ''
            if raw:
                dept_ru[dept_name][raw] += 1
        if prof_name:
            prof_en[prof_name][parts['profile']] += 1
            raw = data.get('profile_prefix_raw') or ''
            if raw:
                prof_ru[prof_name][raw] += 1

    def emit_section(title: str, en_map: dict, ru_map: dict) -> list[str]:
        lines = [f'{title}:']
        # sort by total count desc, then name
        items = []
        for name, counter in en_map.items():
            total = sum(counter.values())
            en, en_n = _majority(counter)
            if len(counter) > 1:
                conflicts.append(
                    f'{title}/{name!r}: {dict(counter)} -> majority {en!r}'
                )
            ru, _ = _majority(ru_map.get(name, Counter()))
            if title in ('faculty', 'department'):
                guess = cyrillic_abbr_guess(en)
                if not ru:
                    ru = guess
                elif guess and latin_abbr(ru) != en:
                    # Сырое Сокращение не сходится с en — берём обратный транслит en
                    ru = guess
            items.append((total, name, en, ru))
        items.sort(key=lambda x: (-x[0], x[1].casefold()))
        if not items:
            lines.append('  {}')
            return lines
        for total, name, en, ru in items:
            key = name.replace('"', '\\"')
            lines.append(f'  # n={total}')
            lines.append(f'  "{key}":')
            lines.append(f'    en: "{en}"')
            lines.append(f'    ru: "{ru}"')
        return lines

    header = [
        '# Словарь аббревиатур PLX: полное имя → {en, ru}',
        '# Комментарий # n=N — число вхождений в корпусе userfiles.',
        '# en — токен имени файла; ru — подпись в UI (можно переопределять вручную).',
        '# Сгенерировано: scripts/plx_canonical_research.py build-dict',
        '',
    ]
    body: list[str] = []
    body.extend(emit_section('faculty', fac_en, fac_ru))
    body.append('')
    body.extend(emit_section('department', dept_en, dept_ru))
    body.append('')
    body.extend(emit_section('profile', prof_en, prof_ru))
    body.append('')

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text('\n'.join(header + body), encoding='utf-8')
    print(f'Wrote {out_path} (from {parsed} parsed files with filename parts)')
    if conflicts:
        print(f'Conflicts ({len(conflicts)}):')
        for line in conflicts[:40]:
            print(' ', line)
        if len(conflicts) > 40:
            print(f'  ... and {len(conflicts) - 40} more')
    reload_abbr_dict(str(out_path))
    return 0


def _component_mismatches(expected_parts: dict, built: str) -> list[str]:
    built_parts = parse_filename_parts(built)
    if not built_parts:
        return ['unparseable_built']
    mismatches = []
    for key in ('code', 'ap', 'profile', 'form', 'term', 'fac', 'dept', 'year'):
        if (expected_parts.get(key) or '').lower() != (built_parts.get(key) or '').lower():
            mismatches.append(
                f"{key}:{expected_parts.get(key)!r}->{built_parts.get(key)!r}"
            )
    return mismatches


def cmd_eval(files: list[Path], dict_path: Path, report_path: Path | None) -> int:
    reload_abbr_dict(str(dict_path))
    dict_data = load_abbr_dict(str(dict_path))

    total = 0
    matched = 0
    skipped_unparseable = 0
    errors = 0
    mismatch_reasons: Counter = Counter()
    failures: list[str] = []

    for path in files:
        expected_parts = parse_filename_parts(path.name)
        if not expected_parts:
            skipped_unparseable += 1
            continue
        total += 1
        data = parse_plx_file(str(path))
        if data.get('error'):
            errors += 1
            failures.append(f'{path.name}: parse error: {data["error"]}')
            continue

        built = build_canonical_name(data, dict_data=dict_data)
        exp_norm = normalize_expected_name(path.name)
        got_norm = built.lower()
        if exp_norm == got_norm:
            matched += 1
            continue

        reasons = _component_mismatches(expected_parts, built)
        for r in reasons:
            mismatch_reasons[r.split(':')[0]] += 1
        if len(failures) < 80:
            failures.append(
                f'{path.name}\n  expected: {exp_norm}\n  got:      {got_norm}\n  '
                + ', '.join(reasons)
            )

    coverage = (matched / total) if total else 0.0
    print(f'eval: matched={matched}/{total} coverage={coverage:.2%}')
    print(f'skipped_unparseable_filename={skipped_unparseable} parse_errors={errors}')
    print('mismatch by component:', dict(mismatch_reasons.most_common()))
    if failures:
        print(f'failures (showing {len(failures)}):')
        for line in failures[:25]:
            print(line)
            print('---')

    if report_path:
        lines = [
            f'# PLX canonical name eval',
            f'',
            f'- matched: {matched}/{total}',
            f'- coverage: {coverage:.2%}',
            f'- threshold: {COVERAGE_THRESHOLD:.0%}',
            f'- skipped unparseable filenames: {skipped_unparseable}',
            f'- parse errors: {errors}',
            f'',
            f'## Mismatch by component',
            f'',
        ]
        for k, v in mismatch_reasons.most_common():
            lines.append(f'- {k}: {v}')
        lines.append('')
        lines.append('## Failures')
        lines.append('')
        lines.extend(failures)
        report_path.write_text('\n'.join(lines), encoding='utf-8')
        print(f'report: {report_path}')

    if coverage <= COVERAGE_THRESHOLD:
        print(f'FAIL: coverage {coverage:.2%} <= {COVERAGE_THRESHOLD:.0%}')
        return 1
    print(f'OK: coverage {coverage:.2%} > {COVERAGE_THRESHOLD:.0%}')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'mode',
        choices=('census', 'build-dict', 'eval', 'all'),
        help='Режим работы',
    )
    parser.add_argument(
        '--dir',
        type=Path,
        default=DEFAULT_DIR,
        help=f'Каталог с .plx (по умолчанию {DEFAULT_DIR})',
    )
    parser.add_argument(
        '--dict',
        type=Path,
        default=DEFAULT_DICT,
        dest='dict_path',
        help=f'Путь к YAML-словарю (по умолчанию {DEFAULT_DICT})',
    )
    parser.add_argument(
        '--report',
        type=Path,
        default=None,
        help='Путь для markdown-отчёта eval',
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Завершить с кодом 1, если coverage ≤ 90% '
             '(без имени файла типичное покрытие ниже)',
    )
    args = parser.parse_args(argv)

    root = args.dir
    if not root.is_dir():
        print(f'Directory not found: {root}', file=sys.stderr)
        return 2

    files = iter_plx_files(root)
    if not files:
        print(f'No .plx files under {root}', file=sys.stderr)
        return 2
    print(f'Found {len(files)} .plx under {root}')

    if args.mode in ('census', 'all'):
        cmd_census(files)
    if args.mode in ('build-dict', 'all'):
        cmd_build_dict(files, args.dict_path)
    if args.mode in ('eval', 'all'):
        code = cmd_eval(files, args.dict_path, args.report)
        if args.strict:
            return code
        return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
