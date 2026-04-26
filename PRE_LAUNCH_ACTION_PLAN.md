# Buddi — Founder Pre-Launch Action Plan

**Purpose:** This is the practical execution checklist to get Buddi from “runs locally with issues” to a credible web launch / pilot demo.

**Context:** This plan is based on the terminal analysis from launching the current frontend and backend. The frontend starts cleanly, but the backend currently fails on missing Python dependencies and environment configuration. The UI also calls several backend endpoints that do not exist yet.

---

## Priority Order

Do not jump straight to branding, landing pages, or cloud deployment until Phase 1 is complete.

1. **Make the backend boot reliably.**
2. **Make the frontend talk to real backend routes.**
3. **Turn the mock UI into a real demo workflow.**
4. **Make the revenue recovery and audit trail visible.**
5. **Only then deploy publicly.**

---

## Phase 1 — Make It Actually Run

**Target:** Days 1–3  
**Outcome:** `start_dev.py` should launch backend + frontend without crashing.

### 1.1 Fix the Python Environment

The backend currently crashes with:

```text
ModuleNotFoundError: No module named 'pydantic_settings'
```

The active system Python environment is missing several required backend packages. Use a dedicated virtual environment instead of system Python.

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Missing packages observed during terminal analysis:

- `pydantic-settings`
- `openai`
- `langchain-openai`
- `tiktoken`
- `psycopg2-binary`
- `pgvector`
- `opentelemetry-instrumentation-fastapi`
- `python-json-logger`
- `pytest-asyncio`

Also fix the dependency pin in `requirements.txt`:

```text
starlette==1.0.0
```

That Starlette version does not exist on PyPI. Pin Starlette to the version required by the selected FastAPI version.

### 1.2 Create a Real Local `.env`

Your current `.env` is missing mandatory backend settings. Without these, the app will fail Pydantic settings validation even after packages are installed.

Add these values locally:

```bash
SECRET_KEY=<generate-32-plus-char-random-secret>
BUDDI_STORAGE_KEY=<generate-16-plus-char-random-secret>
DATABASE_URL=postgresql://buddi_user:yourpassword@localhost:5432/buddi
CORS_ORIGINS=http://localhost:5173
API_KEY=<generate-local-dev-api-key>
```

Generate secrets with:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
python3 -c "import secrets; print(secrets.token_hex(16))"
```

Important: Do not commit real `.env` values.

### 1.3 Provision PostgreSQL + pgvector

The backend expects Postgres and pgvector.

Local Docker option:

```bash
docker run -d \
  --name buddi-postgres \
  -e POSTGRES_USER=buddi_user \
  -e POSTGRES_PASSWORD=yourpassword \
  -e POSTGRES_DB=buddi \
  -p 5432:5432 \
  ankane/pgvector
```

Then run migrations:

```bash
source venv/bin/activate
alembic upgrade head
```

### 1.4 Create `frontend/.env`

Make the frontend’s API target explicit:

```bash
echo "VITE_API_BASE=http://localhost:8001/api" > frontend/.env
```

### 1.5 Confirm the App Boots

Run:

```bash
source venv/bin/activate
python3 start_dev.py
```

Expected:

- Backend: `http://127.0.0.1:8001`
- Frontend: `http://localhost:5173`
- No import crashes
- No CORS failure from the browser

---

## Phase 2 — Fix Frontend / Backend Contract

**Target:** Days 4–7  
**Outcome:** The UI should stop calling missing endpoints.

### 2.1 Current Route Mismatches

The frontend currently calls endpoints that do not exist in `backend/api.py`.

| Frontend Call | Current Backend Status | Required Action |
|---|---|---|
| `POST /api/chat/chat` | Missing | Add route or change frontend |
| `GET /api/patient/:id` | Missing | Add route or remove call |
| `GET /api/audit/` | Mismatch | Change to `/audit/query` or add compatible alias |

Recommended path: add backend routes that match the frontend, because the UI is already designed around a chat-style workflow.

### 2.2 Add a Real Chat Route

Add a route similar to:

