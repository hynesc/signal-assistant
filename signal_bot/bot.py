import argparse
import asyncio
import json
import logging
import re
import time
from collections import OrderedDict
from typing import Any

import requests
from requests.exceptions import ReadTimeout

from .contacts import load_contacts
from .signal_account import (
    ensure_bot_account_ready,
    extract_cli_group_id,
    resolve_sender_identifier,
)
from .config import AppConfig
from .llm import (
    DuckDuckGoSearchClient,
    OllamaClient,
    sanitize_model_reply,
    should_search,
)
from .persona import PersonaManager
from .commands import admin_registry
from .signal_client import SignalClient
from .state import ChatStateStore


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


class SignalBotApp:
    def __init__(
        self,
        config: AppConfig,
        signal_client: SignalClient | None = None,
        llm_client: OllamaClient | None = None,
        search_client: DuckDuckGoSearchClient | None = None,
    ) -> None:
        self.config = config
        self.signal = signal_client or SignalClient(config)
        self.llm = llm_client or OllamaClient(config)
        self.search = search_client or DuckDuckGoSearchClient()
        self.persona = PersonaManager(config.persona_name)
        self.state = ChatStateStore(state_ttl_seconds=config.state_ttl_seconds)
        self.history = self.state.history
        self.chat_settings = self.state.chat_settings
        self.chat_locks = self.state.chat_locks
        self.chat_last_used = self.state.chat_last_used
        self.contacts = load_contacts(config.contacts_file)
        self.in_flight_tasks: set[asyncio.Task[Any]] = set()
        self.receive_semaphore = asyncio.Semaphore(config.max_in_flight_messages)
        self.signal_cli_lock = asyncio.Lock()
        self.outgoing_pending = asyncio.Event()
        self.pending_send_count = 0
        self.mention_pattern = re.compile(
            rf"@{re.escape(config.bot_mention_name)}\b", re.IGNORECASE
        )
        self.service_id_cache: OrderedDict[str, str | None] = OrderedDict()

    def get_history_key(self, sender: str, group_id: str | None) -> str:
        return self.state.history_key(sender, group_id)

    def get_settings_key(self, sender: str, group_id: str | None) -> str:
        return self.state.settings_key(sender, group_id)

    def get_chat_settings(self, settings_key: str) -> dict[str, Any]:
        return self.state.get_settings(settings_key)

    def get_chat_lock(self, history_key: str) -> asyncio.Lock:
        return self.state.get_lock(history_key)

    def touch_chat_state(self, history_key: str, settings_key: str) -> None:
        self.state.touch(history_key, settings_key)

    def prune_stale_state(self) -> None:
        self.state.prune_stale()

    def get_effective_model(self, settings_key: str) -> str:
        return str(
            self.chat_settings.get(settings_key, {}).get("model")
            or self.config.default_model_id
        )

    def get_effective_temperature(
        self, settings_key: str, contact: dict[str, Any] | None
    ) -> float:
        if "temperature" in self.chat_settings.get(settings_key, {}):
            return float(self.chat_settings[settings_key]["temperature"])
        if contact and contact.get("role") == "friendly":
            return 1.0
        return 0.75

    def summarize_history(self, history_key: str, settings_key: str) -> None:
        history = self.history.get(history_key)
        if not history or len(history) < self.config.summary_every * 2:
            return

        to_summarize = list(history)[: -self.config.summary_every]
        remaining = list(history)[-self.config.summary_every :]
        messages = [
            {
                "role": "system",
                "content": (
                    "Summarize the following conversation into a concise memory. "
                    "Preserve important facts, relationships, tone, conflicts, and ongoing plans. "
                    "Write in third person. Do not add commentary."
                ),
            },
            {
                "role": "user",
                "content": "\n".join(
                    f"{message['role']}: {message['content']}"
                    for message in to_summarize
                ),
            },
        ]

        try:
            summary = sanitize_model_reply(
                self.llm.chat(
                    messages,
                    model_id=self.get_effective_model(settings_key),
                    temperature=0.3,
                    timeout=120,
                    num_predict=self.config.summary_max_tokens,
                )
            )
            if not summary:
                return

            self.state.replace_history(
                history_key,
                [{"role": "system", "content": f"[Conversation summary]\n{summary}"}]
                + remaining,
            )
            logging.info("Summarized conversation history")
        except Exception as exc:
            logging.error("History summarization failed: %s", exc)

    def think_with_tools(
        self, settings_key: str, question: str, sender_id: str | None = None
    ) -> str:
        contact = self.contacts.get(sender_id)
        identity_hint = ""
        if contact:
            identity_hint = f"\n\n[Contact]\nThe user you are talking to is named {contact.get('name')}."

        current_date = time.strftime("%A, %d %B %Y")
        messages = [
            {
                "role": "system",
                "content": self.persona.system_prompt
                + identity_hint
                + f"\n\n[Context]\nToday is {current_date}.\n\n[Think mode]\nRespond thoughtfully and thoroughly.",
            }
        ]

        if should_search(question):
            search_result = self.search.search(question)
            messages.append(
                {
                    "role": "system",
                    "content": f"[Web search results for '{question}']\n{search_result}",
                }
            )

        messages.append({"role": "user", "content": question})

        try:
            logging.info("Think mode engaged.")
            reply = sanitize_model_reply(
                self.llm.chat(
                    messages,
                    model_id=self.get_effective_model(settings_key),
                    temperature=0.6,
                    timeout=180,
                    num_predict=self.config.think_max_tokens,
                )
            )
            return reply or "I thought about it and came up empty."
        except Exception as exc:
            logging.error("Think mode failed: %s", exc)
            return "I couldn't complete that request. Please try again."

    def handle_admin_command(
        self,
        text: str,
        history_key: str,
        settings_key: str,
        sender: str,
    ) -> str | None:
        if sender not in self.config.admin_numbers:
            return None

        settings = self.get_chat_settings(settings_key)

        return admin_registry.handle(
            text,
            prefix=self.config.bot_cmd_prefix,
            app=self,
            history_key=history_key,
            settings_key=settings_key,
            settings=settings,
            sender=sender,
        )

    def get_bot_response(
        self,
        history_key: str,
        settings_key: str,
        user_text: str,
        sender_id: str | None = None,
    ) -> str:
        if user_text.startswith("[Think mode]"):
            return user_text

        history = self.state.get_history(history_key)
        history.append({"role": "user", "content": user_text})

        contact = self.contacts.get(sender_id) if sender_id else None
        identity_hint = self.persona.build_identity_hint(contact)
        current_date = time.strftime("%A, %d %B %Y")
        messages = [
            {
                "role": "system",
                "content": self.persona.system_prompt
                + ("\n\n" + identity_hint if identity_hint else "")
                + f"\n\n[Context]\nToday is {current_date}.",
            }
        ] + list(history)

        try:
            logging.info("Thinking on %s...", self.config.ollama_url)
            reply_text = sanitize_model_reply(
                self.llm.chat(
                    messages,
                    model_id=self.get_effective_model(settings_key),
                    temperature=self.get_effective_temperature(settings_key, contact),
                    timeout=120,
                )
            )
            if not reply_text:
                raise ValueError("Empty response from Ollama")

            history.append({"role": "assistant", "content": reply_text})
            self.summarize_history(history_key, settings_key)
            return reply_text
        except requests.exceptions.ConnectionError as exc:
            logging.error(
                "Could not connect to Ollama on %s: %s", self.config.ollama_url, exc
            )
            if history:
                history.pop()
            return "The language model is unavailable. Please try again later."
        except Exception as exc:
            logging.error("Ollama error: %s", exc)
            if history:
                history.pop()
            return "I couldn't generate a response. Please try again."

    async def process_incoming_message(self, msg: dict[str, Any]) -> None:
        envelope = msg.get("envelope", {})
        data_msg = envelope.get("dataMessage", {})

        if not data_msg or "message" not in data_msg:
            return

        text = data_msg["message"]
        sender = resolve_sender_identifier(
            self.config, envelope, cache=self.service_id_cache
        )

        if not sender or sender == self.config.bot_number:
            return

        raw_group_id = None
        if "groupInfo" in data_msg:
            raw_group_id = data_msg["groupInfo"].get("groupId")
        elif "groupV2" in data_msg:
            raw_group_id = data_msg["groupV2"].get("id")

        group_id = extract_cli_group_id(raw_group_id)

        if not sender or not text or text.strip() == "":
            return

        mentions = data_msg.get("mentions", [])
        is_mentioned_in_array = any(
            mention.get("number") == self.config.bot_number
            or mention.get("uuid") == self.config.bot_uuid
            for mention in mentions
        )

        is_tagged_text = bool(self.mention_pattern.search(text))
        is_tagged = is_mentioned_in_array or is_tagged_text
        is_admin_cmd = (
            text.strip().lower().startswith(self.config.bot_cmd_prefix.lower())
        )
        is_dm = group_id is None

        if not is_tagged and not is_admin_cmd and not is_dm:
            return

        if is_tagged_text:
            text = self.mention_pattern.sub("", text).strip()

        text = text.replace("\ufffc", "").strip()

        logging.info("Received %s message (length: %s)", "group" if group_id else "direct", len(text))

        if (
            sender not in self.contacts
            and isinstance(sender, str)
            and sender.startswith("+")
        ):
            self.contacts[sender] = {"name": envelope.get("sourceName") or "Unknown"}
            logging.info("New contact detected")

        history_key = self.get_history_key(sender, group_id)
        settings_key = self.get_settings_key(sender, group_id)
        self.touch_chat_state(history_key, settings_key)

        async with self.receive_semaphore:
            async with self.get_chat_lock(history_key):
                think_cmd = f"{self.config.bot_cmd_prefix} think".lower()
                if (
                    sender in self.config.admin_numbers
                    and text.strip().lower().startswith(think_cmd)
                ):
                    # Extract the question after the think command
                    parts = text.strip().split(maxsplit=2)
                    if len(parts) < 3 or not parts[2].strip():
                        reply_text = "Think about what?"
                    else:
                        try:
                            reply_text = await asyncio.to_thread(
                                self.think_with_tools,
                                settings_key,
                                parts[2].strip(),
                                sender,
                            )
                        except Exception as exc:
                            logging.error("Failed to run think mode: %s", exc)
                            return
                else:
                    admin_reply = self.handle_admin_command(
                        text, history_key, settings_key, sender
                    )
                    if admin_reply:
                        reply_text = admin_reply
                    else:
                        if not self.chat_settings.get(settings_key, {}).get(
                            "enabled", True
                        ):
                            return

                        try:
                            start = time.time()
                            reply_text = await asyncio.to_thread(
                                self.get_bot_response,
                                history_key,
                                settings_key,
                                text,
                                sender,
                            )
                            logging.info("LLM latency: %.2fs", time.time() - start)
                        except Exception as exc:
                            logging.error("Failed to generate reply: %s", exc)
                            return

                try:
                    self.pending_send_count += 1
                    self.outgoing_pending.set()
                    async with self.signal_cli_lock:
                        await asyncio.to_thread(
                            self.signal.send_message,
                            reply_text,
                            sender if not group_id else None,
                            group_id,
                        )
                except Exception as exc:
                    logging.error("Failed to send reply: %s", exc)
                finally:
                    self.pending_send_count -= 1
                    if self.pending_send_count <= 0:
                        self.pending_send_count = 0
                        self.outgoing_pending.clear()

    def _track_task(self, task: asyncio.Task[Any]) -> None:
        self.in_flight_tasks.add(task)
        task.add_done_callback(self.in_flight_tasks.discard)
        task.add_done_callback(self._log_task_exception)

    @staticmethod
    def _log_task_exception(task: asyncio.Task[Any]) -> None:
        try:
            task.result()
        except Exception as exc:
            logging.error("Background message task failed: %s", exc)

    async def listen_and_respond(self) -> None:
        logging.info(
            "Bot is 'working' (Signal via direct signal-cli in %s, Brain on %s, max in flight %s)...",
            self.config.signal_container_name,
            self.config.ollama_url,
            self.config.max_in_flight_messages,
        )

        while True:
            try:
                if self.outgoing_pending.is_set():
                    await asyncio.sleep(0.1)
                    continue

                receive_timeout = 1 if self.in_flight_tasks else None
                async with self.signal_cli_lock:
                    batch = await asyncio.to_thread(
                        self.signal.receive_messages,
                        receive_timeout,
                    )

                for msg in batch:
                    task = asyncio.create_task(self.process_incoming_message(msg))
                    self._track_task(task)

                done = {task for task in self.in_flight_tasks if task.done()}
                self.in_flight_tasks.difference_update(done)
                self.prune_stale_state()
            except ReadTimeout:
                continue
            except Exception as exc:
                logging.error("Connection lost (%s). Reconnecting in 5s...", exc)
                await asyncio.sleep(5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Signal bot.")
    parser.add_argument(
        "--print-bot-number",
        action="store_true",
        help="Print the configured bot number and exit.",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print effective config as JSON and exit.",
    )
    parser.add_argument(
        "--check-account-ready",
        action="store_true",
        help="Validate the configured Signal account state and exit.",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run config and account diagnostics and exit.",
    )
    return parser.parse_args()


def run_doctor(config: AppConfig) -> int:
    errors = config.validate()
    report = {
        "config": config.to_dict(),
        "config_errors": errors,
        "account_ready": False,
    }
    if not errors:
        report["account_ready"] = ensure_bot_account_ready(config)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors and report["account_ready"] else 1


def main() -> int:
    args = parse_args()
    config = AppConfig.from_env()

    if args.print_bot_number:
        print(config.bot_number)
        return 0

    if args.print_config:
        print(json.dumps(config.to_dict(), indent=2, sort_keys=True))
        return 0

    if args.doctor:
        return run_doctor(config)

    config_errors = config.validate()
    if config_errors:
        for error in config_errors:
            logging.error("Config error: %s", error)
        return 1

    if args.check_account_ready:
        return 0 if ensure_bot_account_ready(config) else 1

    if not ensure_bot_account_ready(config):
        return 1

    app = SignalBotApp(config)
    asyncio.run(app.listen_and_respond())
    return 0
