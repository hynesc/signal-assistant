import asyncio
import time
from collections import deque
from typing import Any


class ChatStateStore:
    def __init__(self, *, state_ttl_seconds: int, history_maxlen: int = 20) -> None:
        self.state_ttl_seconds = state_ttl_seconds
        self.history_maxlen = history_maxlen
        self.history: dict[str, deque[dict[str, str]]] = {}
        self.chat_settings: dict[str, dict[str, Any]] = {}
        self.chat_locks: dict[str, asyncio.Lock] = {}
        self.chat_last_used: dict[str, float] = {}

    @staticmethod
    def history_key(sender: str, group_id: str | None) -> str:
        if group_id:
            return f"group:{group_id}:sender:{sender}"
        return f"dm:{sender}"

    @staticmethod
    def settings_key(sender: str, group_id: str | None) -> str:
        if group_id:
            return f"group:{group_id}"
        return f"dm:{sender}"

    def get_settings(self, settings_key: str) -> dict[str, Any]:
        return self.chat_settings.setdefault(settings_key, {})

    def get_history(self, history_key: str) -> deque[dict[str, str]]:
        return self.history.setdefault(history_key, deque(maxlen=self.history_maxlen))

    def replace_history(self, history_key: str, messages: list[dict[str, str]]) -> None:
        self.history[history_key] = deque(messages, maxlen=self.history_maxlen)

    def get_lock(self, history_key: str) -> asyncio.Lock:
        lock = self.chat_locks.get(history_key)
        if lock is None:
            lock = asyncio.Lock()
            self.chat_locks[history_key] = lock
        return lock

    def touch(self, history_key: str, settings_key: str) -> None:
        now = time.time()
        self.chat_last_used[history_key] = now
        self.chat_last_used[settings_key] = now

    def prune_stale(self) -> None:
        cutoff = time.time() - self.state_ttl_seconds
        stale_keys = [
            key for key, last_used in self.chat_last_used.items() if last_used < cutoff
        ]
        for key in stale_keys:
            self.chat_last_used.pop(key, None)
            self.history.pop(key, None)
            self.chat_settings.pop(key, None)
            lock = self.chat_locks.get(key)
            if lock and not lock.locked():
                self.chat_locks.pop(key, None)
