import base64
import json
import logging
import sqlite3
from collections import OrderedDict
from pathlib import Path
from typing import Any

from .config import AppConfig


def _digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def inspect_local_signal_account(config: AppConfig, bot_number: str) -> dict[str, Any]:
    result = {
        "exact_matches": [],
        "near_matches": [],
        "errors": [],
        "ready": False,
    }

    accounts_path = config.signal_data_dir / "accounts.json"
    if not accounts_path.exists():
        result["errors"].append(f"Missing local account index: {accounts_path}")
        return result

    try:
        accounts_payload = json.loads(accounts_path.read_text())
    except Exception as exc:
        result["errors"].append(f"Could not parse {accounts_path}: {exc}")
        return result

    accounts = accounts_payload.get("accounts", [])
    target_digits = _digits_only(bot_number)

    for entry in accounts:
        number = entry.get("number", "")
        path_name = entry.get("path", "")
        account_path = config.signal_data_dir / path_name
        details = {
            "number": number,
            "path": str(account_path),
            "registered": None,
        }

        if account_path.exists():
            try:
                state = json.loads(account_path.read_text())
                details["registered"] = bool(state.get("registered"))
                details["device_id"] = state.get("deviceId")
                details["is_multi_device"] = state.get("isMultiDevice")
            except Exception as exc:
                details["error"] = f"Could not parse {account_path}: {exc}"
        else:
            details["error"] = f"Missing account state file: {account_path}"

        if number == bot_number:
            result["exact_matches"].append(details)
            if details.get("registered") is True:
                result["ready"] = True
        elif target_digits and _digits_only(number).endswith(target_digits[-10:]):
            result["near_matches"].append(details)

    return result


def get_account_db_path(config: AppConfig, bot_number: str) -> Path | None:
    accounts_path = config.signal_data_dir / "accounts.json"
    if not accounts_path.exists():
        return None

    try:
        accounts_payload = json.loads(accounts_path.read_text())
    except Exception:
        return None

    for entry in accounts_payload.get("accounts", []):
        if entry.get("number") != bot_number:
            continue
        db_path = config.signal_data_dir / f"{entry.get('path', '')}.d" / "account.db"
        if db_path.exists():
            return db_path

    return None


def lookup_number_by_service_id(
    config: AppConfig,
    service_id: str | None,
    cache: OrderedDict[str, str | None] | None = None,
) -> str | None:
    if not service_id:
        return None

    if cache is not None and service_id in cache:
        cache.move_to_end(service_id)
        return cache[service_id]

    db_path = get_account_db_path(config, config.bot_number)
    if not db_path:
        return None

    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "select number from recipient where aci = ? or pni = ?",
                (service_id, service_id),
            ).fetchone()
    except Exception as exc:
        logging.warning("Could not resolve Signal recipient %s via %s: %s", service_id, db_path, exc)
        return None

    resolved_number = row[0] if row and row[0] else None
    if cache is not None:
        cache[service_id] = resolved_number
        while len(cache) > config.max_cached_service_ids:
            cache.popitem(last=False)
    return resolved_number


def resolve_sender_identifier(
    config: AppConfig,
    envelope: dict[str, Any],
    cache: OrderedDict[str, str | None] | None = None,
) -> str | None:
    source_number = envelope.get("sourceNumber")
    if source_number:
        return source_number

    source_uuid = envelope.get("sourceUuid") or envelope.get("source")
    return lookup_number_by_service_id(config, source_uuid, cache=cache) or source_uuid


def ensure_bot_account_ready(config: AppConfig) -> bool:
    account_state = inspect_local_signal_account(config, config.bot_number)

    for error in account_state["errors"]:
        logging.error(error)

    if account_state["near_matches"]:
        stale_numbers = ", ".join(
            sorted({entry["number"] for entry in account_state["near_matches"] if entry.get("number")})
        )
        logging.warning("Found similar local Signal account entries: %s", stale_numbers)

    if account_state["ready"]:
        return True

    if not account_state["exact_matches"]:
        logging.error("No local Signal account entry matches %s.", config.bot_number)
    else:
        logging.error(
            "Signal account %s exists locally but is marked registered=false.",
            config.bot_number,
        )

    logging.error("Register and verify the standalone number before starting the bot.")
    return False


def extract_cli_group_id(raw_group_id: str | None) -> str | None:
    if not raw_group_id:
        return None

    group_id = str(raw_group_id).strip()
    if group_id.startswith("group."):
        group_id = group_id.split(".", 1)[1]
        try:
            decoded = base64.b64decode(group_id).decode("utf-8")
            if decoded:
                group_id = decoded
        except Exception:
            pass

    return group_id
