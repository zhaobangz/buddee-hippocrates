#!/usr/bin/env python3
"""
Demo walkthrough guide — PT‑9012 (Marcus Holloway).

Prints the shot list one beat at a time and opens the demo URL in the
default browser. Press Enter to advance to the next beat. Use alongside
a screen recorder (QuickTime, OBS, or macOS Cmd+Shift+5) for a clean,
deterministic 60‑second demo capture.

Usage:
    python scripts/demo_walkthrough.py
    VITE_API_BASE_URL=https://buddi-demo.vercel.app python scripts/demo_walkthrough.py

Requirements:
    - Backend must be running (deterministic stub, no LLM keys, BAA=0)
    - Frontend must be running at VITE_API_BASE_URL (default: http://localhost:5173)
    - Python 3.10+ (webbrowser + input only)
"""
from __future__ import annotations

import os
import sys
import time
import webbrowser

FRONTEND_URL = os.environ.get(
    "VITE_API_BASE_URL", "http://localhost:5173"
).rstrip("/")

BEATS = [
    {
        "time": "0:00",
        "title": "Land on demo",
        "caption": "Buddi Health — deterministic synthetic demo (zero LLM spend, zero PHI)",
        "action": f"Browser opens → {FRONTEND_URL}/?demo=true",
    },
    {
        "time": "0:05",
        "title": "Patient loads",
        "caption": "PT‑9012 (Marcus Holloway) — Safe‑Harbor synthetic patient",
        "action": "Dashboard shows patient card + 'DEMO MODE' banner",
    },
    {
        "time": "0:10",
        "title": "Run shadow audit",
        "caption": "Shadow‑mode HCC audit runs in <2s — deterministic, no LLM call",
        "action": "Click 'Run Shadow Audit' or navigate to /shadow",
    },
    {
        "time": "0:18",
        "title": "Review suggestions",
        "caption": "3 missed HCC codes · $15,700 estimated · each with evidence + confidence",
        "action": "Highlight: E11.22 ($8,400), N18.31 ($4,100), I12.9 ($3,200)",
    },
    {
        "time": "0:26",
        "title": "Open audit trail",
        "caption": "Every suggestion is written to the hash‑chained audit trail",
        "action": "Click 'Audit Trail' in the left sidebar",
    },
    {
        "time": "0:31",
        "title": "Show chain",
        "caption": "Each event links to its predecessor via SHA‑256 — tamper‑evident",
        "action": "Scroll through events — show hash + previous_hash columns",
    },
    {
        "time": "0:39",
        "title": "Verify chain",
        "caption": "Daily Merkle root signed — the artifact auditors request",
        "action": "Click 'Verify Chain' — show verification result",
    },
    {
        "time": "0:47",
        "title": "Review queue",
        "caption": "Every suggestion is queued for human review — Buddi drafts, clinicians decide",
        "action": "Click 'Review Queue' tab — show 'Human Review Required' badges",
    },
    {
        "time": "0:55",
        "title": "End card",
        "caption": f"Try it: {FRONTEND_URL}/?demo=true",
        "action": "Return to Dashboard — 'DEMO MODE' banner visible — fade out",
    },
]


def main() -> int:
    print("🎬  Buddi Demo Walkthrough Guide")
    print(f"    Target: {FRONTEND_URL}/?demo=true")
    print(f"    Beats:  {len(BEATS)}")
    print("    Est. duration: ~60s")
    print()
    print("    Press Enter to advance to the next beat.")
    print("    Press Ctrl+C to exit at any time.")
    print()

    # Open the demo URL in the default browser.
    demo_url = f"{FRONTEND_URL}/?demo=true"
    print(f"🌐  Opening {demo_url} …")
    webbrowser.open(demo_url)
    time.sleep(2)

    for i, beat in enumerate(BEATS):
        print()
        print("─" * 60)
        print(f"  BEAT {i + 1}/{len(BEATS)}  [{beat['time']}]  {beat['title']}")
        print("─" * 60)
        print(f"  📺  Caption: {beat['caption']}")
        print(f"  🖱️   Action:  {beat['action']}")
        print()

        if i < len(BEATS) - 1:
            try:
                input("  ⏎  Press Enter for next beat…")
            except (EOFError, KeyboardInterrupt):
                print("\n\n🛑  Walkthrough stopped.")
                return 0
        else:
            print("  🏁  End of walkthrough. Stop recording.")

    print()
    print("✅  Demo walkthrough complete.")
    print()
    print("Claims‑lint checklist (review before publishing):")
    print("  ☐ Never says 'HIPAA compliant' — say 'HIPAA‑aligned posture'")
    print("  ☐ Never says 'auto‑submits' — say 'Buddi drafts, clinicians submit'")
    print("  ☐ Never implies live AI during demo — say 'deterministic synthetic demo'")
    print("  ☐ Revenue numbers labeled 'estimated' and 'synthetic'")
    print("  ☐ PRODUCT_TRUTH.md reviewed within last 7 days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
