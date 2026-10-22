"""Embeddings for RAG chunk search.

Mirrors llm.py's shape: an OpenAI-compatible endpoint when configured,
otherwise (or on any failure) a deterministic offline stub, so chunk search
stays testable and never raises. Unlike llm.chat(), a failure here falls
back to the stub rather than returning None - a stored chunk needs some
vector to stay searchable at all; there's no "template" escape hatch for a
missing embedding the way there is for missing prose.
"""

from __future__ import annotations

import hashlib
import math
import re

from ..config import get_settings

settings = get_settings()

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def embed(text: str) -> list[float] | None:
    """Embed one string. Returns None only for empty/whitespace input."""
    text = (text or "").strip()
    if not text:
        return None
    base_url = settings.embedding_base_url or settings.llm_base_url
    if base_url and settings.ai_data_processing_enabled:
        try:
            return _remote_embed(text, base_url)
        except Exception:
            return _stub_embed(text)
    return _stub_embed(text)


def embed_batch(texts: list[str]) -> list[list[float] | None]:
    return [embed(t) for t in texts]


def _remote_embed(text: str, base_url: str) -> list[float]:
    import httpx

    headers = {"Content-Type": "application/json"}
    api_key = settings.embedding_api_key or settings.llm_api_key
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = base_url.rstrip("/") + "/embeddings"
    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        resp = client.post(
            url,
            json={"model": settings.embedding_model, "input": text},
            headers=headers,
        )
        resp.raise_for_status()
        return [float(x) for x in resp.json()["data"][0]["embedding"]]


def _stub_embed(text: str) -> list[float]:
    """Deterministic, dependency-free hashed bag-of-words vector.

    Not a real ML embedding - just a stable, comparable representation so
    cosine similarity ranking is meaningful offline and in tests. Each token
    hashes into one of embedding_dim buckets; bucket weight is log(1+count),
    then the whole vector is L2-normalized.
    """
    dim = settings.embedding_dim
    buckets = [0.0] * dim
    tokens = _TOKEN_RE.findall(text.lower())
    counts: dict[int, int] = {}
    for token in tokens:
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim
        counts[idx] = counts.get(idx, 0) + 1
    for idx, count in counts.items():
        buckets[idx] = math.log1p(count)
    norm = math.sqrt(sum(v * v for v in buckets))
    if norm == 0:
        return buckets
    return [v / norm for v in buckets]
