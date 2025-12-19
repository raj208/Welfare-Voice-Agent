import json
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

STORE_PATH = Path("data/applications.jsonl")

def save_application(profile: dict, scheme: dict):
    """
    scheme must include: scheme_id, name_hi
    Returns: tracking_id
    """
    tracking_id = uuid4().hex[:10].upper()
    record = {
        "tracking_id": tracking_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scheme_id": scheme.get("scheme_id"),
        "scheme_name_hi": scheme.get("name_hi"),
        "profile": profile,
        "status": "submitted"
    }
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STORE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return tracking_id
