import json
import re
from llm_backends import ollama_chat

# Step-3: tool call after profile is ready
try:
    from tools.retriever import search_schemes
except Exception:
    search_schemes = None  # you will add tools/retriever.py in Step-3

REQUIRED_FIELDS = ["state", "age", "annual_income", "category"]

ALLOWED_CATEGORIES = {"sc", "st", "obc", "general", "ews"}

# Common STT mistakes → normalize
def normalize_hi(t: str) -> str:
    t = (t or "").strip()
    # common miss-hearings for lakh
    t = t.replace("लग", "लाख").replace("लाग", "लाख")
    # common miss-hearings for states in your test
    t = t.replace("जारकण", "झारखंड").replace("झारखण्ड", "झारखंड")
    t = t.replace("बिहाड", "बिहार")
    return t

HINDI_NUM_WORDS = {
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
    "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14,
    "पंद्रह": 15, "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19,
    "बीस": 20, "इक्कीस": 21, "बाईस": 22, "बाई": 22,  # ✅ "बाई साल"
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
    # add more later (not required for demo)
}

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
    """
    Only for optional extraction. We'll validate hard.
    """
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
    """
    Supports:
    - "1 लाख", "एक लाख", "2 लाख"
    - digits only: "200000"
    - common STT: "एक लग" -> normalized to "एक लाख"
    """
    text = normalize_hi(text)

    # digits only
    m = re.search(r"(\d{4,9})", text)
    if m:
        v = int(m.group(1))
        return v if 1000 <= v <= 10**9 else None

    # "x लाख"
    if "लाख" in text:
        # digits + लाख
        m2 = re.search(r"(\d+(\.\d+)?)\s*लाख", text)
        if m2:
            return int(float(m2.group(1)) * 100000)

        # word + लाख
        for w, v in HINDI_NUM_WORDS.items():
            if w in text:
                return int(v * 100000)

    return None

def parse_category(text: str):
    t = normalize_hi(text).lower()
    # accept only clear categories
    if "sc" in t or "एससी" in t:
        return "SC"
    if "st" in t or "एसटी" in t:
        return "ST"
    if "obc" in t or "ओबीसी" in t:
        return "OBC"
    if "ews" in t or "ईडब्ल्यूएस" in t:
        return "EWS"
    if "general" in t or "जनरल" in t or "सामान्य" in t:
        return "General"
    return None

def parse_state(text: str):
    t = normalize_hi(text)
    # direct match on Hindi state names
    for hi, en in STATE_HI_TO_EN.items():
        if hi in t:
            return en
    # if user says just one word, try exact mapping
    if t in STATE_HI_TO_EN:
        return STATE_HI_TO_EN[t]
    return None

def ask_for_field(field: str) -> str:
    qmap = {
        "state": "आप किस राज्य में रहते हैं?",
        "age": "आपकी उम्र कितनी है? (उदाहरण: 20)",
        "annual_income": "आपकी सालाना आय लगभग कितनी है? (₹ में, उदाहरण: 200000 या 1 लाख)",
        "category": "आपकी श्रेणी क्या है? (SC/ST/OBC/General/EWS)",
    }
    return qmap.get(field, "कृपया यह जानकारी बताइए।")

def field_label(field: str) -> str:
    return {
        "state": "राज्य",
        "age": "उम्र",
        "annual_income": "सालाना आय",
        "category": "श्रेणी",
    }.get(field, field)

