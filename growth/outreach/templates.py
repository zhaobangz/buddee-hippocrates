"""Buddee outreach templates — codified from Buddee_AI_Outreach_Kit.docx.

Every template is claims-disciplined: only statements true as of July 2026
(shadow-mode, tamper-evident audit trail, pre-pilot, modeled estimates).
The linter in claims_lint.py enforces the forbidden list on all output.

Placeholders use str.format-style fields:
  {org} {first_name} {city} {relevance_line} {founder_name} {founder_email}
  {founder_phone} {demo_link}
"""

FOUNDER = {
    "founder_name": "Zhao",
    "founder_title": "Founder, Buddee",
    "founder_email": "zhuzhaobang70@gmail.com",
    "founder_phone": "[phone]",
    "demo_link": "[demo link]",
}

# Template A — risk-bearing primary care / IPA / ACO (RCM/Ops or Medical Director)
EMAIL_A_SUBJECT = "{org} — the ~40% of HCCs manual coding misses"
EMAIL_A = """Hi {first_name},

Manual coders catch roughly 60% of billable HCC diagnoses. For a risk-bearing \
group like {org}, the missing ~40% isn't a coding miss — it's revenue you've \
already earned and are quietly writing off, plus the RAF accuracy you'll wish \
you had on file the day CMS runs a RADV audit.

{relevance_line}

Buddee is an AI-native auditor that runs in shadow mode alongside your EHR. On \
encounters your team has already closed, it surfaces the suspected missed HCCs, \
drafts the CMS-grounded support for each, and writes a tamper-evident audit \
trail — no workflow change, no clinician retraining.

Rather than ask you to take my word for it, I built a 30-second demo on a \
synthetic patient so you can see exactly what it flags before you spend a \
minute on a call: {demo_link}.

Worth 15 minutes to run it against a sample of your own de-identified \
encounters? I'll work around your schedule.

Best,
{founder_name}
{founder_title}  ·  {founder_phone}  ·  {founder_email}
"""

# Template B — Compliance Officer (the gatekeeper)
EMAIL_B_SUBJECT = "Shadow-mode AI for HCC capture — starting with the audit trail"
EMAIL_B = """Hi {first_name},

Most AI-coding pitches land on a compliance desk as a new risk to manage, so \
let me start with the part your team actually weighs: the audit trail.

Buddee runs in shadow mode next to the EHR and surfaces suspected missed HCC \
codes — but every suggestion is written to a hash-chained, cryptographically \
signed log. If a code we surface is ever questioned in a RADV review, there's \
a tamper-evident record of exactly what was suggested, on what evidence, and \
who reviewed it. It's built to make an audit easier to defend, not harder.

{relevance_line}

We sign BAAs, redact PHI from logs, and keep the model in an advisory, \
human-in-the-loop posture — a coder always makes the call.

I'd rather send a one-page security & audit-posture summary than a demo. Can I \
email it over, and if it's useful, grab 20 minutes with you and your coding lead?

Best,
{founder_name}
{founder_title}
"""

# Template C — billing & coding company / MSO (reseller / gain-share)
EMAIL_C_SUBJECT = "An HCC-capture line you can add for your physician clients"
EMAIL_C = """Hi {first_name},

You already own the management relationship with your physician groups — \
including the internal-medicine and capitated panels where HCC capture drives \
the real money. What if you could add a premium capture line without hiring a \
coding team to run it?

{relevance_line}

Buddee is an AI auditor that surfaces suspected missed HCC codes and produces \
a tamper-evident audit trail for each one. We'd rather sit behind you than \
compete with you: you offer HCC capture as a premium service line, keep the \
client relationship, and we align on gain-share — so it only costs when it \
actually recovers dollars. Our incentives point the same direction as yours, \
by design.

Open to a 20-minute call to see whether the economics fit your book? I'll walk \
through a synthetic-patient demo and a simple partner model.

Best,
{founder_name}
{founder_title}  ·  {founder_phone}  ·  {founder_email}
"""

# Follow-up #1 (+3–4 business days)
FOLLOWUP_1_SUBJECT = "Re: {original_subject}"
FOLLOWUP_1 = """Hi {first_name},

Quick nudge — and a specific reason I think 15 minutes pays for itself at \
{org}: {relevance_line_short}

Here's the 30-second demo again so you can judge it for yourself: {demo_link}.

If it's not a fit, just say so and I'll close the loop — no more follow-ups.

Best,
{founder_name}
"""

# Follow-up #2 / break-up (+7–9 business days)
FOLLOWUP_2_SUBJECT = "Re: {original_subject}"
FOLLOWUP_2 = """Hi {first_name},

I don't want to crowd your inbox, so this is my last note. If HCC capture and \
RADV defensibility are anywhere on your radar for this quarter, I'd still like \
to show you what Buddee flags on your own de-identified data — 15 minutes, \
your encounters, no obligation.

And if the timing's simply off, tell me when to check back and I'll go quiet \
until then.

Thanks either way,
{founder_name}
"""

# LinkedIn connection note (≤300 chars after substitution — pipeline enforces)
LINKEDIN_NOTE = (
    "Hi {first_name} — I'm building Buddee, a shadow-mode AI auditor that "
    "surfaces the missed HCC codes manual coding leaves behind and leaves a "
    "RADV-defensible audit trail. Given {org_short}'s risk contracts, I think "
    "it's worth 15 minutes — happy to send a 30-second demo first."
)

#: Target-role string (from the spreadsheet) → (template key, email, subject)
ROLE_TEMPLATE_MAP = {
    "rcm/ops director": ("A", EMAIL_A, EMAIL_A_SUBJECT),
    "medical director": ("A", EMAIL_A, EMAIL_A_SUBJECT),
    "compliance officer": ("B", EMAIL_B, EMAIL_B_SUBJECT),
    "billing/mso": ("C", EMAIL_C, EMAIL_C_SUBJECT),
}
