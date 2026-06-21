# Runbook: Secret Rotation

**Scope:** rotating the secrets Buddi depends on, on Google Cloud (Secret Manager
+ Cloud Run). **Audience:** on-call / platform engineer with `roles/secretmanager.admin`
and `roles/run.admin` on the project.

**Golden rules**
- Never paste a secret into a shell history, a commit, a PR, a ticket, or Slack.
  Pipe from a file or `--data-file=-` and clear your clipboard afterwards.
- Add the **new** version *before* you remove the old one. Cloud Run reads the
  secret at instance start, so an in-flight revision keeps the old value until it
  is replaced — rotate forward, verify, then revoke.
- Every rotation ends with a health check and an audit-log note.

Secret Manager names used below (adjust to your project's layout — see
`infra/cloud-run-api.yaml`):

| Secret | Secret Manager name | Env var consumed |
|---|---|---|
| Anthropic API key | `buddi-anthropic-key` | `ANTHROPIC_API_KEY` |
| OpenAI API key | `buddi-openai-key` | `OPENAI_API_KEY` |
| App signing secret | `buddi-secret-key` | `SECRET_KEY` |
| Storage/DEK wrap key | `buddi-storage-key` | `BUDDI_STORAGE_KEY` |
| DB connection string | `buddi-database-url` | `DATABASE_URL` |

> Cloud Run wiring assumed below:
> `--set-secrets ANTHROPIC_API_KEY=buddi-anthropic-key:latest,...`. With `:latest`,
> a **new revision** picks up the newest enabled version automatically; that is why
> every rotation includes "deploy a new revision". If you pin explicit versions
> instead, bump the version number in the `--set-secrets` reference.

---

## 1. Anthropic API key (`ANTHROPIC_API_KEY`)

Cadence: **90 days** (see schedule).

1. Generate a new key in the Anthropic Console (Settings → API Keys → Create Key).
   Keep the old key active for now.
2. Add it as a new Secret Manager version (input is piped, never echoed):
   ```bash
   printf '%s' "$NEW_ANTHROPIC_KEY" | \
     gcloud secrets versions add buddi-anthropic-key --data-file=-
   ```
3. Roll a new Cloud Run revision so instances pick up `:latest` (no image change):
   ```bash
   gcloud run services update buddi-api    --region="$REGION" --revision-suffix="rot-$(date +%Y%m%d)"
   gcloud run services update buddi-worker --region="$REGION" --revision-suffix="rot-$(date +%Y%m%d)"
   ```
   The worker also calls the LLM, so rotate it too.
4. Verify:
   ```bash
   curl -fsS "https://api.buddi.health/health"        # 200
   curl -fsS "https://api.buddi.health/api/health" -H "Authorization: Bearer $API_KEY"   # 200, llm reachable
   ```
   Then run one `?sync=true` shadow-audit against a synthetic note and confirm a
   real (non-demo) response.
5. **Revoke** the old key in the Anthropic Console. Confirm traffic still healthy.
6. Disable the superseded Secret Manager version once the new one is proven:
   ```bash
   gcloud secrets versions disable <OLD_VERSION> --secret=buddi-anthropic-key
   ```

> BAA note: a key swap does not change BAA status. Do not flip `BUDDI_BAA_CONFIRMED`
> as part of rotation.

## 2. OpenAI API key (`OPENAI_API_KEY`)

Cadence: **90 days**. Identical procedure to §1 with `buddi-openai-key` /
`OPENAI_API_KEY`. OpenAI is embeddings-only by default; the RAG path degrades to
"embeddings disabled" rather than erroring if the key is briefly invalid, but
rotate-forward-then-revoke anyway. Revoke the old key at platform.openai.com.

## 3. `SECRET_KEY` (application signing secret)

Cadence: **365 days**.

**Current state.** `SECRET_KEY` is a mandatory, validated secret (`core/config.py`
rejects the insecure default). Buddi's request auth today is **per-tenant API keys**
(`backend/auth.py`: `api_key_lookup_hash` + Argon2 `hashed_key`), which do **not**
depend on `SECRET_KEY`. So with the current code a rotation is a single forward
replace + redeploy:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))" | \
  gcloud secrets versions add buddi-secret-key --data-file=-
