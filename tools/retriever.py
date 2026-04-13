import json
from pathlib import Path

DATA_PATH = Path("data/schemes.jsonl")
INDEX_PATH = Path("data/faiss.index")
META_PATH = Path("data/meta.json")

_model = None
_index = None
_meta = None


def _lazy_imports():
    try:
        import numpy as np
        import faiss
        from sentence_transformers import SentenceTransformer
        return np, faiss, SentenceTransformer
    except Exception:
        return None, None, None


def _load_model():
    global _model
    if _model is None:
        np, faiss, SentenceTransformer = _lazy_imports()
        if SentenceTransformer is None:
            return None
        _model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    return _model


def _load_schemes():
    schemes = []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                schemes.append(json.loads(line))
    return schemes


def build_index():
    np, faiss, _ = _lazy_imports()
    model = _load_model()
    if model is None or np is None or faiss is None:
        return False

    schemes = _load_schemes()

    texts = []
    meta = []
    for s in schemes:
        txt = (
            f"{s['name_hi']}. {s['summary_hi']} लाभ: {s.get('benefits_hi','')} "
            f"दस्तावेज: {', '.join(s.get('documents_hi', []))}. आवेदन: {s.get('apply_hi','')}"
        )
        texts.append(txt)
        meta.append(s)

    emb = model.encode(texts, normalize_embeddings=True)
    emb = np.array(emb, dtype="float32")

    dim = emb.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(emb)

    faiss.write_index(index, str(INDEX_PATH))
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return True


def _load_index():
    global _index, _meta
    np, faiss, _ = _lazy_imports()
    if faiss is None:
        return None, None

    if _index is None or _meta is None:
        if not INDEX_PATH.exists() or not META_PATH.exists():
            if not build_index():
                return None, None
        _index = faiss.read_index(str(INDEX_PATH))
        with open(META_PATH, "r", encoding="utf-8") as f:
            _meta = json.load(f)
    return _index, _meta


def _semantic_search(query_hi: str, top_k: int = 5):
    np, _, _ = _lazy_imports()
    model = _load_model()
    index, meta = _load_index()

    if model is None or index is None or meta is None or np is None:
        return []

    q = model.encode([query_hi], normalize_embeddings=True)
    q = np.array(q, dtype="float32")

    scores, ids = index.search(q, top_k)
    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx == -1:
            continue
        s = meta[idx]
        results.append(
            {
                "scheme_id": s["scheme_id"],
                "name_hi": s["name_hi"],
                "summary_hi": s["summary_hi"],
                "benefits_hi": s.get("benefits_hi", ""),
                "apply_hi": s.get("apply_hi", ""),
                "documents_hi": s.get("documents_hi", []),
                "score": float(score),
                "search_backend": "semantic",
                "source_confidence": 0.75,
            }
        )
    return results


def _tokenize(text: str):
    return [t for t in (text or "").lower().replace("/", " ").replace("-", " ").split() if t]


def _lexical_search(query_hi: str, top_k: int = 5):
    schemes = _load_schemes()
    q_tokens = set(_tokenize(query_hi))
    results = []

    for s in schemes:
        hay = " ".join(
            [
                s.get("name_hi", ""),
                s.get("summary_hi", ""),
                s.get("benefits_hi", ""),
                " ".join(s.get("documents_hi", [])),
                s.get("apply_hi", ""),
            ]
        )
        h_tokens = set(_tokenize(hay))
        overlap = len(q_tokens.intersection(h_tokens))
        score = overlap / max(len(q_tokens), 1)
        if score > 0:
            results.append(
                {
                    "scheme_id": s["scheme_id"],
                    "name_hi": s["name_hi"],
                    "summary_hi": s["summary_hi"],
                    "benefits_hi": s.get("benefits_hi", ""),
                    "apply_hi": s.get("apply_hi", ""),
                    "documents_hi": s.get("documents_hi", []),
                    "score": float(score),
                    "search_backend": "lexical",
                    "source_confidence": 0.55,
                }
            )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def search_schemes(query_hi: str, top_k: int = 5, use_internet: bool = True, internet_top_n: int = 3):
    local = _semantic_search(query_hi, top_k=max(top_k, internet_top_n))
    if not local:
        local = _lexical_search(query_hi, top_k=max(top_k, internet_top_n))

    if not local:
        return []

    if use_internet:
        try:
            from tools.internet_search import enrich_scheme_results
            local = enrich_scheme_results(local, use_internet=True, internet_top_n=internet_top_n)
        except Exception:
            pass

    return local[:top_k]
