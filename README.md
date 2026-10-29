# BRIGHTNOVA AI STUDIO

**Build Locally. Think Beyond.**

BrightNova AI Studio is a native Ubuntu desktop workspace for local AI-assisted software development. It combines Ollama server control, model management, streaming chat, live system telemetry, VS Code, and project-level OpenCode configuration in one dark PySide6 application.

All inference stays on your machine. There are no paid API keys, cloud inference calls, telemetry, or automatic model downloads.

---

## Features

- **Dashboard** with real Ollama health checks, server controls, live resource cards, and functional quick actions.
- **Ollama server management** with detection of existing, external, and systemd-managed instances.
- **Dynamic model discovery** from `/api/tags`; load and unload state comes from `/api/ps`.
- **Streaming local chat** with Markdown rendering, session history, cancellation, clearing, and response copying.
- **Development projects** with per-project model selection and safe OpenCode configuration.
- **OpenCode integration** using the installed CLI's OpenAI-compatible local provider format.
- **VS Code and terminal launching** inside the selected project directory.
- **Live system monitor** for CPU, RAM, disk, Ollama process memory, and loaded models.
- **Persistent local settings**, timestamped configuration backups, logging, and background workers.
- **Ubuntu application launcher** through a generated `.desktop` entry.

---

## Requirements

- Ubuntu Linux with a graphical session.
- Python 3.10 or newer.
- Ollama installed and on `PATH`.
- At least one locally installed Ollama model.
- Optional: VS Code (`code`), OpenCode (`opencode`), and a supported terminal emulator.

The application is tuned for CPU-only inference. A 7B model is usable but slower than a 3B model on integrated graphics; the interface remains responsive because server, model, chat, and monitoring operations run outside the GUI thread.

---

## Installation

### 1. Install system prerequisites

```bash
sudo apt update
sudo apt install python3-venv python3-pip libxcb-cursor0 libxkbcommon-x11-0
```

Install Ollama from the official package for your Ubuntu release, then verify:

```bash
ollama --version
systemctl status ollama --no-pager
```

### 2. Create the Python environment

```bash
cd /home/brightdev/Desktop/BrightNova_AI
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Prepare local models

BrightNova never downloads models by itself. Install them explicitly if needed:

```bash
ollama pull qwen2.5-coder:3b
ollama pull qwen2.5-coder:7b
ollama list
```

### 4. Run BrightNova

```bash
./run.sh
```

`run.sh` automatically uses `.venv/bin/python` when the virtual environment exists.

---

## First Run

1. BrightNova checks `http://127.0.0.1:11434/api/version`.
2. The dashboard shows **BRIGHT NOVA IS ONLINE** only after that health check succeeds.
3. Open **AI Models** to inspect the models returned by Ollama.
4. Select a model, then open **AI Chat** to begin a local session.
5. Add a project under **Development Projects**.
6. Configure OpenCode for the project and launch it.

The default mentor system prompt can be changed in **Settings**. Changes apply to new chat sessions.

---

## Ollama Server Control

BrightNova distinguishes four states:

| State | Behavior |
| --- | --- |
| Existing systemd service | Connects to it; stop/restart uses `systemctl` through PolicyKit when required. |
| External process | Connects without starting a duplicate; BrightNova refuses to kill an unrelated process. |
| BrightNova-owned process | Starts `ollama serve` on localhost, tracks the child process, and stops only that child. |
| Offline | Reports offline and offers a real start attempt. |

- Health is determined from the Ollama API, not from the presence of a process.
- Start/stop/restart operations run in worker threads.
- Systemd stop/restart prompts for confirmation by default.
- The API endpoint remains bound to `127.0.0.1:11434`.

If PolicyKit is unavailable, service control returns an actionable error instead of silently failing.

---

## Model Management

Model cards show data from Ollama, including:

- technical model ID and display name;
- size, parameter count, and quantization;
- actual loaded state from `/api/ps`;
- Select, Run, and Unload actions.

`Run Model` loads a model with a 30-minute keep-alive. `Unload Model` sends `keep_alive: 0` and asks for confirmation because it can interrupt active work.

---

## AI Chat

- Streams `/api/chat` responses token by token.
- Keeps the current session history in memory.
- Renders Markdown in assistant bubbles.
- Stops an in-flight response without freezing the interface.
- Copies the last response or any individual assistant response.
- Clears the session after confirmation.
- Uses the configured mentor system prompt.

Chat cancellation closes the active HTTP stream from the worker and safely discards partial state if the conversation is cleared.

---

## OpenCode Integration

BrightNova detects the installed OpenCode version and writes project-level configuration using OpenCode's current custom-provider format.

