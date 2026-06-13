"""SQLAlchemy ORM definitions for the Buddi clinical data model.

Re-audit (April 21) follow-ups applied here:

* CQ-04 — every ``default=datetime.datetime.utcnow`` has been replaced with
  the timezone-aware ``_utcnow`` helper. ``datetime.utcnow()`` is deprecated
  in Python 3.12 and scheduled for removal in 3.14. Because every affected
  column is ``DateTime(timezone=True)``, swapping in
  ``datetime.now(timezone.utc)`` preserves the stored value (an aware UTC
  instant) while silencing the deprecation warning.

* DB-05 — ``RecoveryEvent.id`` is now a proper ``PG_UUID`` column with
  ``uuid.uuid4`` as the default, instead of a free-form string. This removes
  the string-index overhead on joins and guarantees DB-level uniqueness.
"""

from __future__ import annotations

import datetime
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, UUID as PG_UUID
from sqlalchemy.orm import declarative_base, relationship  # noqa: F401  (relationship re-exported for future models)

Base = declarative_base()


def _utcnow() -> datetime.datetime:
    """Timezone-aware UTC 'now' — replacement for the deprecated
    ``datetime.utcnow()``. Used as a SQLAlchemy ``default=`` callable so every
    row stamps its creation time consistently across Python versions.
    """
    return datetime.datetime.now(datetime.timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    # Manual §7.2 Risk #1 mitigation: real PHI cannot flow through
    # /ingest/fhir for this tenant until the BAA paperwork (LLM
    # provider + tenant) is filed and this column is flipped to True.
    # See alembic/versions/7a3c8d9f0142_rls_baa_hnsw.py and
    # docs/COMPLIANCE/baa_status.md.
    baa_confirmed = Column(Boolean, nullable=False, default=False, server_default="false")
    baa_confirmed_at = Column(DateTime(timezone=True), nullable=True)


class TenantApiKey(Base):
    """Per-tenant API credential metadata.

    ``key_hash_sha256`` is deterministic and safe to index for lookup. The full
    presented key is then verified against the salted Argon2 ``hashed_key``.
    Canonical scopes are ``clinician``, ``ingest``, and ``admin``.
    """

    __tablename__ = "tenant_api_keys"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    key_hash_sha256 = Column(String(64), nullable=False, unique=True, index=True)
    hashed_key = Column(Text, nullable=False, unique=True)
    scopes = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)


class Patient(Base):
    __tablename__ = "patients"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    external_ehr_id = Column(String(255))
    demographics_encrypted = Column(BYTEA)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class Encounter(Base):
    __tablename__ = "encounters"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    patient_id = Column(PG_UUID(as_uuid=True), ForeignKey("patients.id"))
    encounter_date = Column(DateTime(timezone=True))
    hl7_event_type = Column(String(50))
    status = Column(String(50), default="open")
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class ClinicalNote(Base):
    __tablename__ = "clinical_notes"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    encounter_id = Column(PG_UUID(as_uuid=True), ForeignKey("encounters.id"))
    provider_id = Column(String(255))
    note_text = Column(Text)
    is_signed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class BillingCode(Base):
    __tablename__ = "billing_codes"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    encounter_id = Column(PG_UUID(as_uuid=True), ForeignKey("encounters.id"))
    code = Column(String(50))
    code_type = Column(String(20))
    is_hcc = Column(Boolean, default=False)
    source = Column(String(50))
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class HccSuggestion(Base):
    __tablename__ = "hcc_suggestions"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    encounter_id = Column(PG_UUID(as_uuid=True), ForeignKey("encounters.id"))
    suggested_code = Column(String(50))
    justification = Column(Text)
    confidence_score = Column(Float)
    status = Column(String(50), default="pending")
    llm_request_id = Column(PG_UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class PriorAuthorizationRequest(Base):
    __tablename__ = "prior_authorization_requests"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    encounter_id = Column(PG_UUID(as_uuid=True), ForeignKey("encounters.id"))
    procedure_code = Column(String(50))
    payer_name = Column(String(255))
    status = Column(String(50), default="draft")
    submission_payload = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)


