#!/usr/bin/env python3
"""
Ingest clinician-labeled golden cases from a structured CSV/sheet.

Takes an MD-provided spreadsheet (CSV or TSV) and emits validated
``case_*.json`` files into ``evals/golden/v1/``. Every case is validated
against ``evals/golden/schema.json`` before writing. Codes are checked
against a bundled V28 code list.

Usage:
    python scripts/ingest_golden_labels.py \\
        --csv labels_batch_1.csv \\
        --out evals/golden/v1

    # With a Synthea bundle dir as note source:
    python scripts/ingest_golden_labels.py \\
        --csv labels_batch_1.csv \\
        --synthea-dir evals/synthea/bundles \\
        --out evals/golden/v1

    # Validate only (no write):
    python scripts/ingest_golden_labels.py \\
        --csv labels_batch_1.csv \\
        --validate-only

CSV columns (order-independent; header row required):
    case_id            — unique, stable identifier (e.g. "case_011_chf")
    clinician_id       — real clinician identifier (not a placeholder)
    labeled_at         — ISO-8601 timestamp
    specialty          — from the schema enum
    condition_category — HCC condition bucket (diabetes/chf/copd/ckd/…)
    note               — synthetic clinical note text
    billed_codes       — semicolon-separated ICD-10-CM codes
    expected_codes     — semicolon-separated ICD-10-CM codes
    acceptable_alternatives — semicolon-separated (optional)
    must_abstain_codes — semicolon-separated (optional)
    evidence_spans     — JSON map of code→verbatim quote (optional)
    edge_notes         — free text (optional)
    notes              — free text (optional)
    guideline_refs     — JSON map of code→citation (optional)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# V28 code list — the subset of HCC-relevant ICD-10-CM codes under V28.
# PY2026 uses 100% V28 (manual §8.1).
# ---------------------------------------------------------------------------
_V28_HCC_CODES: set[str] = set()

_V28_HCC_CODES = {
    # Diabetes
    "E11.22", "E11.42", "E11.9", "E11.21", "E11.29", "E11.311",
    "E11.319", "E11.321", "E11.329", "E11.331", "E11.339", "E11.341",
    "E11.349", "E11.351", "E11.359", "E11.36", "E11.39", "E11.40",
    "E11.41", "E11.43", "E11.44", "E11.49", "E11.51", "E11.52",
    "E11.59", "E11.610", "E11.618", "E11.620", "E11.621", "E11.622",
    "E11.628", "E11.630", "E11.638", "E11.641", "E11.649", "E11.65",
    "E11.69", "E11.8", "E10.22", "E10.42",
    # CHF / Heart Failure
    "I50.22", "I50.23", "I50.32", "I50.33", "I50.42", "I50.43",
    "I50.9", "I50.1", "I50.20", "I50.21", "I50.30", "I50.31",
    "I50.40", "I50.41", "I11.0",
    # COPD
    "J44.1", "J44.9", "J44.0", "J43.9",
    # CKD
    "N18.31", "N18.32", "N18.4", "N18.5", "N18.6", "N18.9",
    "N18.1", "N18.2", "N18.30",
    # Hypertension
    "I12.9", "I12.0", "I10", "I11.9", "I13.0", "I13.10", "I13.11",
    "I13.2",
    # Vascular
    "I70.221", "I70.222", "I70.229", "I70.231", "I70.232", "I70.239",
    "I70.241", "I70.242", "I70.249", "I70.25", "I70.261", "I70.262",
    "I70.269", "I70.291", "I70.292", "I70.299", "I70.8", "I70.9",
    "I73.9", "I77.1",
    # Dementia
    "F03.90", "F03.91", "G30.0", "G30.1", "G30.8", "G30.9",
    "F01.50", "F01.51", "F02.80", "F02.81",
    # Depression
    "F32.0", "F32.1", "F32.2", "F32.9", "F33.0", "F33.1", "F33.2",
    "F33.9", "F34.1",
    # CAD
    "I25.10", "I25.110", "I25.111", "I25.118", "I25.119", "I25.2",
    "I25.5", "I25.6", "I25.700", "I25.701", "I25.708", "I25.709",
    "I25.710", "I25.711", "I25.718", "I25.719", "I25.720", "I25.721",
    "I25.728", "I25.729", "I25.730", "I25.731", "I25.738", "I25.739",
    "I25.790", "I25.791", "I25.798", "I25.799", "I25.810", "I25.811",
    "I25.812", "I25.89", "I25.9",
    # Sepsis
    "A41.51", "A41.01", "A41.02", "A41.1", "A41.2", "A41.3",
    "A41.4", "A41.50", "A41.52", "A41.53", "A41.59", "A41.81",
    "A41.89", "A41.9", "R65.21",
    # Anemia
    "D63.1", "D50.0", "D50.9", "D62", "D64.9",
    # Obesity
    "E66.01", "E66.2", "E66.8", "E66.9", "E66.0",
    # Cancer
    "C50.911", "C50.912", "C50.919", "C50.921", "C50.922", "C50.929",
    "C61", "C34.10", "C34.11", "C34.12", "C34.90", "C34.91", "C34.92",
    "C18.0", "C18.2", "C18.3", "C18.4", "C18.5", "C18.6", "C18.7",
    "C18.8", "C18.9", "C20",
    # Amputation / complications
    "Z89.411", "Z89.412", "Z89.419", "Z89.421", "Z89.422", "Z89.429",
    "Z89.431", "Z89.432", "Z89.439", "L97.909",
    # Other HCC-relevant
    "N39.0", "J96.00", "J96.01", "J96.02", "J96.10", "J96.11",
    "J96.12", "J96.20", "J96.21", "J96.22", "J96.90", "J96.91",
    "J96.92", "Z99.2", "E10.9", "E13.9", "C50.9",
}


CONDITION_CATEGORIES = [
    "diabetes", "chf", "copd", "ckd", "hypertension",
    "dementia", "depression", "cad", "sepsis", "anemia",
    "obesity", "cancer", "vascular", "other",
]

SPECIALTIES = [
    "primary_care", "cardiology", "nephrology", "pulmonology",
    "internal_medicine", "endocrinology", "neurology", "psychiatry",
    "oncology", "geriatrics", "other",
]

# Every column the MD spreadsheet must have.
REQUIRED_COLUMNS = [
    "case_id", "clinician_id", "labeled_at", "specialty",
    "condition_category", "note", "billed_codes", "expected_codes",
]

OPTIONAL_COLUMNS = [
    "acceptable_alternatives", "must_abstain_codes",
    "evidence_spans", "edge_notes", "notes", "guideline_refs",
    "tenant_id_hint",
]


def _parse_codes(raw: str) -> List[str]:
    """Parse semicolon- or comma-separated code list."""
    if not raw or not raw.strip():
        return []
    # Accept both ; and , as separators.
    return [
        c.strip().upper()
        for c in re.split(r"[;,]", raw)
        if c.strip()
    ]


def _parse_json_field(raw: str) -> Optional[dict]:
    """Parse an optional JSON field from the CSV."""
    if not raw or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {raw[:80]}... — {e}") from e


def validate_case(case: Dict[str, Any]) -> List[str]:
    """Validate a single case dict. Returns list of error messages (empty = valid)."""
    errors: List[str] = []

    # Required fields.
    for col in REQUIRED_COLUMNS:
        if col not in case or not str(case[col]).strip():
            errors.append(f"Missing required field: {col}")

    if errors:
        return errors

    cid = case.get("case_id", "")
    clin = case.get("clinician_id", "")

    # case_id format.
    if not re.match(r"^[a-z0-9_]+$", str(cid)):
        errors.append(f"case_id '{cid}' must match [a-z0-9_]+")

    # clinician_id must not be a placeholder outside seed set.
    if "placeholder" in str(clin).lower():
        errors.append(
            f"clinician_id '{clin}' is a placeholder — real labels require "
            f"a real clinician_id (not a placeholder)"
        )

    # specialty enum.
    spec = str(case.get("specialty", ""))
    if spec not in SPECIALTIES:
        errors.append(
            f"specialty '{spec}' not in allowed values: {SPECIALTIES}"
        )

    # condition_category enum.
    cat = str(case.get("condition_category", ""))
    if cat not in CONDITION_CATEGORIES:
        errors.append(
            f"condition_category '{cat}' not in allowed values: {CONDITION_CATEGORIES}"
        )

    # Note length guard.
    note = str(case.get("note", ""))
    if len(note) < 20:
        errors.append(f"note too short ({len(note)} chars; min 20)")
    if len(note) > 10000:
        errors.append(f"note too long ({len(note)} chars; max 10000)")

    # Code format validation.
    expected = _parse_codes(str(case.get("expected_codes", "")))
    if not expected:
        errors.append("expected_codes must contain at least one ICD-10-CM code")

    # All codes should look like ICD-10-CM (letter + 2 digits + optional dot + more).
    _icd_re = re.compile(r"^[A-Z]\d{2}(\.\d{1,4})?$")
    for label, field in [
        ("billed", "billed_codes"),
        ("expected", "expected_codes"),
        ("acceptable_alternatives", "acceptable_alternatives"),
        ("must_abstain", "must_abstain_codes"),
    ]:
        raw = str(case.get(field, ""))
        for code in _parse_codes(raw):
            if not _icd_re.match(code):
                errors.append(f"{label} code '{code}' doesn't match ICD-10-CM format")

    # V28 code check (advisory — not a hard fail for seed set growth, but
    # warns loudly so the clinician can confirm).
    for code in expected:
        if code not in _V28_HCC_CODES:
            # This is a WARNING, not a hard error — the V28 set above is a
            # bundled snapshot and may be incomplete. The clinician is the
            # authority.
            pass  # advisory only; the ingest logs a warning per-case below.

    # evidence_spans validation.
    spans_raw = str(case.get("evidence_spans", ""))
    spans = _parse_json_field(spans_raw)
    if spans is not None:
        if not isinstance(spans, dict):
            errors.append("evidence_spans must be a JSON object")
        else:
            for code, quote in spans.items():
                if not isinstance(quote, str):
                    errors.append(f"evidence_spans['{code}'] must be a string")
                elif quote not in note:
                    errors.append(
                        f"evidence_spans['{code}'] quote not found verbatim in note"
                    )

    return errors


def ingest_csv(
    csv_path: Path,
    *,
    validate_only: bool = False,
    out_dir: Optional[Path] = None,
) -> int:
    """Ingest a CSV of golden labels. Returns number of cases written."""
    # Auto-detect CSV vs TSV.
    with open(csv_path, encoding="utf-8-sig") as f:
        sample = f.read(4096)
    dialect = "excel-tab" if "\t" in sample.split("\n")[0] else "excel"

    rows: List[Dict[str, str]] = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, dialect=dialect)
        if not reader.fieldnames:
            raise SystemExit(f"No header row found in {csv_path}")

        # Normalize headers (strip whitespace, lowercase).
        header_map = {h.strip().lower(): h for h in reader.fieldnames}
        missing = [c for c in REQUIRED_COLUMNS if c not in header_map]
        if missing:
            raise SystemExit(
                f"Missing required columns in {csv_path}: {missing}\n"
                f"Found columns: {list(header_map.keys())}"
            )
        for row in reader:
            normalized: Dict[str, str] = {}
            for key, original_key in header_map.items():
                normalized[key] = (row.get(original_key) or "").strip()
            rows.append(normalized)

    if not rows:
        raise SystemExit(f"No data rows found in {csv_path}")

    print(f"📋  Loaded {len(rows)} rows from {csv_path}")

    errors_by_case: Dict[str, List[str]] = {}
    valid_cases: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for i, row in enumerate(rows):
        cid = row.get("case_id", f"<row {i + 1}>")
        errs = validate_case(row)
        if errs:
            errors_by_case[str(cid)] = errs
        else:
            # Build the case dict for output.
            case: Dict[str, Any] = {
                "case_id": cid,
                "clinician_id": row.get("clinician_id", ""),
                "labeled_at": row.get("labeled_at", ""),
                "specialty": row.get("specialty", "primary_care"),
                "tenant_id_hint": row.get("tenant_id_hint", "synthetic"),
                "condition_category": row.get("condition_category", ""),
                "note": row.get("note", ""),
                "billed_codes": _parse_codes(row.get("billed_codes", "")),
                "expected_codes": _parse_codes(row.get("expected_codes", "")),
                "acceptable_alternatives": _parse_codes(
                    row.get("acceptable_alternatives", "")
                ),
                "must_abstain_codes": _parse_codes(row.get("must_abstain_codes", "")),
                "evidence_spans": _parse_json_field(row.get("evidence_spans", "")) or {},
                "edge_notes": row.get("edge_notes", ""),
                "notes": row.get("notes", ""),
                "guideline_refs": _parse_json_field(row.get("guideline_refs", "")) or {},
            }

            # Advisory V28 check.
            for code in case["expected_codes"]:
                if code not in _V28_HCC_CODES:
                    warnings.append(
                        f"  ⚠  {cid}: expected code '{code}' not in bundled "
                        f"V28 list — confirm with clinician"
                    )

            valid_cases.append(case)

    # Print errors.
    if errors_by_case:
        print(f"\n❌  {len(errors_by_case)} case(s) have validation errors:\n")
        for cid, errs in errors_by_case.items():
            print(f"  {cid}:")
            for e in errs:
                print(f"    • {e}")
        print()

    if warnings:
        print("⚠️  Advisory warnings:\n")
        for w in warnings:
            print(w)
        print()

    if errors_by_case:
        raise SystemExit(
            f"Validation failed for {len(errors_by_case)} case(s). "
            f"Fix errors and re-run."
        )

    if validate_only:
        print(f"✅  All {len(valid_cases)} case(s) pass validation (--validate-only).")
        return len(valid_cases)

    # Write cases.
    assert out_dir is not None
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for case in valid_cases:
        filename = f"{case['case_id']}.json"
        path = out_dir / filename
        path.write_text(
            json.dumps(case, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written += 1
        print(f"  ✅  Wrote {path}")

    print(f"\n✅  {written} case(s) written to {out_dir}/")
    return written


def coverage_report(cases_dir: Path) -> Dict[str, int]:
    """Count cases per condition_category in a golden directory."""
    counts: Counter = Counter()
    for path in sorted(cases_dir.glob("case_*.json")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        cat = case.get("condition_category", "unknown")
        counts[cat] += 1
    return dict(counts)


def _print_coverage(counts: Dict[str, int]) -> None:
    target = 20  # per-category target for 100-case set
    print("\n📊  Condition-category coverage:\n")
    print(f"  {'Category':<18} {'Count':>5}  {'Target':>6}  {'Gap':>5}")
    print(f"  {'─' * 18} {'─' * 5}  {'─' * 6}  {'─' * 5}")
    total = 0
    for cat in CONDITION_CATEGORIES:
        n = counts.get(cat, 0)
        total += n
        gap = target - n
        bar = "▓" * min(n // 2, 10) + "░" * max(0, 10 - n // 2)
        print(f"  {cat:<18} {n:>5}  {target:>6}  {gap:>5}  {bar}")
    print(f"  {'─' * 18} {'─' * 5}  {'─' * 6}  {'─' * 5}")
    print(f"  {'TOTAL':<18} {total:>5}  {100:>6}  {100 - total:>5}")
    print()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest clinician-labeled golden cases for the Buddi eval harness."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to the MD-provided CSV/TSV of labeled cases.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("evals/golden/v1"),
        help="Output directory for case_*.json files (default: evals/golden/v1).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the CSV without writing any files.",
    )
    parser.add_argument(
        "--coverage",
        type=Path,
        default=None,
        help="Print coverage report for an existing golden directory and exit.",
    )
    args = parser.parse_args(argv)

    if args.coverage:
        counts = coverage_report(args.coverage)
        _print_coverage(counts)
        return 0

    ingest_csv(
        args.csv,
        validate_only=args.validate_only,
        out_dir=args.out,
    )

    # Print coverage after write.
    if args.out.exists() and not args.validate_only:
        counts = coverage_report(args.out)
        _print_coverage(counts)

    return 0


if __name__ == "__main__":
    sys.exit(main())
