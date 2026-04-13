import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests

CACHE_PATH = Path("data/scheme_enrichment_cache.json")
CACHE_TTL_DAYS = 14
STALE_WARNING_DAYS = 45
HTTP_USER_AGENT = "WelfareVoiceAgent/1.0"
HIGH_CONFIDENCE_WITH_CONTENT = 0.85
LOW_CONFIDENCE_SPARSE_CONTENT = 0.55
HYBRID_CONFIDENCE_WEIGHT = 0.15
HYBRID_FRESHNESS_BONUS = 0.03

TRUSTED_DOMAINS = {
    "india.gov.in",
    "myscheme.gov.in",
    "nsp.gov.in",
    "scholarships.gov.in",
    "pmkisan.gov.in",
    "pmjay.gov.in",
    "pmuy.gov.in",
    "pmjdy.gov.in",
    "petroleum.nic.in",
    "jansuraksha.gov.in",
}

SCHEME_SOURCE_URLS = {
    "pmjay": "https://www.pmjay.gov.in/",
    "nsp": "https://scholarships.gov.in/",
    "pmuy": "https://www.pmuy.gov.in/",
    "pmsby": "https://jansuraksha.gov.in/",
    "pmkisan": "https://pmkisan.gov.in/",
    "jan_dhan": "https://www.pmjdy.gov.in/",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(dt: str):
    if not dt:
        return None
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except Exception:
        return None


def _is_stale(dt: str, max_days: int) -> bool:
    parsed = _parse_iso(dt)
    if not parsed:
        return True
    age_days = (datetime.now(timezone.utc) - parsed).days
    return age_days > max_days


def _get_domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().split(":")[0]
    except Exception:
        return ""


def is_trusted_source(url: str) -> bool:
    domain = _get_domain(url)
    return any(domain == d or domain.endswith(f".{d}") for d in TRUSTED_DOMAINS)


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(cache: dict):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


class _SafeHTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_stack = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style"}:
            self._skip_stack.append(tag.lower())

    def handle_endtag(self, tag):
        if self._skip_stack and self._skip_stack[-1] == tag.lower():
            self._skip_stack.pop()

    def handle_data(self, data):
        if not self._skip_stack and data:
            self.parts.append(data)


def _html_to_text(html: str) -> str:
    parser = _SafeHTMLTextExtractor()
    parser.feed(html or "")
    text = " ".join(parser.parts)
    return re.sub(r"\s+", " ", text).strip()


def _extract_points(text: str, keywords, max_points=4):
    chunks = re.split(r"(?<=[.!?।])\s+", text)
    out = []
    for c in chunks:
        low = c.lower()
        if any(k in low for k in keywords):
            c = c.strip()
            if 20 <= len(c) <= 220:
                out.append(c)
        if len(out) >= max_points:
            break
    return out


def _extract_last_updated(text: str) -> str:
    patterns = [
        r"(last\s+updated\s*[:\-]?\s*[0-9]{1,2}[\-/][0-9]{1,2}[\-/][0-9]{2,4})",
        r"(updated\s+on\s*[:\-]?\s*[0-9]{1,2}[\-/][0-9]{1,2}[\-/][0-9]{2,4})",
        r"(अद्यतन\s*[:\-]?\s*[0-9]{1,2}[\-/][0-9]{1,2}[\-/][0-9]{2,4})",
    ]
    low = text.lower()
    for p in patterns:
        m = re.search(p, low)
        if m:
            return m.group(1)
    return ""


def _default_payload(scheme_id: str, scheme_name_hi: str, source_url: str):
    return {
        "scheme_id": scheme_id,
        "name_hi": scheme_name_hi,
        "eligibility_points_hi": [],
        "benefits_points_hi": [],
        "documents_points_hi": [],
        "apply_guidance_hi": "",
        "apply_link": source_url,
        "source_url": source_url,
        "source_confidence": 0.0,
        "source_type": "official",
        "last_updated_date": "",
        "fetched_at": _now_iso(),
        "is_stale": True,
        "freshness_note_hi": "ऑनलाइन डेटा उपलब्ध नहीं है, कृपया आधिकारिक पोर्टल पर सत्यापित करें।",
        "fetch_status": "failed",
    }


def fetch_scheme_details_from_internet(
    scheme_id: str,
    scheme_name_hi: str = "",
    timeout: int = 6,
    retries: int = 1,
):
    source_url = SCHEME_SOURCE_URLS.get(scheme_id, "https://www.india.gov.in/")
    payload = _default_payload(scheme_id, scheme_name_hi, source_url)

    if not is_trusted_source(source_url):
        payload["freshness_note_hi"] = "स्रोत भरोसेमंद नहीं है, इसलिए इंटरनेट डेटा का उपयोग नहीं किया गया।"
        return payload

    headers = {"User-Agent": HTTP_USER_AGENT}
    last_err = None
    for _ in range(retries + 1):
        try:
            resp = requests.get(source_url, timeout=timeout, headers=headers)
            resp.raise_for_status()
            final_url = resp.url or source_url
            if not is_trusted_source(final_url):
                payload["freshness_note_hi"] = "रीडायरेक्ट के बाद स्रोत भरोसेमंद नहीं रहा, इसलिए डेटा छोड़ा गया।"
                return payload

            text = _html_to_text(resp.text)
            eligibility = _extract_points(text, ["eligibility", "पात्रता", "criteria", "eligible"])[:4]
            benefits = _extract_points(text, ["benefit", "लाभ", "coverage", "assistance"])[:4]
            docs = _extract_points(text, ["document", "दस्तावेज", "required", "proof"])[:4]
            apply_points = _extract_points(text, ["apply", "application", "register", "आवेदन"])[:2]

            payload.update(
                {
                    "eligibility_points_hi": eligibility,
                    "benefits_points_hi": benefits,
                    "documents_points_hi": docs,
                    "apply_guidance_hi": " ".join(apply_points).strip(),
                    "apply_link": final_url,
                    "source_url": final_url,
                    "source_confidence": (
                        HIGH_CONFIDENCE_WITH_CONTENT if (eligibility or benefits) else LOW_CONFIDENCE_SPARSE_CONTENT
                    ),
                    "last_updated_date": _extract_last_updated(text),
                    "fetch_status": "ok",
                }
            )
            payload["is_stale"] = _is_stale(payload.get("fetched_at"), STALE_WARNING_DAYS)
            payload["freshness_note_hi"] = (
                "डेटा अपेक्षाकृत नया है, फिर भी आवेदन से पहले आधिकारिक पोर्टल देखें।"
                if not payload["is_stale"]
                else "ऑनलाइन जानकारी पुरानी हो सकती है, कृपया आधिकारिक पोर्टल पर सत्यापित करें।"
            )
            return payload
        except Exception as e:
            last_err = str(e)

    if last_err:
        payload["error"] = last_err
    return payload


def get_cached_scheme_enrichment(
    scheme_id: str,
    scheme_name_hi: str = "",
    force_refresh: bool = False,
):
    cache = _load_cache()
    cached = cache.get(scheme_id)

    if cached and not force_refresh:
        fetched_at = cached.get("fetched_at")
        if fetched_at and not _is_stale(fetched_at, CACHE_TTL_DAYS):
            cached["cache_hit"] = True
            cached["is_stale"] = _is_stale(fetched_at, STALE_WARNING_DAYS)
            if cached.get("is_stale"):
                cached["freshness_note_hi"] = "कैश डेटा पुराना हो सकता है, कृपया आधिकारिक पोर्टल पर सत्यापित करें।"
            return cached

    fresh = fetch_scheme_details_from_internet(scheme_id, scheme_name_hi=scheme_name_hi)
    fresh["cache_hit"] = False
    cache[scheme_id] = fresh
    _save_cache(cache)
    return fresh


def enrich_scheme_results(local_results, use_internet: bool = True, internet_top_n: int = 3):
    if not use_internet:
        return local_results

    merged = []
    for i, item in enumerate(local_results):
        result = dict(item)
        if i < internet_top_n:
            enrich = get_cached_scheme_enrichment(
                scheme_id=result.get("scheme_id", ""),
                scheme_name_hi=result.get("name_hi", ""),
            )
            result["internet_enrichment"] = enrich
            result["source_url"] = enrich.get("source_url", "")
            result["source_confidence"] = enrich.get("source_confidence", result.get("source_confidence", 0.5))
            result["last_updated_date"] = enrich.get("last_updated_date", "")
            result["is_stale"] = enrich.get("is_stale", True)
            result["freshness_note_hi"] = enrich.get("freshness_note_hi", "")
            result["eligibility_points_hi"] = enrich.get("eligibility_points_hi", [])
            result["benefits_points_hi"] = enrich.get("benefits_points_hi", [])
            docs = list(result.get("documents_hi", []))
            for d in enrich.get("documents_points_hi", []):
                if d not in docs:
                    docs.append(d)
            result["documents_hi"] = docs
            if enrich.get("apply_guidance_hi"):
                result["apply_hi"] = enrich["apply_guidance_hi"]
            if enrich.get("apply_link"):
                result["apply_link"] = enrich["apply_link"]
        else:
            result.setdefault("source_confidence", 0.5)
            result.setdefault("is_stale", True)
            result.setdefault("freshness_note_hi", "स्थानीय डेटा उपयोग किया गया है।")

        base = float(result.get("score", 0.0))
        conf = float(result.get("source_confidence", 0.5))
        fresh_bonus = HYBRID_FRESHNESS_BONUS if not result.get("is_stale", True) else 0.0
        result["hybrid_score"] = base + (HYBRID_CONFIDENCE_WEIGHT * conf) + fresh_bonus
        merged.append(result)

    merged.sort(key=lambda x: x.get("hybrid_score", x.get("score", 0.0)), reverse=True)
    return merged
