from __future__ import annotations

import math
from abc import ABC, abstractmethod

from care_lifeline.tools.rag.chunker import Chunk
from care_lifeline.tools.rag.embeddings import EmbeddingPort
from care_lifeline.tools.rag.store import VectorStore


def _tokenize(text: str) -> list[str]:
    """Chinese: per-character; latin/digit: per-token. Good enough for BM25."""
    tokens: list[str] = []
    buf = ""
    for ch in text.lower():
        if "一" <= ch <= "鿿":
            tokens.append(ch)
        elif ch.isalnum():
            buf += ch
        else:
            if buf:
                tokens.append(buf)
                buf = ""
    if buf:
        tokens.append(buf)
    return [t for t in tokens if t]


class SimpleBM25:
    """Minimal BM25 over an in-memory corpus; no external dependency."""

    def __init__(self) -> None:
        self._docs: list[list[str]] = []
        self._chunks: list[Chunk] = []
        self._df: dict[str, int] = {}
        self._avg_len = 0.0

    def add(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            toks = _tokenize(chunk.text)
            self._docs.append(toks)
            self._chunks.append(chunk)
            for term in set(toks):
                self._df[term] = self._df.get(term, 0) + 1
        if self._docs:
            self._avg_len = sum(len(d) for d in self._docs) / len(self._docs)

    def search(self, query: str, top_k: int = 5) -> list[tuple[Chunk, float]]:
        q = _tokenize(query)
        n = len(self._docs) or 1
        scored: list[tuple[Chunk, float]] = []
        for i, doc in enumerate(self._docs):
            scored.append((self._chunks[i], self._score(q, doc, n)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def _score(self, q: list[str], doc: list[str], n: int) -> float:
        if not doc:
            return 0.0
        tf: dict[str, int] = {}
        for term in doc:
            tf[term] = tf.get(term, 0) + 1
        dl = len(doc)
        avg = self._avg_len or 1.0
        total = 0.0
        for term in q:
            if term not in self._df:
                continue
            tf_term = tf.get(term, 0)
            if tf_term == 0:
                continue
            idf = math.log((n - self._df[term] + 0.5) / (self._df[term] + 0.5) + 1.0)
            denom = tf_term + 1.2 * (1.0 - 0.75 + 0.75 * dl / avg)
            total += idf * (tf_term * (1.2 + 1.0)) / denom
        return total


class Retriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, k: int | None = None) -> list[Chunk]: ...


class HybridRetriever(Retriever):
    """Fuse vector + BM25 via Reciprocal Rank Fusion (RRF)."""

    def __init__(
        self, store: VectorStore, embedding: EmbeddingPort, bm25: SimpleBM25, k: int = 5
    ) -> None:
        self._store = store
        self._embedding = embedding
        self._bm25 = bm25
        self._k = k

    def retrieve(self, query: str, k: int | None = None) -> list[Chunk]:
        k = k or self._k
        vector = self._embedding.embed([query])[0]
        vec_hits_list = self._store.search(vector, k * 2)
        lex_hits_list = self._bm25.search(query, k * 2)
        vec_hits = {c.index: s for c, s in vec_hits_list}
        lex_hits = {c.index: s for c, s in lex_hits_list}
        fused: dict[int, float] = {}
        for rank, idx in enumerate(sorted(vec_hits, key=lambda i: -vec_hits[i])):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (rank + 1 + 60)
        for rank, idx in enumerate(sorted(lex_hits, key=lambda i: -lex_hits[i])):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (rank + 1 + 60)
        all_chunks = {c.index: c for c, _ in vec_hits_list}
        for c, _ in lex_hits_list:
            all_chunks.setdefault(c.index, c)
        ranked = sorted(fused, key=lambda i: -fused[i])[:k]
        return [all_chunks[i] for i in ranked if i in all_chunks]
