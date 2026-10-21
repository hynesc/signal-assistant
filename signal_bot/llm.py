import logging
import re
import threading
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any

import requests

from .config import AppConfig


def sanitize_model_reply(raw_text: str) -> str:
    """
    Cleans up the model's response, handling <think> blocks from reasoning models.
    """
    if not raw_text:
        return ""

    # Strategy:
    # 1. If there's content after the last </think> tag, that's likely the final answer.
    # 2. If no closing tag, but there's an opening <think> tag, take everything before it.
    # 3. If everything is wrapped in tags, or there are no tags, return the text cleaned of any stray tags.

    text = raw_text.strip()

    # 1. Content after last </think>
    if "</think>" in text:
        after_think = text.split("</think>")[-1].strip()
        if after_think:
            return after_think

    # 2. Content before first <think>
    if "<think>" in text:
        before_think = text.split("<think>")[0].strip()
        if before_think:
            return before_think

    # 3. Fallback: just strip the tags and return whatever is left
    reply_text = re.sub(r"</?think>", "", text).strip()
    return re.sub(r"\n+", "\n", reply_text).strip()


def should_search(text: str) -> bool:
    triggers = (
        "what is",
        "who is",
        "when did",
        "how much",
        "how many",
        "latest",
        "current",
        "today",
        "now",
        "salary",
        "price",
        "release",
        "news",
        "should i",
        "weather",
        "stock",
        "rate",
    )
    text_l = text.lower()
    return any(trigger in text_l for trigger in triggers)


@dataclass
class SearchResult:
    title: str
    snippet: str


class DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[SearchResult] = []
        self._in_title = False
        self._in_snippet = False
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = set((dict(attrs).get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._in_title = True
            self._title_parts = []
        elif "result__snippet" in classes:
            self._in_snippet = True
            self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._in_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
        if self._in_snippet and tag in {"a", "div"}:
            self._in_snippet = False
            title = _normalize_text(" ".join(self._title_parts))
            snippet = _normalize_text(" ".join(self._snippet_parts))
            if title and snippet:
                self.results.append(SearchResult(title=title, snippet=snippet))
                self._title_parts = []
                self._snippet_parts = []


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def parse_duckduckgo_results(html: str, limit: int = 8) -> list[SearchResult]:
    parser = DuckDuckGoHTMLParser()
    parser.feed(html)
    return parser.results[:limit]


class DuckDuckGoSearchClient:
    def __init__(self) -> None:
        self._local = threading.local()
        self.url = "https://html.duckduckgo.com/html/"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

    @property
    def session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            self._local.session = session
        return session

    def search(self, query: str, max_chars: int = 3000) -> str:
        try:
            response = self.session.post(
                self.url,
                data={"q": query},
                headers=self.headers,
                timeout=15,
            )
            response.raise_for_status()
            results = parse_duckduckgo_results(response.text)
            if not results:
                return "No useful search results found."

            text = "\n\n".join(
                f"### {result.title}\n{result.snippet}" for result in results
            )
            return text[:max_chars]
        except Exception as exc:
            logging.error("Web search failed: %s", exc)
            return f"Web search failed: {exc}"


class OllamaClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._local = threading.local()

    @property
    def session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            self._local.session = session
        return session

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model_id: str,
        temperature: float,
        timeout: int,
        num_predict: int | None = None,
    ) -> str:
        options: dict[str, Any] = {"temperature": temperature}
        if num_predict is not None:
            options["num_predict"] = num_predict

        payload = {
            "model": model_id,
            "messages": messages,
            "stream": False,
            "options": options,
        }

        try:
            response = self.session.post(
                self.config.ollama_url, json=payload, timeout=timeout
            )
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")
        except Exception as exc:
            logging.error("Ollama API call failed: %s", exc)
            raise


def web_search(http: requests.Session, query: str, max_chars: int = 3000) -> str:
    client = DuckDuckGoSearchClient()
    client._local.session = http
    return client.search(query, max_chars=max_chars)


def ollama_chat(
    http: requests.Session,
    config: AppConfig,
    messages: list[dict[str, str]],
    *,
    model_id: str,
    temperature: float,
    timeout: int,
    num_predict: int | None = None,
) -> str:
    client = OllamaClient(config)
    client._local.session = http
    return client.chat(
        messages,
        model_id=model_id,
        temperature=temperature,
        timeout=timeout,
        num_predict=num_predict,
    )