```text
POST /api/chat/chat
```

Request:

```json
{
  "message": "Find missed HCC codes in this encounter",
  "patient_id": "PT-9012"
}
```

Response:

```json
{
  "response": "...",
  "citations": [],
  "intent_detected": "shadow_mode_rcm"
}
```

Internally, this should call `Agent.handle()` and preserve the safety layer.

### 2.3 Add a Patient Route or Remove the Fake Fetch

Either add:

```text
GET /api/patient/{patient_id}
```

or remove the frontend fetch until real patient storage exists.

For launch/demo, a synthetic patient endpoint is acceptable if clearly labeled as demo data.

### 2.4 Fix Audit Route Naming

Choose one standard route and use it everywhere.

Recommended:

```text
GET /api/audit/query
```

Then update `frontend/src/store/useStore.js` accordingly.

---

## Phase 3 — Turn the Beautiful Mockup Into a Real Demo

**Target:** Days 8–14  
**Outcome:** A prospect can use the product and see one real workflow end-to-end.

### 3.1 Make Shadow Mode Real

`frontend/src/pages/ShadowPage.jsx` is currently hardcoded. This is the highest-leverage product fix.

Implement:

- Clinical note input
- Billed code input
- Submit button
- Backend request to a real shadow-mode route
- Rendered result showing:
  - missed code
  - description
  - clinical justification
  - estimated recovered revenue
  - confidence / review status
  - citations or retrieved guideline snippets

This page should become the core demo.

### 3.2 Make Revenue Recovery the Hero Metric

Buddi should not merely say “AI coding assistant.” It should say:

> “Buddi finds missed reimbursable documentation opportunities and proves every recommendation with a tamper-evident audit trail.”

Add to the dashboard:

- Total estimated recovered revenue
- Number of missed codes found
- Average value per encounter
- Accepted / rejected suggestion rate
- Top code categories recovered

This gives buyers a reason to care immediately.

### 3.3 Make the Audit Trail Visible

The codebase already has cryptographic hash-chain logic. This should be productized.

On `AuditPage.jsx`, show:

- event type
- actor
- timestamp
- current hash
- previous hash
- verification status badge
- “Export audit report” button

Positioning line:

> “Every recommendation is not just logged — it is cryptographically chained for tamper-evident review.”

### 3.4 Add Demo Mode

Most prospects will not have a FHIR bundle ready during a web launch.

Add a `?demo=true` or “Try Sample Patient” workflow that:

- loads synthetic patient `PT-9012`
- preloads realistic T2D / CKD / hypertension data
- runs one shadow-mode audit
- shows `$XX,XXX` in recoverable annual revenue
- shows a verified audit trail event

This lets visitors understand the product in under 60 seconds.

---

## Phase 4 — Make It Stand Out Before Web Launch

**Target:** Days 15–30  
**Outcome:** The product has a memorable hook and credible differentiation.

### 4.1 Position Around a Specific Buyer Pain

Avoid generic positioning like:

> “AI healthcare assistant.”

Use specific positioning:

> “Revenue integrity copilots for value-based care teams.”

or:

> “Shadow-mode HCC and prior-auth review with tamper-evident audit logs.”

### 4.2 Seed the RAG Engine With Credible Sources

Before demoing clinical recommendations, seed the RAG layer with trusted guideline content.

Recommended initial corpus:

- CMS HCC Model V28 references
- ICD-10-CM coding guideline excerpts
- ADA diabetes standards
- ACC/AHA hypertension guidance
- USPSTF preventive care guidance

Every recommendation should have evidence. Evidence is what makes the tool feel trustworthy.

### 4.3 Make Prior Auth Generate an Actual Draft

`POST /prior-auth/generate` currently creates a DB record but does not produce a useful draft artifact.

Before launch, make it return:

- draft letter
- supporting diagnosis codes
- payer-facing rationale
- evidence snippets
- missing information checklist
- copy/export action

This is a concrete workflow a buyer understands instantly.

### 4.4 Remove or Wire Dead UI Controls

The Paperclip and Mic controls in the chat page are currently decorative.

