#!/usr/bin/env bash
# Buddi Tier 2 — GCP PHI‑tier provisioning.
#
# Idempotent: re‑running safely skips already‑created resources.
# Run with --dry-run to preview gcloud commands without executing them.
# Run with --teardown to destroy ALL provisioned resources (requires
# confirmation).
#
# Prerequisites (run once before first use):
#   1. gcloud auth login
#   2. gcloud config set project "$GCP_PROJECT_ID"
#   3. Enable APIs:
#        gcloud services enable \
#          sqladmin.googleapis.com \
#          cloudkms.googleapis.com \
#          secretmanager.googleapis.com \
#          redis.googleapis.com \
#          run.googleapis.com \
#          artifactregistry.googleapis.com \
#          compute.googleapis.com \
#          servicenetworking.googleapis.com \
#          cloudresourcemanager.googleapis.com \
#          iamcredentials.googleapis.com
#   4. BAA STATUS GATE: every Required‑BAA row in
#      docs/COMPLIANCE/baa_status.md must say ``signed: yes``.
#      Do NOT provision this tier until counsel confirms.
#
# Usage:
#   cp infra/env.tier2.example infra/env.tier2   # fill in values
#   source infra/env.tier2
#   bash infra/provision_gcp.sh                  # full provision
#   bash infra/provision_gcp.sh --dry-run        # preview only
#   bash infra/provision_gcp.sh --teardown       # destroy everything

set -euo pipefail

# ------------------------------------------------------------------
# Config — sourced from infra/env.tier2 (or env vars already set).
# ------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/env.tier2"

if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi

REQUIRED_VARS=(
  GCP_PROJECT_ID GCP_REGION VPC_CONNECTOR_NAME
  CLOUDSQL_INSTANCE CLOUDSQL_TIER CLOUDSQL_DB CLOUDSQL_USER CLOUDSQL_CMEK_KEY
  KMS_KEY_RING KMS_KEY_RING_LOCATION KMS_SIGNING_KEY
  AUDIT_BUCKET AUDIT_BUCKET_LOCATION AUDIT_OBJECT_LOCK_DAYS
  SECRET_NAME_DATABASE_URL SECRET_NAME_SECRET_KEY SECRET_NAME_STORAGE_KEY SECRET_NAME_API_KEY
  REDIS_INSTANCE API_SA WORKER_SA MIGRATE_SA AR_REPO AR_LOCATION
)

MODE="${1:-provision}"
DRY_RUN=false
DO_TEARDOWN=false

case "$MODE" in
  --dry-run) DRY_RUN=true ;;
  --teardown) DO_TEARDOWN=true ;;
  provision) ;;
  *) echo "Usage: $0 [--dry-run | --teardown]"; exit 1 ;;
esac

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
_gcloud() {
  if $DRY_RUN; then
    echo "[dry-run] gcloud $*"
    return 0
  fi
  gcloud "$@"
}

_say()  { echo "==> $*"; }
_done() { echo "    ✅  $*"; }
_skip() { echo "    ⏭️   $*"; }
_info() { echo "    📋  $*"; }

_check_project() {
  if ! gcloud projects describe "$GCP_PROJECT_ID" &>/dev/null; then
    echo "❌  Project $GCP_PROJECT_ID not found or gcloud not authenticated."
    echo "    Run: gcloud auth login && gcloud config set project $GCP_PROJECT_ID"
    exit 1
  fi
}

# ------------------------------------------------------------------
# Pre‑flight
# ------------------------------------------------------------------
_preflight() {
  _say "Pre‑flight checks"

  for var in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!var:-}" ]]; then
      echo "❌  $var is not set. Source infra/env.tier2 first."
      exit 1
    fi
  done

  if ! $DRY_RUN; then
    _check_project
  fi

  _done "All required vars set, project reachable"
}

