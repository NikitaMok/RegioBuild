"""Восстановление SQLite из каталога/архива scripts.backup.

Пример:
  python -m scripts.restore_backup data/backups/20260723T120000Z.tar.gz
  python -m scripts.restore_backup data/backups/20260723T120000Z --force
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

from app.core.config import get_settings

BASE_DIR = Path(__file__).resolve().parent.parent


def _db_path_from_url(db_url: str) -> Path:
    raw_path = db_url.split("sqlite:///")[-1]
    if raw_path.startswith("/"):
        return Path(raw_path)
    return (BASE_DIR / raw_path).resolve()


def _extract_source(source: Path, tmp: Path) -> Path:
    if source.is_dir():
        return source
    if source.suffixes[-2:] == [".tar", ".gz"] or source.name.endswith(".tar.gz"):
        with tarfile.open(source, "r:gz") as tar:
            tar.extractall(tmp)
        kids = [p for p in tmp.iterdir() if p.is_dir()]
        if len(kids) == 1:
            return kids[0]
        return tmp
    raise SystemExit(f"непонятный источник бэкапа: {source}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore RegioBuild SQLite backup")
    parser.add_argument("source", help="Путь к .tar.gz или каталогу бэкапа")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Перезаписать текущую БД без подтверждения",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url.startswith("sqlite"):
        print("restore: сейчас только sqlite", file=sys.stderr)
        return 1

    source = Path(args.source)
    if not source.exists():
        print(f"нет файла: {source}", file=sys.stderr)
        return 1

    db_path = _db_path_from_url(settings.database_url)
    with tempfile.TemporaryDirectory() as tmp_name:
        root = _extract_source(source, Path(tmp_name))
        candidates = list(root.glob("*.db"))
        if not candidates:
            print("в бэкапе нет .db", file=sys.stderr)
            return 1
        backup_db = candidates[0]
        if db_path.exists() and not args.force:
            print(f"БД уже есть: {db_path}. Укажите --force.", file=sys.stderr)
            return 1
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            shutil.copy2(db_path, db_path.with_suffix(".db.bak"))
        shutil.copy2(backup_db, db_path)
        print(f"restore: OK → {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
