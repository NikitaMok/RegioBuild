"""Бэкап SQLite (и при наличии — Chroma) с ротацией.

Запуск:
  python -m scripts.backup
  python -m scripts.backup --keep 8
  python -m scripts.backup --root /app/data/backups --keep 8
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BACKUP_ROOT = BASE_DIR / "data" / "backups"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_sqlite(db_url: str, dest_dir: Path) -> Path | None:
    if not db_url.startswith("sqlite"):
        print(f"пропуск SQLite backup: не sqlite URL ({db_url})")
        return None
    raw_path = db_url.split("sqlite:///")[-1]
    if raw_path.startswith("/"):
        db_path = Path(raw_path)
    else:
        db_path = (BASE_DIR / raw_path).resolve()
    if not db_path.exists():
        print(f"БД не найдена: {db_path}")
        return None

    dest = dest_dir / f"{db_path.stem}.db"
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
        print(f"Chroma не найдена (ок для Qdrant Cloud): {chroma_dir}")
        return None
    dest = dest_dir / "chroma"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(chroma_dir, dest)
    print(f"Chroma → {dest}")
    return dest


def backup_llm_cache(data_dir: Path, dest_dir: Path) -> Path | None:
    cache = data_dir / "llm_cache.json"
    if not cache.exists():
        return None
    dest = dest_dir / "llm_cache.json"
    shutil.copy2(cache, dest)
    print(f"LLM cache → {dest}")
    return dest


def pack_archive(dest_dir: Path) -> Path:
    archive = dest_dir.with_suffix(".tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(dest_dir, arcname=dest_dir.name)
    print(f"архив → {archive}")
    return archive


def rotate(backup_root: Path, keep: int) -> None:
    if keep <= 0:
        return
    archives = sorted(backup_root.glob("*.tar.gz"), reverse=True)
    dirs = sorted(
        [p for p in backup_root.iterdir() if p.is_dir()],
        reverse=True,
    )
    for old in archives[keep:]:
        old.unlink(missing_ok=True)
        print(f"удалён старый архив {old.name}")
    for old in dirs[keep:]:
        shutil.rmtree(old, ignore_errors=True)
        print(f"удалён старый каталог {old.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Бэкап RegioBuild")
    parser.add_argument(
        "--root",
        default="",
        help="Каталог бэкапов (по умолчанию data/backups или BACKUP_ROOT)",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=0,
        help="Сколько последних копий хранить (0 = не чистить; иначе из BACKUP_KEEP/8)",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Не упаковывать в tar.gz",
    )
    args = parser.parse_args()

    settings = get_settings()
    import os

    backup_root = Path(
        args.root
        or os.environ.get("BACKUP_ROOT")
        or str(DEFAULT_BACKUP_ROOT)
    )
    keep = args.keep or int(os.environ.get("BACKUP_KEEP") or "8")

    stamp = _timestamp()
    dest_dir = backup_root / stamp
    dest_dir.mkdir(parents=True, exist_ok=True)

    db_ok = backup_sqlite(settings.database_url, dest_dir)
    chroma_ok = backup_chroma(Path(settings.chroma_persist_dir), dest_dir)

    data_dir = Path("/app/data")
    if not data_dir.exists():
        data_dir = BASE_DIR / "data"
    cache_ok = backup_llm_cache(data_dir, dest_dir)

    if not db_ok and not chroma_ok and not cache_ok:
        print("backup: ничего не скопировано", file=sys.stderr)
        return 1

    if not args.no_archive:
        pack_archive(dest_dir)
        shutil.rmtree(dest_dir, ignore_errors=True)

    rotate(backup_root, keep)
    print(f"backup: OK → {backup_root} (keep={keep})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