def process_turn(user_text: str, lang_name: str, memory: dict):
    """
    Memory:
      stage: INTAKE / PROFILE_COLLECTION / READY / RECOMMEND
      profile: {}
      pending_confirm: {field, old, new} or None
      expected_field: which field we asked last
      goal: original user goal (e.g., scholarship)
    """
    memory = memory or {}
    memory.setdefault("stage", "INTAKE")
    memory.setdefault("profile", {})
    memory.setdefault("pending_confirm", None)
    memory.setdefault("expected_field", None)
    memory.setdefault("goal", None)

    profile = memory["profile"]
    user_text = normalize_hi(user_text)

    # store goal early (for retrieval later)
    if memory["goal"] is None and memory["stage"] in ["INTAKE", "PROFILE_COLLECTION"]:
        memory["goal"] = user_text

    # 1) If waiting for confirmation (only yes/no)
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

    # 2) Deterministic parse for the field we asked last
    extracted = {}
    ef = memory.get("expected_field")

    if ef == "state":
        v = parse_state(user_text)
        if v:
            extracted["state"] = v
    elif ef == "age":
        v = parse_age(user_text)
        if v is not None:
            extracted["age"] = v
    elif ef == "annual_income":
        v = parse_income(user_text)
        if v is not None:
            extracted["annual_income"] = v
    elif ef == "category":
        v = parse_category(user_text)
        if v:
            extracted["category"] = v

    # 3) If expected field parsing didn't work, do a safe LLM extraction + validation
    if not extracted:
        llm_data = llm_extract_profile(user_text, lang_name) or {}

        # validate category strictly
        if "category" in llm_data:
            c = str(llm_data["category"]).strip().lower()
            if c not in ALLOWED_CATEGORIES:
                llm_data.pop("category", None)

        # validate state: accept only if matches our list (via parse_state)
        if "state" in llm_data:
            st = parse_state(str(llm_data["state"]))
            if st:
                llm_data["state"] = st
            else:
                llm_data.pop("state", None)

        # validate ints
        if "age" in llm_data:
            try:
                a = int(llm_data["age"])
                if 1 <= a <= 120:
                    llm_data["age"] = a
                else:
                    llm_data.pop("age", None)
            except Exception:
                llm_data.pop("age", None)

        if "annual_income" in llm_data:
            try:
                inc = int(llm_data["annual_income"])
                if 1000 <= inc <= 10**9:
                    llm_data["annual_income"] = inc
                else:
                    llm_data.pop("annual_income", None)
            except Exception:
                llm_data.pop("annual_income", None)

        extracted.update(llm_data)

    # 4) Contradiction check
    for k, v in extracted.items():
        if k in profile and profile[k] != v:
            memory["pending_confirm"] = {"field": k, "old": profile[k], "new": v}
            return (f"आपने पहले {field_label(k)} {profile[k]} बताया था, अभी {v} कहा। क्या मैं {v} अपडेट कर दूँ? (हाँ/नहीं)", memory)

    # 5) Apply updates
    profile.update(extracted)

    # 6) Stage transition
    if memory["stage"] == "INTAKE":
        memory["stage"] = "PROFILE_COLLECTION"

    # 7) Ask missing fields
    missing = [f for f in REQUIRED_FIELDS if f not in profile]
    if missing:
        memory["expected_field"] = missing[0]
        return (ask_for_field(missing[0]), memory)

    # 8) READY -> Recommend using retriever tool (Step-3)
    memory["stage"] = "READY"
    memory["expected_field"] = None

    if search_schemes is None:
        # Tool not wired yet
        return ("आपकी जानकारी मिल गई। अब Step-3 में मैं योजना खोजने वाला टूल जोड़ूँगा, फिर सुझाव दूँगा।", memory)

    query = memory.get("goal") or user_text
    results = search_schemes(query, top_k=3)

    if not results:
        return ("मुझे अभी कोई उपयुक्त योजना नहीं मिली। आप किस तरह की मदद चाहते हैं (शिक्षा/स्वास्थ्य/घर/नौकरी)?", memory)

    msg = "आपके लिए ये योजनाएँ उपयोगी हो सकती हैं:\n"
    for i, r in enumerate(results, 1):
        msg += f"{i}) {r['name_hi']}: {r['summary_hi']}\n"
    msg += "आप किस योजना की आवेदन प्रक्रिया जानना चाहते हैं? (1/2/3)"
    memory["stage"] = "RECOMMEND"
    memory["last_results"] = results
    return (msg, memory)