Example generated configuration:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local)",
      "options": {
        "baseURL": "http://127.0.0.1:11434/v1"
      },
      "models": {
        "qwen2.5-coder:3b": {
          "name": "qwen2.5-coder:3b"
        },
        "qwen2.5-coder:7b": {
          "name": "qwen2.5-coder:7b"
        }
      }
    }
  },
  "model": "ollama/qwen2.5-coder:7b"
}
```

### Integration workflow

1. Open **Development Projects** and choose **Add Project**.
2. Select the project directory and local model.
3. Choose **Configure OpenCode**.
4. If `opencode.json` or `opencode.jsonc` already exists, approve the update.
5. BrightNova preserves other providers and settings, writes the Ollama provider, sets the selected default model, and creates a timestamped backup.
6. Choose **Open in VS Code** or **Launch OpenCode**.

The **OpenCode Integration** page re-reads the actual project configuration and only marks the integration ready when an Ollama provider is present. BrightNova does not claim a model has project access merely because a button was clicked.

### Supported configuration behavior

- Prefers an existing `opencode.jsonc`, then `opencode.json`.
- Parses JSON with line comments, block comments, and trailing commas.
- Never overwrites a configuration without explicit confirmation.
- Backs up the original file before updating.
- Writes atomically to avoid partial configuration files.
- Launches OpenCode inside the project working directory.
- Supports Ptyxis, GNOME Terminal, Konsole, Xfce Terminal, kitty, xterm, and the `x-terminal-emulator` alternative.

To verify the generated file manually:

```bash
cd /path/to/project
opencode debug config
```

The resolved configuration should include the `ollama` provider and `ollama/qwen2.5-coder:7b` model.

---

## System Monitor

The monitor refreshes every two seconds by default, using a background worker:

- CPU percentage and a rolling CPU chart.
- Total, used, and available RAM with memory pressure.
- Disk total, used, free, and percentage.
- Ollama process RSS across matching processes.
- Models currently loaded by Ollama, with memory and expiry data.

The interval is configurable from 1 to 10 seconds in **Settings**. Monitoring uses `psutil` counters and a short local `/api/ps` timeout so it does not block inference or the interface.

---

## Desktop Launcher

Install BrightNova into the Ubuntu application menu:

```bash
./scripts/install_desktop.sh
```

This creates `~/.local/share/applications/brightnova-ai-studio.desktop` with the correct absolute path and icon. Re-run the script if the project directory moves.

The repository also includes `BrightNova.desktop`, preconfigured for the current workspace path.

---

## Project Layout

```text
BrightNova_AI/
├── main.py
├── run.sh
├── requirements.txt
├── README.md
├── BrightNova.desktop
├── assets/
│   └── icons/
├── brightnova/
│   ├── config.py
│   ├── context.py
│   ├── logging_setup.py
│   ├── ollama_manager.py
│   ├── project_manager.py
│   ├── system_monitor.py
│   └── workers.py
├── scripts/
│   └── install_desktop.sh
├── tests/
└── ui/
    ├── about_page.py
    ├── chat_page.py
    ├── dashboard.py
    ├── main_window.py
    ├── models_page.py
    ├── monitor_page.py
    ├── opencode_page.py
    ├── projects_page.py
    ├── settings_page.py
    ├── styles.qss
    └── widgets.py
```

Backend modules contain no Qt code, so they can be tested without a display.

---

## Tests

Run the backend suite with the virtual environment:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The suite covers:

- settings persistence, corruption recovery, project storage;
- JSONC parsing, safe OpenCode merges, backups, provider preservation;
- Ollama health, model discovery, load/unload, streaming, cancellation, and error handling;
- protection against stopping externally managed Ollama processes;
- real system monitor sampling.

UI construction can be smoke-tested headlessly:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python main.py
```

---

## Logs and Configuration

- Settings: `~/.config/brightnova/settings.json`
- Logs: `~/.config/brightnova/logs/brightnova.log`
- Owned Ollama log: `~/.config/brightnova/logs/ollama.log`

The settings file is written atomically. A corrupt settings file is preserved with a timestamp before defaults are restored. Logs rotate at 2 MB with three backups.

---

## Troubleshooting

### BrightNova reports Ollama offline but `ollama list` works

Check that the API is reachable:

```bash
curl http://127.0.0.1:11434/api/version
systemctl status ollama --no-pager
```

If Ollama is running in another environment or container, make sure it is bound to `127.0.0.1:11434` and accessible to the desktop user.

### Start Server fails for the systemd service

Systemd control may require PolicyKit:

```bash
systemctl start ollama
```

BrightNova invokes `pkexec systemctl ...` when not running as root. If no authentication agent is available, start the service manually.

### PySide6 fails to load the platform plugin

Install the XCB runtime libraries:

```bash
sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1
```

On Wayland, Qt may use the Wayland plugin; the XCB fallback can be selected with `QT_QPA_PLATFORM=xcb` when needed.

### OpenCode cannot find the model

Verify the resolved configuration and Ollama's OpenAI-compatible endpoint:

```bash
cd /path/to/project
opencode debug config
curl http://127.0.0.1:11434/v1/models
```

Make sure the model ID in `provider.ollama.models` exactly matches the ID returned by Ollama.

### Launch OpenCode does nothing

Check that a supported terminal and the OpenCode CLI are installed:

```bash
command -v opencode
command -v ptyxis || command -v gnome-terminal || command -v x-terminal-emulator
```

OpenCode is a terminal user interface and cannot be launched as a detached GUI process.

### Chat is slow or the 7B model takes a long time to load

CPU-only inference is expected to be slower. Use `qwen2.5-coder:3b` for faster iteration, close memory-heavy applications, and keep the monitor interval at two seconds or higher.

### A model unload interrupts work

Unloading is confirmed before execution because Ollama may be serving other clients. Stop active chat or other tools first.

---

## Migration Note

The workspace supplied for this build did not contain a prior `BrightNova.py`, so this is a fresh, complete V3 implementation of the supplied specification. No unspecified legacy behavior was removed. If an earlier file becomes available, its features can be analyzed and mapped into the modular backend and UI without weakening the current architecture.

---

## Security and Privacy

- Ollama communication is restricted to the configured local endpoint, defaulting to `127.0.0.1:11434`.
- No application telemetry or analytics.
- No automatic package or model installation.
- No API keys are required or stored.
- Existing OpenCode configuration is backed up before an approved merge.
- Destructive or externally visible actions require confirmation or are refused.

**BRIGHTNOVA AI STUDIO** — *Build Locally. Think Beyond.*
