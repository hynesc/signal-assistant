# Signal Assistant

A configurable Signal chatbot with local Ollama inference, isolated conversation memory, template personas, and administrator commands. Python owns the application logic; a Docker container provides `signal-cli` and its account state.

This public edition includes a neutral assistant persona and fictional contacts. Account identifiers and administrator numbers must be supplied by the operator. No account data, chat logs, personal personas, or previous Git history are included.

## Features

- Replies to direct messages and explicitly mentioned group messages.
- Serializes Signal CLI access and conversation processing while allowing inference across different chats concurrently.
- Keeps conversation history in memory with rolling summaries and an idle-state expiry.
- Supports per-chat model, temperature, and mute settings through administrator commands.
- Loads text-based personas and optional contact tone templates.
- Offers an administrator-only think command with DuckDuckGo search when query heuristics match.
- Omits message text, sender names, phone numbers, and group identifiers from routine incoming-message logs.
- Includes account diagnostics and explicit cleanup utilities.

## Requirements

Python 3.10+, Docker, curl, an Ollama server with a downloaded chat model, and an operator-provided Signal account. The lifecycle scripts use Bash on Linux or macOS. Use an account whose messages you intend the bot to process.

## Setup

Clone the public repository:

```bash
git clone https://github.com/hynesc/signal-assistant.git
cd signal-assistant
```

Run from the project directory:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
```

Edit `.env` and set `BOT_NUMBER` (E.164), `BOT_UUID` (Signal service identifier), and `ADMIN_NUMBERS` (comma-separated E.164 numbers). There are no built-in account or administrator defaults. `OLLAMA_URL` is the full chat endpoint, ending in `/api/chat`. Set `MODEL_ID` to a model installed on your Ollama server.

Optionally copy `contacts.example.json` to `contacts.json` and replace the fictional entries. Contacts are not an access allowlist: the bot responds to any incoming direct message. Only numbers in `ADMIN_NUMBERS` can change settings or use think mode.

Create the container for initial account setup:

```bash
mkdir -p signal-data
docker run -d --name signal-assistant-api \
  -p 127.0.0.1:8080:8080 \
  -v "$PWD/signal-data:/home/.local/share/signal-cli" \
  -e MODE=normal -e LOG_LEVEL=warn \
  bbernhard/signal-cli-rest-api:latest
```

Link it as a device by opening `http://localhost:8080/v1/qrcodelink?device_name=signal-assistant` and scanning the QR code from Signal's linked-device settings. Registration and verification of a standalone account is another option. Follow the upstream [Signal CLI REST API setup guide](https://github.com/bbernhard/signal-cli-rest-api) for account setup and supported CLI binaries.

With the bot stopped, obtain the account's ACI (service identifier) from your local Signal CLI account metadata or account-management tooling and set `BOT_UUID`. Do not share the account metadata file; it also contains private registration state.

The diagnostics require the account state under `signal-data/data/` to match the configured number and report `registered=true`. Account layouts can vary by upstream version. If diagnostics fail, check the local account state before starting.

```bash
./start_bot.sh
./stop_bot.sh
```

The scripts load `.env` automatically. For diagnostics or a foreground run, export its values first:

```bash
set -a
source .env
set +a
.venv/bin/python run_bot.py --doctor
# Or run in the foreground:
.venv/bin/python run_bot.py
```

`--doctor` and `--print-config` deliberately display account configuration; do not publish their output.

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
| `persona assistant` | Switch the application-wide persona. |
| `clearall` | Clear all in-memory history and chat settings. |

To add a persona, create `signal_bot/personas/<name>/system.txt`. Optional role templates live under its `roles/` directory. Persona changes are application-wide; model, temperature, and mute settings are chat-scoped.

## Data handling and limits

Signal encrypts messages in transit, but the bot decrypts messages on its host and sends conversation context to the configured Ollama endpoint. Optional think-mode searches send the query to DuckDuckGo. Contacts, account keys, sessions, and runtime data are local private files ignored by Git.

The stop script deletes its log file and attachments and attempts to clear two SQLite send-log tables. This is best-effort housekeeping, **not a guarantee of complete history removal or secure erasure**. Account credentials remain, and upstream logs, backups, crash output, and other database tables may retain information. A foreground shutdown does not invoke the stop script. Review diagnostics and exception output before sharing them.

This is a self-hosted prototype. The included container uses the upstream `latest` image; pin a tested version for repeatable deployments. There is no hosted demo connected to a real account.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests use temporary account fixtures and fake clients; no real Signal account or running model is required. GitHub Actions runs the suite on Python 3.10 and 3.12 and builds the Python wheel. See [ARCHITECTURE.md](ARCHITECTURE.md) for the runtime flow and Signal account locking constraints, and [PUBLISHING.md](PUBLISHING.md) for the initial repository push.
