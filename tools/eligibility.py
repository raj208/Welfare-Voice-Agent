import json
import re
from pathlib import Path

RULES_PATH = Path("data/rules.json")


def load_rules():
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _to_number(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)

    s = str(x).strip().replace(",", "").replace("₹", "").replace("।", "")
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
    lb = _to_bool(left)
    rb = _to_bool(right) if not isinstance(right, (list, tuple, set)) else None
    if lb is not None and (rb is not None or isinstance(right, bool)):
        rbool = right if isinstance(right, bool) else rb
        if op == "==":
            return lb == rbool
        if op == "!=":
            return lb != rbool

    ln = _to_number(left)
    rn = _to_number(right) if not isinstance(right, (list, tuple, set)) else None
    if ln is not None and rn is not None and op in [">", ">=", "<", "<=", "==", "!="]:
        if op == ">":
            return ln > rn
        if op == ">=":
            return ln >= rn
        if op == "<":
            return ln < rn
        if op == "<=":
            return ln <= rn
        if op == "==":
            return ln == rn
        if op == "!=":
            return ln != rn

    lt = _norm_text(left)
    if op in ["in", "not_in"] and isinstance(right, (list, tuple, set)):
        opts = set(_norm_text(v) for v in right)
        ok = lt in opts
        return ok if op == "in" else (not ok)

    if op == "contains":
        rt = _norm_text(right)
        if lt is None or rt is None:
            return False
        return rt in lt

    rt = _norm_text(right)
    if op == "==":
        return lt == rt
    if op == "!=":
        return lt != rt
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


def check_eligibility(scheme_id: str, profile: dict, scheme_data: dict | None = None):
    """
    Returns:
      {
        "status": "eligible"|"not_eligible"|"unknown",
        "missing_fields": [...],
        "checks": [{"ok": true/false/None, "explain_hi": "..."}],
        "reason_blocks": [
          {
            "field": "age",
            "status": "matched|failed|missing|info",
            "reason_hi": "...",
            "evidence_source": "..."
          }
        ]
      }
    """
    rules_db = load_rules()
    scheme_rules = rules_db.get(scheme_id)

    if not scheme_rules:
        return {
            "status": "unknown",
            "missing_fields": [],
            "checks": [],
            "reason_blocks": [
                {
                    "field": "rule_set",
                    "status": "missing",
                    "reason_hi": "इस योजना के लोकल नियम उपलब्ध नहीं हैं।",
                    "evidence_source": (scheme_data or {}).get("source_url", "local_rules"),
                }
            ],
            "external_eligibility_points": (scheme_data or {}).get("eligibility_points_hi", []),
        }

    required_fields = scheme_rules.get("required_fields", [])
    rules = scheme_rules.get("rules", [])

    missing = []
    checks = []
    reason_blocks = []
    failed = False
    source = (scheme_data or {}).get("source_url", "local_rules")

    for f in required_fields:
        if f not in profile or profile.get(f) in [None, ""]:
            missing.append(f)
            reason_blocks.append(
                {
                    "field": f,
                    "status": "missing",
                    "reason_hi": f"⚠️ {_field_hi(f)} की जानकारी चाहिए।",
                    "evidence_source": source,
                }
            )

    for r in rules:
        field = r.get("field")
        op = r.get("op")
        val = r.get("value")

        if field not in profile or profile.get(field) in [None, ""]:
            missing.append(field)
            msg = f"⚠️ {_field_hi(field)} की जानकारी चाहिए।"
            checks.append({"ok": None, "explain_hi": msg})
            reason_blocks.append(
                {
                    "field": field,
                    "status": "missing",
                    "reason_hi": msg,
                    "evidence_source": source,
                }
            )
            continue

        ok = _compare(op, profile.get(field), val)
        pass_msg = r.get("pass_hi") or f"✅ शर्त पूरी: {_field_hi(field)} ठीक है।"
        fail_msg = r.get("fail_hi") or (
            f"❌ शर्त पूरी नहीं: {_field_hi(field)} ({profile.get(field)}) {op} {val} होना चाहिए।"
        )

        if ok is True:
            checks.append({"ok": True, "explain_hi": pass_msg})
            reason_blocks.append(
                {
                    "field": field,
                    "status": "matched",
                    "reason_hi": pass_msg,
                    "evidence_source": source,
                }
            )
        elif ok is False:
            failed = True
            checks.append({"ok": False, "explain_hi": fail_msg})
            reason_blocks.append(
                {
                    "field": field,
                    "status": "failed",
                    "reason_hi": fail_msg,
                    "evidence_source": source,
                }
            )
        else:
            unclear = f"⚠️ {_field_hi(field)} की जानकारी/फॉर्मेट स्पष्ट नहीं है।"
            checks.append({"ok": None, "explain_hi": unclear})
            reason_blocks.append(
                {
                    "field": field,
                    "status": "missing",
                    "reason_hi": unclear,
                    "evidence_source": source,
                }
            )

    external_points = (scheme_data or {}).get("eligibility_points_hi", [])
    for p in external_points[:3]:
        reason_blocks.append(
            {
                "field": "internet_eligibility",
                "status": "info",
                "reason_hi": f"ℹ️ आधिकारिक स्रोत संकेत: {p}",
                "evidence_source": source,
            }
        )

    missing = sorted(set(missing))
    if missing:
        status = "unknown"
    elif failed:
        status = "not_eligible"
    else:
        status = "eligible"

    return {
        "status": status,
        "missing_fields": missing,
        "checks": checks,
        "reason_blocks": reason_blocks,
        "external_eligibility_points": external_points,
    }
