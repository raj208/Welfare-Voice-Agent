import json
import re
from llm_backends import ollama_chat
from tools.eligibility import check_eligibility

# Step-3 Retriever (safe import)
try:
    from tools.retriever import search_schemes
except Exception:
    search_schemes = None

REQUIRED_FIELDS = ["state", "age", "annual_income", "category"]
ALLOWED_CATEGORIES = {"sc", "st", "obc", "general", "ews"}

# ----------------------------
# Normalization (STT fixes)
# ----------------------------
def normalize_hi(t: str) -> str:
    t = (t or "").strip()

    # lakh STT variants
    t = t.replace("लग", "लाख").replace("लाग", "लाख").replace("लाक", "लाख")

    # scholarship STT variants
    t = t.replace("चात्र", "छात्र").replace("विती", "वृत्ति").replace("वित", "वृ")

    # common OBC STT variants
    t = t.replace("अबिसी", "ओबीसी").replace("उबिसी", "ओबीसी").replace("ओ बि सी", "ओबीसी")

    # state STT variants
    t = t.replace("जारकण", "झारखंड").replace("झारखण्ड", "झारखंड")
    t = t.replace("बिहाड", "बिहार")

    return t


HINDI_NUM_WORDS = {
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
    "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14,
    "पंद्रह": 15, "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19,
    "बीस": 20, "इक्कीस": 21, "बाईस": 22, "बाई": 22,
    "तेईस": 23, "चौबीस": 24, "पच्चीस": 25,
    "छब्बीस": 26, "सत्ताईस": 27, "अट्ठाईस": 28, "उनतीस": 29,
    "तीस": 30, "चालीस": 40, "पचास": 50, "साठ": 60, "सत्तर": 70, "अस्सी": 80, "नब्बे": 90,
}

STATE_HI_TO_EN = {
    "झारखंड": "Jharkhand",
    "बिहार": "Bihar",
    "उत्तर प्रदेश": "Uttar Pradesh",
    "मध्य प्रदेश": "Madhya Pradesh",
    "राजस्थान": "Rajasthan",
    "पश्चिम बंगाल": "West Bengal",
    "ओडिशा": "Odisha",
    "छत्तीसगढ़": "Chhattisgarh",
    "महाराष्ट्र": "Maharashtra",
    "दिल्ली": "Delhi",
    "कर्नाटक": "Karnataka",
    "तमिलनाडु": "Tamil Nadu",
    "तेलंगाना": "Telangana",
    "आंध्र प्रदेश": "Andhra Pradesh",
    "गुजरात": "Gujarat",
    "पंजाब": "Punjab",
    "हरियाणा": "Haryana",
    "केरल": "Kerala",
    "असम": "Assam",
}

# ----------------------------
# Optional LLM extraction (only when ef is None)
# ----------------------------
def _safe_json_loads(s: str):
    try:
        return json.loads(s)
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(s[start:end + 1])
            except Exception:
                return None
        return None

def llm_extract_profile(user_text: str, lang_name: str):
    sys = (
        "Return ONLY valid JSON. No markdown. No extra words.\n"
        "Allowed keys: state, age, annual_income, category.\n"
        "category must be one of: SC, ST, OBC, General, EWS.\n"
        "If unsure, omit the field."
    )
    prompt = f"User text: {user_text}\nReturn JSON:"
    out = ollama_chat([{"role": "system", "content": sys}, {"role": "user", "content": prompt}])
    data = _safe_json_loads(out)
    return data if isinstance(data, dict) else {}

# ----------------------------
# Parsers
# ----------------------------
def parse_age(text: str):
    text = normalize_hi(text)
    m = re.search(r"(\d{1,3})", text)
    if m:
        v = int(m.group(1))
        return v if 1 <= v <= 120 else None
    for w, v in HINDI_NUM_WORDS.items():
        if w in text:
            return v if 1 <= v <= 120 else None
    return None

def parse_income(text: str):
    text = normalize_hi(text)

    m = re.search(r"(\d{4,9})", text)
    if m:
        v = int(m.group(1))
        return v if 1000 <= v <= 10**9 else None

    if "लाख" in text:
        m2 = re.search(r"(\d+(\.\d+)?)\s*लाख", text)
        if m2:
            return int(float(m2.group(1)) * 100000)

        for w, v in HINDI_NUM_WORDS.items():
            if w in text:
                return int(v * 100000)

    return None