# ------------------------------------------------------------------
# BAA gate
# ------------------------------------------------------------------
_baa_gate() {
  _say "⛔  BAA SIGN‑OFF GATE"
  echo ""
  echo "    Before provisioning Tier 2, confirm:"
  echo ""
  echo "    1. Anthropic BAA is signed and counter‑signed"
  echo "    2. Google Cloud BAA is signed and counter‑signed"
  echo "    3. docs/COMPLIANCE/baa_status.md shows signed: yes for both"
  echo "    4. Both founders have approved the Tier 2 go‑live"
  echo ""
  if $DRY_RUN; then
    _info "Dry‑run — skipping BAA confirmation prompt"
  else
    read -r -p "    Type YES to confirm all BAAs are signed: " CONFIRM
    if [[ "$CONFIRM" != "YES" ]]; then
      echo "❌  BAA gate not passed. Aborting."
      exit 1
    fi
  fi
  _done "BAA gate acknowledged"
}

# ------------------------------------------------------------------
# 1. Enable APIs
# ------------------------------------------------------------------
_enable_apis() {
  _say "Enabling required GCP APIs"
  local apis=(
    sqladmin.googleapis.com
    cloudkms.googleapis.com
    secretmanager.googleapis.com
    redis.googleapis.com
    run.googleapis.com
    artifactregistry.googleapis.com
    compute.googleapis.com
    servicenetworking.googleapis.com
    cloudresourcemanager.googleapis.com
    iamcredentials.googleapis.com
    monitoring.googleapis.com
  )
  for api in "${apis[@]}"; do
    if gcloud services list --enabled --project="$GCP_PROJECT_ID" 2>/dev/null | grep -q "$api"; then
      _skip "$api (already enabled)"
    else
      _gcloud services enable "$api" --project="$GCP_PROJECT_ID" --quiet
      _done "$api enabled"
    fi
  done
}

# ------------------------------------------------------------------
# 2. VPC connector (Cloud Run → private services)
# ------------------------------------------------------------------
_provision_vpc() {
  _say "VPC connector: $VPC_CONNECTOR_NAME"
  if gcloud compute networks vpc-access connectors describe "$VPC_CONNECTOR_NAME" \
      --region="$GCP_REGION" --project="$GCP_PROJECT_ID" &>/dev/null; then
    _skip "$VPC_CONNECTOR_NAME already exists"
  else
    _gcloud compute networks vpc-access connectors create "$VPC_CONNECTOR_NAME" \
      --region="$GCP_REGION" \
      --network=default \
      --range="10.8.0.0/28" \
      --project="$GCP_PROJECT_ID" \
      --quiet
    _done "VPC connector created"
  fi
}

# ------------------------------------------------------------------
# 3. Cloud KMS (Merkle‑root signing key)
# ------------------------------------------------------------------
_provision_kms() {
  _say "Cloud KMS key ring: $KMS_KEY_RING ($KMS_KEY_RING_LOCATION)"

  if gcloud kms keyrings describe "$KMS_KEY_RING" \
      --location="$KMS_KEY_RING_LOCATION" --project="$GCP_PROJECT_ID" &>/dev/null; then
    _skip "Key ring already exists"
  else
    _gcloud kms keyrings create "$KMS_KEY_RING" \
      --location="$KMS_KEY_RING_LOCATION" \
      --project="$GCP_PROJECT_ID"
    _done "Key ring created"
  fi

  if gcloud kms keys describe "$KMS_SIGNING_KEY" \
      --keyring="$KMS_KEY_RING" \
      --location="$KMS_KEY_RING_LOCATION" \
      --project="$GCP_PROJECT_ID" &>/dev/null; then
    _skip "Signing key already exists"
  else
    _gcloud kms keys create "$KMS_SIGNING_KEY" \
      --keyring="$KMS_KEY_RING" \
      --location="$KMS_KEY_RING_LOCATION" \
      --purpose=asymmetric-signing \
      --default-algorithm="$KMS_SIGNING_KEY_ALGORITHM" \
      --protection-level=software \
      --project="$GCP_PROJECT_ID"
    _done "Signing key created ($KMS_SIGNING_KEY_ALGORITHM)"

    # Print the key resource ID for core/merkle.py.
    _info "KMS key resource ID:"
    _info "  projects/$GCP_PROJECT_ID/locations/$KMS_KEY_RING_LOCATION/keyRings/$KMS_KEY_RING/cryptoKeys/$KMS_SIGNING_KEY/cryptoKeyVersions/1"
    _info "Set BUDDI_AUDIT_KMS_PROVIDER=gcp and BUDDI_AUDIT_KMS_KEY=<above> in production env."
  fi
}

