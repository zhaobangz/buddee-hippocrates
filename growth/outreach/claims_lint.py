"""Claims-discipline linter — enforces MANUAL_TASKS.md / Outreach Kit rules.

Blocks any outbound copy that states something not yet true. Run on every
generated draft; the pipeline refuses to write a file that fails.

Rules sourced from Buddee_AI_Outreach_Kit.docx "Claims discipline" and
Buddee_AI_Advisor_Outreach.docx "Claims discipline".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: (pattern, why it's forbidden) — case-insensitive.
FORBIDDEN: list[tuple[str, str]] = [
    (r"\bHIPAA[- ]compliant\b", "HIPAA compliance not verified — say 'BAAs signed or in progress'"),
    (r"\bSOC[- ]?2\b(?![^.]*in progress)", "SOC 2 not complete — do not name it"),
    (r"\buniversity of\b|\bstanford\b|\bberkeley\b|\bucla\b|\bucsf\b", "No university affiliation may be claimed"),
    (r"\bproduction EHR integration\b|\blive (?:EHR )?integration\b", "No production EHR integration yet"),
    (r"\bregulatory[- ]grade\b", "'regulatory-grade' is an unverifiable claim"),
    (r"\bguarantee[ds]?\b", "Never guarantee outcomes or dollars"),
    (r"\$\s?\d[\d,]*(\s?(k|K|/encounter|per encounter|/physician))?", "Dollar figures are modeled, not proven — keep them out of cold sends"),
    (r"\blive pilots?\b|\bpaying customers?\b", "No live pilots / paying customers may be claimed"),
    (r"\b(?:99|9\d)% (?:accura|precis)", "No specific accuracy numbers until golden-set eval exists"),
    (r"\bFDA[- ](?:cleared|approved)\b", "Never claim FDA status"),
    (r"\bdiagnos(?:es|is|ing) patients\b", "Buddee never diagnoses — advisory posture only"),
]

#: Language that must appear somewhere in a first-touch email (posture markers).
REQUIRED_ANY: list[tuple[str, str]] = [
    (r"shadow[- ]mode", "first-touch copy must anchor on shadow-mode posture"),
]


@dataclass
class LintResult:
    ok: bool
    errors: list[str]
    warnings: list[str]


def lint(text: str, *, first_touch: bool = False) -> LintResult:
    errors: list[str] = []
    warnings: list[str] = []
    for pattern, why in FORBIDDEN:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            errors.append(f"forbidden claim {m.group(0)!r}: {why}")
    if first_touch:
        for pattern, why in REQUIRED_ANY:
            if not re.search(pattern, text, flags=re.IGNORECASE):
                warnings.append(f"missing posture marker /{pattern}/: {why}")
    leftover = re.findall(r"\[(?!demo link\]|phone\])[^\[\]]{2,40}\]", text)
    for token in leftover:
        warnings.append(f"unresolved placeholder {token} — personalize before sending")
    return LintResult(ok=not errors, errors=errors, warnings=warnings)
