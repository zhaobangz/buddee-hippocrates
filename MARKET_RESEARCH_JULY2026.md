# Buddee — Independent Market Research Report

**Date:** July 21, 2026
**Prepared for:** Zhao (Founder)
**Scope:** Product understanding grounded in the `buddee-health-hippocrates` codebase and internal strategy documents (Founders Manual 3rd/4th Ed., Strategy Deep-Dive July 2026, prospect/investor/advisor lists). Market claims independently re-verified against public sources in July 2026. Modeled figures are labeled *modeled*, consistent with the claims discipline in Founders Manual §10.4 — no measured pilot results exist yet.

---

## 1. Executive summary

Buddee is a shadow-mode AI revenue-integrity platform for risk-bearing outpatient physician groups. It reads clinical charts (via FHIR), suggests risk-adjustment (HCC) codes the documentation actually supports, flags codes already billed that the chart does *not* support, and records every suggestion, approval, and abstention in a cryptographically signed, tamper-evident audit trail. Nothing is auto-submitted; a human approves everything.

The core finding of this research: **the market timing thesis in the internal documents checks out against independent sources.** In 2025–2026 the U.S. government converted Medicare Advantage (MA) documentation accuracy from an occasional risk into an annual, universal audit event. Every claim underpinning the strategy was verified:

- CMS now audits **all eligible MA contracts annually (~550, up from ~60)** and scaled its coder workforce from 40 to ~2,000. Payment-year 2018–2024 audit backlog cleared on an expedited schedule; new audits run continuously.
- The federal government estimates **~$17B/year in MA overpayments from unsupported diagnoses**; MedPAC's March 2026 report puts total MA payments **$76B (14%) above** fee-for-service equivalent, with **$22–28B attributed to coding intensity**.
- OIG's **February 2026 Industry Compliance Program Guidance** (first MA update since 1999) explicitly names **AI-generated EMR prompts pushing risk-adjusting diagnoses as a potentially abusive practice** — a direct threat to one-sided competitor models and a direct tailwind for Buddee's two-sided design.
- The **Kaiser $556M settlement (Jan 2026)** — the largest MA False Claims Act settlement in history — was about exactly the conduct Buddee's architecture is built to prevent: retrospective mining that generated ~500,000 unsupported diagnoses.

The competitive lane the strategy claims is open **is, as of July 2026, verifiably open**: no funded competitor leads with a signed, two-sided, clinician-gated audit artifact for risk-bearing outpatient groups. The adjacent clusters (Navina, SmarterDx, Abridge, Optum/Reveleer, EHR-native AI) are all real, well-funded, and monetize capture, throughput, or workflow — not proof.

The main honest caveats: (1) the $82K/physician/year opportunity number is a *model*, not a measurement — no pilot has validated it; (2) the open lane is open partly because "compliance artifact" has never been proven as a wedge that closes deals at this segment's price point; (3) EHR-native AI (Epic, athenahealth) is compressing the space around it quickly; and (4) the company is pre-revenue, pre-incorporation, with a 90-day window (per the internal plan) to convert prospects into a signed pilot.

---

## 2. What Buddee is (grounded in the code)

From the repository (`README.md`, `backend/`, `core/`), Buddee is a working system, not a slide deck:

- **Input:** FHIR R4 clinical bundles from EHRs (Epic Community Connect, athenahealth, eCW, NextGen) via SMART-on-FHIR or direct POST.
- **Pipeline:** RAG over CMS-HCC V28 / ICD-10 FY2026 guidelines (pgvector) → Claude Opus 4.8 suggester → confidence floor (0.70) → LLM-as-judge second pass (Claude Sonnet 4.6) → deterministic validators (verbatim-quote substring check, ICD-10 validity, V28 mapping).
- **Outputs:** (a) suspected HCC documentation gaps with mandatory verbatim chart evidence; (b) unsupported-diagnosis alerts (codes on claims with no chart support — the two-sided half); (c) prior-authorization drafts; (d) an append-only, hash-chained audit ledger with daily KMS-signed Merkle roots exported to WORM storage.
- **Safety posture:** fail-closed BAA gates on PHI, abstention as a first-class logged outcome, human approval required on every suggestion, nothing ever auto-submitted to a payer.

