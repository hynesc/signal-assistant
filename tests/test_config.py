import tempfile
import unittest
from pathlib import Path

from signal_bot.config import AppConfig


class ConfigValidationTests(unittest.TestCase):
    def test_validate_accepts_reasonable_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig(
                ollama_url="http://localhost:11434/api/chat",
                default_model_id="model",
                bot_number="+12025550100",
                bot_uuid="uuid",
                bot_mention_name="Bot",
                admin_numbers=frozenset({"+12025550101"}),
                receive_timeout_seconds=5,
                signal_data_dir=Path(temp_dir),
                signal_container_name="signal-api",
                summary_every=10,
                summary_max_tokens=300,
                think_max_tokens=600,
                max_in_flight_messages=4,
                state_ttl_seconds=86400,
                max_cached_service_ids=2048,
                persona_name="assistant",
                bot_cmd_prefix="/bot",
                signal_cli_binary="signal-cli-native",
                signal_cli_config_dir="/home/.local/share/signal-cli",
            )
            self.assertEqual(config.validate(), [])

    def test_validate_reports_multiple_errors(self) -> None:
        config = AppConfig(
            ollama_url="localhost",
            default_model_id="",
            bot_number="15551234567",
            bot_uuid="",
            bot_mention_name="",
            admin_numbers=frozenset({"15557654321"}),
            receive_timeout_seconds=0,
            signal_data_dir=Path("/definitely/missing"),
            signal_container_name="signal-api",
            summary_every=0,
            summary_max_tokens=0,
            think_max_tokens=0,
            max_in_flight_messages=0,
            state_ttl_seconds=0,
            max_cached_service_ids=0,
            persona_name="",
            bot_cmd_prefix="",
            signal_cli_binary="",
            signal_cli_config_dir="",
        )
        errors = config.validate()
        self.assertGreaterEqual(len(errors), 12)
        self.assertTrue(any("OLLAMA_URL" in error for error in errors))
        self.assertTrue(any("SIGNAL_DATA_DIR" in error for error in errors))
        self.assertTrue(any("BOT_PERSONA" in error for error in errors))
        self.assertTrue(any("BOT_CMD_PREFIX" in error for error in errors))
        self.assertTrue(any("SIGNAL_CLI_BINARY" in error for error in errors))
        self.assertTrue(any("SIGNAL_CLI_CONFIG_DIR" in error for error in errors))
