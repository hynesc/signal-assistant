import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signal_bot.bot import SignalBotApp
from signal_bot.config import AppConfig


class FakeSignalClient:
    def __init__(self) -> None:
        self.sent_messages = []
        self.typing_events = []

    def send_message(
        self, message: str, recipient: str | None = None, group_id: str | None = None
    ) -> bool:
        self.sent_messages.append(
            {"message": message, "recipient": recipient, "group_id": group_id}
        )
        return True

    def send_typing(
        self,
        recipient: str | None = None,
        group_id: str | None = None,
        stop: bool = False,
    ) -> bool:
        self.typing_events.append(
            {"recipient": recipient, "group_id": group_id, "stop": stop}
        )
        return True


def build_config(temp_dir: str) -> AppConfig:
    return AppConfig(
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


class AppTests(unittest.TestCase):
    def test_admin_model_command_is_chat_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = SignalBotApp(build_config(temp_dir), signal_client=FakeSignalClient())
            reply = app.handle_admin_command(
                "/bot model alternate-model",
                "group:g1:sender:+12025550101",
                "group:g1",
                "+12025550101",
            )
            self.assertEqual(reply, "Model set to alternate-model for this chat.")
            self.assertEqual(app.get_effective_model("group:g1"), "alternate-model")
            self.assertEqual(app.get_effective_model("dm:+12025550102"), "model")

    def test_compact_admin_command_form_is_parsed_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = SignalBotApp(build_config(temp_dir), signal_client=FakeSignalClient())
            reply = app.handle_admin_command(
                "/bottemp 0.4",
                "dm:+12025550101",
                "dm:+12025550101",
                "+12025550101",
            )
            self.assertEqual(reply, "Temp set to 0.4.")
            self.assertEqual(app.chat_settings["dm:+12025550101"]["temperature"], 0.4)

    def test_group_message_without_mention_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            signal = FakeSignalClient()
            app = SignalBotApp(build_config(temp_dir), signal_client=signal)
            msg = {
                "envelope": {
                    "sourceNumber": "+12025550102",
                    "dataMessage": {
                        "message": "hello everyone",
                        "groupInfo": {"groupId": "group.raw-group"},
                    },
                }
            }
            with patch("signal_bot.bot.asyncio.to_thread", new=self.run_inline):
                asyncio.run(app.process_incoming_message(msg))
            self.assertEqual(signal.sent_messages, [])

    def test_direct_message_generates_reply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            signal = FakeSignalClient()
            app = SignalBotApp(build_config(temp_dir), signal_client=signal)
            app.get_bot_response = lambda *args, **kwargs: "reply text"
            msg = {
                "envelope": {
                    "sourceNumber": "+12025550102",
                    "sourceName": "Test User",
                    "dataMessage": {
                        "message": "hey",
                    },
                }
            }
            with patch("signal_bot.bot.asyncio.to_thread", new=self.run_inline):
                asyncio.run(app.process_incoming_message(msg))
            self.assertEqual(signal.sent_messages[0]["message"], "reply text")
            self.assertEqual(signal.sent_messages[0]["recipient"], "+12025550102")

    def test_prune_stale_state_removes_idle_chat_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = build_config(temp_dir)
            config = AppConfig(
                **{
                    **config.__dict__,
                    "state_ttl_seconds": 1,
                }
            )
            app = SignalBotApp(config, signal_client=FakeSignalClient())
            app.history["dm:+1"] = {}
            app.chat_settings["dm:+1"] = {"enabled": True}
            app.chat_locks["dm:+1"] = app.get_chat_lock("dm:+1")
            app.chat_last_used["dm:+1"] = 0
            app.prune_stale_state()
            self.assertNotIn("dm:+1", app.history)
            self.assertNotIn("dm:+1", app.chat_settings)
            self.assertNotIn("dm:+1", app.chat_locks)

    @staticmethod
    async def run_inline(func, *args, **kwargs):
        return func(*args, **kwargs)