**The strategic bet:** the moat is not the LLM (anyone can call Claude) — it is the *audit chain*: a signed, offline-verifiable proof of what was suggested, approved, abstained, and retracted. In a market where the auditor is now guaranteed to show up, the artifact is the product.

Status per the codebase and 4th Edition manual: MVP is functionally complete (31 auth-gated routes, CI/CD, eval harness, red-team suite, demo mode), but pre-incorporation, pre-BAA, pre-pilot, pre-revenue. Two founders as of July 2026.

---

## 3. The problem, and why now

### 3.1 The problem in one paragraph

About 35.2 million Americans (55% of eligible Medicare beneficiaries) are in Medicare Advantage. MA pays doctors' groups based on how sick their patients are documented to be, via Hierarchical Condition Category (HCC) codes that roll into a Risk Adjustment Factor (RAF) score. Two failure modes cost money: **under-documentation** (a real, treated condition never makes it into the codes → the group is paid less than the care justifies) and **over-documentation** (a code goes on a claim the chart can't support → an audit claws the money back, with penalties, sometimes extrapolated across the whole population). Risk-bearing groups need both problems fixed, and — as of 2026 — need to *prove* their documentation process to auditors.

### 3.2 The 2026 policy stack (all independently verified)

| Development | Verified facts | Why it creates demand for Buddee |
|---|---|---|
| **RADV audit universalization** | CMS audits all eligible MA contracts annually (~550 vs ~60 before); coders 40 → ~2,000; 35–200 enrollee samples; PY2018–2024 backlog cleared on expedited timeline (announced May 2025, executing through 2026) | The buyer's trigger event ("an audit letter arrived") is now annual and universal. Plans push documentation-defense obligations down to risk-bearing groups — Buddee's exact customer. |
| **V28 risk model fully phased in** | PY2026 is 100% V28; payable codes cut ~9,800 → ~7,770; HCCs restructured 86 → 115; avg risk scores compressed ~3.1%; coding-intensity impact fell from ~10% (2022) to ~4% (2026) | Easy/vague coding no longer pays. Value shifted to *specificity* and linked manifestations — exactly the class of gap an evidence-quoting LLM pass surfaces. |
| **MedPAC March 2026** | MA payments ~$76B (14%) above FFS-equivalent; $22–28B attributed to coding intensity; federal estimate ~$17B/yr overpaid on unsupported diagnoses | Political pressure on MA payment is structural. The durable position is documentation *accuracy* — which pays regardless of which direction policy moves. |
| **Enforcement climate** | FY2025 record FCA year (~$6.8B; ~$5.7B healthcare). Kaiser: $556M MA settlement (Jan 2026), largest ever, over ~500K unsupported retrospectively-mined diagnoses. Aetna: $117.7M (Mar 2026 — note: the internal manual dates this 2025; DOJ announced March 2026). DOJ names AI-enabled billing an enforcement priority | Every one-way "find more codes" vendor now carries enforcement risk on its face. Compliance officers know it. |
| **OIG ICPG (Feb 3, 2026)** | First MA compliance guidance since 1999. Names EMR prompts — "including prompts generated by artificial intelligence algorithms" — pushing risk-adjusting diagnoses as potentially abusive. Recommends two-sided review (adding *and* deleting codes) | The regulator effectively wrote Buddee's product spec: two-sided findings, human judgment, provable process. Capture-only AI tools are now presumptively suspect. |
| **ACO REACH tightening** | PY2026: 74 participants, ~126K providers, 1.7M beneficiaries; savings/loss corridors tightened to 10%; quality withhold 2% → 5% | Risk-bearing groups' margins swing harder on documentation than ever. The prospect lists target these organizations by name. |
| **Interoperability rules** | CMS-0057-F: payers must expose FHIR prior-auth/patient/provider APIs by Jan 1, 2027; WISeR (CMS's own AI + human-review prior-auth model) live 2026–2031 | FHIR-native ingestion (already built) gets easier every year; CMS itself normalized "AI + human review." |

**Interpretation:** this is a rare alignment where regulation *creates* the demand (mandatory annual audits), *disqualifies* the incumbents' approach (one-way capture named abusive), and *validates* the product's architecture (two-sided + human-in-the-loop + provable). The timing argument in the internal documents is not hype; it is documented in CMS press releases and the Federal Register.

---

## 4. Market size

### 4.1 Top-down context (the big funnel)

- **U.S. healthcare revenue cycle management (RCM):** ~$73B in 2026, growing ~11.6%/yr (projected ~$196B by 2035). Global RCM estimates run $180–200B. This is the broad category Buddee lives inside — context, not an addressable claim.
- **Risk adjustment / coding-integrity segment:** no clean public number exists for the exact segment; proxies include the ~$17B/yr federal overpayment estimate (the "error pool" Buddee's two-sided posture addresses) and the rapid growth of adjacent funded categories (industry estimates put ambient-AI documentation at under $200M revenue in 2022 scaling to a multi-billion-dollar run-rate by 2026).
- **The leakage pool itself:** the internal model estimates ~$82K/physician/year (*modeled*) in documentation under-specification losses for MA panels. Across just the ~170,000 physicians in America's Physician Groups member organizations, that implies a multi-billion-dollar annual accuracy gap — directionally consistent with MedPAC's independent $22–28B coding-intensity figure sitting alongside the $17B unsupported-diagnosis estimate (the two sides of the same coin Buddee audits).

### 4.2 Bottom-up TAM / SAM / SOM (*modeled*, using Buddee's own pricing)

Using Buddee's central-case realized fee of ~$7,000/physician/year (gain-share leg governing; floor $3,900/MD/yr):

| Layer | Definition | Size (modeled) |
|---|---|---|
| **TAM** | All U.S. physicians in risk-bearing/value-based arrangements (APG's ~360 groups / ~170K physicians is the visible core; total risk-exposed PCP base is larger) | ~170K+ physicians × ~$7K ≈ **$1.2B+/yr** for the provider-side wedge alone; expands with payer-side, prior-auth, and scribe-verification adjacencies |
| **SAM** | The ICP: independent, risk-bearing primary-care groups/IPAs/MSOs, 10–75 physicians, meaningful MA/ACO REACH exposure, on a supported EHR — nationally on the order of low thousands of organizations | Rough order: ~1,500–2,500 groups × ~25 MDs avg × ~$7K ≈ **$260–440M/yr** |
| **SOM (12–24 mo)** | Per the internal plan: 2 paid pilots by late 2026 → 3–5 paying groups by mid-2027, California beachhead | 3–5 groups × 25 MDs × $3.9–7K ≈ **$300K–$900K ARR** potential; first-year realistic revenue is pilot-priced (tens of thousands) |

Honesty notes on this table: SAM group-count is an estimate (no public registry of 10–75-MD risk-bearing groups exists; ACO REACH alone is only 74 organizations, but MA-delegated IPA/MSO arrangements — especially in California — are far more numerous). The per-physician fee is the *modeled* central case from the Deep-Dive's honesty chain ($82K pool → ~$40.4K realized net recovery → ~17.4% effective take). Until a pilot measures surfacing yield, approval rate, and retraction offset, every row here is a hypothesis.

### 4.3 The more useful framing for a pre-seed company

At this stage, market size matters less than **market pull**. The evidence of pull: (a) audits are now mandatory and annual, so every ICP organization has the trigger event every year; (b) the prospect list already contains 40+ named, researched California organizations (16 in List 1, 26 in List 2) sourced from the CMS ACO REACH PY2026 participant list and APG's California membership; (c) the buyer has budget-relevant pain in both directions — money left on the table *and* clawback exposure. A $260M+ SAM is plenty to build a venture-scale company if the wedge converts; the risk is conversion, not ceiling.

---

## 5. Customers and buyers

### 5.1 Ideal customer profile (from the manual, consistent with the prospect lists)

**Primary ICP:** risk-bearing primary-care practice, IPA, or MSO — 10–75 physicians, ≥20–30% Medicare Advantage or ACO REACH exposure, on athenahealth / eCW / NextGen / Epic Community Connect, independent (not hospital- or payer-owned). Examples already on the lists: Rancho Family Medical Group (Temecula), CareConnectMD (high-needs ACO REACH), Nivano Physicians IPA (Sacramento), Santé Physicians (Fresno), SCCIPA, Key Medical Group.

**Secondary ICP:** billing companies / MSOs serving those groups (one contract, many groups). **Deferred:** regional health systems. **Anti-ICP (correctly excluded):** Kaiser-model staff HMOs, Optum-owned groups, academic medical centers, FFS-only practices, solo practitioners.

**Why California first:** densest concentration of delegated-risk medical groups in the country (a legacy of 1990s capitation), plus the CMS ACO REACH participant list provides a public, verifiable targeting file — which the team has already mined.

### 5.2 Who actually signs (buyer personas)

- **Economic buyer:** RCM/Operations Director — owns the P&L leak; the $82K/MD *modeled* pool (presented honestly as a model) is their number.
- **The 2026 gatekeeper:** Compliance Officer — post-OIG-ICPG, any AI touching risk adjustment goes through them. Buddee is unusual in *selling to* this person (two-sided findings, signed artifact, retraction credits) rather than around them.
- **Champion:** Medical Director — cares that clinicians aren't asked to change workflow (shadow mode) and that queries are non-leading (AHIMA-compliant templates).
- **Veto holders:** IT/security (met with pre-built CAIQ-Lite, security whitepaper — already in `docs/`) and the EHR question ("our EHR will do this") — met with the five-strike segregation-of-duties battle card.

### 5.3 Funnel reality check (from the uploaded lists)

- Prospect List 1: 16 high-fit CA targets with named decision-maker roles and tailored angles.
- Prospect List 2: 26 tiered targets (A/B/C) with status tracking — **all currently "Not started."**
- Angel shortlist: 14 healthcare-fluent angels/groups (Nikhil Krishnan, Chrissy Farr/Scrub Capital, AngelMD, HealthTech Capital, Aneesh Chopra...) — matched to the $400–750K pre-seed SAFE plan.
- Advisor longlist: 33 candidates across clinical, health-law/RADV, and coding categories.

The research and targeting work is done; the outreach clock (90-day plan, YC deadline July 27) is the binding constraint, not market knowledge.

---

## 6. Competitive landscape (verified July 2026)

### 6.1 The six clusters

| Cluster | Key players (verified funding/status) | What they sell | Gap Buddee exploits |
|---|---|---|---|
| Point-of-care VBC copilots | **Navina** — $55M Series C led by Goldman Sachs Growth (2025), ~$100M total; deployed across agilon (~2,800 PCPs), Privia; Best-in-KLAS | Pre-visit/point-of-care insights inside clinician workflow, per-provider subscription | Closest ICP overlap. One-sided in economic effect (surfaces risk-adjusting dx to act on); requires clinician adoption; no signed, exportable audit chain |
| Pre-bill hospital revenue integrity | **SmarterDx** — ~$71M raised (Series B led by Transformation Capital); one of the sector's fastest growers (valuation reports conflict: ~$213M–$1B) | Post-discharge, pre-bill chart audit for hospital inpatient (DRG world), priced on found dollars | Validates "audit before money moves" economics — but FFS/inpatient scope; silent on MA risk, RADV, V28. Buddee transposes the motion to outpatient MA risk |
| Ambient documentation + coding | **Abridge** — $300M Series E at $5.3B (Jun 2025) + $316M extension (Apr 2026); $100M+ ARR; real-time prior auth via Availity. **Ambience** — $243M Series C. Microsoft/Nuance DAX (via $19.7B Nuance acquisition) | AI scribes that write the note and increasingly suggest codes; per-clinician subscriptions | Liability concentrates at note creation: "the same AI wrote the chart and suggested the code" is an auditor's opening question. No independent verification layer. Partnership surface ("we audit what your scribe wrote") more than head-to-head |
| Autonomous coding | CodaMetrix (~$109M; Best-in-KLAS Feb 2026), Fathom, Nym | Hospital/health-system computer-assisted coding for FFS throughput, per chart | Different buyer, different claim type; irrelevant to first 20 deals |
| Payer-side retrospective risk adjustment | Optum, Solventum (3M), Datavant/Apixio, **Reveleer** (70+ plans, 66M lives; acquired Curation Health Oct 2024 to pivot provider-side), RAAPID, Vatica | Retrospective chart review/mining for plans, priced per chart or % of RAF captured | The Kaiser-settlement conduct pattern. OIG language lands directly on one-way mining and uplift-linked pricing. Their brand burden is Buddee's compliance-officer opener. Reveleer's provider-side pivot *validates* the provider-side thesis |
| EHR-native + payer UM | Epic AI Charting (live Feb 2026, 150+ platform AI features); athenaAmbient (free inside athenaOne, GA 2026); Oracle Health agentic RCM; Cohere Health, Anterior (payer UM) | "Good-enough" native assistants, increasingly free | The structural conflict: an EHR vendor cannot credibly sign an independent audit trail of its own AI's suggestions. Buddee positions as the segregation-of-duties layer that makes native AI *safe to use* |

### 6.2 The open lane (independently confirmed)

Searches across the risk-adjustment vendor landscape (RAAPID, Reveleer, Vatica, Navina, etc., July 2026) confirm the internal claim: **no funded competitor leads with a cryptographically signed, two-sided, clinician-gated documentation-integrity artifact for risk-bearing outpatient groups.** Vendors advertise "audit-defensible" workflows, but none ships offline-verifiable signed proof, none logs abstentions as first-class events, and none prices with retraction credits (being *paid* to remove unsupported revenue). The lane is open because every incumbent's economics point the other way — payer-side capture fees, point-of-care capture, or EHR conflict-of-interest.

The sober counterpoint: lanes stay open for two reasons — structural awkwardness (true here) *or* because nobody has proven customers pay for it (also currently true here). The first pilot is the experiment that distinguishes them.

### 6.3 The biggest competitive threat

Not a startup — **EHR-native AI given away free** (athenaAmbient bundled into athenaOne; Epic shipping continuously). It compresses willingness-to-pay for anything that looks like "AI coding help." Buddee's counter must stay disciplined: never sell "AI coding help"; sell the independent verification artifact the EHR structurally cannot provide. The five-strike battle card in the Deep-Dive is the right play and should be treated as core product, not sales collateral.

---

## 7. Pricing and business model vs. market norms

**Buddee's structure (pre-pilot posture):** greater of (a) 15–20% gain-share on validated, clinician-approved, customer-submitted recovery *net of retractions*, with a ~10% retraction credit, or (b) $250–400/physician/month floor. Central case (*modeled*): ~$7,036/MD/yr fee on ~$40.4K realized net recovery → customer keeps ~83%, ~5.7× ROI; a 25-MD group ≈ $176K/yr.

**Against observed market norms:** copilots price per-provider PMPM (predictable, but "prove the ROI" pressure in 2026); ambient vendors price per-clinician ($200–600/mo class) with bundling pressure from free EHR-native scribes; pre-bill auditors price on found dollars (the proof-based motion Buddee borrows); payer-side vendors price per chart or % of RAF uplift — **which OIG's 2026 guidance now makes a liability**. Buddee's hybrid is legible against all of these, and the retraction credit is genuinely unique in the July 2026 map — it makes the compliance posture financially self-enforcing (the vendor profits from removing bad revenue, not just adding good).

Two pricing risks to watch: (1) gain-share requires attribution plumbing (customer attestation/webhook of submitted recoveries) that adds contracting friction to a first pilot — the floor exists to de-risk this; (2) never let procurement pressure bend the fee basis toward RAF uplift or suggestion volume — that is the exact structure OIG flagged, and the internal manual correctly makes it a two-signature protected line.

---

## 8. Funding environment (for the raise)

- **U.S. digital health H1 2026 (Rock Health):** $7.4B across 244 deals — up ~$1B YoY; median deal $14M; 20 megadeals took 45% of all capital. An AI-powered rebound, but sharply concentrated: capital flows to demonstrated traction. (The manual's $22.6B figure is a global tally from a different source; the directional read — flat-to-recovering, concentrated, traction-priced — is the same.)
- **Implication (matches the manual's conclusion):** a pre-pilot healthcare-AI company should not attempt a priced seed. The $400–750K pre-seed SAFE from healthcare-fluent angels, sized to reach pilot proof, is the correct instrument; the pilot then prices the seed ($2–4M target when 2 paid pilots + case study exist). YC Fall 2026 (deadline July 27) is a branch, not a dependency.
- **Why this niche can still raise:** enforcement-driven categories with government-mandated demand are legible to healthcare-fluent angels even pre-revenue — the angel shortlist (physician-executives, RCM/compliance-fluent operators) is selected for exactly that literacy.

---

## 9. Risks and open questions

1. **Model ≠ measurement (the big one).** Every dollar figure ($82K pool, $40.4K realized, 5.7× ROI) is modeled. The first pilot's measured surfacing yield, approval rate, and $/encounter either validate the category or force a re-price. Mitigation is already designed: the model's parameters are instrumented as pilot KPIs.
2. **Wedge conversion risk.** "Compliance artifact" has never been proven to close 10–75-MD group deals. The counter-evidence: the buyer's trigger event is now annual (RADV), and the pitch leads with recovered dollars (RCM Director) while the artifact wins the gatekeeper (Compliance Officer). Still unproven until an LOI converts.
3. **EHR-native compression.** Free, bundled AI raises the bar for any paid add-on. Defense: segregation-of-duties positioning + cross-EHR/TIN coverage + the artifact.
4. **Fast follow on the moat.** The audit chain is replicable engineering; the defense is (a) provisioning the KMS/WORM artifact *now*, (b) accumulating per-tenant approval/abstention corpora as eval ground truth, (c) incumbents' economic conflicts. The manual's own estimate — the lane stays open only until a funded player notices — argues for pilot speed above all.
5. **Regulatory whiplash.** The tailwind is policy; policy can shift (e.g., the Sept 2025 ruling vacating parts of the 2023 RADV rule on procedural grounds — CMS appealed and audits continue). Two-sided *accuracy* is the position that survives either direction; one-way capture is the position that doesn't.
6. **Execution/structural.** Pre-incorporation (blocks BAAs, Stripe, YC, SAFE), two-founder equity unresolved until first money, 90-day plan with hard dates (YC July 27; entity by Aug 1). All named in §11 of the 4th Edition with owners — the risk is calendar, not awareness.
7. **First-audit exposure.** The moment of maximum danger: the first real customer's first real RADV interaction. A single `partially_verified` audit-chain response is, per the internal SLOs, a Sev-1 credibility incident. This is the right paranoia.

---

## 10. What this means for the MVP

The MVP as built is aligned with the verified market reality — three checks the research supports:

1. **Right wedge:** shadow-mode + two-sided + artifact matches what the 2026 regulatory stack rewards and what no funded competitor sells. Nothing in the external record suggests re-scoping.
2. **Right sequencing:** the internal directives — provision KMS + Object Lock (turn the diagram into an artifact), ship the methodology one-pager, run the CA outreach lists, land one design-partner pilot with measured KPIs — are exactly the market-validating actions. The prospect research is done and current (sourced from the CMS PY2026 participant list); the only missing input is sends.
3. **Right honesty posture:** labeling $82K as modeled, pricing on validated-net-of-retraction dollars, and logging abstentions is not just ethics — post-ICPG it is the sales differentiator, because every competitor claim of "more captured revenue" now reads as risk to a compliance officer.

**The single most important market-research conclusion:** this market's demand is now created by the government on an annual schedule, the incumbents are structurally blocked from the compliance-first position, and the window is defined by how fast one funded competitor notices. The research phase is over; the pilot phase is the experiment that matters.

---

## 11. Beginner's glossary

| Term | Plain meaning |
|---|---|
| **Medicare Advantage (MA)** | Private insurance plans paid by the government to cover Medicare patients — 35.2M people, 55% of eligible beneficiaries (2026) |
| **Risk adjustment** | The government pays plans more for sicker patients, based on diagnosis codes submitted |
| **HCC** | Hierarchical Condition Category — a group of diagnosis codes that carries payment weight (115 categories in the V28 model) |
| **RAF score** | Risk Adjustment Factor — a patient's overall "sickness score"; drives payment |
| **V28** | The current (stricter) version of the CMS payment model, fully in effect 2026 — killed payment for vague codes, rewards specificity |
| **RADV audit** | CMS's audit checking whether billed diagnoses are actually supported by the medical chart; unsupported ones trigger clawbacks, now potentially extrapolated |
| **RCM** | Revenue Cycle Management — everything between care delivered and payment received |
| **FHIR** | The standard data format for exchanging medical records between systems |
| **Shadow mode** | Buddee runs alongside existing systems, reads data, suggests — never changes clinician workflow, never submits anything itself |
| **Two-sided** | Flags both missed revenue (under-coding) *and* unsupported codes (over-coding) — the posture regulators now effectively require |
| **BAA** | Business Associate Agreement — the HIPAA contract required before a vendor may touch patient data |
| **Merkle root / WORM** | Cryptographic fingerprint of each day's audit events, signed and stored in write-once storage — makes tampering detectable, which is what makes the audit trail trustworthy to CMS |
| **IPA / MSO** | Independent Practice Association / Management Services Organization — the group structures that hold risk contracts; Buddee's customers |
| **ACO REACH** | A CMS program where provider groups take financial risk on traditional Medicare patients — 74 participant organizations in 2026, heavily represented on the prospect lists |
| **ICP** | Ideal Customer Profile |
| **TAM / SAM / SOM** | Total / Serviceable / Obtainable market — everyone who could buy / the segment you target / what you can realistically win near-term |
| **SAFE** | Simple Agreement for Future Equity — the standard early-stage fundraising instrument |
| **Gain-share** | Pricing as a percentage of the money the customer actually recovers |

---

## 12. Sources

**Internal (product & strategy ground truth):** repository `buddee-health-hippocrates` (README.md, BUILD_PLAN.md, backend/, core/, docs/); Buddee Strategy Deep-Dive (July 2026); Founders Manual 3rd & 4th Editions; CA Prospect Lists 1–2; Angel Investor Shortlist; Advisor Candidates; Summer Sprint Daily Plan.

**External (July 2026 verification):**

- CMS — [Aggressive strategy to enhance and accelerate MA audits](https://www.cms.gov/newsroom/press-releases/cms-rolls-out-aggressive-strategy-enhance-accelerate-medicare-advantage-audits) · [RADV program page](https://www.cms.gov/data-research/monitoring-programs/medicare-risk-adjustment-data-validation-program) · [ACO REACH model](https://www.cms.gov/priorities/innovation/innovation-models/aco-reach) · [2026 ACO participation fact sheet](https://www.cms.gov/newsroom/fact-sheets/2026-medicare-accountable-care-organization-initiatives-participation-highlights)
- Wolters Kluwer — [RADV audit guidelines 2026](https://www.wolterskluwer.com/en/expert-insights/cms-guidelines-for-radv-audits) · Ropes & Gray — [RADV changes analysis](https://www.ropesgray.com/en/insights/alerts/2025/05/cms-announces-significant-changes-to-radv-auditing-efforts-considerations-and-next-steps) · Healthcare Dive — [CMS presses ahead on accelerated audits](https://www.healthcaredive.com/news/cms-medicare-advantage-audits-radv-risk-adjustment-update/811320/)
- OIG ICPG — Sidley Austin [analysis](https://www.sidley.com/en/insights/newsupdates/2026/02/oig-releases-long-awaited-medicare-advantage-compliance-program-guidance) · Morgan Lewis [analysis](https://www.morganlewis.com/pubs/2026/02/oig-issues-new-industry-compliance-program-guidance-for-medicare-advantage-in-first-major-update-since-1999) · Hinshaw [alert](https://www.hinshawlaw.com/en/insights/healthcare-alert/the-oig-just-raised-the-bar-new-medicare-advantage-compliance-guidance-you-cannot-afford-to-ignore)
- Enforcement — White & Case [DOJ record FY2025 FCA recoveries ($6.8B; ~$5.7B healthcare)](https://www.whitecase.com/insight-alert/dojs-record-breaking-2025-false-claims-act-recoveries-and-key-healthcare-fraud) · DOJ [Aetna $117.7M (Mar 2026)](https://www.justice.gov/opa/pr/aetna-agrees-pay-1177-million-resolve-false-claims-act-allegations)
- Kaiser settlement — Fierce Healthcare [$556M report](https://www.fiercehealthcare.com/payers/kaiser-permanente-pay-556m-settle-medicare-advantage-fraud-claims) · AGG [implications](https://www.agg.com/news-insights/publications/kaisers-556-million-medicare-advantage-fca-settlement-implications-for-providers-and-plan-disputes/) · RISE Health [summary](https://www.risehealth.org/insights-articles/article/landmark-settlement-kaiser-permanente-affiliates-to-pay-556m-to-resolve-ma-risk-adjustment-fraud-allegations/)
- MedPAC — [March 2026 Report to Congress](https://www.medpac.gov/document/march-2026-report-to-the-congress-medicare-payment-policy/) · Healthcare Dive [$76B overpayments](https://www.healthcaredive.com/news/medicare-advantage-overpayments-76b-2026-medpac/809859/) · Fierce Healthcare [MedPAC estimate](https://www.fiercehealthcare.com/regulatory/feds-will-overpay-medicare-advantage-plans-76b-year-medpac-estimates) · Georgetown [upcoding after V28](https://medicare.chir.georgetown.edu/the-gameing-isnt-over-upcoding-after-v28/) · KFF [coding intensity](https://www.kff.org/medicare/decoding-medicare-advantage-coding-intensity/)
- Enrollment — KFF [MA in 2026](https://www.kff.org/medicare/medicare-advantage-in-2026-enrollment-update-and-key-trends/) · Fierce Healthcare [14.3M in ACOs](https://www.fiercehealthcare.com/regulatory/cms-estimates-143m-medicare-beneficiaries-are-enrolled-aco-2026)
- Market size — Fortune Business Insights [RCM market](https://www.fortunebusinessinsights.com/industry-reports/revenue-cycle-management-market-100275) · Towards Healthcare [US RCM sizing](https://www.towardshealthcare.com/insights/us-healthcare-revenue-cycle-management-market-sizing) · Persistence [RCM software](https://www.persistencemarketresearch.com/market-research/healthcare-revenue-cycle-management-software-market.asp)
- Competitors — Fierce Healthcare [Navina $55M Series C](https://www.fiercehealthcare.com/ai-and-machine-learning/navina-reels-55m-series-c-led-goldman-sachs) · Fierce Healthcare [Abridge $300M Series E at $5.3B](https://www.fiercehealthcare.com/ai-and-machine-learning/ambient-ai-startup-abridge-scores-300m-series-e-backed-a16z-and-khosla) · Sacra [Abridge profile](https://sacra.com/c/abridge/) · SmarterDx [Series B](https://www.smarterdx.com/resources/smarterdx-raises-50m-to-bolster-hospital-revenue-integrity-and-quality-with-its-clinical-ai-solution) · Reveleer [Curation Health acquisition](https://www.reveleer.com/news/reveleer-acquires-curation) · RAAPID [risk-adjustment vendor landscape](https://www.raapidinc.com/blogs/risk-adjustment-coding-companies/)
- Funding climate — Rock Health [H1 2026 overview](https://rockhealth.com/insights/h1-2026-funding-and-market-overview-durable-roots-shifting-routes/) · Fierce Healthcare [$7.4B H1 2026](https://www.fiercehealthcare.com/digital-health/digital-health-brought-74b-vc-funding-ai-powered-rebound-fuels-market)
- Physician groups — [America's Physician Groups](https://www.apg.org/) (~360 groups, ~170K physicians)

*Modeled figures are labeled modeled. No measured pilot results exist as of this report's date. Re-verify any figure before external/customer-facing use, per Founders Manual §8.2 and §10.4.*
