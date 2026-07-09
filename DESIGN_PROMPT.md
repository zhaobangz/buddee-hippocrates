# Design Prompt for Claude Code — Buddee Health Portal UX Redesign

Paste this entire document into Claude Code, run from the repo root (`buddee-health-hippocrates/`).

---

## Mission

Redesign the Buddee Health portal (`frontend/`) so it is **approachable, usable, and logical for hospital-system users**: medical coders / CDI specialists, compliance officers and auditors, clinicians, revenue-cycle managers, and hospital IT admins. Keep the React + Tailwind stack and the existing routes (`/`, `/chat`, `/shadow`, `/audit`), but you are free to restructure navigation, information architecture, and every component within them.

A set of reference mockups accompanies this prompt (`Portal Redesign Mockups.dc.html`). Match their layout, tone, and token values.

## Why (diagnosis of the current UI — verify by reading these files first)

Read before writing any code: `frontend/src/App.jsx`, `components/Layout.jsx`, `components/Sidebar.jsx`, `components/TopBar.jsx`, `pages/Dashboard.jsx`, `pages/ShadowPage.jsx`, `pages/AuditPage.jsx`, `pages/ChatPage.jsx`, `components/PatientBrief.jsx`, `components/AnalyticsDashboard.jsx`, `index.css`, `tailwind.config.js`, and `docs/PRODUCT_TRUTH.md`.

Problems to fix:

1. **Consumer-app aesthetic in a clinical tool.** Dark glassmorphism (`glass-panel`, `mesh-background`, glow animations, gradient text) reads as a crypto dashboard, not hospital software. Hospitals run bright rooms and daytime shifts; procurement expects a calm, light, clinical UI.
2. **Contrast & type-size failures.** Pervasive `text-[10px]` uppercase labels and `text-slate-500` on `#020617` fail WCAG 2.1 AA. Minimum body text 14px, minimum label 12px, all text ≥ 4.5:1 contrast.
3. **Engineering jargon leaks into the UI.** "Shadow Mode" as a nav item, `Tenant …{uuid}`, raw `audit_hash`, `human_review_required` enum strings, "Tamper-Evident Hash Chain", "GENESIS". Users know clinical/RCM terms (HCC, CDI, prior auth, E11.9) — keep those; translate engineering terms (see Terminology Map).
4. **Personas are blended on one screen.** `Dashboard.jsx` mixes clinical decision support (hyperkalemia risk, retinal exam reminders, "ORDER NOW") with RCM metrics. Clinical-care suggestions imply capabilities the product does not have (see PRODUCT_TRUTH.md) — remove them entirely.
5. **The core workflow is buried.** A coder's job is: work a queue of flagged encounters → review evidence → accept/dismiss codes. The current Shadow page is a paste-a-note dev form. The redesign centers a **Review Queue**.
6. **Trust is decorative, not structural.** The product's moat is "Buddee suggests; your team approves; every review is written to a verifiable audit trail." That promise must be persistent, plainly worded, and load-bearing in the UI — not a blinking `SHADOW MODE ACTIVE` pill.
7. **Broken/dead elements.** Sidebar "History" links to a route that does not exist; chat input is absolutely positioned and overlaps content; the API-key prompt is a bare modal with no product framing; hardcoded demo patient (`Marcus Holloway`) is presented as real data in `PatientBrief.jsx`.
8. **Marketing voice in-product.** "let's find the revenue you've already earned", "Run a Live Demo" gradient CTAs. Product voice should be calm, specific, and second-person-professional.

## Design system (replace the current tokens)

Apply in `tailwind.config.js` + `index.css`. Ship **both light and dark themes** via the existing `darkMode: 'class'`; **light is the default**. Persist the choice (`localStorage`) with a toggle in Settings/top bar.

**Type.** IBM Plex Sans (400/500/600/700) for UI; IBM Plex Mono for codes, record IDs, timestamps. Google Fonts, self-host or link in `index.html`. Remove Inter. Scale: 14px base UI, 16px reading text, 13px secondary, 12px min for labels (sentence case — kill the 10px uppercase-tracking-widest pattern everywhere), 20/24/30px headings. `text-wrap: pretty` on headings.

**Light theme tokens.**
- Background `#F6F7F5` (warm neutral); surface/cards `#FFFFFF`; borders `#E3E7E4`; subtle fill `#EEF1EF`.
- Ink: primary `#15302D`, secondary `#4A625E`, muted `#6E827F` (never lighter for meaningful text).
- Primary action: teal `#0F766E` (hover `#115E59`), white text. Solid buttons only — no gradients, no glow shadows, no `active:scale-95`.
- Status (AA on white): positive `#047857`, caution `#B45309`, risk `#BE123C`, info `#1D4ED8`. Use tinted backgrounds (`#ECFDF3`, `#FEF3E2`, `#FDECEF`) with dark text — not translucent white-alpha layers.

