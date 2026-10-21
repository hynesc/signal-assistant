# Standalone Signal account setup

The original deployment used a dedicated phone number registered on the server through `bbernhard/signal-cli-rest-api`. This guide follows that arrangement. The API registers a number you already control; it does not provide a phone number. Device linking is an alternative, covered below.

The REST API handles initial registration and verification. During normal operation, this application invokes `signal-cli` inside the same container with `docker exec` for receiving and sending. There is no webhook, callback server, REST receive loop, or WebSocket client in the Python bot.

## 1. Install and configure the host application

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
```

Set `BOT_NUMBER` to the dedicated number in E.164 format and `ADMIN_NUMBERS` to the operator's number(s). Leave `BOT_UUID` blank until registration is complete. Keep the default container name and paths for this walkthrough.

Export the file for the commands below:

```bash
set -a
source .env
set +a
signal_api_url=http://127.0.0.1:8080
```

The Python entrypoint does not load `.env` itself. The start and stop scripts do load it.

## 2. Create the account container

```bash
mkdir -p signal-data
docker run -d --name "$SIGNAL_CONTAINER_NAME" \
  -p 127.0.0.1:8080:8080 \
  -v "$PWD/signal-data:/home/.local/share/signal-cli" \
  -e MODE=normal -e LOG_LEVEL=warn \
  bbernhard/signal-cli-rest-api:latest
curl -fsS "$signal_api_url/v1/about"
```

The host needs Docker access; the Python process calls `docker exec` and reads the mounted account files. Keep the bind mount when recreating the container. It contains the registration, identity keys, sessions, and account database.

`MODE=normal` avoids a continuously running account daemon. The bot independently selects `signal-cli-native` with `SIGNAL_CLI_BINARY`; if that binary is unavailable on the chosen image/platform, set `SIGNAL_CLI_BINARY=signal-cli`. Check it while the bot is stopped:

```bash
docker exec "$SIGNAL_CONTAINER_NAME" "$SIGNAL_CLI_BINARY" --version
```

Do not use `MODE=json-rpc` or `json-rpc-native` with this direct-CLI implementation. Do not enable `AUTO_RECEIVE_SCHEDULE`: another consumer could remove messages before the bot sees them. The upstream image documents these execution modes and receive scheduling in its [README](https://github.com/bbernhard/signal-cli-rest-api#execution-modes). Record the image tag/digest and CLI version you test; `latest` can change.

If the server is remote, access the loopback API through SSH rather than publishing port 8080. For example, from your laptop use `ssh -L 8080:127.0.0.1:8080 user@server` and keep that session open. All registration commands below run on the server or through that tunnel.

## 3. Register and verify the dedicated number

Keep the bot stopped during account setup. Request an SMS verification:

```bash
curl -fsS -X POST -H 'Content-Type: application/json' \
  "$signal_api_url/v1/register/${BOT_NUMBER}"
```

If using voice verification instead, submit `--data '{"use_voice":true}'` with the same POST. If Signal asks for a CAPTCHA, follow the upstream [registration examples](https://github.com/bbernhard/signal-cli-rest-api/blob/master/doc/EXAMPLES.md) and retry with a JSON `captcha` field. Use the current challenge instructions rather than repeatedly requesting codes.

Complete verification with the code delivered to that number:

```bash
read -r -s -p 'Verification code: ' signal_verification_code
printf '\n'
curl -fsS -X POST -H 'Content-Type: application/json' \
  "$signal_api_url/v1/register/${BOT_NUMBER}/verify/${signal_verification_code}"
unset signal_verification_code
curl -fsS "$signal_api_url/v1/accounts"
```

Use a new dedicated account for this flow. If the number already has an account or registration protection, follow the upstream recovery/verification requirements before proceeding. Do not register again merely to troubleshoot an otherwise working installation.

## 4. Set the bot's service identifier

With no bot or other account consumer running:

```bash
docker exec "$SIGNAL_CONTAINER_NAME" "$SIGNAL_CLI_BINARY" \
  --config "$SIGNAL_CLI_CONFIG_DIR" -o json listAccounts