def parse_yes_no(text: str):
    t = normalize_hi(text).lower()
    if "हाँ" in t or "हां" in t or "जी" in t or "yes" in t:
        return True
    if "नहीं" in t or "नही" in t or "no" in t:
        return False
    return None

def parse_gender(text: str):
    t = normalize_hi(text)
    if "महिला" in t or "औरत" in t:
        return "female"
    if "पुरुष" in t or "लड़का" in t:
        return "male"
    return None

def parse_category(text: str):
    t = normalize_hi(text).lower()
    if "ओबीसी" in t or "obc" in t:
        return "OBC"
    if "एससी" in t or "sc" in t:
        return "SC"
    if "एसटी" in t or "st" in t:
        return "ST"
    if "ईडब्ल्यूएस" in t or "ews" in t:
        return "EWS"
    if "सामान्य" in t or "जनरल" in t or "general" in t:
        return "General"
    return None

def parse_state(text: str):
    t = normalize_hi(text)
    for hi, en in STATE_HI_TO_EN.items():
        if hi in t:
            return en
    if t in STATE_HI_TO_EN:
        return STATE_HI_TO_EN[t]
    return None

# ----------------------------
# Prompts
# ----------------------------
def ask_for_field(field: str) -> str:
    qmap = {
        "state": "आप किस राज्य में रहते हैं?",
        "age": "आपकी उम्र कितनी है? (उदाहरण: 20)",
        "annual_income": "आपकी सालाना आय लगभग कितनी है? (₹ में, उदाहरण: 200000 या 1 लाख)",
        "category": "आपकी श्रेणी क्या है? (SC/ST/OBC/General/EWS)",
        "is_student": "क्या आप अभी छात्र/छात्रा हैं? (हाँ/नहीं)",
        "gender": "आपका लिंग क्या है? (पुरुष/महिला)",
    }
    return qmap.get(field, "कृपया यह जानकारी बताइए।")

def field_label(field: str) -> str:
    return {
        "state": "राज्य",
        "age": "उम्र",
        "annual_income": "सालाना आय",
        "category": "श्रेणी",
        "is_student": "छात्र स्थिति",
        "gender": "लिंग",
    }.get(field, field)

def rewrite_query(q: str) -> str:
    q = normalize_hi(q)
    if ("छात्र" in q) or ("छात्रवृत्ति" in q) or ("स्कॉलर" in q):
        return "छात्रवृत्ति NSP स्कॉलरशिप"
    return q

