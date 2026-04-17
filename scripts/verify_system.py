import requests
import json
import time

BASE_URL = "http://localhost:8001/api"

def test_shadow_mode_rcm():
    print("\n--- Testing Shadow Mode RCM ---")
    payload = {
        "payload": json.dumps({
            "note": "Patient presents with persistent cough and fatigue. History of Type 2 Diabetes with known diabetic neuropathy in lower extremities.",
            "billed_codes": ["E11.9"] # Type 2 DM without complications
        }),
        "task_type": "shadow_mode_rcm"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/process", json=payload)
        data = response.json()
        print("Response received:")
        print(data.get("response"))
    except Exception as e:
        print(f"Error connecting to API: {e}. Is server running?")

def test_audit_integrity():
    print("\n--- Testing Audit Integrity Verification ---")
    try:
        response = requests.get(f"{BASE_URL}/audit/verify")
        print("Audit Integrity Status:", response.json())
    except Exception as e:
        print(f"Error connecting to API: {e}")

if __name__ == "__main__":
    test_shadow_mode_rcm()
    test_audit_integrity()
