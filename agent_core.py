import json
import re
from llm_backends import ollama_chat
from tools.eligibility import check_eligibility
from tools.application_store import save_application




def _trace_reset(memory: dict):
    memory["turn_trace"] = []  # per-turn
    return memory["turn_trace"]

def _trace_finalize(memory: dict):
    memory["last_trace"] = " → ".join(memory.get("turn_trace", []))


# Step-3 Retriever (safe import)
try:
    from tools.retriever import search_schemes
except Exception:
    search_schemes = None



# REQUIRED_FIELDS = ["state", "age", "annual_income", "category"]
REQUIRED_FIELDS = ["state", "age", "annual_income", "category", "is_student", "gender"]
ALLOWED_CATEGORIES = {"sc", "st", "obc", "general", "ews"}

# ----------------------------
# Normalization (STT fixes)
# ----------------------------
def normalize_hi(t: str) -> str:
    t = t.replace(",", "").replace("₹", "")

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

def parse_choice(text: str, max_n: int):
    t = normalize_hi(text).strip()

    # digits: "1", "2", "3"
    m = re.search(r"\b([1-9])\b", t)
    if m:
        v = int(m.group(1))
        return v if 1 <= v <= max_n else None

    # Hindi words
    if "पहला" in t or "एक" == t:
        return 1 if max_n >= 1 else None
    if "दूसरा" in t or "दो" == t:
        return 2 if max_n >= 2 else None
    if "तीसरा" in t or "तीन" == t:
        return 3 if max_n >= 3 else None

    return None



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
        # "age": "आपकी उम्र कितनी है? (उदाहरण: 20)",
        "age": "आपकी उम्र कितनी है?",
        # "annual_income": "आपकी सालाना आय लगभग कितनी है? (₹ में, उदाहरण: 200000 या 1 लाख)",
        "annual_income": "आपकी सालाना आय लगभग कितनी है?",
        "category": "आपकी श्रेणी क्या है? (SC/ST/OBC/General/EWS)",
        # "is_student": "क्या आप अभी छात्र/छात्रा हैं? (हाँ/नहीं)",
        "is_student": "क्या आप अभी छात्र/छात्रा हैं?",
        "gender": "आपका लिंग क्या है?",
        # "gender": "आपका लिंग क्या है? (पुरुष/महिला)",
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


def canonical_fallback_for_expected_field(user_text: str, ef: str, lang_name: str):
    """
    If deterministic parse failed, try LLM forced-choice mapping.
    Returns a dict like {"gender": "female"} or {} if unsure.
    """
    if ef == "gender":
        res = llm_classify_enum(user_text, "gender", ["male", "female"], lang_name)
        if res["confidence"] >= 0.5 and res["value"]:
            return {"gender": res["value"]}

    if ef == "category":
        res = llm_classify_enum(user_text, "category", ["SC", "ST", "OBC", "General", "EWS"], lang_name)
        if res["confidence"] >= 0.6 and res["value"]:
            return {"category": res["value"]}

    if ef == "is_student":
        res = llm_classify_enum(user_text, "is_student", [True, False], lang_name)
        if res["confidence"] >= 0.6 and (res["value"] is True or res["value"] is False):
            return {"is_student": res["value"]}

    # For choice(1/2/3) we handle in RECOMMEND stage (below), not here.
    return {}



