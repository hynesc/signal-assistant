# Signal Assistant

A configurable Signal chatbot with local Ollama inference, isolated conversation memory, template personas, and administrator commands. Python owns the application logic; a Docker container provides `signal-cli` and its account state.

This public edition includes a neutral assistant persona and fictional contacts. Account identifiers and administrator numbers must be supplied by the operator. No account data, chat logs, personal personas, or previous Git history are included.

## Features

- Replies to direct messages and group messages triggered by mentions or a command prefix.
- Serializes Signal CLI access and conversation processing while allowing inference across different chats concurrently.
- Keeps conversation history in memory with rolling summaries and an idle-state expiry.
- Supports per-chat model, temperature, and mute settings through administrator commands.
- Loads text-based personas and optional contact tone templates.
- Offers an administrator-only think command with DuckDuckGo search when query heuristics match.
- Omits message text, sender names, phone numbers, and group identifiers from routine incoming-message logs.
- Includes account diagnostics and explicit cleanup utilities.

## Requirements

Python 3.10+, Docker, curl, an Ollama server with a downloaded chat model, and an operator-provided Signal account. The lifecycle scripts use Bash on Linux or macOS. Use an account whose messages you intend the bot to process.

## Setup and configuration

The original deployment registered a **dedicated Signal account and phone number on the server** through the REST API supplied by `bbernhard/signal-cli-rest-api`.

| Guide | Coverage |
| --- | --- |
| [SETUP.md](SETUP.md) | Container creation, standalone registration and verification, ACI discovery, transport checks, Ollama, groups, lifecycle, and troubleshooting. |
| [CONFIGURATION.md](CONFIGURATION.md) | Every environment variable, path, default, state scope, and restart requirement. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Module map, actual receive/send commands, blocking work, account locking, and persistence. |

Clone and install before following the setup guide:

```bash
git clone https://github.com/hynesc/signal-assistant.git
cd signal-assistant
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
```

Register and verify your account with the container's REST API, then set `BOT_NUMBER`, `BOT_UUID`, and `ADMIN_NUMBERS`. Once setup is complete:

```bash
./start_bot.sh
./stop_bot.sh
```

During normal operation the bot runs **CLI receive/send commands through `docker exec`**, sharing the account created through the REST API. Device linking is an alternative setup, not a prerequisite for the dedicated-number arrangement.

Contacts are optional context, not an access allowlist. Use an account whose incoming messages you intend the bot to process. The supplied scripts use a local account mount and port 8080; custom paths or ports must be changed consistently as described in the guides.

## Commands

Send these from an administrator account, using the configured prefix (default `/bot`):

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

For example, `/bot persona assistant` selects the included `assistant` persona. To add a persona, create `signal_bot/personas/<name>/system.txt`. Optional role templates live under its `roles/` directory. Persona changes are application-wide; model, temperature, and mute settings are chat-scoped.

## Data handling and limits

Signal encrypts messages in transit, but the bot decrypts messages on its host and sends conversation context to the configured Ollama endpoint. Optional think-mode searches send the query to DuckDuckGo. Contacts, account keys, sessions, and runtime data are local private files ignored by Git.

The stop script deletes its log file and attachments and attempts to clear two SQLite send-log tables. This is best-effort housekeeping, **not a guarantee of complete history removal or secure erasure**. Account credentials remain, and upstream logs, backups, crash output, and other database tables may retain information. A foreground shutdown does not invoke the stop script. Review diagnostics and exception output before sharing them.

This is a self-hosted prototype. The included container uses the upstream `latest` image; pin a tested version for repeatable deployments. There is no hosted demo connected to a real account.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests use temporary account fixtures and fake clients; no real Signal account or running model is required. GitHub Actions runs the suite on Python 3.10 and 3.12 and builds the Python wheel. See [ARCHITECTURE.md](ARCHITECTURE.md) for the runtime flow and Signal account locking constraints, and [PUBLISHING.md](PUBLISHING.md) for the initial repository push.
