#!/usr/bin/env python3
"""Compile documents/locale/ru/LC_MESSAGES/django.po → django.mo (polib or subprocess msgfmt)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PO = ROOT / 'src/education_site/documents/locale/ru/LC_MESSAGES/django.po'
MO = PO.with_suffix('.mo')


def compile_with_polib() -> None:
    import polib

    po = polib.pofile(str(PO))
    po.save_as_mofile(str(MO))


def compile_with_msgfmt() -> None:
    msgfmt = shutil.which('msgfmt')
    if not msgfmt:
        raise RuntimeError(
            'polib is not installed and msgfmt was not found. '
            'Run: pip install polib'
        )
    subprocess.run([msgfmt, '-o', str(MO), str(PO)], check=True)


def main() -> int:
    if not PO.is_file():
        print(f'PO file not found: {PO}', file=sys.stderr)
        return 1
    try:
        compile_with_polib()
    except ImportError:
        try:
            compile_with_msgfmt()
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
    print(f'Wrote {MO}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
