import json
from pathlib import Path

RULES_PATH = Path("data/rules.json")

def load_rules():
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _compare(op, a, b):
    if a is None:
        return None
    try:
        if op == "==": return a == b
        if op == "!=": return a != b
        if op == "<=": return float(a) <= float(b)
        if op == ">=": return float(a) >= float(b)
        if op == "<":  return float(a) < float(b)
        if op == ">":  return float(a) > float(b)
    except Exception:
        return None
    return None

def check_eligibility(scheme_id: str, profile: dict):
    """
    Returns:
      {
        "status": "eligible"|"not_eligible"|"unknown",
        "missing_fields": [...],
        "checks": [{"ok": true/false/None, "explain_hi": "..."}]
      }
    """
    rules_db = load_rules()
    scheme_rules = rules_db.get(scheme_id)

    if not scheme_rules:
        return {"status": "unknown", "missing_fields": [], "checks": []}

    required_fields = scheme_rules.get("required_fields", [])
    rules = scheme_rules.get("rules", [])

    missing = []
    checks = []
    failed = False

    # missing required fields
    for f in required_fields:
        if f not in profile:
            missing.append(f)

    # rule checks
    for r in rules:
        field = r["field"]
        op = r["op"]
        val = r["value"]
        explain = r.get("explain_hi", "")

        if field not in profile:
            missing.append(field)
            checks.append({"ok": None, "explain_hi": explain})
            continue

        ok = _compare(op, profile.get(field), val)
        checks.append({"ok": ok, "explain_hi": explain})
        if ok is False:
            failed = True

    missing = sorted(list(set(missing)))

    if missing:
        status = "unknown"
    elif failed:
        status = "not_eligible"
    else:
        status = "eligible"

    return {"status": status, "missing_fields": missing, "checks": checks}
