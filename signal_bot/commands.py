import os
import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class CommandInvocation:
    name: str
    args: list[str]
    raw_text: str


class CommandRegistry:
    def __init__(self):
        self.commands: dict[str, Callable[..., str | None]] = {}

    def register(self, name: str):
        """Register a command name (without the prefix)."""

        def decorator(func: Callable[..., str | None]):
            self.commands[name.lower()] = func
            return func

        return decorator

    def parse(self, text: str, prefix: str) -> CommandInvocation | None:
        parts = text.strip().split()
        if not parts:
            return None

        first_token = parts[0].lower()
        prefix = prefix.lower()

        if first_token == prefix:
            cmd_name = parts[1].lower() if len(parts) > 1 else "help"
            args = parts[2:] if len(parts) > 1 else []
            return CommandInvocation(cmd_name, args, text)

        if first_token.startswith(prefix):
            cmd_name = first_token[len(prefix) :] or "help"
            return CommandInvocation(cmd_name, parts[1:], text)

        return None

    def handle(self, text: str, prefix: str, **kwargs) -> str | None:
        invocation = self.parse(text, prefix)
        if invocation is None:
            return None
        handler = self.commands.get(invocation.name)
        if handler is None:
            return None
        return handler(text, command=invocation, **kwargs)


# Instance for the bot to use
admin_registry = CommandRegistry()


@admin_registry.register("help")
def help_cmd(text: str, app: Any, **kwargs) -> str:
    from .persona import build_help_text

    return build_help_text(app.config.bot_cmd_prefix)


@admin_registry.register("reset")
def reset_cmd(text: str, app: Any, history_key: str, **kwargs) -> str:
    app.history.pop(history_key, None)
    return "Alright. Memory wiped."


@admin_registry.register("temp")
def temp_cmd(
    text: str, app: Any, settings: dict[str, Any], command: CommandInvocation, **kwargs
) -> str:
    if len(command.args) != 1:
        return f"Usage: {app.config.bot_cmd_prefix} temp <value>"
    val_str = command.args[0]

    try:
        value = float(val_str)
    except ValueError:
        return "Bad temp value."
    settings["temperature"] = value
    return f"Temp set to {value}."


@admin_registry.register("model")
def model_cmd(
    text: str, app: Any, settings: dict[str, Any], command: CommandInvocation, **kwargs
) -> str:
    if not command.args:
        return f"Usage: {app.config.bot_cmd_prefix} model <model_id>"
    model_value = " ".join(command.args).strip()

    if model_value.lower() == "default":
        settings.pop("model", None)
        return f"Model reset to default ({app.config.default_model_id})."
    settings["model"] = model_value
    return f"Model set to {model_value} for this chat."


@admin_registry.register("mute")
def mute_cmd(text: str, app: Any, settings: dict[str, Any], **kwargs) -> str:
    settings["enabled"] = False
    return "Muted for this chat."


@admin_registry.register("unmute")
def unmute_cmd(text: str, app: Any, settings: dict[str, Any], **kwargs) -> str:
    settings["enabled"] = True
    return "Back for this chat."


@admin_registry.register("status")
def status_cmd(
    text: str, app: Any, settings: dict[str, Any], settings_key: str, **kwargs
) -> str:
    model_override = settings.get("model")
    scope = "group chat" if settings_key.startswith("group:") else "direct chat"
    return (
        f"Status ({scope}):\n"
        f"- Enabled: {settings.get('enabled', True)}\n"
        f"- Temp: {settings.get('temperature', 'default')}\n"
        f"- Model: {app.get_effective_model(settings_key)}\n"
        f"- Model Override: {model_override if model_override else 'none'}\n"
        f"- Persona: {app.persona.persona_name}"
    )


@admin_registry.register("clearall")
def clearall_cmd(text: str, app: Any, **kwargs) -> str:
    app.history.clear()
    app.chat_settings.clear()
    return "Everything wiped. Clean slate."


@admin_registry.register("persona")
def persona_cmd(text: str, app: Any, command: CommandInvocation, **kwargs) -> str:
    if len(command.args) != 1:
        return f"Usage: {app.config.bot_cmd_prefix} persona <name>"
    new_name = command.args[0].lower()

    persona_path = os.path.join(app.persona.personas_dir, new_name)

    if not re.fullmatch(r"[a-zA-Z0-9_-]+", new_name) or not os.path.isfile(os.path.join(persona_path, "system.txt")):
        return f"Persona '{new_name}' not found."

    from .persona import PersonaManager

    app.persona = PersonaManager(new_name)
    return f"Switched persona to: {new_name}"
