# Demo Walkthrough — PT‑9012 (Marcus Holloway)

**Duration:** ~60 seconds
**Audio:** No voiceover needed — screen capture with captions.
**Claims safety:** Every claim below is sourced directly from `docs/PRODUCT_TRUTH.md`.
Do not add narration that implies HIPAA compliance, SOC 2, EHR integration,
auto‑submission, or live AI — those are explicitly marked NOT‑SHIPPED.

## Pre‑flight checklist

- [ ] Backend running at the target `VITE_API_BASE_URL` (Render, Fly, or localhost:8001)
- [ ] Frontend running at the demo URL (Vercel, or localhost:5173)
- [ ] `BUDDI_BAA_CONFIRMED=0` on the backend (verified)
- [ ] No LLM API keys set on the backend (verified — deterministic stub)
- [ ] Browser in incognito/private window (clean state, no cookies)
- [ ] DevTools closed (clean capture)
- [ ] Screen resolution ≥ 1440×900, browser zoom 100%

## Shot list (timestamped)

| Time | Duration | What to show | On‑screen caption |
|------|----------|-------------|-------------------|
| 0:00 | 5s | Open browser, paste URL `https://<app>.vercel.app/?demo=true` | "Buddi Health — deterministic synthetic demo (zero LLM spend, zero PHI)" |
| 0:05 | 5s | Landing: dashboard loads with PT‑9012 patient card visible. The demo banner ("DEMO MODE — Synthetic data only") is visible. | "Loads PT‑9012 (Marcus Holloway) — a Safe‑Harbor synthetic patient" |
| 0:10 | 8s | Click "Run Shadow Audit" (or it auto‑fires from `?demo=true`). Progress indicator: "Retrieving guidelines…" → "Running analysis…" → "Complete." | "Shadow‑mode HCC/revenue audit runs in <2s — deterministic rule‑based path, no LLM call" |
| 0:18 | 8s | Scroll to the identified codes table. Highlight the three surfaced codes: **E11.22** (diabetic CKD, $8,400), **N18.31** (CKD stage 3a, $4,100), **I12.9** (hypertensive CKD, $3,200). Point out the evidence quotes and confidence scores. | "3 missed HCC codes found · $15,700 estimated recoverable revenue · each with evidence quote + confidence" |
| 0:26 | 5s | Switch to the **Audit Trail** tab (left sidebar). | "Every suggestion is written to the hash‑chained audit trail" |
| 0:31 | 8s | The audit events list is visible — scroll to show the `shadow_mode_rcm` events. Point out the cryptographic hash column and previous‑hash linking. | "Each event links to its predecessor via SHA‑256 — a tamper‑evident chain" |
| 0:39 | 8s | Click **"Verify Chain"** button. Show the verification result: chain verified, event count, status. | "Daily Merkle root signed + chain verification — the artifact auditors request" |
| 0:47 | 8s | Briefly toggle to the **Review Queue** tab to show the queued suggestions with "Human Review Required" badges. | "Every suggestion is queued for human review — Buddi drafts, clinicians decide" |
| 0:55 | 5s | End on the Dashboard with the "Demo mode" banner clearly visible. Fade out. | "Try it: <public‑demo‑url>/?demo=true — deterministic, zero LLM spend, zero PHI" |

## Optional: auto‑drive with Playwright

A script at `scripts/demo_walkthrough.py` drives the same path programmatically
so you can screen‑record a clean, deterministic take.

```bash
# Install Playwright browsers once:
npx playwright install chromium

# Run (reads VITE_API_BASE_URL from env, defaults to localhost:5173):
VITE_API_BASE_URL=http://localhost:5173 python scripts/demo_walkthrough.py

# Or against a live deployment:
VITE_API_BASE_URL=https://buddi-demo.vercel.app python scripts/demo_walkthrough.py
```

The script pauses at each beat so the screen recorder captures the state cleanly.
Press Enter to advance to the next beat.

## Claims‑lint checklist (review before publishing)

- [ ] Never says "HIPAA compliant" — say "HIPAA‑aligned posture"
- [ ] Never says "auto‑submits" — say "Buddi drafts, clinicians submit"
- [ ] Never implies a live AI model when demo mode is active — say "deterministic synthetic demo"
- [ ] Never claims EHR integration — the demo uses a committed fixture, not a live FHIR endpoint
- [ ] Revenue numbers are labeled "estimated" and "synthetic"
- [ ] `docs/PRODUCT_TRUTH.md` has been reviewed within the last 7 days (check date at top of file)
