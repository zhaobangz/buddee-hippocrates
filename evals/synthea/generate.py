"""Generate the 25-bundle synthetic FHIR library used by the demo + evals.

Usage::

    python -m evals.synthea.generate --out evals/synthea/bundles

The output directory is wiped and rewritten so the script is safe to
re-run as the case library evolves. Each bundle is fully self-
contained: one Patient, one Encounter, one Condition list, and one
DocumentReference whose attachment carries the deidentified note text.

Demographics are drawn from a small pool of culturally-diverse Safe
Harbor-compliant placeholders. Birth dates are quantised to year only
(per HIPAA Safe Harbor §164.514(b)(2)(i)(B)) and no ZIP code is ever
generated narrower than the first three digits.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence


# A stable per-case UUID seed so re-running the generator produces the
# same patient IDs in the same order. The seed is the SHA-256 of the
# case slug — this is deterministic but not predictable from the slug
# alone.
def _seeded_uuid(slug: str, kind: str) -> str:
    digest = hashlib.sha256(f"buddi-synthea::{slug}::{kind}".encode("utf-8")).hexdigest()
    return str(uuid.UUID(digest[:32]))


@dataclass
class SyntheticCase:
    """A single Safe-Harbor demographic + clinical-note vignette."""

    slug: str
    given_name: str
    family_name: str
    gender: str  # "male" / "female" / "other"
    birth_year: int  # year only — per Safe Harbor
    note: str
    billed_codes: Sequence[str]  # Condition resources to emit
    encounter_class: str = "AMB"  # AMB = ambulatory; FHIR ActCode
    notes: str = ""

    @property
    def patient_id(self) -> str:
        return _seeded_uuid(self.slug, "patient")

    @property
    def encounter_id(self) -> str:
        return _seeded_uuid(self.slug, "encounter")

    @property
    def composition_id(self) -> str:
        return _seeded_uuid(self.slug, "composition")


# Twenty-five Safe-Harbor synthetic vignettes. The set deliberately
# overlaps with ``evals/golden/`` so the same labels can be re-used
# when the bundles are run through the offline eval path.
CASES: List[SyntheticCase] = [
    SyntheticCase(
        slug="diabetic-ckd",
        given_name="Marcus", family_name="Holloway", gender="male",
        birth_year=1958,
        note=(
            "67-year-old male with type 2 diabetes mellitus complicated by "
            "chronic kidney disease stage 3a. eGFR 51 and urine "
            "albumin/creatinine ratio 42 mg/g. Hypertension treated with "
            "lisinopril."
        ),
        billed_codes=["E11.9", "I10"],
    ),
    SyntheticCase(
        slug="chf-systolic",
        given_name="Linda", family_name="Park", gender="female",
        birth_year=1953,
        note=(
            "72-year-old female with chronic systolic congestive heart "
            "failure, EF 32% on echo. NYHA Class III. On GDMT including "
            "carvedilol, lisinopril, spironolactone, furosemide."
        ),
        billed_codes=["I50.20"],
    ),
    SyntheticCase(
        slug="copd-exacerbation",
        given_name="Robert", family_name="Vasquez", gender="male",
        birth_year=1960,
        note=(
            "65-year-old former smoker with COPD, recently completed a "
            "5-day prednisone burst for acute exacerbation with purulent "
            "sputum and increased dyspnea."
        ),
        billed_codes=["J44.9"],
    ),
    SyntheticCase(
        slug="morbid-obesity",
        given_name="Maya", family_name="Patel", gender="female",
        birth_year=1967,
        note=(
            "58-year-old female with BMI 45.2. Documented morbid (severe) "
            "obesity. Continues weight management counseling."
        ),
        billed_codes=["E66.9"],
    ),
    SyntheticCase(
        slug="depression-recurrent",
        given_name="Eunice", family_name="Okonkwo", gender="female",
        birth_year=1981,
        note=(
            "44-year-old female with recurrent major depressive disorder, "
            "currently in partial remission on sertraline 100mg daily."
        ),
        billed_codes=["F32.9"],
    ),
    SyntheticCase(
        slug="afib-chronic",
        given_name="Hiroshi", family_name="Tanaka", gender="male",
        birth_year=1949,
        note=(
            "76-year-old male with longstanding chronic atrial "
            "fibrillation, rate-controlled on metoprolol, anticoagulated "
            "on apixaban. CHA2DS2-VASc 4."
        ),
        billed_codes=["I48.91"],
    ),
    SyntheticCase(
        slug="amputation-status",
        given_name="Devon", family_name="Reeves", gender="male",
        birth_year=1964,
        note=(
            "61-year-old male with type 2 diabetes, prior right "
            "below-knee amputation 2019 for diabetic foot ulcer with "
            "gangrene. Uses prosthesis, ambulates independently."
        ),
        billed_codes=["E11.9"],
    ),
    SyntheticCase(
        slug="vascular-pad",
        given_name="Aaron", family_name="Bell", gender="male",
        birth_year=1956,
        note=(
            "69-year-old male with peripheral artery disease, claudication "
            "at one block, ABI 0.62 on the right. History of CEA 2018."
        ),
        billed_codes=["I73.9"],
    ),
    SyntheticCase(
        slug="dementia-alzheimers",
        given_name="Beatrice", family_name="Ngozi", gender="female",
        birth_year=1943,
        note=(
            "82-year-old female with Alzheimer's-type dementia, late "
            "onset. MoCA 14/30. Behavioral disturbance with nighttime "
            "agitation."
        ),
        billed_codes=["F03.90"],
    ),
    SyntheticCase(
        slug="cancer-history",
        given_name="Renee", family_name="Goldberg", gender="female",
        birth_year=1970,
        note=(
            "55-year-old female with history of breast cancer, stage IIA, "
            "status post lumpectomy + radiation + 5 years aromatase "
            "inhibitor (completed). Currently disease-free."
        ),
        billed_codes=["C50.911"],
    ),
    SyntheticCase(
        slug="cad-stable",
        given_name="Cesar", family_name="Mendoza", gender="male",
        birth_year=1951,
        note=(
            "74-year-old male with stable CAD, history of two-vessel "
            "stenting 2017. Asymptomatic. On dual antiplatelet, statin."
        ),
        billed_codes=["I25.10"],
    ),
    SyntheticCase(
        slug="sleep-apnea",
        given_name="Bahar", family_name="Hosseini", gender="female",
        birth_year=1972,
        note=(
            "53-year-old female with obstructive sleep apnea, AHI 28 "
            "(severe). CPAP-adherent at 6.2 hours/night."
        ),
        billed_codes=["G47.30"],
    ),
    SyntheticCase(
        slug="rheumatoid-arthritis",
        given_name="Yusuf", family_name="Diallo", gender="male",
        birth_year=1968,
        note=(
            "57-year-old male with seropositive rheumatoid arthritis, on "
            "methotrexate + adalimumab. CDAI 6 (low disease activity)."
        ),
        billed_codes=["M06.9"],
    ),
    SyntheticCase(
        slug="hyperlipidemia",
        given_name="Eve", family_name="Christensen", gender="female",
        birth_year=1979,
        note=(
            "46-year-old female with mixed hyperlipidemia, LDL 168 on "
            "rosuvastatin 20mg. Strong family history of premature CAD."
        ),
        billed_codes=["E78.5"],
    ),
    SyntheticCase(
        slug="parkinsons",
        given_name="Sebastian", family_name="Wu", gender="male",
        birth_year=1944,
        note=(
            "81-year-old male with idiopathic Parkinson disease, Hoehn & "
            "Yahr stage 3. On carbidopa/levodopa + rasagiline. Falls "
            "twice in past 6 months."
        ),
        billed_codes=["G20"],
    ),
    SyntheticCase(
        slug="hiv-suppressed",
        given_name="Marcus", family_name="Andersson", gender="male",
        birth_year=1985,
        note=(
            "40-year-old male with HIV, virally suppressed on bictegravir/"
            "emtricitabine/TAF. CD4 720, viral load undetectable. No "
            "opportunistic infections."
        ),
        billed_codes=["B20"],
    ),
    SyntheticCase(
        slug="stroke-history",
        given_name="Priya", family_name="Subramanian", gender="female",
        birth_year=1957,
        note=(
            "68-year-old female with history of left MCA ischemic stroke "
            "2022, residual right-arm weakness 4/5. On aspirin + statin."
        ),
        billed_codes=["I63.9"],
    ),
    SyntheticCase(
        slug="ckd-stage4",
        given_name="Daniel", family_name="Yamamoto", gender="male",
        birth_year=1950,
        note=(
            "75-year-old male with stage 4 CKD, eGFR 26. Nephrology "
            "preparing for AV fistula creation. No diabetes. "
            "Hypertensive CKD."
        ),
        billed_codes=["N18.9", "I10"],
    ),
    SyntheticCase(
        slug="liver-cirrhosis",
        given_name="Quinn", family_name="Thompson", gender="other",
        birth_year=1976,
        note=(
            "49-year-old patient with alcohol-related cirrhosis, "
            "Child-Pugh A. Documented ascites managed with diuretics. "
            "Abstinent for 14 months."
        ),
        billed_codes=["K70.30"],
    ),
    SyntheticCase(
        slug="asthma-persistent",
        given_name="Olivia", family_name="Brennan", gender="female",
        birth_year=1989,
        note=(
            "36-year-old female with moderate persistent asthma, ACT "
            "score 17. On medium-dose ICS/LABA. Two oral steroid bursts "
            "in past year."
        ),
        billed_codes=["J45.40"],
    ),
    SyntheticCase(
        slug="t1dm-pump",
        given_name="Lucas", family_name="Romero", gender="male",
        birth_year=1991,
        note=(
            "34-year-old male with type 1 diabetes since age 12, insulin "
            "pump + CGM. A1C 7.1. No retinopathy, microalbuminuria 28 "
            "mg/g."
        ),
        billed_codes=["E10.9"],
    ),
    SyntheticCase(
        slug="lupus-active",
        given_name="Naomi", family_name="Carrasco", gender="female",
        birth_year=1986,
        note=(
            "39-year-old female with SLE, current flare with arthralgias "
            "and rash. On hydroxychloroquine + low-dose prednisone. "
            "Lupus nephritis class III on biopsy."
        ),
        billed_codes=["M32.9"],
    ),
    SyntheticCase(
        slug="esrd-dialysis",
        given_name="Frank", family_name="Sokolova", gender="male",
        birth_year=1952,
        note=(
            "73-year-old male with ESRD on hemodialysis MWF via AV "
            "fistula. Underlying diabetic nephropathy. Kt/V 1.6."
        ),
        billed_codes=["N18.6"],
    ),
    SyntheticCase(
        slug="multiple-sclerosis",
        given_name="Ines", family_name="Almeida", gender="female",
        birth_year=1981,
        note=(
            "44-year-old female with relapsing-remitting MS, on ocrelizumab. "
            "EDSS 2.5. No clinical relapses past 18 months."
        ),
        billed_codes=["G35"],
    ),
    SyntheticCase(
        slug="ckd-htn-elderly",
        given_name="George", family_name="Banerjee", gender="male",
        birth_year=1939,
        note=(
            "86-year-old male with stage 3b CKD (eGFR 38) on background "
            "of long-standing hypertension. Documented hypertensive heart "
            "and chronic kidney disease."
        ),
        billed_codes=["I10", "N18.9"],
    ),
]


def _build_bundle(case: SyntheticCase) -> Dict:
    """Render a single ``SyntheticCase`` into a FHIR Bundle dict."""

    attachment_bytes = case.note.encode("utf-8")
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "id": _seeded_uuid(case.slug, "bundle"),
        "meta": {
            "tag": [
                {
                    "system": "https://buddi.health/fhir/CodeSystem/synthetic",
                    "code": "synthea-vignette",
                    "display": "Synthetic, Safe-Harbor compliant; no real PHI",
                }
            ]
        },
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": case.patient_id,
                    "gender": case.gender,
                    "birthDate": f"{case.birth_year}-01-01",
                    "name": [
                        {
                            "use": "official",
                            "family": case.family_name,
                            "given": [case.given_name],
                        }
                    ],
                }
            },
            {
                "resource": {
                    "resourceType": "Encounter",
                    "id": case.encounter_id,
                    "status": "finished",
                    "class": {
                        "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                        "code": case.encounter_class,
                        "display": "ambulatory",
                    },
                    "subject": {"reference": f"Patient/{case.patient_id}"},
                }
            },
            {
                "resource": {
                    "resourceType": "DocumentReference",
                    "id": case.composition_id,
                    "status": "current",
                    "subject": {"reference": f"Patient/{case.patient_id}"},
                    "context": {
                        "encounter": [{"reference": f"Encounter/{case.encounter_id}"}]
                    },
                    "content": [
                        {
                            "attachment": {
                                "contentType": "text/plain",
                                "data": base64.b64encode(attachment_bytes).decode("ascii"),
                                "title": f"Progress note ({case.slug})",
                            }
                        }
                    ],
                }
            },
            *[
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": _seeded_uuid(case.slug, f"condition::{code}"),
                        "subject": {"reference": f"Patient/{case.patient_id}"},
                        "encounter": {"reference": f"Encounter/{case.encounter_id}"},
                        "code": {
                            "coding": [
                                {
                                    "system": "http://hl7.org/fhir/sid/icd-10-cm",
                                    "code": code,
                                }
                            ]
                        },
                    }
                }
                for code in case.billed_codes
            ],
        ],
    }


def write_bundles(output_dir: Path) -> List[Path]:
    if output_dir.exists():
        for child in output_dir.iterdir():
            if child.is_file():
                child.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for index, case in enumerate(CASES, start=1):
        bundle = _build_bundle(case)
        filename = f"bundle_{index:03d}_{case.slug.replace('-', '_')}.json"
        path = output_dir / filename
        path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
        paths.append(path)
    return paths


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("evals/synthea/bundles"),
        help="Directory to write the synthetic bundles into.",
    )
    args = parser.parse_args(argv)
    written = write_bundles(args.out)
    print(f"Wrote {len(written)} synthetic FHIR bundles to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
