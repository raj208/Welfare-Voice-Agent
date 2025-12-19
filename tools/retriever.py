import json
from pathlib import Path
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

DATA_PATH = Path("data/schemes.jsonl")
INDEX_PATH = Path("data/faiss.index")
META_PATH = Path("data/meta.json")

_model = None
_index = None
_meta = None

def _load_model():
    global _model
    if _model is None:
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
    model = _load_model()
    schemes = _load_schemes()

    texts = []
    meta = []
    for s in schemes:
        txt = f"{s['name_hi']}. {s['summary_hi']} लाभ: {s.get('benefits_hi','')} दस्तावेज: {', '.join(s.get('documents_hi', []))}. आवेदन: {s.get('apply_hi','')}"
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

def _load_index():
    global _index, _meta
    if _index is None or _meta is None:
        if not INDEX_PATH.exists() or not META_PATH.exists():
            build_index()
        _index = faiss.read_index(str(INDEX_PATH))
        with open(META_PATH, "r", encoding="utf-8") as f:
            _meta = json.load(f)
    return _index, _meta

def search_schemes(query_hi: str, top_k: int = 5):
    model = _load_model()
    index, meta = _load_index()

    q = model.encode([query_hi], normalize_embeddings=True)
    q = np.array(q, dtype="float32")

    scores, ids = index.search(q, top_k)
    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx == -1:
            continue
        s = meta[idx]
        results.append({
            "scheme_id": s["scheme_id"],
            "name_hi": s["name_hi"],
            "summary_hi": s["summary_hi"],
            "apply_hi": s.get("apply_hi", ""),
            "documents_hi": s.get("documents_hi", []),
            "score": float(score),
        })
    return results