# ------------------------------------------------------------------
# 4. Cloud SQL (Postgres 16 + pgvector, CMEK, private IP)
# ------------------------------------------------------------------
_provision_cloudsql() {
  _say "Cloud SQL: $CLOUDSQL_INSTANCE (tier=$CLOUDSQL_TIER)"

  if gcloud sql instances describe "$CLOUDSQL_INSTANCE" \
      --project="$GCP_PROJECT_ID" &>/dev/null; then
    _skip "Cloud SQL instance already exists"
  else
    _gcloud sql instances create "$CLOUDSQL_INSTANCE" \
      --database-version=POSTGRES_16 \
      --tier="$CLOUDSQL_TIER" \
      --region="$GCP_REGION" \
      --storage-type=SSD \
      --storage-size=10GB \
      --storage-auto-increase \
      --backup \
      --backup-start-time=03:00 \
      --enable-point-in-time-recovery \
      --retained-backups-count=7 \
      --retained-transaction-log-days=7 \
      --network=default \
      --no-assign-ip \
      --disk-encryption-key="$CLOUDSQL_CMEK_KEY" \
      --project="$GCP_PROJECT_ID" \
      --quiet
    _done "Cloud SQL instance created (CMEK, private IP, PITR enabled)"
  fi

  # Database
  if gcloud sql databases describe "$CLOUDSQL_DB" \
      --instance="$CLOUDSQL_INSTANCE" --project="$GCP_PROJECT_ID" &>/dev/null; then
    _skip "Database '$CLOUDSQL_DB' already exists"
  else
    _gcloud sql databases create "$CLOUDSQL_DB" \
      --instance="$CLOUDSQL_INSTANCE" \
      --project="$GCP_PROJECT_ID"
    _done "Database created"
  fi

  # User
  if gcloud sql users list --instance="$CLOUDSQL_INSTANCE" --project="$GCP_PROJECT_ID" 2>/dev/null | grep -q "$CLOUDSQL_USER"; then
    _skip "User '$CLOUDSQL_USER' already exists"
  else
    _gcloud sql users create "$CLOUDSQL_USER" \
      --instance="$CLOUDSQL_INSTANCE" \
      --password="$(openssl rand -base64 32)" \
      --project="$GCP_PROJECT_ID"
    _info "User '$CLOUDSQL_USER' created — save the password securely"
  fi

  # Enable pgvector (requires postgres connection after provisioning).
  _info "After provisioning, run:"
  _info "  gcloud sql connect $CLOUDSQL_INSTANCE --user=$CLOUDSQL_USER --database=$CLOUDSQL_DB"
  _info "  CREATE EXTENSION IF NOT EXISTS vector;"
}

# ------------------------------------------------------------------
# 5. GCS audit bucket (Object Lock, COMPLIANCE mode)
# ------------------------------------------------------------------
_provision_audit_bucket() {
  _say "GCS audit bucket: $AUDIT_BUCKET"

  if gcloud storage buckets describe "gs://$AUDIT_BUCKET" &>/dev/null; then
    _skip "Bucket already exists"
  else
    _gcloud storage buckets create "gs://$AUDIT_BUCKET" \
      --location="$AUDIT_BUCKET_LOCATION" \
      --project="$GCP_PROJECT_ID" \
      --uniform-bucket-level-access

    # Enable Object Lock (must be set at creation — can't be added later).
    _gcloud storage buckets update "gs://$AUDIT_BUCKET" \
      --object-lock-enabled

    # Set a default retention policy (COMPLIANCE mode).
    _gcloud storage buckets update "gs://$AUDIT_BUCKET" \
      --retention-period="${AUDIT_OBJECT_LOCK_DAYS}d" \
      --default-retention-mode=COMPLIANCE

    _done "Bucket created with Object Lock (COMPLIANCE, ${AUDIT_OBJECT_LOCK_DAYS}d retention)"
    _info "Set BUDDI_AUDIT_ROOTS_BUCKET=gs://$AUDIT_BUCKET/ in production env."
    _info "Set BUDDI_AUDIT_OBJECT_LOCK_MODE=COMPLIANCE"
    _info "Set BUDDI_AUDIT_OBJECT_LOCK_DAYS=$AUDIT_OBJECT_LOCK_DAYS"
  fi
}

