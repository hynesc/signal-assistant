import tempfile
import unittest
from pathlib import Path

from signal_bot.contacts import load_contacts


class ContactTests(unittest.TestCase):
    def test_load_contacts_reads_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contacts.json"
            path.write_text(
                '{"+12025550100": {"name": "Example", "role": "friendly"}}',
                encoding="utf-8",
            )

            contacts = load_contacts(path)

            self.assertEqual(contacts["+12025550100"]["name"], "Example")
            self.assertEqual(contacts["+12025550100"]["role"], "friendly")

    def test_load_contacts_missing_file_is_empty(self) -> None:
        self.assertEqual(load_contacts(Path("/definitely/missing/contacts.json")), {})


if __name__ == "__main__":
    unittest.main()