def llm_classify_enum(text: str, field: str, options, lang_name: str):
    """
    Forced-choice classification to canonical values.
    Returns: {"value": <one of options> or None, "confidence": float 0..1}
    """
    sys = (
        "You are a strict classifier.\n"
        "Return ONLY valid JSON, no extra text.\n"
        'Schema: {"value": <one of OPTIONS or null>, "confidence": <number between 0 and 1>}\n'
        "If unsure, set value=null and confidence<0.6.\n"
    )

    # Add field-specific hints (helps a LOT for noisy Hindi STT)
    hint = ""
    if field == "gender":
        hint = 'Hints: male synonyms: "पुरुष","लड़का","आदमी". female synonyms: "महिला","लड़की","औरत".\n'
    elif field == "category":
        hint = (
            'Hints: SC synonyms: "एससी","दलित". ST synonyms: "एसटी","जनजाति". '
            'OBC synonyms: "ओबीसी","पिछड़ा". General synonyms: "जनरल","सामान्य". '
            'EWS synonyms: "ईडब्ल्यूएस".\n'
        )
    elif field == "is_student":
        hint = 'Hints: yes: "हाँ","हां","जी","हाँ जी". no: "नहीं","नही","ना".\n'
    elif field == "choice":
        hint = 'Hints: 1 synonyms: "एक","पहला". 2 synonyms: "दो","दू","दूसरा". 3 synonyms: "तीन","तीसरा".\n'

    prompt = (
        f"Field: {field}\n"
        f"OPTIONS: {options}\n"
        f"Language: {lang_name}\n"
        f"{hint}"
        f"Text: {text}\n"
        "Return JSON now."
    )

    out = ollama_chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": prompt}]
    )
    data = _safe_json_loads(out) or {}

    val = data.get("value", None)
    conf = data.get("confidence", 0.0)
    try:
        conf = float(conf)
    except Exception:
        conf = 0.0

    if val not in options:
        val = None

    return {"value": val, "confidence": conf}




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
    memory.setdefault("last_results", None)       # ranked = [(r,e,tag), ...]
    memory.setdefault("selected_scheme", None)

    # --- trace setup (per turn) ---
    trace = _trace_reset(memory)
    trace.append(f"stage={memory.get('stage')}")

    def set_stage(s: str):
        memory["stage"] = s
        trace.append(f"stage={s}")

    def ret(text: str):
        _trace_finalize(memory)
        return (text, memory)

    profile = memory["profile"]
    user_text = normalize_hi(user_text)
    def detect_inline_profile_update(text: str):
        upd = {}

        # age update
        if ("उम्र" in text) or ("साल" in text):
            a = parse_age(text)
            if a is not None:
                upd["age"] = a

        # income update
        if ("आय" in text) or ("कमाई" in text) or ("लाख" in text) or ("₹" in text) or ("रुप" in text):
            inc = parse_income(text)
            if inc is not None:
                upd["annual_income"] = inc

        # category update
        if ("श्रेणी" in text) or ("कैटेगरी" in text) or ("ओबीसी" in text) or ("एससी" in text) or ("एसटी" in text) or ("ईडब्ल्यूएस" in text) or ("जनरल" in text) or ("सामान्य" in text):
            c = parse_category(text)
            if c:
                upd["category"] = c

        # gender update
        if ("लिंग" in text) or ("महिला" in text) or ("पुरुष" in text):
            g = parse_gender(text)
            if g:
                upd["gender"] = g

        # student update
        if ("छात्र" in text) or ("स्टूडेंट" in text):
            yn = parse_yes_no(text)
            if yn is not None:
                upd["is_student"] = yn

        # state update (only if strong hint words exist)
        if ("राज्य" in text) or ("में रहता" in text) or ("से हूँ" in text) or ("से हूं" in text):
            st = parse_state(text)
            if st:
                upd["state"] = st

        return upd


    # store initial goal early (only during intake/collection)
    if memory["goal"] is None and memory["stage"] in ["INTAKE", "PROFILE_COLLECTION"]:
        memory["goal"] = user_text
        trace.append("goal=set")

    # 1) pending confirm has highest priority
    if memory["pending_confirm"]:
        pc = memory["pending_confirm"]
        t = user_text.lower()

        if "हाँ" in t or "हा" in t or "जी" in t or "yes" in t:
            profile[pc["field"]] = pc["new"]
            memory["pending_confirm"] = None
            trace.append(f"pending_confirm=yes field={pc['field']}")
            return ret("ठीक है, मैंने अपडेट कर दिया।")

        if "नहीं" in t or "मत" in t or "no" in t:
            memory["pending_confirm"] = None
            trace.append(f"pending_confirm=no field={pc['field']}")
            return ret("ठीक है, मैं पहले वाला मान ही रखूँगा।")

        trace.append("pending_confirm=unclear")
        return ret("कृपया सिर्फ 'हाँ' या 'नहीं' में बताइए।")
    
