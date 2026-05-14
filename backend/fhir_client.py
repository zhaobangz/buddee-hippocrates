from typing import Dict, Any
import base64

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB per attachment

class FHIRAdapter:
    @staticmethod
    def _decode_attachment(resource: dict) -> str:
        """Decodes base64 attachment data from DocumentReference."""
        text = ""
        content = resource.get("content", [])
        for item in content:
            attachment = item.get("attachment", {})
            # Simplified attachment decoding
            data = attachment.get("data", "")
            if data:
                try:
                    raw = base64.b64decode(data)
                except Exception:
                    pass
                else:
                    # Security: reject oversized embedded documents before appending to the agent prompt.
                    if len(raw) > MAX_ATTACHMENT_BYTES:
                        raise ValueError(f"Attachment exceeds {MAX_ATTACHMENT_BYTES} bytes limit")
                    text += raw.decode("utf-8") + "\n"
            # Also handle plain text string if not base64 encoded
            elif attachment.get("title"):
                text += attachment.get("title", "") + "\n"
        return text

    @staticmethod
    def extract_from_bundle(bundle: Dict[str, Any]) -> dict:
        """Parses a FHIR DocumentReference and Condition bundle into agent format."""
        note_text = ""
        billed_codes = []
        
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            rtype = resource.get("resourceType")
            
            if rtype == "DocumentReference":
                # Extract base64 clinical note data
                note_text += FHIRAdapter._decode_attachment(resource)
            elif rtype == "Condition":
                # Extract previously billed ICD-10s
                for coding in resource.get("code", {}).get("coding", []):
                    if coding.get("system", "").endswith("icd-10-cm"):
                        billed_codes.append(coding.get("code"))
                        
        return {"note": note_text.strip(), "billed_codes": billed_codes}
