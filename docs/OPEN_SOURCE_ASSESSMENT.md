# Open‑Source Readiness Assessment — Decision Aid

**Status:** Draft for founders' decision (manual §2.1, §5.2)
**Date:** 2026-07-21
**Decision required:** Both founders, one page of rationale, before any license change

---

## 1. What would become public

### Audit‑chain core (the "verify our math yourself" surface)

These modules are the structural moat — making them public lets prospects and auditors independently verify the chain math, which is a sales asset per manual §9.1:

| Module | LOC | What it proves |
|--------|-----|----------------|
| `core/merkle.py` | ~250 | Daily Merkle‑root construction + KMS signing |
| `core/ledger.py` | ~200 | Hash‑chained audit event ordering |
| `core/phi_guard.py` | 78 | BAA tripwire + PHI‑processing precondition |
| `core/safety.py` | 383 | PII redaction patterns, `redact_for_logs` |
| `core/secure_fields.py` | 80 | App‑layer envelope encryption (PBKDF2+Fernet) |
| `backend/auth.py` | 185 | Argon2 API‑key hashing, scope‑based authorization |
| `evals/metrics.py` | ~210 | Precision/recall/citation math |

### Must stay private (never public)

| Asset | Reason |
|-------|--------|
| `growth/outreach/` | Prospect lists, email templates, competitive positioning |
| `growth/outbox/` | Contact PII (already gitignored) |
| `evals/golden_set/` | Clinician‑labeled data (even de‑identified, labeling strategy is moat) |
| `docs/*.pptx` | Strategy, financial projections, pitch deck |
| `config/credentials.json` | Secrets (gitignored) |
| Any prompt templates in `core/agent.py` | Prompt engineering is competitive moat |
| `data/` ingest scripts with real CMS crosswalks | Licensed data derivatives |

### Gray area (requires founder call)

| Asset | Risk if public | Benefit if public |
|-------|---------------|-------------------|
| `core/agent.py` (prompt paths) | Reveals prompt‑engineering strategy | Shows clinical‑reasoning rigor |
| `core/llm_manager.py` | Reveals provider‑routing logic | Shows BAA‑guard architecture |
| `evals/red_team/` prompts | Attackers see our defense surface | Security researchers can contribute |
| `backend/smart_fhir.py` | Reveals integration surface before partnerships | Shows FHIR competency |
| `backend/billing.py` | Reveals pricing mechanics to competitors | Shows revenue‑model transparency |

---

## 2. License options — one‑page trade‑off

| License | Copyleft? | "Verify our chain" possible? | VC‑friendliness | Competitor risk |
|---------|-----------|------------------------------|-----------------|----------------|
| **AGPL‑3.0** | Strong (network use = distribution) | Yes — anyone can read + verify + run | Mixed — some enterprises avoid AGPL like GPL | Low — competitors must open their modifications |
| **BSL (Business Source License) 1.1** | Time‑delayed (becomes open after N years) | Yes — source is visible from day 1 | Good — common in devtools (Sentry, CockroachDB) | Medium — competitors can read but not compete on the same code for N years |
| **Apache 2.0 / MIT** | None | Yes | Excellent — enterprises love permissive | High — anyone can fork and compete immediately |
| **Dual AGPL + commercial** | Strong for OSS, paid for proprietary | Yes | Good — monetization path (MongoDB, Elastic model) | Low — commercial users pay; competitors need a license |
| **Stay private** | N/A | No — must spin up a hosted verifier | Irrelevant for now | None |

**Recommendation for discussion:** AGPL‑3.0 for the audit‑chain core (modules listed in §1 above), with a separate private repo for `growth/`, `evals/golden_set/`, and prompt templates. This gives the "verify our chain math yourself" sales asset without exposing the full clinical reasoning strategy or business pipeline.

---

## 3. Proposed repo split

```
buddee-health-hippocrates (PUBLIC — AGPL‑3.0)
├── core/
│   ├── merkle.py          ✅ public
│   ├── ledger.py          ✅ public
│   ├── phi_guard.py       ✅ public
│   ├── safety.py          ✅ public
│   ├── secure_fields.py   ✅ public
│   ├── db_session.py      ✅ public (RLS patterns)
│   └── agent.py           ⚠️  redact prompt templates first
├── backend/
│   ├── auth.py            ✅ public
│   └── api.py             ⚠️  audit routes only; redact clinical routes
├── evals/
│   ├── metrics.py         ✅ public
│   └── run_eval.py        ✅ public
└── tests/ (audit‑chain tests only)

buddee-health-private (PRIVATE)
├── core/agent.py          (full prompt templates)
├── core/llm_manager.py    (provider routing)
├── growth/
├── evals/golden_set/
└── backend/api.py         (full clinical routes)
```

---

## 4. Pre‑push checklist (must complete before any public push)

- [ ] Run `gitleaks detect --source .` — already in CI; verify clean on current HEAD
- [ ] Remove or redact all `# TODO(human)` comments that reference internal strategy
- [ ] Redact prompt templates from `core/agent.py` (replace with `<REDACTED — see private repo>` stubs)
- [ ] Remove `docs/*.pptx` from the public repo
- [ ] Confirm no API keys, credentials, or secrets in git history (the July‑18 reset was done for this purpose)
- [ ] Add `CONTRIBUTING.md` — contribution guidelines
- [ ] Add `CODE_OF_CONDUCT.md` — standard CNCF or Contributor Covenant
- [ ] Add `SECURITY.md` — vulnerability disclosure policy (security@buddi.health)
- [ ] Add `LICENSE` file — AGPL‑3.0 (or chosen license)
- [ ] Add license headers to all public `.py` files
- [ ] Both founders sign off on the license choice and repo split (§5.2)

---

## 5. Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Competitor forks and rebrands the audit‑chain core | Low (audit math is commodity; integration + clinical reasoning is the moat) | AGPL ensures modifications come back |
| Security researcher finds a vulnerability via public code | Medium (more eyes = more findings, which is net positive) | `SECURITY.md` + responsible disclosure policy |
| AGPL scares off an enterprise pilot | Low‑Medium (pilot customers license the SaaS; they aren't self‑hosting) | Offer commercial license for on‑prem deployments |
| Open‑sourcing reveals how thin the clinical reasoning layer is | Low (the demo is already public and deterministic) | Redact prompt templates; keep `core/agent.py` private |

---

## 6. Decision

**Decision:** _________________________ (AGPL / BSL / Apache / stay private)

**Rationale:** _________________________

**Signed (both founders):**

_________________________  Date: _________

_________________________  Date: _________

**Next step after decision:** Create the public repo, apply the split, add LICENSE + governance files.
