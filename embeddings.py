"""Gemini Embedding 2 (3072 dimensions) through the Euron EURI gateway or the Google API, as in task 4."""
import time

import requests

import settings


def doc_input(title, text):
    """Embedding text for a chunk (Gemini Embedding 2 retrieval format, same as task 4)."""
    return f"title: {title} | text: {text}"


def query_input(question):
    """Embedding text for a search question (same as task 4)."""
    return f"task: search result | query: {question}"


def _euron(texts):
    r = requests.post(f"{settings.EURI_BASE_URL}/embeddings",
                      headers={"Authorization": f"Bearer {settings.EURI_API_KEY}"},
                      json={"model": settings.EMBED_MODEL, "input": texts, "dimensions": settings.EMBED_DIM},
                      timeout=120)
    if r.status_code in (429, 502, 503):
        raise RuntimeError(f"{r.status_code} retry")
    r.raise_for_status()
    return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]


_genai = None


def _google(texts):
    global _genai
    from google import genai
    from google.genai import types
    if _genai is None:
        _genai = genai.Client(api_key=settings.GOOGLE_API_KEY)
    res = _genai.models.embed_content(
        model=settings.EMBED_MODEL,
        # one Content per text: a plain list of strings is merged into ONE vector by this model
        contents=[types.Content(parts=[types.Part.from_text(text=t)]) for t in texts],
        config=types.EmbedContentConfig(output_dimensionality=settings.EMBED_DIM))
    return [e.values for e in res.embeddings]


def embed(texts, tries=6):
    """Embed a list of texts; waits 5, 10, 20, 40, 80 s on rate limits or gateway hiccups."""
    for attempt in range(tries):
        try:
            vecs = _euron(texts) if settings.EMBED_PROVIDER == "euron" else _google(texts)
            if len(vecs) != len(texts) or any(len(v) != settings.EMBED_DIM for v in vecs):
                raise ValueError("wrong number or size of vectors")
            return vecs
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if attempt < tries - 1 and any(s in msg for s in ("429", "502", "503", "retry", "RESOURCE_EXHAUSTED", "timed out")):
                time.sleep(5 * 2 ** attempt)
            else:
                raise