**Dark theme tokens.** Background `#0E1B1A`; surface `#152423`; border `rgba(255,255,255,0.09)`; ink `#E8EFED` / `#9FB4B0`; primary `#2DD4BF` on dark with `#06302B` text for filled buttons. No mesh background, no blur, no glass.

**Shape & density.** 8px radius cards, 6px controls (retire `rounded-3xl`). 8px spacing grid; calm and spacious — one primary subject per screen, generous whitespace, max content width 1200px. Cards: 1px border + `0 1px 2px rgba(21,48,45,0.06)` shadow max. Delete `.glass-panel`, `.glass-card`, `.mesh-background`, `.orb-glow`, gradient text, `float`/`glow` keyframes.

**Motion.** 150–200ms ease-out fades/position only. Remove framer-motion hover-lift on cards and pulsing dots (a static colored dot is fine).

## Terminology map (apply everywhere, including empty states and toasts)

- "Shadow Mode" (nav/page) → **Review Queue**; explain the mode inline once: "Buddee reviews encounters in the background and suggests codes. Nothing is billed or submitted without your team's approval."
- "Tamper-Evident Hash Chain" / "Merkle root" → **"Verifiable audit trail"** with plain subtext: "Every review is permanently recorded. Records are cryptographically linked so any alteration is detectable." Keep the crypto detail in an expandable "Technical details" section for compliance officers.
- `audit_hash` → **Record ID** (mono, truncated, copy button, full value on expand).
- `human_review_required` → badge **"Needs coder review"**; `verified` → "Verified"; `not_checked` → "Not yet verified".
- `Tenant …{uuid}` → the organization's display name (add to tenant context; fall back to "Your organization" + ID under an info tooltip for IT admins).
- "AI Active" → remove; replace with meaningful status only when it changes behavior (e.g. "Demo mode — sample data" banner).
- Keep as-is: HCC, CDI, prior auth, ICD-10 codes, RAF, encounter, payer.

## Information architecture

**Navigation (left sidebar, keep):** Today (`/`) · Review Queue (`/shadow`) · Ask Buddee (`/chat`) · Audit Trail (`/audit`) · Settings. Remove the dead "History" item. Sidebar footer: real user name + role, org name, sign out.

**Persistent trust bar (new, in `Layout.jsx`):** a single quiet strip under the top bar, visible on every page: "**Shadow mode** — Buddee suggests, your team approves. Nothing is submitted automatically." plus an audit-status chip ("Audit trail verified · 2,341 records") linking to `/audit`. This replaces the three blinking status pills in `TopBar.jsx` and `Sidebar.jsx`.

**Top bar:** global search (patients, codes, encounters, ⌘K), theme toggle, notifications, user menu. Remove the "Reviewing {patient}" block — patient context belongs to the Review Queue detail view, not global chrome.

**Right rail (`PatientBrief.jsx`):** remove from the global layout. Its content (patient demographics, relevant labs/meds *as documented evidence*) moves into the Review Queue's encounter detail pane. Never show clinical "focus areas" or care suggestions.

## Screen specs

### 1) Sign in / Connect (replace `ApiKeyPrompt` in `App.jsx`)
Full-page, centered card on the light background (not a modal over a broken app). Logo + product name, one-line value statement ("Coding review and audit support for your revenue-cycle team"), API-key field with show/hide, helper text "Your key stays in this browser's memory — never saved to disk", link "Where do I find my key?" for IT admins, and a small footnote row: "Shadow mode only · Verifiable audit trail · No auto-submission". On 401 mid-session, show the same page with "Your session key is no longer valid."

### 2) Today (Dashboard, `/`)
Audience: coders start their day; managers glance at outcomes.
- Header: "Good morning, {name}" + date. Plain, no gradient text, no revenue slogans.
- **Primary card — "Your queue":** count of encounters awaiting review, oldest-item age, one primary button "Open review queue". This is the biggest thing on the page.
- **Three metric cards** (from existing `/api/metrics`): Identified revenue (MTD) with "pending your team's review" caption; Suggestions accepted vs dismissed (this week); Audit trail status ("Verified · n records", last verified time, link to Audit Trail). Keep `SLOPanel` data but demote it to a collapsed "System status" section for IT admins.
- **Demo affordance:** a clearly-bounded "Sandbox" card — "Try Buddee on a synthetic patient (no PHI, nothing is recorded against your organization)" with a secondary button. Never a gradient hero CTA.
- Remove entirely: risk-factor cards, "Buddi's Suggestions" clinical panel, "ORDER NOW", welcome banner (fold its one useful sentence into the trust bar).

