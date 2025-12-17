# buddi

buddi is a personal AI assistant designed to act as a "virtual twin," capable of understanding your screen, listening to your voice, and performing tasks on your computer. It uses a Large Language Model (LLM) to interpret natural language commands and execute them using a modular set of tools.

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