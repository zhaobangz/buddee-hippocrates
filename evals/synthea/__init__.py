"""Synthetic FHIR R4 bundles for the public demo + eval harness.

Manual §2.2 week 4 deliverable: 25 synthetic FHIR bundles spanning the
HCC-heavy specialties the primary ICP cares about (diabetes
complications, CHF, COPD, CKD, sepsis, dementia). The intent is to
seed the public `demo.buddi.health` sandbox without ever using real
PHI.

The bundles produced here are **not** real Synthea exports — Synthea
proper is a multi-GB Java project. They are minimal,
schema-conformant ``Bundle`` documents that exercise the same
``FHIRAdapter.extract_from_bundle`` path real exports do, so the
shape contract between Synthea and the API holds.
"""