### 3) Review Queue (`/shadow`)
Two-pane master–detail, the heart of the product.
- **Left pane — queue list:** encounters with patient (name + MRN), date, payer, n suggestions, total est. value, status badge (Needs review / Reviewed / Abstained). Filters: status, date, value. Keyboard: ↑/↓ to move, Enter to open.
- **Right pane — encounter detail:** patient header (demographics only); then one card per suggested code: `E11.22 — Type 2 diabetes with diabetic CKD`, est. value, confidence shown as a labeled band ("High confidence · 87%") not a bare percent, and — most important — the **evidence quote from the note, verbatim, highlighted**, with "From the clinical note, {date}". Actions per card: **Accept** (primary) / **Dismiss** (secondary, requires a reason from a short list). Footer of the pane: "Accepted codes are exported for your billing workflow — Buddee never submits claims." Abstained items appear in a collapsed "Buddee abstained on n items" section with plain-language reasons.
- Keep the paste-a-note form as a secondary "Manual check" tab for ad-hoc audits (same form as today, restyled), not the default view.
- The existing demo flow (`loadDemoPatient` → `runShadowAudit`) seeds the queue with the synthetic patient, labeled "Sample — synthetic data".

### 4) Audit Trail (`/audit`)
Audience: compliance officers/auditors first.
- Header: "Audit trail" + subtext "A permanent, verifiable record of every review." Buttons: "Verify integrity" (primary-quiet) and "Export (JSON)".
- **Status banner (persistent, not a toast):** green "Integrity verified across n records · last checked {time}" or red "Verification failed at record n — contact support". Replaces the ephemeral `verifyMessage`.
- **Event table** (not cards): Time · Event ("Coding review completed", "Suggestion accepted by J. Rivera") · Actor · Patient/encounter ref · Status badge. Row expands to details: full Record ID (mono, copy), linked previous record, payload summary, and a "Technical details" disclosure containing hashes/chain info for those who want it.
- Right column: "How verification works" plain-language card (3 short sentences + technical disclosure) and **honest compliance posture** — keep the existing FE-04 stance verbatim in spirit: pre-certification, no badges until audits complete. Remove the mock "Pending Confirmations / EHR Write / APPROVE-REJECT" panel — the product does not write to EHRs (PRODUCT_TRUTH.md).

### 5) Ask Buddee (`/chat`)
- Normal flex column (fix the absolutely-positioned input). Empty state: "Ask about coding, documentation, or prior auth for the encounter you're reviewing" + 3–4 starter prompts (reuse `askBuddiPrompts`, reworded to RCM tasks only — no clinical-care prompts).
- Messages: user right-aligned teal; Buddee left-aligned white card with citations as a labeled row of chips ("Sources: CMS-HCC v28 · Note, Mar 12"). 16px reading text.
- Persistent quiet footer: "Buddee provides coding and documentation support, not medical advice. Nothing here is submitted anywhere."
- Keep the B6.4 demo-mode banner, reworded: "Demo mode — responses are pre-written samples, not the live clinical agent."

## Accessibility (WCAG 2.1 AA — hard requirement)

- 4.5:1 contrast for all text, 3:1 for large text and UI borders on interactive controls. Audit every token pairing.
- Full keyboard operability: visible `:focus-visible` rings (2px teal offset), logical tab order, queue keyboard nav, Escape closes panes/modals, focus trapped in dialogs and returned on close.
- Semantic HTML: real `<nav>`, `<main>`, `<table>` for audit events, `<button>` everywhere (no clickable divs), form labels bound with `htmlFor`, status messages as `role="status"`/`aria-live="polite"`.
- Hit targets ≥ 40px. `prefers-reduced-motion` disables all transitions. Never encode meaning with color alone — badges always carry text.

## Truthfulness constraints (from `docs/PRODUCT_TRUTH.md` — non-negotiable)

- Never claim HIPAA compliance, SOC 2, EHR integration, or auto-submission. No compliance badges.
- All clinical-care suggestion UI (medication checks, screening reminders, "ORDER NOW") is removed, not restyled.
- Demo/synthetic data is always labeled as such at the point of display.
- "Buddee drafts; clinicians/coders submit" is stated wherever an action could be mistaken for a submission.

## Process & acceptance criteria

1. Read every file listed in the diagnosis section before editing.
2. Update `tailwind.config.js` + `index.css` tokens first; then `Layout`/`Sidebar`/`TopBar`; then pages in order: Sign-in, Today, Review Queue, Audit Trail, Ask Buddee.
3. Keep `useStore` API contracts intact (`runShadowAudit`, `fetchAuditLogs`, `verifyAuditTrail`, `fetchDashboardMetrics`, demo bootstrap, `?demo=true` handler, per-route ErrorBoundaries, FE-06/FE-07 fixes).
4. Done means: no `text-[10px]`, no glass/mesh/glow classes, no uppercase-tracking-widest labels, no dead nav items, light+dark both pass AA, every engineering term in the Terminology Map is translated, `npm run lint` passes, and each screen visually matches the reference mockups.
