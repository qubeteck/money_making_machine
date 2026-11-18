"""Create a consistent SQLite backup while the app is running.

Usage:
    python scripts/backup_db.py

The script uses SQLite's online backup API so WAL content is included. Safe to
run from cron while the bot is writing to the database. The scheduler also runs
this automatically when BACKUP_ENABLED=true.
"""

from __future__ import annotations

from app.config import get_settings
from app.services.backup import backup_sqlite


def main() -> None:
    target = backup_sqlite(get_settings().backup_keep_days)
    print(target)


if __name__ == "__main__":
    main()
