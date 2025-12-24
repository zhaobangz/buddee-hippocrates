"""Project-level optional settings.

This file provides a safe, editable set of defaults for developer convenience.
Runtime configuration should come from environment variables or
`config/credentials.json` for secrets.
"""

import os

# Human-friendly defaults
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Buddi")
USE_VOICE = os.getenv("USE_VOICE", "False").lower() == "true"
MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "True").lower() == "true"

# Work domain hints the assistant can use (example only)
WORK_DOMAINS = {
    "coding": ["debugging", "code review", "algorithm design", "documentation"],
    "writing": ["emails", "reports", "documentation", "presentations"],
    "research": ["web search", "data analysis", "summarization"],
    "planning": ["task management", "scheduling", "priority setting"],
    "communication": ["email drafting", "meeting notes", "follow-ups"]
}

# NOTE: Do not hard-code API keys here. Use environment variables or
# `config/credentials.json` (gitignored) to store secrets.

