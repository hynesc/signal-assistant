import json
from pathlib import Path
from typing import Any


def load_contacts(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("contacts file must contain a JSON object")

    contacts: dict[str, dict[str, Any]] = {}
    for number, details in payload.items():
        if not isinstance(number, str) or not number.startswith("+"):
            raise ValueError(f"contact key must be an E.164 number: {number}")
        if not isinstance(details, dict):
            raise ValueError(f"contact details must be an object for {number}")
        contacts[number] = dict(details)
    return contacts
