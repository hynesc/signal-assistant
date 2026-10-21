# Configuration reference

Restart the application after environment changes. Lifecycle scripts load `.env`; export it for foreground runs and diagnostics. Contacts load at startup; persona templates load at startup or when switched.

## Account, routing, and inference

| Variable | Default | Purpose |
| --- | --- | --- |
| `BOT_NUMBER` | Empty; required | Bot's registered Signal number in E.164 format. |
| `BOT_UUID` | Empty; required | Bot's ACI/service identifier for group mention detection. |
| `ADMIN_NUMBERS` | Empty; required | Comma-separated E.164 sender numbers allowed to execute administrator commands. |
| `BOT_MENTION_NAME` | `Assistant` | Text trigger such as `@Assistant` in a group. |
| `BOT_CMD_PREFIX` | `/bot` | Administrator command prefix and group message trigger. |
| `BOT_PERSONA` | `assistant` | Directory name under `signal_bot/personas/`. |
| `CONTACTS_FILE` | Repository `contacts.json` | Optional local JSON contact names and tone roles. Missing file means no configured contacts. Relative paths use the process working directory. |
| `OLLAMA_URL` | `http://localhost:11434/api/chat` | Complete native Ollama chat endpoint, including `/api/chat`. |
| `MODEL_ID` | `llama3.1:8b` | Model already downloaded on that Ollama server. |

Contacts are context and tone settings, not an allowlist. Any incoming direct-message sender can get a reply. Group messages enter processing for number/UUID mentions, matching text mentions, or a command prefix. Administrator handlers check the sender against `ADMIN_NUMBERS`; non-admin command-like text can still be processed as ordinary conversation.

## Transport and account paths

| Variable | Default | Purpose |
| --- | --- | --- |
| `SIGNAL_CONTAINER_NAME` | `signal-assistant-api` | Container passed to `docker exec`; lifecycle scripts use the same name. |
| `SIGNAL_CLI_BINARY` | `signal-cli-native` | Executable inside the container; `signal-cli` is an alternative. |
| `SIGNAL_CLI_CONFIG_DIR` | `/home/.local/share/signal-cli` | Container-side account root, passed as `--config`. |
| `SIGNAL_DATA_DIR` | Repository `signal-data/data` | Host-side data subdirectory read by account diagnostics and sender-ID lookup. |
| `RECEIVE_TIMEOUT_SECONDS` | `30` | Normal CLI receive window; receive is shortened to one second while reply tasks are active. |

The supplied scripts mount repository `signal-data/` at the container config root and probe `http://localhost:8080/v1/about`. `SIGNAL_DATA_DIR` changes the application's host-side reader only; it does not change the scripts' bind mount or cleanup root. For a custom storage layout, adapt those scripts and the container together rather than changing just one variable. `MODE`, `LOG_LEVEL`, and `AUTO_RECEIVE_SCHEDULE` are upstream container variables; putting them in the bot's `.env` does not reconfigure an already-created container.

## Account storage layout

| Host path | Container view / use |
| --- | --- |
| `signal-data/` | Mounted at `/home/.local/share/signal-cli`. |
| `signal-data/data/accounts.json` | Account index used by readiness checks. |
| `signal-data/data/<account-path>` | Account state; readiness expects `registered=true`. |
| `signal-data/data/<account-path>.d/account.db` | Recipient lookup and selected send-log tables. |

These paths depend on the upstream version. Reuse the mount when recreating the container to retain account identity.

## Concurrency and conversation state

| Variable | Default | Purpose |
| --- | --- | --- |
| `MAX_IN_FLIGHT_MESSAGES` | `4` | Maximum message-processing tasks inside the inference semaphore. |
| `STATE_TTL_SECONDS` | `86400` | Idle lifetime of in-memory conversation/settings state. Pruned during receive-loop iterations. |
| `MAX_CACHED_SERVICE_IDS` | `2048` | Bound on cached Signal service-ID-to-number lookups. |
| `SUMMARY_EVERY` | `10` | Summarize once history reaches twice this many message entries. |
| `SUMMARY_MAX_TOKENS` | `300` | Generation limit for a conversation summary. |
| `THINK_MAX_TOKENS` | `600` | Generation limit for think-mode replies. |

History is a fixed 20-entry deque. A `SUMMARY_EVERY` value above 10 will never reach its trigger with that history bound. Memory is keyed by direct-message sender or by group plus sender. Model, temperature, and mute settings are shared per group, or per sender for direct messages. Persona switching affects the whole application. State and runtime overrides are not persisted across restarts.

Ordinary generation uses a temperature of 0.75, or 1.0 for the example `friendly` contact role, unless a chat overrides it. Summarization uses 0.3 and think mode uses 0.6. HTTP timeouts are fixed in code: ordinary/summary requests use 120 seconds, think mode 180 seconds, and search 15 seconds. The CLI send timeout is 60 seconds. These are implementation constants, not extra environment settings.

## Persona templates

Create `signal_bot/personas/<name>/system.txt` with the system prompt. Optional tone overrides go in its `roles/` directory and are selected by a contact's `role` in `contacts.json`. `/bot persona <name>` switches the application-wide persona; `/bot persona assistant` selects the included example. Model, temperature, and mute overrides remain chat-scoped.

## Private local files

- `.env`: account identifiers, operator settings, and endpoint overrides.
- `contacts.json`: local contact identities and roles; `contacts.example.json` contains fictional entries.
- `signal-data/`: registration, cryptographic identity, sessions, and databases.
- `bot.log` and `.bot.pid`: runtime log and checkout-specific process ID.

Git ignores these files. Keep private material out of examples. `--doctor`, `--print-config`, manual CLI output, and exception logs can expose identifiers despite routine message-log redaction.

Signal encrypts messages in transit; the host handles decrypted messages and sends context to Ollama. Think-mode searches send queries to DuckDuckGo.

The stop script removes `bot.log` and attachments and attempts to clear the SQLite `message_send_log` and `message_send_log_content` tables with `DELETE` and `VACUUM`. Account credentials remain; other tables, upstream logs, backups, and crash output may retain data. This is best-effort housekeeping, not complete history removal or secure erasure. A foreground shutdown does not invoke the stop script.

## Diagnostics and operation

`--doctor` validates configuration and local account readiness; `--check-account-ready` checks readiness after validation. `--print-config` and `--print-bot-number` deliberately print configuration values. None of these performs a complete Signal-and-Ollama round trip.

For first registration, manual send/receive checks, group setup, lifecycle steps, and troubleshooting, use [SETUP.md](SETUP.md). [ARCHITECTURE.md](ARCHITECTURE.md) maps the code modules and locking behavior.
