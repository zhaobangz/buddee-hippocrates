# Business Associate Agreement (BAA) Status

**Owner:** Founder (Zhao)
**Cadence:** Reviewed weekly until first BAA lands, then quarterly.
**Last reviewed:** *fill in at every retrospective*

This document is the single source of truth for "which of our vendors
has a signed BAA, and which has not." It is referenced by
`core/llm_manager.py:_baa_guard`, `backend/api.py:_enforce_baa_precondition`,
and the tenant provisioning runbook.

The technical fail-closed posture is documented in
`Buddi_Strategic_Founders_Operating_Manual.pdf` §7.2 Risk #1. Until
every row in the **Required BAAs** table below is `signed: yes`, the
production env must keep `BUDDI_BAA_CONFIRMED=0` and every
`tenants.baa_confirmed` flag must remain FALSE. Together these two
guards refuse to send any prompt that resembles real PHI to an LLM
provider, and refuse to accept any FHIR bundle from an unconfirmed
tenant.

## Required BAAs

| Vendor                       | Purpose                                     | BAA filed | Signed | Counter-signed | Effective date | Stored at                                  |
| ---------------------------- | ------------------------------------------- | --------- | ------ | -------------- | -------------- | ------------------------------------------ |
| Anthropic                    | Primary LLM (clinical reasoning)            | TODO      | no     | no             | —              | (encrypted folder in counsel's vault)      |
| OpenAI                       | Embeddings only (`text-embedding-3-large`)  | TODO      | no     | no             | —              | (encrypted folder in counsel's vault)      |
| Google Cloud (GCP)           | Cloud Run, Cloud SQL, KMS, Cloud Logging    | TODO      | no     | no             | —              | (encrypted folder in counsel's vault)      |
| Render (interim hosting)     | Pre-pilot marketing backend                 | TODO      | no     | no             | —              | (encrypted folder in counsel's vault)      |
| (Any payer integration)      | Future                                      | n/a       | n/a    | n/a            | —              | —                                          |

## Per-tenant BAAs

These are tracked at the database level via `tenants.baa_confirmed`
and `tenants.baa_confirmed_at`. The provisioning runbook flips them
manually after counsel has verified the signed PDF and counter-
signature.

```sql
-- Flip the flag for a tenant after the BAA is signed:
UPDATE tenants
   SET baa_confirmed = TRUE,
       baa_confirmed_at = NOW()
 WHERE id = '<tenant-uuid>';
```

The provisioning runbook (`docs/COMPLIANCE/tenant_provisioning.md`,
TODO) must require:

1. Counsel-signed copy of the BAA on file (encrypted vault).
2. Counter-signed by the customer's compliance officer.
3. The flag flip is recorded in the audit chain as
   `tenant_baa_confirmed` so a future auditor can see exactly when
   each tenant became eligible to send real PHI.

## How the technical guards reference this file

* `core/llm_manager.py:_baa_guard` — Refuses prompts > 200 bytes or
  containing `<clinical_note>` / `<clinical_context>` delimiters when
  `BUDDI_BAA_CONFIRMED != 1`. Set `BUDDI_BAA_CONFIRMED=1` only when
  *every* row in the **Required BAAs** table is `signed: yes`.

* `backend/api.py:_enforce_baa_precondition` — Refuses `/ingest/fhir`
  bundles with HTTP 412 when the requesting tenant's
  `baa_confirmed` flag is FALSE.

* `core/merkle.py:MerkleSigner.from_env` — The signed daily Merkle
  root is the artifact you hand a CMS / OIG auditor; it is independent
  of the BAA flow but lives in the same compliance posture.

## Founder action checklist

Per manual §2.2 week 1, this week:

- [ ] File the OpenAI BAA application.
- [ ] File the Anthropic BAA application.
- [ ] Confirm GCP BAA is in place (GCP signs BAAs without enterprise
      minimums; see Cloud HIPAA documentation).
- [ ] Add `BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH` pointing at an Ed25519
      key provisioned in Cloud KMS / AWS KMS, *not* a local PEM. Update
      this file with the key ID once provisioned.
- [ ] Update this file's "Last reviewed" header.

## Per-vendor notes

### Anthropic

Anthropic offers BAAs through their healthcare program; request via
their sales contact. Required before any PHI prompt routes through
`core/llm_manager.py:_anthropic_chat`.

### OpenAI

OpenAI BAAs are available on Enterprise tier. If you are not on
Enterprise: **do not send a single real chart through the OpenAI
prompt path**. Embeddings of non-PHI guideline text (`core/rag_engine.py`)
are a separate question and the position taken in this codebase is
that public CMS guideline embeddings are not PHI. Reconfirm with
counsel before scaling.

### Google Cloud

GCP signs HIPAA BAAs without enterprise minimums. Confirm that **all**
in-scope services for the deployment are covered by the BAA — the
list is published at
https://cloud.google.com/security/compliance/hipaa-compliance — and
update this file with the effective date.