# ----------------------------
# MAIN
# ----------------------------
def process_turn(user_text: str, lang_name: str, memory: dict):
    memory = memory or {}
    memory.setdefault("stage", "INTAKE")
    memory.setdefault("profile", {})
    memory.setdefault("pending_confirm", None)
    memory.setdefault("expected_field", None)
    memory.setdefault("goal", None)
    memory.setdefault("last_results", None)

    profile = memory["profile"]
    user_text = normalize_hi(user_text)

    # store initial goal
    if memory["goal"] is None and memory["stage"] in ["INTAKE", "PROFILE_COLLECTION"]:
        memory["goal"] = user_text

    # 1) pending confirm
    if memory["pending_confirm"]:
        pc = memory["pending_confirm"]
        t = user_text.lower()
        if "हाँ" in t or "हा" in t or "जी" in t or "yes" in t:
            profile[pc["field"]] = pc["new"]
            memory["pending_confirm"] = None
            return ("ठीक है, मैंने अपडेट कर दिया।", memory)
        if "नहीं" in t or "मत" in t or "no" in t:
            memory["pending_confirm"] = None
            return ("ठीक है, मैं पहले वाला मान ही रखूँगा।", memory)
        return ("कृपया सिर्फ 'हाँ' या 'नहीं' में बताइए।", memory)

    extracted = {}
    ef = memory.get("expected_field")

    # 2) deterministic parse ONLY for expected field
    if ef == "state":
        v = parse_state(user_text)
        if v: extracted["state"] = v
    elif ef == "age":
        v = parse_age(user_text)
        if v is not None: extracted["age"] = v
    elif ef == "annual_income":
        v = parse_income(user_text)
        if v is not None: extracted["annual_income"] = v
    elif ef == "category":
        v = parse_category(user_text)
        if v: extracted["category"] = v
    elif ef == "is_student":
        v = parse_yes_no(user_text)
        if v is not None: extracted["is_student"] = v
    elif ef == "gender":
        v = parse_gender(user_text)
        if v: extracted["gender"] = v

    # ✅ If expected field still not parsed, ask again (NO LLM fallback)
    if not extracted and ef is not None:
        return (ask_for_field(ef), memory)

    # 3) Only if ef is None, allow LLM extraction (validated hard)
    if not extracted and ef is None:
        llm_data = llm_extract_profile(user_text, lang_name) or {}

        # validate & normalize
        if "state" in llm_data:
            st = parse_state(str(llm_data["state"]))
            if st: extracted["state"] = st

        if "age" in llm_data:
            try:
                a = int(llm_data["age"])
                if 1 <= a <= 120:
                    extracted["age"] = a
            except Exception:
                pass

        if "annual_income" in llm_data:
            try:
                inc = int(llm_data["annual_income"])
                if 1000 <= inc <= 10**9:
                    extracted["annual_income"] = inc
            except Exception:
                pass

        if "category" in llm_data:
            c = parse_category(str(llm_data["category"]))
            if c:
                extracted["category"] = c

    # 4) contradiction check
    for k, v in extracted.items():
        if k in profile and profile[k] != v:
            memory["pending_confirm"] = {"field": k, "old": profile[k], "new": v}
            return (f"आपने पहले {field_label(k)} {profile[k]} बताया था, अभी {v} कहा। क्या मैं {v} अपडेट कर दूँ? (हाँ/नहीं)", memory)

    # 5) apply updates
    profile.update(extracted)

    # 6) stage transition
    if memory["stage"] == "INTAKE":
        memory["stage"] = "PROFILE_COLLECTION"

    # 7) ask required fields
    missing = [f for f in REQUIRED_FIELDS if f not in profile]
    if missing:
        memory["expected_field"] = missing[0]
        return (ask_for_field(missing[0]), memory)

    # 8) recommend
    memory["stage"] = "READY"
    memory["expected_field"] = None

    if search_schemes is None:
        return ("आपकी जानकारी मिल गई। अभी retriever tool सेट नहीं है।", memory)

    query = rewrite_query(memory.get("goal") or user_text)
    results = search_schemes(query, top_k=3)

    if not results:
        return ("मुझे अभी कोई उपयुक्त योजना नहीं मिली। आप किस तरह की मदद चाहते हैं (शिक्षा/स्वास्थ्य/घर/नौकरी)?", memory)

    msg = "आपके लिए ये योजनाएँ उपयोगी हो सकती हैं:\n"
    ranked = []

    for r in results:
        e = check_eligibility(r["scheme_id"], profile)
        if e["status"] == "eligible":
            tag = "✅ पात्र"
        elif e["status"] == "not_eligible":
            tag = "❌ पात्र नहीं"
        else:
            tag = "⚠️ जानकारी चाहिए"
        ranked.append((r, e, tag))

    for i, (r, e, tag) in enumerate(ranked, 1):
        msg += f"\n{i}) {r['name_hi']} {tag}\n"
        msg += f"   - {r['summary_hi']}\n"
        if e.get("checks"):
            first = e["checks"][0]
            if first.get("explain_hi"):
                msg += f"   - कारण: {first['explain_hi']}\n"

    top_missing = ranked[0][1].get("missing_fields", []) if ranked else []
    if top_missing:
        mfield = top_missing[0]
        memory["expected_field"] = mfield
        memory["stage"] = "PROFILE_COLLECTION"
        memory["last_results"] = ranked
        return (f"इस योजना की पात्रता जांचने के लिए एक सवाल: {ask_for_field(mfield)}", memory)

    msg += "\nआप किस योजना की आवेदन प्रक्रिया जानना चाहते हैं? (1/2/3)"
    memory["stage"] = "RECOMMEND"
    memory["last_results"] = ranked
    return (msg, memory)
