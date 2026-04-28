import argparse
import csv
import os
from pathlib import Path

try:
    # When executed as `python -m src.export_plx_csv` from repo root
    from .plx_parser import parse_plx_file  # type: ignore
except Exception:
    # When executed as `python src/export_plx_csv.py`
    from plx_parser import parse_plx_file


def iter_plx_files(root_dir: Path):
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(".plx"):
                yield Path(dirpath) / filename


def export_plx_to_csv(userfiles_root: Path, output_csv: Path) -> dict:
    userfiles_root = userfiles_root.resolve()
    output_csv = output_csv.resolve()

    rows = 0
    ok = 0
    failed = 0

    output_csv.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "source_path",
        "direction_code",
        "direction",
        "faculty",
        "department",
        "year_start",
        "qualification",
        "disciplines_count",
        "error",
    ]

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for abs_path in iter_plx_files(userfiles_root):
            rows += 1
            rel_path = abs_path.relative_to(userfiles_root).as_posix()

            result = parse_plx_file(str(abs_path))
            err = result.get("error", "")

            if err:
                failed += 1
            else:
                ok += 1

            writer.writerow(
                {
                    "source_path": rel_path,
                    "direction_code": result.get("direction_code", ""),
                    "direction": result.get("direction", ""),
                    "faculty": result.get("faculty", ""),
                    "department": result.get("department", ""),
                    "year_start": result.get("year_start", ""),
                    "qualification": result.get("qualification", ""),
                    "disciplines_count": len(result.get("disciplines", []) or []),
                    "error": err,
                }
            )

    return {"scanned": rows, "ok": ok, "failed": failed, "csv": str(output_csv)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parse all .plx under userfiles/ and export summary to CSV."
    )
    parser.add_argument(
        "--userfiles",
        type=str,
        default=str(Path(__file__).resolve().parent.parent / "userfiles"),
        help="Path to userfiles directory (default: <repo>/userfiles)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(Path(__file__).resolve().parent.parent / "plx_export.csv"),
        help="Output CSV path (default: <repo>/plx_export.csv)",
    )
    args = parser.parse_args(argv)

    root = Path(args.userfiles)
    if not root.exists() or not root.is_dir():
        print(f"ERROR: userfiles dir not found: {root}")
        return 2

    stats = export_plx_to_csv(root, Path(args.out))
    print(
        f"Done. scanned={stats['scanned']} ok={stats['ok']} failed={stats['failed']} csv={stats['csv']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