class PriorAuthState(Base):
    __tablename__ = "prior_auth_states"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    prior_auth_id = Column(PG_UUID(as_uuid=True), ForeignKey("prior_authorization_requests.id"))
    state = Column(String(50))  # Draft, pending_approval, submitted, approved, denied
    changed_at = Column(DateTime(timezone=True), default=_utcnow)
    changed_by = Column(PG_UUID(as_uuid=True))
    reasoning = Column(Text)


class LlmRequest(Base):
    __tablename__ = "llm_requests"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    encounter_id = Column(PG_UUID(as_uuid=True), ForeignKey("encounters.id"))
    prompt_template_version = Column(String(255))
    model = Column(String(255))
    full_prompt = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class LlmResponse(Base):
    __tablename__ = "llm_responses"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    llm_request_id = Column(PG_UUID(as_uuid=True), ForeignKey("llm_requests.id"))
    raw_response = Column(Text)
    parsed_json = Column(JSONB)
    tokens_used = Column(Integer)
    latency_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class RagRetrieval(Base):
    __tablename__ = "rag_retrievals"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    llm_request_id = Column(PG_UUID(as_uuid=True), ForeignKey("llm_requests.id"))
    chunk_id = Column(PG_UUID(as_uuid=True))
    similarity_score = Column(Float)
    retrieved_at = Column(DateTime(timezone=True), default=_utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    clinical_note_id = Column(PG_UUID(as_uuid=True), ForeignKey("clinical_notes.id"))
    content = Column(Text)
    embedding = Column(Vector(1536))
    chunk_index = Column(Integer)
    version = Column(Integer, default=1)


class EhrIntegration(Base):
    __tablename__ = "ehr_integrations"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    ehr_vendor = Column(String(100))
    api_endpoint = Column(String(255))
    auth_credentials_encrypted = Column(BYTEA)
    status = Column(String(50), default="active")
    last_sync = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class ComplianceFlag(Base):
    __tablename__ = "compliance_flags"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    encounter_id = Column(PG_UUID(as_uuid=True), ForeignKey("encounters.id"))
    flag_type = Column(String(100))
    description = Column(Text)
    severity = Column(String(50))
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class AuditEvent(Base):
    # ``audit_events`` is RANGE-partitioned by ``timestamp`` (monthly) — see
    # migration ``c4f1e2d3a5b6_partition_audit_events.py``. Postgres requires
    # the partition key to be part of the PRIMARY KEY, so the physical PK is
    # ``(event_id, timestamp)``. The ORM still treats ``event_id`` as the
    # logical row identifier — ``BIGSERIAL`` keeps it globally unique — and
    # SQLAlchemy is happy to load/save rows through this single-column
    # mapping without composite-PK ceremony.
    #
    # Query caveat: range queries that **omit** ``timestamp`` cannot be
    # partition-pruned and will fan out across every monthly partition.
    # Hot paths (verify-chain walks, recent-event reads) should always
    # include a ``timestamp >= ...`` filter so the planner can prune.
    __tablename__ = "audit_events"
    event_id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    patient_id = Column(PG_UUID(as_uuid=True), ForeignKey("patients.id"), nullable=True)
    actor_id = Column(PG_UUID(as_uuid=True), nullable=True)
    event_type = Column(String(100))
    payload = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), default=_utcnow)
    cryptographic_hash = Column(Text)
    previous_hash = Column(Text)


class RecoveryEvent(Base):
    __tablename__ = "recovery_events"
    # DB-05: id is a real UUID, not a stringified one. This matches the rest
    # of the data model, enables efficient index lookups, and prevents
    # hex-formatting drift between callers.
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"))
    audit_hash = Column(String, index=True)
    patient_id = Column(String)
    recovered_revenue = Column(Float)
    timestamp = Column(DateTime(timezone=True), default=_utcnow)
