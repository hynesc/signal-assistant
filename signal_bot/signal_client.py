import json
import subprocess
from typing import Any

from .config import AppConfig


class SignalClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def run_cli(
        self,
        command_args: list[str],
        *,
        timeout: int,
        json_output: bool = False,
        allow_timeout: bool = False,
    ) -> str:
        container_timeout_seconds = max(int(timeout), 1)
        command = [
            "docker",
            "exec",
            self.config.signal_container_name,
            "timeout",
            "--kill-after=5s",
            f"{container_timeout_seconds}s",
            self.config.signal_cli_binary,
            "--config",
            self.config.signal_cli_config_dir,
        ]
        if json_output:
            command.extend(["-o", "json"])
        command.extend(["-a", self.config.bot_number])
        command.extend(command_args)

        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = proc.communicate(
                    timeout=container_timeout_seconds + 15
                )
                returncode = proc.returncode
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                returncode = 124
        except Exception as exc:
            raise RuntimeError(f"Failed to launch signal-cli: {exc}") from exc

        if returncode == 124 and allow_timeout:
            return stdout

        if returncode != 0:
            details = (stderr or stdout or "").strip().replace("\n", " ")
            if returncode == 124:
                details = details or "signal-cli command exceeded container timeout"
            raise RuntimeError(
                f"signal-cli command failed ({returncode}): {details or '<no output>'}"
            )

        return stdout

    def receive_messages(
        self, timeout_seconds: int | None = None
    ) -> list[dict[str, Any]]:
        receive_timeout_seconds = timeout_seconds or self.config.receive_timeout_seconds
        output = self.run_cli(
            [
                "receive",
                "-t",
                str(receive_timeout_seconds),
                "--ignore-attachments",
                "--ignore-stories",
                "--ignore-avatars",
                "--ignore-stickers",
            ],
            timeout=receive_timeout_seconds + 15,
            json_output=True,
            allow_timeout=True,
        )

        payload: list[Any] = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, list):
                payload.extend(item)
            else:
                payload.append(item)

        return [item for item in payload if isinstance(item, dict)]

    def send_message(
        self, message: str, recipient: str | None = None, group_id: str | None = None
    ) -> bool:
        command = ["send", "--message", message]
        if group_id:
            command.extend(["--group-id", group_id])
        else:
            recipient_list = recipient if isinstance(recipient, list) else [recipient]
            recipient_list = [item for item in recipient_list if item]
            if not recipient_list:
                return False
            command.extend(recipient_list)

        self.run_cli(command, timeout=60)
        return True

    def send_typing(
        self,
        recipient: str | None = None,
        group_id: str | None = None,
        stop: bool = False,
    ) -> bool:
        command = ["sendTyping"]
        if stop:
            command.append("--stop")

        if group_id:
            command.extend(["--group-id", group_id])
        elif recipient:
            recipient_list = recipient if isinstance(recipient, list) else [recipient]
            command.extend([item for item in recipient_list if item])
        else:
            return False

        self.run_cli(command, timeout=10)
        return True
