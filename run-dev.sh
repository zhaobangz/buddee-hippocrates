#!/usr/bin/env bash
# Development helper for setting up and running Buddi locally.
# Usage: ./run-dev.sh [options]
# Options:
#   --install    Create venv and install requirements
#   --check      Run scripts/startup_check.py
#   --run-main   Run python main.py
#   --run-sidebar Run sidebar demo

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
VENV_DIR="$ROOT_DIR/venv"

# Detect whether the script is being sourced. When sourced, we can activate
# the venv in the caller's shell. When executed, we perform actions in a
# subshell and cannot change the parent shell environment.
SCRIPT_SOURCED=0
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
  SCRIPT_SOURCED=1
fi

function create_venv() {
  if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "Created venv at $VENV_DIR"
  fi
  # Install requirements using the venv's python
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/pip" install -r "$ROOT_DIR/requirements.txt"

  # If the user sourced this script, auto-activate the venv in their shell
  if [ "$SCRIPT_SOURCED" -eq 1 ]; then
    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"
    echo "Virtualenv activated in current shell."
  else
    echo "Virtualenv created at $VENV_DIR. To activate it in your shell run:"
    echo "  source $VENV_DIR/bin/activate"
  fi
}

function run_check() {
  # Use venv python if present
  if [ -f "$VENV_DIR/bin/python" ]; then
    "$VENV_DIR/bin/python" "$ROOT_DIR/scripts/startup_check.py"
  else
    python3 "$ROOT_DIR/scripts/startup_check.py"
  fi
}

function run_main() {
  if [ -f "$VENV_DIR/bin/python" ]; then
    "$VENV_DIR/bin/python" "$ROOT_DIR/main.py"
  else
    python3 "$ROOT_DIR/main.py"
  fi
}

function run_sidebar() {
  if [ -f "$VENV_DIR/bin/python" ]; then
    "$VENV_DIR/bin/python" "$ROOT_DIR/ui/widget.py" --sidebar
  else
    python3 "$ROOT_DIR/ui/widget.py" --sidebar
  fi
}

if [ ${#@} -eq 0 ]; then
  echo "Run with --install, --check, --run-main or --run-sidebar"
  echo "Example: ./run-dev.sh --install --check"
  exit 0
fi

while [ ${#@} -gt 0 ]; do
  case "$1" in
    --install)
      create_venv
      shift
      ;;
    --activate)
      if [ -f "$VENV_DIR/bin/activate" ]; then
        # If the script is being sourced, activate the venv in current shell.
        if [ "$SCRIPT_SOURCED" -eq 1 ]; then
          # shellcheck disable=SC1090
          source "$VENV_DIR/bin/activate"
          echo "Activated venv in current shell."
        else
          echo "To activate the venv in your shell, run:"
          echo "  source $VENV_DIR/bin/activate"
        fi
      else
        echo "No venv found. Run './run-dev.sh --install' first."
      fi
      shift
      ;;
    --check)
      run_check
      shift
      ;;
    --run-main)
      run_main
      shift
      ;;
    --run-sidebar)
      run_sidebar
      shift
      ;;
    *)
      echo "Unknown option: $1"
      shift
      ;;
  esac
done
