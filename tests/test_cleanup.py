import sqlite3
import tempfile
import unittest
from pathlib import Path

from signal_bot.data_cleanup import purge_attachments, purge_message_databases


class CleanupTests(unittest.TestCase):
    def test_purge_attachments_removes_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            signal_root = Path(temp_dir)
            attachments = signal_root / "attachments"
            attachments.mkdir()
            file_path = attachments / "one.txt"
            file_path.write_text("x")

            removed = purge_attachments(signal_root)

            self.assertEqual(removed, [str(file_path)])
            self.assertEqual(list(attachments.iterdir()), [])

    def test_purge_message_databases_clears_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            account_dir = data_dir / "123.d"
            account_dir.mkdir()
            db_path = account_dir / "account.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE message_send_log(id INTEGER)")
                conn.execute("CREATE TABLE message_send_log_content(id INTEGER)")
                conn.execute("INSERT INTO message_send_log VALUES (1)")
                conn.execute("INSERT INTO message_send_log_content VALUES (1)")
                conn.commit()

            results = purge_message_databases(data_dir)

            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].ok)
            with sqlite3.connect(db_path) as conn:
                count_a = conn.execute("SELECT COUNT(*) FROM message_send_log").fetchone()[0]
                count_b = conn.execute("SELECT COUNT(*) FROM message_send_log_content").fetchone()[0]
            self.assertEqual(count_a, 0)
            self.assertEqual(count_b, 0)
