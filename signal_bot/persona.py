import os
import re


class PersonaManager:
    def __init__(self, persona_name: str = "assistant"):
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", persona_name):
            raise ValueError("Persona names may contain only letters, numbers, underscores, and hyphens")
        self.persona_name = persona_name
        self.base_dir = os.path.dirname(__file__)
        self.personas_dir = os.path.join(self.base_dir, "personas")
        self.persona_path = os.path.join(self.personas_dir, persona_name)
        self.roles_dir = os.path.join(self.persona_path, "roles")

        # Load system prompt
        self.system_prompt = self._load_template(os.path.join(self.persona_path, "system.txt"))

    def _load_template(self, path: str) -> str:
        """Helper to load a template file safely."""
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()

    def build_identity_hint(self, contact: dict | None) -> str:
        if not contact:
            return ""

        name = contact.get("name", "Unknown")
        role = contact.get("role")
        hint = f"The user you are talking to is named {name}."

        if role and re.fullmatch(r"[a-zA-Z0-9_-]+", role):
            role_template_path = os.path.join(self.roles_dir, f"{role}.txt")
            role_rules = self._load_template(role_template_path)
            if role_rules:
                hint += f"\n\n{role_rules}"

        return hint


def build_help_text(prefix: str) -> str:
    return (
        f"Bot commands ({prefix}):\n"
        "\n"
        f"{prefix} help — show this menu\n"
        f"{prefix} think <question> — slow, deeper reasoning (may use web search)\n"
        f"{prefix} reset — wipe conversation memory for this speaker/chat\n"
        f"{prefix} temp <value> — set response temperature for this chat\n"
        f"{prefix} model <model_id> — set model for this chat\n"
        f"{prefix} model default — clear chat model override\n"
        f"{prefix} mute — disable replies in this chat\n"
        f"{prefix} unmute — re-enable replies in this chat\n"
        f"{prefix} status — show current settings\n"
        f"{prefix} persona <name> — switch bot personality\n"
        f"{prefix} clearall — wipe ALL memory and settings\n"
    )
