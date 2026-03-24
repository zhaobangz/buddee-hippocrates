"""Tests for the Safety & Audit layer."""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# We need to set up config before importing safety
os.environ.setdefault("ENABLE_SAFETY_LAYER", "True")
os.environ.setdefault("ENABLE_AUDIT_LOG", "True")
os.environ.setdefault("REQUIRE_HUMAN_APPROVAL", "True")

from core.safety import (
    validate_action,
    check_safety_boundaries,
    sanitize_response,
    log_audit_event,
    get_recent_audit_events,
    request_human_approval,
)
from core.config import Config


class TestValidation:
    def test_safe_action_allowed(self):
        """Normal clinical actions should be allowed."""
        result = validate_action("guidelines_lookup")
        assert result["allowed"] is True

    def test_blocked_diagnosis_action(self):
        """Diagnosis actions must be blocked."""
        result = validate_action("diagnosis")
        assert result["allowed"] is False
        assert "blocked" in result["reason"].lower() or "diagnos" in result["reason"].lower()

    def test_blocked_prescribe_action(self):
        """Prescribe actions must be blocked."""
        result = validate_action("prescribe_medication")
        assert result["allowed"] is False

    def test_requires_approval(self):
        """Prior auth submit should require human approval."""
        result = validate_action("prior_auth_submit")
        assert result["allowed"] is True
        assert result["requires_approval"] is True


class TestSafetyBoundaries:
    def test_safe_response(self):
        """A safe clinical response should pass."""
        result = check_safety_boundaries(
            "Based on ADA guidelines, metformin is the first-line treatment."
        )
        assert result["safe"] is True
        assert len(result["flagged_phrases"]) == 0

    def test_unsafe_response_diagnosis(self):
        """Response containing diagnosis language should be flagged."""
        result = check_safety_boundaries(
            "Based on the symptoms, you have diabetes."
        )
        assert result["safe"] is False
        assert "you have" in result["flagged_phrases"]

    def test_sanitize_safe_response(self):
        """Safe response should not get a disclaimer."""
        response = "Guidelines recommend regular monitoring."
        sanitized = sanitize_response(response)
        assert sanitized == response  # unchanged

    def test_sanitize_unsafe_response(self):
        """Unsafe response should get a disclaimer appended."""
        response = "I diagnose this as a rare condition."
        sanitized = sanitize_response(response)
        assert "DISCLAIMER" in sanitized
        assert response in sanitized  # original text preserved


class TestAuditLog:
    def setup_method(self):
        """Use a temp file for audit log."""
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
        self._tmp.close()
        self._orig = Config.AUDIT_LOG_FILE
        Config.AUDIT_LOG_FILE = self._tmp.name

    def teardown_method(self):
        Config.AUDIT_LOG_FILE = self._orig
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_log_and_retrieve(self):
        """Write an audit event and read it back."""
        log_audit_event("test_event", {"key": "value"}, user_id="test_user")
        events = get_recent_audit_events(10)
        assert len(events) >= 1
        last = events[-1]
        assert last["event_type"] == "test_event"
        assert last["user_id"] == "test_user"
        assert last["details"]["key"] == "value"

    def test_multiple_events(self):
        """Multiple events are stored in order."""
        for i in range(5):
            log_audit_event(f"event_{i}", {"index": i})
        events = get_recent_audit_events(10)
        assert len(events) >= 5


class TestHumanApproval:
    def test_approval_request_format(self):
        """Human approval request should be formatted properly."""
        message = request_human_approval(
            "prior_auth_submit",
            {"patient": "Jane Doe", "treatment": "MRI"},
        )
        assert "HUMAN APPROVAL REQUIRED" in message
        assert "prior_auth_submit" in message
