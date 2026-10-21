# Signal Assistant Architecture

This document outlines how the Signal chatbot is structured and how it interacts with Docker and the Signal network.

## 1. High-Level Components

*   **Logic Layer (`run_bot.py` / `signal_bot.bot`)**: A Python entrypoint and runtime module running on the host (often inside a `venv`). It manages the active persona, conversation history, and handles message processing via an asynchronous loop.
*   **Persona Manager (`signal_bot.persona`)**: A template-based system that loads persona definitions (system prompts and role overrides) from the `signal_bot/personas/` directory.
*   **Command Registry (`signal_bot.commands`)**: A modular registry for admin commands (e.g., `/bot reset`, `/bot persona`), allowing for easy extension of bot capabilities.
*   **Signal Interface (`signal-assistant-api` container)**: A Docker container running the `bbernhard/signal-cli-rest-api` image. The bot communicates with the Signal network by executing the configured CLI binary inside this container via `docker exec`. The REST API is used for setup and readiness checks, not normal message delivery.
*   **Brain Layer (Ollama)**: The bot sends conversation context to an Ollama instance to generate responses.
*   **Storage Layer (Bind Mount)**: Account credentials, group metadata, and cryptographic keys are stored under the host `signal-data/` directory, which is bind-mounted into the container.

## 2. The Data Flow

1.  **Receive**: The Python script runs a continuous loop calling `docker exec signal-assistant-api signal-cli-native receive`. This "pulls" new messages from the Signal servers.
2.  **Process**:
    *   The script parses the JSON output from `signal-cli`.
    *   It resolves the sender identity and active persona templates.
    *   It checks the modular **Command Registry** for admin instructions.
    *   If a response is needed, it sends the history and persona context to the Ollama API.
3.  **Send**: Once the LLM responds, the script calls `docker exec signal-api signal-cli send` to deliver the message.

## 3. Critical Architectural "Gotchas"

### The Configuration Lock
The `signal-cli` tool uses a strict file-level lock on its configuration directory.
*   **The Conflict**: Only one process can access the Signal account at a time.
*   **The Consequence**: Because the bot is almost always running a `receive` command, any manual attempt to run `signal-cli` (e.g., to update a profile or list groups) will hang or fail.
*   **The Fix**: You **must** stop the bot script (`./stop_bot.sh`) before running manual maintenance commands.

### Host vs. Container Data
There is a potential discrepancy between the host files and the container view:
*   **Host Path**: `signal-data/` exists on your disk.
*   **Container Path**: `/home/.local/share/signal-cli/` inside the container.
*   **Reality**: The container is configured with a direct bind-mount to the host's `signal-data` folder, so those host files are the live Signal account state the bot uses.

## 4. Common Maintenance Commands

### Stopping the Bot Safely
```bash
# Stops the Python logic and the Docker container
./stop_bot.sh
```

### Updating Profile (Name/Avatar)
*Must be done while bot logic is stopped.*
```bash
docker exec signal-assistant-api signal-cli-native -a <bot_number> updateProfile --name "New Name" --avatar /path/in/container/image.jpg
```

### Starting the Bot
```bash
./start_bot.sh
```
