import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _split_csv(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


@dataclass(frozen=True)
class AppConfig:
    ollama_url: str
    default_model_id: str
    bot_number: str
    bot_uuid: str
    bot_mention_name: str
    admin_numbers: frozenset[str]
    receive_timeout_seconds: int
    signal_data_dir: Path
    signal_container_name: str
    summary_every: int
    summary_max_tokens: int
    think_max_tokens: int
    max_in_flight_messages: int
    state_ttl_seconds: int
    max_cached_service_ids: int
    persona_name: str
    bot_cmd_prefix: str
    signal_cli_binary: str
    signal_cli_config_dir: str
    contacts_file: Path | None = None

    @classmethod
    def from_env(cls) -> "AppConfig":
        base_dir = Path(__file__).resolve().parent.parent
        contacts_file_raw = os.environ.get("CONTACTS_FILE")
        return cls(
            ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat"),
            default_model_id=os.environ.get(
                "MODEL_ID",
                "llama3.1:8b",
            ),
            bot_number=os.environ.get("BOT_NUMBER", ""),
            bot_uuid=os.environ.get("BOT_UUID", ""),
            bot_mention_name=os.environ.get("BOT_MENTION_NAME", "Assistant"),
            admin_numbers=frozenset(_split_csv(os.environ.get("ADMIN_NUMBERS", ""))),
            receive_timeout_seconds=int(
                os.environ.get("RECEIVE_TIMEOUT_SECONDS", "30")
            ),
            signal_data_dir=Path(
                os.environ.get(
                    "SIGNAL_DATA_DIR",
                    str(base_dir / "signal-data" / "data"),
                )
            ),
            signal_container_name=os.environ.get("SIGNAL_CONTAINER_NAME", "signal-assistant-api"),
            summary_every=int(os.environ.get("SUMMARY_EVERY", "10")),
            summary_max_tokens=int(os.environ.get("SUMMARY_MAX_TOKENS", "300")),
            think_max_tokens=int(os.environ.get("THINK_MAX_TOKENS", "600")),
            max_in_flight_messages=int(os.environ.get("MAX_IN_FLIGHT_MESSAGES", "4")),
            state_ttl_seconds=int(os.environ.get("STATE_TTL_SECONDS", "86400")),
            max_cached_service_ids=int(
                os.environ.get("MAX_CACHED_SERVICE_IDS", "2048")
            ),
            persona_name=os.environ.get("BOT_PERSONA", "assistant"),
            bot_cmd_prefix=os.environ.get("BOT_CMD_PREFIX", "/bot"),
            signal_cli_binary=os.environ.get("SIGNAL_CLI_BINARY", "signal-cli-native"),
            signal_cli_config_dir=os.environ.get(
                "SIGNAL_CLI_CONFIG_DIR", "/home/.local/share/signal-cli"
            ),
            contacts_file=Path(contacts_file_raw)
            if contacts_file_raw
            else base_dir / "contacts.json",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ollama_url": self.ollama_url,
            "default_model_id": self.default_model_id,
            "bot_number": self.bot_number,
            "bot_uuid": self.bot_uuid,
            "bot_mention_name": self.bot_mention_name,
            "admin_numbers": sorted(self.admin_numbers),
            "receive_timeout_seconds": self.receive_timeout_seconds,
            "signal_data_dir": str(self.signal_data_dir),
            "signal_container_name": self.signal_container_name,
            "summary_every": self.summary_every,
            "summary_max_tokens": self.summary_max_tokens,
            "think_max_tokens": self.think_max_tokens,
            "max_in_flight_messages": self.max_in_flight_messages,
            "state_ttl_seconds": self.state_ttl_seconds,
            "max_cached_service_ids": self.max_cached_service_ids,
            "persona_name": self.persona_name,
            "bot_cmd_prefix": self.bot_cmd_prefix,
            "signal_cli_binary": self.signal_cli_binary,
            "signal_cli_config_dir": self.signal_cli_config_dir,
            "contacts_file": str(self.contacts_file) if self.contacts_file else None,
        }

    def validate(self) -> list[str]:
        errors: list[str] = []

        if not self.ollama_url.startswith(("http://", "https://")):
            errors.append("OLLAMA_URL must start with http:// or https://")

        if not self.default_model_id.strip():
            errors.append("MODEL_ID must not be empty")

        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", self.bot_number):
            errors.append("BOT_NUMBER must be configured in E.164 format (for example +12025550100)")

        if not self.bot_uuid.strip():
            errors.append("BOT_UUID must not be empty")

        if not self.bot_mention_name.strip():
            errors.append("BOT_MENTION_NAME must not be empty")

        if not self.admin_numbers:
            errors.append("ADMIN_NUMBERS must contain at least one number")

        for number in self.admin_numbers:
            if not re.fullmatch(r"\+[1-9][0-9]{7,14}", number):
                errors.append("ADMIN_NUMBERS entries must be in E.164 format")

        if self.receive_timeout_seconds <= 0:
            errors.append("RECEIVE_TIMEOUT_SECONDS must be greater than 0")

        if self.summary_every <= 0:
            errors.append("SUMMARY_EVERY must be greater than 0")

        if self.summary_max_tokens <= 0:
            errors.append("SUMMARY_MAX_TOKENS must be greater than 0")

        if self.think_max_tokens <= 0:
            errors.append("THINK_MAX_TOKENS must be greater than 0")

        if self.max_in_flight_messages <= 0:
            errors.append("MAX_IN_FLIGHT_MESSAGES must be greater than 0")

        if self.state_ttl_seconds <= 0:
            errors.append("STATE_TTL_SECONDS must be greater than 0")

        if self.max_cached_service_ids <= 0:
            errors.append("MAX_CACHED_SERVICE_IDS must be greater than 0")

        if not self.persona_name.strip():
            errors.append("BOT_PERSONA must not be empty")

        if not self.bot_cmd_prefix.strip():
            errors.append("BOT_CMD_PREFIX must not be empty")

        if not self.signal_cli_binary.strip():
            errors.append("SIGNAL_CLI_BINARY must not be empty")

        if not self.signal_cli_config_dir.strip():
            errors.append("SIGNAL_CLI_CONFIG_DIR must not be empty")

        if (
            self.contacts_file
            and self.contacts_file.exists()
            and not self.contacts_file.is_file()
        ):
            errors.append(f"CONTACTS_FILE is not a file: {self.contacts_file}")

        persona_path = (
            Path(__file__).resolve().parent
            / "personas"
            / self.persona_name
            / "system.txt"
        )
        if self.persona_name.strip() and not persona_path.exists():
            errors.append(f"BOT_PERSONA system prompt does not exist: {persona_path}")
        elif (
            persona_path.exists()
            and not persona_path.read_text(encoding="utf-8").strip()
        ):
            errors.append(f"BOT_PERSONA system prompt is empty: {persona_path}")

        if not self.signal_data_dir.exists():
            errors.append(f"SIGNAL_DATA_DIR does not exist: {self.signal_data_dir}")
        elif not self.signal_data_dir.is_dir():
            errors.append(f"SIGNAL_DATA_DIR is not a directory: {self.signal_data_dir}")

        return errors
