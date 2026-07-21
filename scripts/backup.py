"""Бэкап SQLite и каталога Chroma.

Запуск: python -m scripts.backup
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings

BASE_DIR = Path(__file__).resolve().parent.parent
BACKUP_ROOT = BASE_DIR / "data" / "backups"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_sqlite(db_url: str, dest_dir: Path) -> Path | None:
    if not db_url.startswith("sqlite"):
        print(f"пропуск SQLite backup: не sqlite URL ({db_url})")
        return None
    # sqlite:////app/data/x.db или sqlite:///./regiobuild.db
    raw_path = db_url.split("sqlite:///")[-1]
    if raw_path.startswith("/"):
        db_path = Path(raw_path)
    else:
        db_path = (BASE_DIR / raw_path).resolve()
    if not db_path.exists():
        print(f"БД не найдена: {db_path}")
        return None

    dest = dest_dir / f"{db_path.stem}.db"
    # online backup API — безопаснее чем copy на живой файл
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    print(f"SQLite → {dest}")
    return dest


def backup_chroma(chroma_dir: Path, dest_dir: Path) -> Path | None:
    if not chroma_dir.exists():
        print(f"Chroma не найдена: {chroma_dir}")
        return None
    dest = dest_dir / "chroma"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(chroma_dir, dest)
    print(f"Chroma → {dest}")
    return dest


def main() -> int:
    settings = get_settings()
    stamp = _timestamp()
    dest_dir = BACKUP_ROOT / stamp
    dest_dir.mkdir(parents=True, exist_ok=True)

    db_ok = backup_sqlite(settings.database_url, dest_dir)
    chroma_ok = backup_chroma(Path(settings.chroma_persist_dir), dest_dir)

    if not db_ok and not chroma_ok:
        print("backup: ничего не скопировано", file=sys.stderr)
        return 1

    print(f"backup: OK → {dest_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
