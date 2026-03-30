"""Clinical Storage Utility — Production Hardening.

Provides encrypted I/O for sensitive patient data (Memory, Audit Logs).
Implements AESnd / Fernet symmetric encryption.
"""

import os
import json
import base64
from typing import Any, Dict, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class SecureStorage:
    def __init__(self, encryption_key: Optional[str] = None):
        """Initialize secure storage with a key or environment variable.
        
        Args:
            encryption_key: Raw key or passphrase for storage encryption.
        """
        # Get key from env if not provided
        self.key = encryption_key or os.getenv("BUDDI_STORAGE_KEY", "clinical-dev-key-not-for-prod")
        self._fernet = self._derive_fernet(self.key)

    def _derive_fernet(self, secret: str) -> Fernet:
        """Derive a cryptographic key from a passphrase."""
        # Note: In production, salt should be unique and stored separately
        salt = b"buddi-clinical-salt-2024" 
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
        return Fernet(key)

    def save_json(self, file_path: str, data: Any) -> bool:
        """Encrypt and save data as JSON to a file."""
        try:
            json_data = json.dumps(data).encode()
            encrypted_data = self._fernet.encrypt(json_data)
            
            with open(file_path, "wb") as f:
                f.write(encrypted_data)
            return True
        except Exception as e:
            print(f"SecureStorage Error (Save): {e}")
            return False

    def load_json(self, file_path: str) -> Optional[Any]:
        """Decrypt and load JSON data from a file."""
        if not os.path.exists(file_path):
            return None
            
        try:
            with open(file_path, "rb") as f:
                encrypted_data = f.read()
            
            # If the file is not encrypted (plain JSON), handle gracefully
            stripped = encrypted_data.strip()
            if stripped.startswith(b"{") or stripped.startswith(b"["):
                 try:
                     return json.loads(encrypted_data.decode())
                 except Exception:
                     # If it's pure JSON-lines, convert to list
                     if b"\n" in stripped:
                         return [json.loads(line) for line in encrypted_data.decode().split("\n") if line.strip()]

            decrypted_data = self._fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            print(f"SecureStorage Error (Load): {e}")
            return None

    def save_text(self, file_path: str, text: str) -> bool:
        """Encrypt and save raw text to a file."""
        try:
            encrypted_data = self._fernet.encrypt(text.encode())
            with open(file_path, "wb") as f:
                f.write(encrypted_data)
            return True
        except Exception as e:
            print(f"SecureStorage Error (SaveText): {e}")
            return False

    def load_text(self, file_path: str) -> Optional[str]:
        """Decrypt and load text from a file."""
        if not os.path.exists(file_path):
            return None
            
        try:
            with open(file_path, "rb") as f:
                encrypted_data = f.read()
            
            decrypted_data = self._fernet.decrypt(encrypted_data)
            return decrypted_data.decode()
        except Exception as e:
            print(f"SecureStorage Error (LoadText): {e}")
            return None

    def append_json(self, file_path: str, item: Any) -> bool:
        """Append an item to a list in an encrypted JSON file."""
        data = self.load_json(file_path) or []
        if not isinstance(data, list):
            data = [data]
        if isinstance(data, list):
            data.append(item)
        return self.save_json(file_path, data)