# ------------------------------------------------------------------
# 6. Secret Manager
# ------------------------------------------------------------------
_provision_secrets() {
  _say "Secret Manager entries"

  local secrets=(
    "$SECRET_NAME_DATABASE_URL"
    "$SECRET_NAME_SECRET_KEY"
    "$SECRET_NAME_STORAGE_KEY"
    "$SECRET_NAME_API_KEY"
    "$SECRET_NAME_ANTHROPIC_KEY"
  )
  for name in "${secrets[@]}"; do
    if gcloud secrets describe "$name" --project="$GCP_PROJECT_ID" &>/dev/null; then
      _skip "Secret '$name' already exists"
    else
      _gcloud secrets create "$name" \
        --project="$GCP_PROJECT_ID" \
        --replication-policy=automatic
      _done "Secret '$name' created (add version with: gcloud secrets versions add $name --data-file=-)"
    fi
  done
}

# ------------------------------------------------------------------
# 7. Memorystore Redis (rate limiter + job coordination)
# ------------------------------------------------------------------
_provision_redis() {
  _say "Memorystore Redis: $REDIS_INSTANCE"

  if gcloud redis instances describe "$REDIS_INSTANCE" \
      --region="$GCP_REGION" --project="$GCP_PROJECT_ID" &>/dev/null; then
    _skip "Redis instance already exists"
  else
    _gcloud redis instances create "$REDIS_INSTANCE" \
      --size="$REDIS_SIZE_GB" \
      --region="$GCP_REGION" \
      --tier="$REDIS_TIER" \
      --redis-version=redis_7_0 \
      --network=default \
      --connect-mode=private-service-access \
      --project="$GCP_PROJECT_ID" \
      --quiet
    _done "Redis instance created"

    # Print the connection string for env config.
    local redis_host
    redis_host=$(gcloud redis instances describe "$REDIS_INSTANCE" \
      --region="$GCP_REGION" --project="$GCP_PROJECT_ID" \
      --format="value(host)")
    _info "Redis host: $redis_host"
    _info "Set REDIS_URL=redis://$redis_host:6379/0 in production env."
  fi
}

# ------------------------------------------------------------------
# 8. Artifact Registry
# ------------------------------------------------------------------
_provision_ar() {
  _say "Artifact Registry: $AR_REPO ($AR_LOCATION)"

  if gcloud artifacts repositories describe "$AR_REPO" \
      --location="$AR_LOCATION" --project="$GCP_PROJECT_ID" &>/dev/null; then
    _skip "Repository already exists"
  else
    _gcloud artifacts repositories create "$AR_REPO" \
      --repository-format=docker \
      --location="$AR_LOCATION" \
      --project="$GCP_PROJECT_ID"
    _done "Docker repository created"
  fi
}

