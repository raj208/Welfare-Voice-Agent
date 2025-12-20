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

import re

def _to_number(x):
    """Best-effort numeric coercion for int/float-like inputs."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)

    s = str(x).strip()
    # remove currency symbols, commas, punctuation commonly coming from STT/text
    s = s.replace(",", "").replace("₹", "").replace("।", "").strip()
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None

def _to_bool(x):
    if isinstance(x, bool):
        return x
    if x is None:
        return None
    s = str(x).strip().lower()
    if s in ["true", "yes", "y", "1", "हाँ", "हां", "जी"]:
        return True
    if s in ["false", "no", "n", "0", "नहीं", "नही", "ना"]:
        return False
    return None

def _norm_text(x):
    if x is None:
        return None
    return str(x).strip().lower()

def _compare(op, left, right):
    """
    Supports numeric + text comparisons.
    op: ==, !=, >, >=, <, <=, in, not_in, contains
    """
    # booleans
    lb = _to_bool(left)
    rb = _to_bool(right) if not isinstance(right, (list, tuple, set)) else None
    if lb is not None and (rb is not None or isinstance(right, bool)):
        rbool = right if isinstance(right, bool) else rb
        if op == "==": return lb == rbool
        if op == "!=": return lb != rbool

    # numbers
    ln = _to_number(left)
    rn = _to_number(right) if not isinstance(right, (list, tuple, set)) else None
    if ln is not None and (rn is not None) and op in [">", ">=", "<", "<=", "==", "!="]:
        if op == ">":  return ln > rn
        if op == ">=": return ln >= rn
        if op == "<":  return ln < rn
        if op == "<=": return ln <= rn
        if op == "==": return ln == rn
        if op == "!=": return ln != rn

    # text / categorical
    lt = _norm_text(left)
    if op in ["in", "not_in"]:
        if isinstance(right, (list, tuple, set)):
            opts = set(_norm_text(v) for v in right)
            ok = lt in opts
            return ok if op == "in" else (not ok)

    if op == "contains":
        rt = _norm_text(right)
        if lt is None or rt is None:
            return False
        return rt in lt

    # fallback equality (string)
    rt = _norm_text(right)
    if op == "==": return lt == rt
    if op == "!=": return lt != rt

    # unknown op
    return False


def _field_hi(field: str) -> str:
    return {
        "age": "उम्र",
        "state": "राज्य",
        "annual_income": "सालाना आय",
        "category": "श्रेणी",
        "gender": "लिंग",
        "is_student": "छात्र/छात्रा",
    }.get(field, field)




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

    # required fields
    for f in required_fields:
        if f not in profile or profile.get(f) in [None, ""]:
            missing.append(f)

    # rule checks
    for r in rules:
        field = r.get("field")
        op = r.get("op")
        val = r.get("value")

        # If field missing, mark unknown with a helpful message
        if field not in profile or profile.get(field) in [None, ""]:
            missing.append(field)
            checks.append({
                "ok": None,
                "explain_hi": f"⚠️ {_field_hi(field)} की जानकारी चाहिए।"
            })
            continue

        ok = _compare(op, profile.get(field), val)

        # Build dynamic explanation (PASS/FAIL)
        # If your rules JSON has custom strings, we use them:
        pass_msg = r.get("pass_hi")
        fail_msg = r.get("fail_hi")

        if ok is True:
            explain = pass_msg or f"✅ शर्त पूरी: {_field_hi(field)} ठीक है।"
        elif ok is False:
            failed = True
            # show requirement + user's value
            explain = fail_msg or (
                f"❌ शर्त पूरी नहीं: {_field_hi(field)} ({profile.get(field)}) "
                f"{op} {val} होना चाहिए।"
            )
        else:
            explain = f"⚠️ {_field_hi(field)} की जानकारी/फॉर्मेट स्पष्ट नहीं है।"

        checks.append({"ok": ok, "explain_hi": explain})

    # unique missing
    missing = sorted(set(missing))

    if missing:
        status = "unknown"
    elif failed:
        status = "not_eligible"
    else:
        status = "eligible"

    return {"status": status, "missing_fields": missing, "checks": checks}





