#!/usr/bin/env bash
#
# generate_synthea_bundles.sh — build-out A3.1
#
# Produces the synthetic FHIR bundle library used by the demo and evals.
#
# Two modes:
#
#   DEFAULT (hermetic, deterministic, no network) — runs the in-repo
#   generator, which fabricates Safe-Harbor R4 bundles covering the five
#   strategy-doc conditions plus 20 more, and (re)writes the committed
#   5-bundle demo fixture set under evals/synthea/fixtures/. This is what
#   CI uses; it requires only Python and never touches the network.
#
#   REAL SYNTHEA (USE_REAL_SYNTHEA=1) — downloads the Synthea JAR (if not
#   already cached) and runs it with the five disease modules, emitting 5
#   bundles per condition into evals/synthea/bundles/. Use this to refresh
#   the corpus from upstream Synthea; the output is git-ignored by default
#   so generated bundles are not committed (the committed fixtures are the
#   stable demo set).
#
# Usage:
#   ./scripts/generate_synthea_bundles.sh
#   USE_REAL_SYNTHEA=1 ./scripts/generate_synthea_bundles.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

BUNDLE_DIR="evals/synthea/bundles"
SYNTHEA_JAR="${SYNTHEA_JAR:-build/synthea-with-dependencies.jar}"
SYNTHEA_JAR_URL="${SYNTHEA_JAR_URL:-https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/synthea-with-dependencies.jar}"
PER_CONDITION="${PER_CONDITION:-5}"

# The five strategy-doc disease modules (§2.2). Module names match the
# Synthea module library; adjust if upstream renames a module.
MODULES=(
  "diabetes"
  "congestive_heart_failure"
  "copd"
  "chronic_kidney_disease"
  "sepsis"
)

if [[ "${USE_REAL_SYNTHEA:-0}" != "1" ]]; then
  echo "==> Generating synthetic bundles + demo fixtures via the in-repo generator"
  echo "    (set USE_REAL_SYNTHEA=1 to download and run the real Synthea JAR)"
  python -m evals.synthea.generate --out "${BUNDLE_DIR}" --fixtures
  exit 0
fi

echo "==> USE_REAL_SYNTHEA=1: generating from the upstream Synthea JAR"

if [[ ! -f "${SYNTHEA_JAR}" ]]; then
  echo "==> Synthea JAR not found at ${SYNTHEA_JAR}; downloading..."
  mkdir -p "$(dirname "${SYNTHEA_JAR}")"
  curl -fsSL "${SYNTHEA_JAR_URL}" -o "${SYNTHEA_JAR}"
fi

if ! command -v java >/dev/null 2>&1; then
  echo "ERROR: java is required to run Synthea but was not found on PATH." >&2
  exit 1
fi

mkdir -p "${BUNDLE_DIR}"
for module in "${MODULES[@]}"; do
  echo "==> Synthea module: ${module} (${PER_CONDITION} bundles)"
  java -jar "${SYNTHEA_JAR}" \
    -p "${PER_CONDITION}" \
    -m "${module}" \
    --exporter.fhir.export true \
    --exporter.fhir.use_us_core_ig false \
    --exporter.baseDirectory "${BUNDLE_DIR}/${module}"
done

echo "==> Done. Real Synthea bundles written under ${BUNDLE_DIR}/<module>/."
echo "    Note: generated bundles are git-ignored; the committed demo set is"
echo "    evals/synthea/fixtures/ (regenerate with the default mode of this script)."