# ------------------------------------------------------------------
# 9. Service accounts (least‑priv IAM)
# ------------------------------------------------------------------
_provision_service_accounts() {
  _say "Service accounts"

  local sas=("$API_SA" "$WORKER_SA" "$MIGRATE_SA")
  for sa in "${sas[@]}"; do
    local email="${sa}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
    if gcloud iam service-accounts describe "$email" \
        --project="$GCP_PROJECT_ID" &>/dev/null; then
      _skip "$email already exists"
    else
      _gcloud iam service-accounts create "$sa" \
        --display-name="Buddi — $sa" \
        --project="$GCP_PROJECT_ID"
      _done "$email created"
    fi
  done

  # API SA: Cloud SQL client, Secret Manager accessor, KMS signer, Redis
  _say "IAM bindings — buddi-api"
  local api_email="${API_SA}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
  _gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$api_email" \
    --role="roles/cloudsql.client" --condition=None --quiet || true
  _gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$api_email" \
    --role="roles/secretmanager.secretAccessor" --condition=None --quiet || true
  _gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$api_email" \
    --role="roles/cloudkms.signer" --condition=None --quiet || true
  _gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$api_email" \
    --role="roles/redis.viewer" --condition=None --quiet || true
  _done "buddi-api IAM bound"

  # Worker SA: Cloud SQL client, Secret Manager accessor
  _say "IAM bindings — buddi-worker"
  local worker_email="${WORKER_SA}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
  _gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$worker_email" \
    --role="roles/cloudsql.client" --condition=None --quiet || true
  _gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$worker_email" \
    --role="roles/secretmanager.secretAccessor" --condition=None --quiet || true
  _done "buddi-worker IAM bound"

  # Migrate SA: Cloud SQL client, Secret Manager accessor
  _say "IAM bindings — buddi-migrate"
  local migrate_email="${MIGRATE_SA}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
  _gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$migrate_email" \
    --role="roles/cloudsql.client" --condition=None --quiet || true
  _gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$migrate_email" \
    --role="roles/secretmanager.secretAccessor" --condition=None --quiet || true
  _done "buddi-migrate IAM bound"
}

