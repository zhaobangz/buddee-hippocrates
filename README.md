# buddi

buddi is a personal AI assistant designed to act as a "virtual twin," capable of understanding your screen, listening to your voice, and performing tasks on your computer. It uses a Large Language Model (LLM) to interpret natural language commands and execute them using a modular set of tools.

Don't you hate doing repetitive tasks that a computer should have done for you like apply for internships that match your linkedIn profile, filling out excel sheets with data on paper, and following up with a logical line of questions when attempting to accomplish a task. 

## Features

*   **Conversational AI:** Engages in coherent conversations using an external LLM (e.g., DeepSeek) with persistent memory.
*   **Screen Perception:** Can take screenshots and perform OCR to read text from the screen (optional, requires `pytesseract`).
*   **Audio Input:** Captures audio snippets for voice commands (optional, requires `sounddevice`).
*   **Extensible Tools:** A modular architecture allows for easy addition of new capabilities, such as:
    *   Web browsing
    *   File management
    *   System search

## Project Structure

The project is organized into the following directories:

| Path               | Description                                                                                             |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| `main.py`          | The main entry point that runs the application's primary input-process-output loop.                     |
| `core/`            | Contains the core logic, including the `Agent` orchestrator, `LLMManager`, and conversation `Memory`.   |
| `tools/`           | Holds the various tools the agent can use to perform actions (e.g., browsing, file search).             |
| `input_output/`    | Manages user interaction, with modules for text and speech I/O.                                         |
| `ui/`              | Contains UI components, like the screen and audio capture widget.                                       |
| `config/`          | Stores configuration files, such as API credentials and settings.                                       |
| `data/`            | Used for storing persistent data, like the agent's memory database.                                     |
| `requirements.txt` | A list of Python dependencies for the project.                                                          |

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd buddi
    ```

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *Note: Some features require optional dependencies. See `ui/widget.py` for details on enabling full functionality.*

4.  **Configure Credentials:**
    Add your API keys (e.g., for the LLM) to `config/credentials.json`. You may need to create this file from a template if one exists.

## Usage

To run the assistant, execute the main script from the project root:

```bash
python3 main.py
```

## Docker

Use Docker to ensure a consistent environment for all contributors.

# buddi

buddi is a local, modular AI assistant that uses an LLM to interpret natural language commands and perform actions on your machine. It supports text and optional voice I/O, screen capture + OCR, and a set of tools for automating tasks locally.

## Quick overview

- Conversational AI with persistent memory
- Optional screen capture and OCR (Pillow + pytesseract)
- Optional audio input and TTS (sounddevice, SpeechRecognition, pyttsx3)
- Extensible tools (browser, file manager, search, system)
- Tracing and observability via OpenTelemetry (OTLP exporter)

## Project Structure

- `main.py` — application entrypoint and main loop
- `core/` — agent logic, LLM manager, memory, and tracing integration
- `tools/` — pluggable tools the agent uses to perform actions
- `input_output/` — text and speech handlers
- `ui/` — optional UI widget for screen/audio capture
- `config/` — configuration and credentials
- `data/` — persistent data (e.g., `memory.db`)
- `requirements.txt` — Python dependencies

## What's new: Tracing

This project includes OpenTelemetry tracing. Key points:

- Tracing is initialized in `core/tracing.py` and wired into `main.py` and `core/agent.py`.
- Traces are exported via OTLP (default endpoint `http://localhost:4318`) so you can view them with the AI Toolkit Trace Viewer or any OTLP-compatible collector.
- Automatic instrumentation is enabled for HTTP requests (`requests`) and manual spans are added around intent detection, input handling, tool calls, and LLM requests.

To open the trace viewer in VS Code, run the command: `AI Toolkit: Open Trace Viewer` (this starts the collector at `localhost:4318`).

If you need a different OTLP endpoint, set `OTEL_EXPORTER_OTLP_ENDPOINT` in your environment.

## Setup (recommended)

1. Clone and enter the repo:

```bash
git clone <repository-url>
cd buddi
```

2. Create and activate a virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate   # macOS / Linux
# On Windows: venv\\Scripts\\activate
```

Note: this project may also work inside a Conda environment, but system audio and PortAudio dependencies are often easier to manage with Homebrew/apt and a standard venv.

3. Install dependencies:

```bash
pip install -r requirements.txt
```

If you previously tried `pip install PIL`, use `Pillow` instead; the project depends on `Pillow`.

On macOS, audio packages such as `pyaudio` may require PortAudio via Homebrew:

```bash
brew install portaudio
pip install pyaudio
```

4. Configure credentials

Add your LLM/api keys to `config/credentials.json` or export the appropriate environment variables (e.g., `LLM_API_KEY`, `LLM_PROVIDER`, `LLM_API_URL`). Keep secrets out of git.

## Running the assistant

With the venv active:

```bash
python main.py
```

Or use the full venv python path (if VS Code hasn't activated the venv in the terminal):

```bash
./venv/bin/python main.py
```

To use tracing while running, open the trace viewer in VS Code first (`AI Toolkit: Open Trace Viewer`).

## Docker

Docker is supported via `docker-compose.yml`. Copy `.env.example` to `.env` and adjust values, then:

```bash
docker-compose up --build -d

# attach a shell
docker-compose exec app bash

# stop
docker-compose down
```

## Dev helper scripts

Use `run-dev.sh` to create a venv, install deps, run checks, and launch the app. Examples:

```bash
# install deps into venv
./run-dev.sh --install

# source the venv for interactive use
source ./run-dev.sh --activate

# run startup checks
./run-dev.sh --check

# run the assistant
./run-dev.sh --run-main
```

## Troubleshooting

- Pillow vs PIL: install `Pillow` (the package name is not `PIL`).
- pyaudio on macOS: install PortAudio first (`brew install portaudio`) then `pip install pyaudio`.
- If audio or screen capture fails, verify macOS permissions: System Preferences → Security & Privacy → Screen Recording / Microphone.
- OpenTelemetry: if you don't see traces, open the AI Toolkit Trace Viewer (`AI Toolkit: Open Trace Viewer`) or set `OTEL_EXPORTER_OTLP_ENDPOINT` to your collector URL.
- Virtual environment confusion: ensure you activate the project's venv (`source venv/bin/activate`) or use the venv python path.

## Contributing

Contributions are welcome. Please open issues for bugs or feature requests. For larger changes, open a PR with a clear description and tests where applicable.

## License

(Add license details here)