Before launch:

- wire them to file upload / voice input, or
- remove them from the UI

Dead controls reduce trust.

### 4.5 Create a Founder-Led Demo Script

Your launch demo should follow this path:

1. Open dashboard.
2. Click “Try Sample Patient.”
3. Run a shadow-mode audit.
4. Buddi finds 2–3 missed coding opportunities.
5. Dashboard updates recovered revenue.
6. Open audit page.
7. Show cryptographic verification.
8. Generate a prior-auth draft.
9. End with “Book a pilot.”

---

## Phase 5 — Public Web Launch Readiness

**Target:** Days 30–60  
**Outcome:** Buddi can safely accept early users or pilots.

### 5.1 Compliance Basics

Before handling real PHI:

- Have BAAs in place with infrastructure and model providers.
- Publish privacy policy and terms.
- Document that patient data is not used for training.
- Confirm at-rest encryption is actually implemented, not merely configured.
- Confirm logs do not contain raw PHI.

### 5.2 Add Real Multi-Tenant Auth

The current auth posture is API-key oriented. For a web product, implement:

- users
- organizations / tenants
- tenant-scoped data access
- API-key issuance per tenant
- audit events tied to tenant and actor
- JWT expiration and refresh

### 5.3 Deploy With a Real Production Architecture

Recommended lightweight stack:

- Frontend: Vercel
- Backend: Cloud Run, Render, Railway, or Fly.io
- Database: managed Postgres with pgvector
- Secrets: cloud secret manager
- Observability: structured logs + traces + error alerts

Set production `VITE_API_BASE` to the deployed backend.

### 5.4 Add Health Checks, Rate Limits, and Request IDs

Before public traffic:

- Add an unauthenticated internal health endpoint for load balancers.
- Add rate limiting to protect LLM spend.
- Add `X-Request-ID` middleware.
- Attach request IDs to logs, traces, and audit events.

### 5.5 Build a Separate Landing Page

The current React app is an operator dashboard, not a marketing site.

Create a landing page with:

- clear headline
- 60-second demo video
- ROI/revenue recovery claim
- compliance/audit-trail positioning
- waitlist or “Book a Pilot” form
- founder contact

Example headline:

> “Recover missed HCC revenue and prove every AI recommendation with a tamper-evident audit trail.”

---

## The Three Things That Will Make Buddi Stand Out

If time is limited, prioritize these above everything else.

### 1. Real Revenue Recovery

Show a live, believable dollar amount tied to actual agent output.

This is the buyer hook.

### 2. Real Shadow-Mode Workflow

Let a user paste a clinical note and billed codes, then receive ranked missing-code suggestions with rationale and evidence.

This is the product.

### 3. Visible Tamper-Evident Audit Trail

Show hash-chain verification in the UI.

This is the moat.

---

## Immediate Next 10 Tasks

Use this as the next sprint board.

- [ ] Fix invalid / incompatible Python dependency pins.
- [ ] Create and use a clean Python virtual environment.
- [ ] Install backend dependencies from `requirements.txt`.
- [ ] Add required local `.env` values.
- [ ] Run Postgres + pgvector locally.
- [ ] Run Alembic migrations.
- [ ] Start backend and frontend together with `start_dev.py`.
- [ ] Add missing chat, patient, and audit-compatible API routes.
- [ ] Wire `ShadowPage.jsx` to a real backend response.
- [ ] Make recovered revenue and audit verification visible in the UI.

---

## Launch Gate

Do not launch publicly until all of the following are true:

- [ ] Backend starts without import/config errors.
- [ ] Frontend can call backend without CORS failures.
- [ ] No frontend page depends only on hardcoded fake data unless labeled demo.
- [ ] One complete workflow works end-to-end.
- [ ] Audit events are visible and verifiable.
- [ ] Synthetic demo mode works without real PHI.
- [ ] Rate limiting and request IDs are implemented.
- [ ] Secrets are not committed.
- [ ] Production environment variables are configured outside the repo.
- [ ] Landing page has a waitlist or pilot CTA.
