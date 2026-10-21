import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CleanupResult:
    path: str
    ok: bool
    detail: str


def attachment_dir(signal_root: Path) -> Path:
    return signal_root / "attachments"


def account_db_paths(signal_data_dir: Path) -> list[Path]:
    return sorted(signal_data_dir.glob("*.d/account.db"))


def purge_attachments(signal_root: Path) -> list[str]:
    removed: list[str] = []
    attachments_path = attachment_dir(signal_root)
    if not attachments_path.exists():
        return removed

    for item in attachments_path.iterdir():
        if item.is_dir():
            for nested in sorted(item.rglob("*"), reverse=True):
                if nested.is_file():
                    nested.unlink()
                elif nested.is_dir():
                    nested.rmdir()
            item.rmdir()
        else:
            item.unlink()
        removed.append(str(item))
    return removed


def purge_message_databases(signal_data_dir: Path) -> list[CleanupResult]:
    results: list[CleanupResult] = []
    for db_path in account_db_paths(signal_data_dir):
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM message_send_log")
                cursor.execute("DELETE FROM message_send_log_content")
                conn.commit()
                cursor.execute("VACUUM")
            results.append(CleanupResult(str(db_path), True, "cleared"))
        except Exception as exc:
            results.append(CleanupResult(str(db_path), False, str(exc)))
    return results