```

Find the entry matching `BOT_NUMBER` and copy its ACI into `BOT_UUID` in `.env`. Current upstream JSON uses `aci`; older versions may use a different identifier field. `/v1/accounts` lists account numbers and is not the UUID lookup. Do not copy an entire private account file into configuration or documentation.

Reload `.env` after editing, then diagnose the installation:

```bash
set -a
source .env
set +a
.venv/bin/python run_bot.py --doctor
.venv/bin/python run_bot.py --check-account-ready
```

Diagnostics inspect local files; they do not prove that a live send or model request will succeed. They expect `signal-data/data/accounts.json`, a matching account entry, and an account state file marked `registered=true`. Upstream storage formats can change. Review failures locally rather than publishing account data or diagnostic output.

## 5. Understand and check the message transport

The container also exposes these upstream HTTP routes:

| Purpose | Upstream REST route |
| --- | --- |
| API information | `GET /v1/about` |
| Registered account numbers | `GET /v1/accounts` |
| Account registration | `POST /v1/register/{number}` |
| Code verification | `POST /v1/register/{number}/verify/{code}` |
| Send a message | `POST /v2/send` |
| Receive in normal/native mode | `GET /v1/receive/{number}` |

In daemon modes, upstream receive behavior differs and can use WebSockets. This bot uses the non-daemon direct CLI transport described in [ARCHITECTURE.md](ARCHITECTURE.md).

For an optional one-time HTTP send check, set `SIGNAL_TEST_RECIPIENT` to a consenting recipient's E.164 number, then run:

```bash
curl -fsS -X POST -H 'Content-Type: application/json' \
  --data "{\"number\":\"${BOT_NUMBER}\",\"recipients\":[\"${SIGNAL_TEST_RECIPIENT}\"],\"message\":\"Setup test\"}" \
  "$signal_api_url/v2/send"
```

The bot's receive command is equivalent to:

```bash
docker exec "$SIGNAL_CONTAINER_NAME" "$SIGNAL_CLI_BINARY" \
  --config "$SIGNAL_CLI_CONFIG_DIR" -o json -a "$BOT_NUMBER" \
  receive -t 5 --ignore-attachments --ignore-stories --ignore-avatars --ignore-stickers
```

Run that manually only while the bot is stopped. Receiving consumes pending messages, so messages read during a setup check will not later appear as new messages to the bot. Do not poll the REST receive route and CLI simultaneously. Normal bot sends use CLI `send --message ...` with either a recipient or `--group-id`; no HTTP send endpoint needs to be configured in Python.

## 6. Configure Ollama and start

Run Ollama on the host or another reachable machine, and download `MODEL_ID` there. The Python process runs on the host, so `OLLAMA_URL=http://localhost:11434/api/chat` refers to the host's Ollama service, not the Signal container.

```bash
ollama pull llama3.1:8b
curl -fsS http://localhost:11434/api/tags
./start_bot.sh
```

Use the configured model name and URL if you changed the defaults. Send a direct message from a separate Signal account and verify a reply. From an administrator account, try `/bot status`. Add the bot to a group and mention `@Assistant` (or the configured mention name) to test group routing. Group IDs come from incoming messages and do not need to be hardcoded.

```bash
./stop_bot.sh
```

The stop script stops this checkout's background process and container, removes its log, and attempts attachment/send-log cleanup. Account identity remains. This is not complete history deletion or secure erasure. For foreground mode, export `.env`, ensure the container is running, and run `.venv/bin/python run_bot.py`; press Ctrl-C to end the foreground Python process, then use the stop script for its container and cleanup steps.

## Alternative: link an existing account

Instead of registration and SMS verification, a supported linked-device setup can use `http://localhost:8080/v1/qrcodelink?device_name=signal-assistant` and scan it in the mobile app's linked-device settings. This is a different account arrangement from the dedicated-number deployment. Continue with identifier discovery and diagnostics; the implementation still expects the local account layout described above.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Container cannot publish 8080 | Another service owns the port. The supplied lifecycle scripts use host port 8080; a custom port also requires editing their readiness URL. |
| Account lock/hanging CLI | Stop the bot before manual account operations. Check for a daemon mode, auto-receive schedule, or second consumer. |
| Missing native executable | Set `SIGNAL_CLI_BINARY=signal-cli`, reload `.env`, and check the image's available binaries. |
| Missing/incorrect account state | Match the bind mount, `BOT_NUMBER`, host data path, and container config path. Diagnostics need the original account identity files. |
| Permission denied reading state | Make the mounted files readable to the bot's host user; do not broadly expose the account directory. |
| Ollama cannot be reached | Check the host process's URL, downloaded model, network binding, and firewall. |
| Admin command does not change settings | The incoming sender must resolve to an E.164 number listed in `ADMIN_NUMBERS`. |
| Group message is ignored | Verify membership and an actual number/UUID mention, the text mention name, or command-prefix trigger. |

See [CONFIGURATION.md](CONFIGURATION.md) for every application setting. Upstream API examples and the [Signal CLI manual](https://github.com/AsamK/signal-cli/blob/master/man/signal-cli.1.adoc) were checked during preparation; installed image versions may differ.