# ✅ Interrupt: allow profile updates in ANY stage (RECOMMEND / CONFIRM_SUBMIT too)
    inline_updates = detect_inline_profile_update(user_text)

    if inline_updates:
        trace.append(f"inline_update_detected={','.join(inline_updates.keys())}")

        # contradiction check first
        for k, v in inline_updates.items():
            if k in profile and profile[k] != v:
                memory["pending_confirm"] = {"field": k, "old": profile[k], "new": v}
                trace.append(f"contradiction field={k} old={profile[k]} new={v}")
                return ret(
                    f"आपने पहले {field_label(k)} {profile[k]} बताया था, अभी {v} कहा। "
                    f"क्या मैं {v} अपडेट कर दूँ? (हाँ/नहीं)"
                )

        # no contradiction → apply update
        profile.update(inline_updates)
        trace.append("inline_update_applied")

        # after update, recompute recommendations
        memory["expected_field"] = None
        set_stage("READY")

    # ------------------------------------------------------------------
    # STEP-5: selection + submit flow (stage handlers)
    # ------------------------------------------------------------------

    # If user already submitted, still allow picking another scheme
    if memory.get("stage") == "DONE":
        set_stage("RECOMMEND")

    # --- Handle submit confirmation stage ---
    if memory.get("stage") == "CONFIRM_SUBMIT":
        memory["expected_field"] = None  # prevent profile prompts here
        yn = parse_yes_no(user_text)
        trace.append("confirm_submit=seen")

        if yn is None:
            trace.append("confirm_submit=ask_yes_no")
            return ret("क्या आप आवेदन सबमिट करना चाहते हैं? (हाँ/नहीं)")

        if yn is False:
            set_stage("RECOMMEND")
            trace.append("confirm_submit=no")
            return ret("ठीक है। आप किस योजना की जानकारी चाहते हैं? (1/2/3)")

        # yn True -> submit
        selected = memory.get("selected_scheme")
        if not selected:
            set_stage("RECOMMEND")
            trace.append("confirm_submit=yes_but_no_selected_scheme")
            return ret("मुझे आपकी चुनी हुई योजना नहीं मिल रही। कृपया 1/2/3 चुनिए।")

        trace.append("tool=submit_application")
        tracking_id = save_application(profile, selected)
        trace.append(f"tracking_id={tracking_id}")
        set_stage("DONE")
        return ret(
            f"✅ आपका आवेदन सबमिट कर दिया गया है। ट्रैकिंग आईडी: {tracking_id}\n"
            "आप चाहें तो दूसरी योजना भी देख सकते हैं (1/2/3)।"
        )

    # --- Handle scheme selection stage ---
    if memory.get("stage") == "RECOMMEND":
        memory["expected_field"] = None  # prevent profile prompts here

        ranked = memory.get("last_results")  # [(r,e,tag), ...]
        if not ranked:
            # if nothing stored, fall back to recompute recommendations
            set_stage("READY")
            trace.append("recommend=no_cached_results_fallback_ready")
        else:
            choice = parse_choice(user_text, max_n=min(3, len(ranked)))

            # Canonical forced-choice fallback for selection
            if choice is None:
                res = llm_classify_enum(user_text, "choice", [1, 2, 3], lang_name)
                if res["confidence"] >= 0.6 and res["value"]:
                    choice = int(res["value"])

            if choice is None:
                trace.append("select=invalid")
                return ret("कृपया 1/2/3 में से चुनिए।")



            r, e, tag = ranked[choice - 1]
            memory["selected_scheme"] = r
            set_stage("CONFIRM_SUBMIT")
            trace.append(f"select={choice}")
            trace.append(f"selected_scheme={r.get('scheme_id')}")

            docs = r.get("documents_hi", [])
            docs_text = " , ".join(docs) if docs else "दस्तावेज़ जानकारी उपलब्ध नहीं"

            reply = (
                f"{r['name_hi']}\n"
                f"- कैसे आवेदन करें: {r.get('apply_hi','जानकारी उपलब्ध नहीं')}\n"
                f"- जरूरी दस्तावेज़: {docs_text}\n\n"
                "क्या आप इस योजना के लिए आवेदन सबमिट करना चाहते हैं? (हाँ/नहीं)"
            )
            return ret(reply)

    # ------------------------------------------------------------------
    # PROFILE COLLECTION (deterministic parsing)
    # ------------------------------------------------------------------

    extracted = {}
    ef = memory.get("expected_field")

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

    # If expected field not parsed, ask again (NO LLM fallback)
    # if not extracted and ef is not None:
    #     trace.append(f"parse_failed expected_field={ef}")
    #     trace.append(f"ask_field={ef}")
    #     return ret(ask_for_field(ef))
    
    # If expected field not parsed, try canonical forced-choice fallback
    if not extracted and ef is not None:
        # try LLM constrained classifier for only that field
        extra2 = canonical_fallback_for_expected_field(user_text, ef, lang_name)
        if extra2:
            extracted.update(extra2)
        else:
            trace.append(f"parse_failed expected_field={ef}")
            trace.append(f"ask_field={ef}")
            return ret(ask_for_field(ef))



    # If ef is None, allow optional LLM extraction (validated hard)
    if not extracted and ef is None:
        trace.append("tool=llm_extract_profile")
        llm_data = llm_extract_profile(user_text, lang_name) or {}

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

    # Contradiction check
    for k, v in extracted.items():
        if k in profile and profile[k] != v:
            memory["pending_confirm"] = {"field": k, "old": profile[k], "new": v}
            trace.append(f"contradiction field={k} old={profile[k]} new={v}")
            return ret(
                f"आपने पहले {field_label(k)} {profile[k]} बताया था, अभी {v} कहा। "
                f"क्या मैं {v} अपडेट कर दूँ? (हाँ/नहीं)"
            )

    if extracted:
        trace.append(f"profile_update={','.join(extracted.keys())}")
    profile.update(extracted)

    # stage transition
    if memory["stage"] == "INTAKE":
        set_stage("PROFILE_COLLECTION")

    # ask required fields
    missing = [f for f in REQUIRED_FIELDS if f not in profile]
    if missing:
        memory["expected_field"] = missing[0]
        trace.append(f"ask_field={missing[0]}")
        return ret(ask_for_field(missing[0]))

    # ------------------------------------------------------------------
    # RECOMMENDATION
    # ------------------------------------------------------------------
    set_stage("READY")
    memory["expected_field"] = None

    if search_schemes is None:
        trace.append("retriever=missing")
        return ret("आपकी जानकारी मिल गई। अभी retriever tool सेट नहीं है।")

    query = rewrite_query(memory.get("goal") or user_text)
    trace.append(f"tool=retriever(query={query}, top_k=3)")
    results = search_schemes(query, top_k=3)
    trace.append(f"retriever.results={len(results)}")

    if not results:
        return ret("मुझे अभी कोई उपयुक्त योजना नहीं मिली। आप किस तरह की मदद चाहते हैं (शिक्षा/स्वास्थ्य/घर/नौकरी)?")

    msg = "आपके लिए ये योजनाएँ उपयोगी हो सकती हैं:\n"
    ranked = []

    for r in results:
        trace.append(f"tool=eligibility({r['scheme_id']})")
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
        set_stage("PROFILE_COLLECTION")
        memory["last_results"] = ranked
        trace.append(f"eligibility.top_missing={mfield}")
        trace.append(f"ask_field={mfield}")
        return ret(f"इस योजना की पात्रता जांचने के लिए एक सवाल: {ask_for_field(mfield)}")

    msg += "\nआप किस योजना की आवेदन प्रक्रिया जानना चाहते हैं? (1/2/3)"
    set_stage("RECOMMEND")
    memory["last_results"] = ranked
    return ret(msg)
