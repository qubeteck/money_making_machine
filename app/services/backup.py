from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import BASE_DIR, get_settings, normalize_database_url


def sqlite_path(database_url: str) -> Path:
    normalized = normalize_database_url(database_url)
    if not normalized.startswith("sqlite:///"):
        raise RuntimeError("Automatic backups only support SQLite DATABASE_URL values.")
    if normalized.endswith(":memory:"):
        raise RuntimeError("Cannot back up an in-memory SQLite database.")
    return Path(normalized.removeprefix("sqlite:///"))


def backup_sqlite(keep_days: int = 14) -> Path:
    """Create a consistent online SQLite backup and prune old copies."""
    source = sqlite_path(get_settings().database_url)
    if not source.exists():
        raise FileNotFoundError(f"Database not found: {source}")

    target_dir = BASE_DIR / "data" / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = target_dir / f"money_machine_{stamp}.db"

    source_db = sqlite3.connect(source)
    target_db = sqlite3.connect(target)
    try:
        source_db.backup(target_db)
    finally:
        target_db.close()
        source_db.close()

    if keep_days > 0:
        cutoff = time.time() - keep_days * 86400
        for old_backup in target_dir.glob("money_machine_*.db"):
            try:
                if old_backup.stat().st_mtime < cutoff:
                    old_backup.unlink()
            except OSError:
                # A stale backup should never take down the bot.
                continue

    return target
