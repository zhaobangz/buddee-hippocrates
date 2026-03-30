"""Project integrity tests—ensuring basic import/initialization safety.

Prevents major runtime regressions such as syntax errors or missing dependencies
that lead to uvicorn/fastapi process crashes.
"""

import pytest
import os
import sys

# Ensure root is in path
sys.path.append(os.path.abspath("."))

def test_imports():
    """Verify that core and backend modules import without errors."""
    from core.config import Config
    from core.agent import Agent
    from backend.api import app
    assert Config is not None
    assert Agent is not None
    assert app is not None

def test_config_load():
    """Verify that Config values can be accessed."""
    from core.config import Config
    assert hasattr(Config, "LLM_PROVIDER")
    assert isinstance(Config.ASSISTANT_NAME, str)

def test_agent_init():
    """Verify that Agent can be initialized."""
    from core.agent import Agent
    agent = Agent()
    assert agent is not None
    assert hasattr(agent, "handle")

def test_storage_encryption():
    """Verify that encryption-at-rest basics work."""
    from core.storage import SecureStorage
    import tempfile
    
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name
        
    try:
        storage = SecureStorage(encryption_key="test-key")
        test_data = {"key": "value", "list": [1, 2, 3]}
        
        # Save encrypted
        storage.save_json(tmp_path, test_data)
        
        # Verify it's not plain text anymore
        with open(tmp_path, "rb") as f:
            raw = f.read()
            assert not raw.startswith(b"{")
            
        # Load and decrypt
        loaded = storage.load_json(tmp_path)
        assert loaded == test_data
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":
    pytest.main([__file__])
