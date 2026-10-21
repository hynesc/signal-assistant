import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signal_bot.bot import SignalBotApp
from signal_bot.config import AppConfig
from signal_bot.persona import PersonaManager


class PublicDefaultsTests(unittest.TestCase):
    def test_unconfigured_bot_has_no_account_or_administrators(self):
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig.from_env()
        self.assertEqual(config.bot_number, "")
        self.assertEqual(config.bot_uuid, "")
        self.assertEqual(config.admin_numbers, frozenset())
        errors = config.validate()
        for field in ("BOT_NUMBER", "BOT_UUID", "ADMIN_NUMBERS"):
            self.assertTrue(any(field in error for error in errors))

    def test_missing_contacts_does_not_create_implicit_contacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"CONTACTS_FILE": str(Path(temp_dir) / "missing.json")}, clear=True):
                app = SignalBotApp(AppConfig.from_env())
            self.assertEqual(app.contacts, {})
            self.assertIsNone(app.handle_admin_command("/bot clearall", "dm:test", "dm:test", "+12025550101"))

    def test_packaged_default_persona_and_friendly_role_load(self):
        persona = PersonaManager()
        self.assertIn("conversational AI", persona.system_prompt)
        self.assertIn("warm, informal", persona.build_identity_hint({"name": "Example", "role": "friendly"}))

    def test_persona_path_cannot_escape_templates(self):
        with self.assertRaises(ValueError):
            PersonaManager("../../config")


if __name__ == "__main__":
    unittest.main()