gcloud run services update buddi-api --region="$REGION" --revision-suffix="rot-$(date +%Y%m%d)"
curl -fsS "https://api.buddi.health/health"   # 200
```

**Dual-key window (required once `SECRET_KEY` signs session tokens / JWTs).**
The moment `SECRET_KEY` is used to *sign* anything with a lifetime (JWT session
tokens, signed cookies, `itsdangerous` tokens), a hard swap invalidates every
live token. Use an overlap window:

1. Introduce a second config field, e.g. `SECRET_KEY_PREVIOUS` (default `""`), in
   `core/config.py`.
2. In `backend/auth.py`, **sign with `SECRET_KEY`**, but **verify against every
   key in `[SECRET_KEY, SECRET_KEY_PREVIOUS]`** (skip blanks). Sketch:
   ```python
   def _signing_keys() -> list[str]:
       return [k for k in (settings.SECRET_KEY, settings.SECRET_KEY_PREVIOUS) if k]

   def verify_token(token: str) -> dict:
       last_err = None
       for key in _signing_keys():
           try:
               return jwt.decode(token, key, algorithms=["HS256"])
           except jwt.InvalidTokenError as e:
               last_err = e
       raise last_err  # all keys rejected
   ```
3. Rotation with that code in place:
   - Set `buddi-secret-key-previous` = current key; set `buddi-secret-key` = new key.
   - Deploy **one** revision honoring both (new tokens signed with new key; old
     tokens still verify against previous).
   - After the max token lifetime has elapsed, clear `SECRET_KEY_PREVIOUS` and
     deploy again to retire the old key.

## 4. `BUDDI_STORAGE_KEY` (DEK-wrapping key)

Cadence: **do not rotate until re-encryption tooling exists** (see schedule).

`BUDDI_STORAGE_KEY` wraps the data-encryption keys used by `core/storage.py`
(`SecureStorage`) for encrypted artifacts — `audit_log.json`, encrypted DB
columns (e.g. `patients.demographics_encrypted`, `ehr_integrations.auth_credentials_encrypted`),
and webhook signing secrets. **Rotating it without re-encrypting existing
ciphertext renders all of that permanently unreadable.**

Rotation is therefore a migration, not a config change:

1. **TODO — build `scripts/reencrypt_storage.py` (does not exist yet).** It must,
   inside a single maintenance window with writes quiesced:
   - load the OLD `BUDDI_STORAGE_KEY` and the NEW one,
   - stream every encrypted column / file, decrypt with OLD, re-encrypt with NEW,
     write back transactionally (per-tenant, resumable, with a dry-run mode),
   - re-wrap the audit-chain artifacts and verify the Merkle chain still validates
     end-to-end **before** committing the cutover,
   - emit an audit event (`storage_key_rotated`) recording counts re-encrypted.
2. Only after that script exists and has a tested rollback: add the new version,
   run the re-encryption job, then deploy a revision pointing at the new key.

Until then: **treat `BUDDI_STORAGE_KEY` as non-rotatable.** If it is suspected
compromised, that is an incident (see `docs/INCIDENT_RESPONSE.md`), not a routine
rotation — escalate.

## 5. Database password (`DATABASE_URL`)

Cadence: **180 days**.

1. Cloud SQL → Instances → your instance → **Users** → select the Buddi app user →
   **Change password** (or `gcloud sql users set-password buddi_user --instance=<inst> --prompt-for-password`).
2. Update the connection string secret (new password embedded):
   ```bash
   printf '%s' "postgresql://buddi_user:$NEW_DB_PASSWORD@$DB_HOST:5432/buddi" | \
     gcloud secrets versions add buddi-database-url --data-file=-
   ```
3. Deploy new revisions of **both** `buddi-api` and `buddi-worker` (both hold DB
   connections). Cloud Run drains old instances; pooled connections on old
   revisions close as those instances are torn down.
4. Verify `GET /api/health` (DB-backed) returns 200, then disable the old secret
   version.

> Prefer the Cloud SQL **IAM database authentication** path long-term — it removes
> the static password from `DATABASE_URL` entirely. Migrating to it retires this
> rotation step.

---

## 6. Rotation schedule

| Secret | Interval | Method | Dual-key / re-encryption? |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | 90 days | add version → redeploy → revoke old | No |
| `OPENAI_API_KEY` | 90 days | add version → redeploy → revoke old | No |
| `DATABASE_URL` (DB password) | 180 days | Cloud SQL user pw → update secret → redeploy | No |
| `SECRET_KEY` | 365 days | add version → redeploy | Dual-key once it signs tokens (§3) |
| `BUDDI_STORAGE_KEY` | **do not rotate** until re-encryption tooling exists | migration job (§4) | **Yes — re-encrypt all ciphertext** |

**After every rotation**
- Confirm `GET /health` (200, unauthenticated) and `GET /api/health` (200, authenticated).
- Record the rotation (secret name, new version id, operator, UTC timestamp) in the
  change log; the audit chain captures runtime access but not the rotation event itself.
- Disable — don't destroy — the superseded version until the next rotation, so an
  emergency rollback is one `gcloud secrets versions enable` away.
