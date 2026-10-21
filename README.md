# Signal Assistant

A self-hosted Signal chatbot with local Ollama inference, conversation memory, and configurable personas. Python runs on the host and sends/receives through `signal-cli` in bbernhard's Docker container. The container's REST API registers the dedicated Signal account.

The public edition includes a neutral persona and fictional contacts. Supply your own account and operator settings.

## Features

- Direct messages, group mentions, and administrator commands.
- Concurrent inference across conversations with ordered processing and serialized CLI access.
- In-memory history, rolling summaries, and idle expiry.
- Per-chat model, temperature, and mute controls; text-based persona templates.
- Optional DuckDuckGo search through the administrator-only think command.

## Get started

Requires Python 3.10+, Docker, curl, Bash on Linux/macOS, and a reachable Ollama server with a downloaded chat model.

```bash
git clone https://github.com/hynesc/signal-assistant.git
cd signal-assistant
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
```

Follow [SETUP.md](SETUP.md) to create the container, register and verify your number, and set `BOT_NUMBER`, `BOT_UUID`, and `ADMIN_NUMBERS`. After setup:

```bash
./start_bot.sh
./stop_bot.sh
```

| Guide | Contents |
| --- | --- |
| [Setup](SETUP.md) | Account registration, transport checks, Ollama, groups, and troubleshooting. |
| [Configuration](CONFIGURATION.md) | All settings, paths, persona templates, and data handling. |
| [Architecture](ARCHITECTURE.md) | Components, message flow, and concurrency. |

## Commands

Send from an administrator account using the configured prefix (default `/bot`):

| Command | Behavior |
| --- | --- |
| `help` | List commands. |
| `think <question>` | Generate a longer response, optionally using web search. |
| `reset` | Clear this speaker's conversation history. |
| `model <id>` / `model default` | Set or clear the chat's model override. |
| `temp <value>` | Set the chat's temperature. |
| `mute` / `unmute` | Disable or enable replies in the chat. |
| `status` | Show effective settings. |
| `persona <name>` | Switch the application-wide persona. |
| `clearall` | Clear all in-memory history and chat settings. |

For example, `/bot persona assistant` selects the included persona. See [persona templates](CONFIGURATION.md#persona-templates) to add your own.

## Data handling and limits

The host handles decrypted messages and sends context to Ollama; optional searches send queries to DuckDuckGo. Contacts are context, not an access allowlist. Routine incoming-message logs omit text and sender/group identifiers; diagnostic and exception output may expose local details.

Cleanup is best effort, not secure erasure. Account credentials remain. This is a self-hosted prototype; pin a tested container image version. See [configuration](CONFIGURATION.md#private-local-files) for retention and private files.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests use temporary fixtures and fake clients. GitHub Actions tests Python 3.10/3.12 and builds the wheel; no live account or model is required.
