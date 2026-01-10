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

- Copy `.env.example` to `.env` and adjust values as needed.
- Build and run with docker-compose:

```bash
docker-compose up --build -d
```

- Attach a shell to the running container:

```bash
docker-compose exec app bash
```

- Stop and remove containers:

```bash
docker-compose down
```

You can also use the helper script `run-dev-docker.sh` to start the service in the foreground for development.

## Dev helper scripts

I added `run-dev.sh` and `scripts/startup_check.py` to make development easier.

- Create venv and install deps (and activate if you `source` the script):

```bash
# Create venv and install packages
./run-dev.sh --install

# To activate the venv in your current shell (so `python` refers to the venv), source the script instead:
source ./run-dev.sh --activate
```

- Run a startup check to validate optional dependencies and device availability:

```bash
./run-dev.sh --check
```

- Run the assistant or the sidebar demo (uses venv python if present):

```bash
./run-dev.sh --run-main
./run-dev.sh --run-sidebar
```

Notes:
- If you used `./run-dev.sh --install` but you didn't `source` it, activate the venv in your shell manually with:

```bash
source ./venv/bin/activate
```


## Environment variables (examples)

Configure behavior and optional features using environment variables. Example:

```bash
# LLM / provider
export LLM_PROVIDER=deepseek
export LLM_API_KEY="your_llm_api_key_here"
export LLM_API_URL="https://api.deepseek.com/v1/chat/completions"

# Enable perception features (optional; require optional deps and OS permissions)
export ENABLE_SCREEN_CAPTURE=True   # requires Pillow
export ENABLE_OCR=True              # requires pytesseract + tesseract engine
export ENABLE_AUDIO=True            # requires sounddevice + numpy

# Memory and voice
export MEMORY_ENABLED=True
export USE_VOICE=False

# Optional: persist file for memory
export MEMORY_PERSIST_FILE=memory.json

# Run the main assistant
python3 main.py

# Or run the sidebar UI demo
python3 ui/widget.py --sidebar
```

Notes:
- On macOS you must grant Screen Recording and Microphone permissions for screen/audio capture.
- Keep API keys out of git; use `config/credentials.json` or environment variables.