# ------------------------------------------------------------------
# Teardown
# ------------------------------------------------------------------
_teardown() {
  _say "⛔  TEARDOWN — this destroys ALL Tier 2 resources"

  if $DRY_RUN; then
    _info "Dry‑run — would delete:"
    _info "  Cloud Run services: $CLOUD_RUN_API_SERVICE, $CLOUD_RUN_WORKER_SERVICE"
    _info "  Cloud Run job: $CLOUD_RUN_MIGRATE_JOB"
    _info "  Cloud SQL: $CLOUDSQL_INSTANCE"
    _info "  Redis: $REDIS_INSTANCE"
    _info "  KMS key ring: $KMS_KEY_RING"
    _info "  GCS bucket: $AUDIT_BUCKET"
    _info "  Artifact Registry: $AR_REPO"
    _info "  Secrets: 5 entries"
    _info "  Service accounts: $API_SA, $WORKER_SA, $MIGRATE_SA"
    return 0
  fi

  read -r -p "    Type ${GCP_PROJECT_ID} to confirm teardown: " CONFIRM
  if [[ "$CONFIRM" != "$GCP_PROJECT_ID" ]]; then
    echo "❌  Confirmation mismatch. Aborting."
    exit 1
  fi

  _say "Destroying Tier 2 resources..."

  gcloud run services delete "$CLOUD_RUN_API_SERVICE" --region="$GCP_REGION" --project="$GCP_PROJECT_ID" --quiet || true
  gcloud run services delete "$CLOUD_RUN_WORKER_SERVICE" --region="$GCP_REGION" --project="$GCP_PROJECT_ID" --quiet || true
  gcloud run jobs delete "$CLOUD_RUN_MIGRATE_JOB" --region="$GCP_REGION" --project="$GCP_PROJECT_ID" --quiet || true
  _done "Cloud Run services + job deleted"

  gcloud sql instances delete "$CLOUDSQL_INSTANCE" --project="$GCP_PROJECT_ID" --quiet || true
  _done "Cloud SQL deleted"

  gcloud redis instances delete "$REDIS_INSTANCE" --region="$GCP_REGION" --project="$GCP_PROJECT_ID" --quiet || true
  _done "Redis deleted"

  gcloud kms keys versions destroy 1 --key="$KMS_SIGNING_KEY" --keyring="$KMS_KEY_RING" --location="$KMS_KEY_RING_LOCATION" --project="$GCP_PROJECT_ID" --quiet || true
  _done "KMS key version destroyed"

  gcloud storage rm --recursive "gs://$AUDIT_BUCKET" || true
  _done "Audit bucket emptied"

  gcloud artifacts repositories delete "$AR_REPO" --location="$AR_LOCATION" --project="$GCP_PROJECT_ID" --quiet || true
  _done "Artifact Registry deleted"

  for name in "$SECRET_NAME_DATABASE_URL" "$SECRET_NAME_SECRET_KEY" "$SECRET_NAME_STORAGE_KEY" "$SECRET_NAME_API_KEY" "$SECRET_NAME_ANTHROPIC_KEY"; do
    gcloud secrets delete "$name" --project="$GCP_PROJECT_ID" --quiet || true
  done
  _done "Secrets deleted"

  for sa in "$API_SA" "$WORKER_SA" "$MIGRATE_SA"; do
    gcloud iam service-accounts delete "${sa}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" --project="$GCP_PROJECT_ID" --quiet || true
  done
  _done "Service accounts deleted"

  _done "Teardown complete"
  exit 0
}

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
main() {
  echo ""
  echo "🏗️   Buddi Tier 2 — GCP PHI‑tier provisioning"
  echo "     Project: ${GCP_PROJECT_ID:-<not set>}"
  echo "     Region:  ${GCP_REGION:-<not set>}"
  if $DRY_RUN; then echo "     Mode:    DRY‑RUN (no changes)"; fi
  echo ""

  if $DO_TEARDOWN; then
    _teardown
  fi

  _preflight
  _baa_gate
  _enable_apis
  _provision_vpc
  _provision_kms
  _provision_cloudsql
  _provision_audit_bucket
  _provision_secrets
  _provision_redis
  _provision_ar
  _provision_service_accounts

  echo ""
  echo "═══════════════════════════════════════════════════════════════"
  echo "✅  Tier 2 provisioning complete."
  echo ""
  echo "Next steps (manual):"
  echo ""
  echo "1. Add secret versions:"
  echo "     echo -n 'postgresql://...' | gcloud secrets versions add $SECRET_NAME_DATABASE_URL --data-file=-"
  echo "     # Repeat for SECRET_KEY, STORAGE_KEY, API_KEY, ANTHROPIC_KEY"
  echo ""
  echo "2. Deploy the services:"
  echo "     gcloud builds submit --tag $AR_LOCATION-docker.pkg.dev/$GCP_PROJECT_ID/$AR_REPO/buddi-api:prod"
  echo "     gcloud run services replace infra/cloud-run-api.yaml --region=$GCP_REGION"
  echo "     gcloud run services replace infra/cloud-run-worker.yaml --region=$GCP_REGION"
  echo ""
  echo "3. Run migrations:"
  echo "     gcloud run jobs create $CLOUD_RUN_MIGRATE_JOB --image=... --region=$GCP_REGION"
  echo "     gcloud run jobs execute $CLOUD_RUN_MIGRATE_JOB --region=$GCP_REGION --wait"
  echo ""
  echo "4. Set env vars (see infra/env.tier2 for the full list):"
  echo "     BUDDI_AUDIT_KMS_PROVIDER=gcp"
  echo "     BUDDI_AUDIT_KMS_KEY=projects/$GCP_PROJECT_ID/locations/$KMS_KEY_RING_LOCATION/keyRings/$KMS_KEY_RING/cryptoKeys/$KMS_SIGNING_KEY/cryptoKeyVersions/1"
  echo "     BUDDI_AUDIT_ROOTS_BUCKET=gs://$AUDIT_BUCKET/"
  echo "     BUDDI_AUDIT_OBJECT_LOCK_MODE=COMPLIANCE"
  echo "     REDIS_URL=redis://<redis-host>:6379/0"
  echo ""
  echo "5. Flip BUDDI_BAA_CONFIRMED=1 ONLY after counsel confirms BAAs."
  echo "═══════════════════════════════════════════════════════════════"
}

main
