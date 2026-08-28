from __future__ import annotations

from pathlib import Path

from care_lifeline.tools.rag.chunker import Chunk, chunk_text
from care_lifeline.tools.rag.embeddings import EmbeddingPort
from care_lifeline.tools.rag.retriever import SimpleBM25
from care_lifeline.tools.rag.store import VectorStore


def build_index(
    guideline_dir: str | Path,
    store: VectorStore,
    embedding: EmbeddingPort,
    bm25: SimpleBM25,
    glob: str = "*.md",
) -> list[Chunk]:
    """Index guideline/report documents into the vector store + BM25 corpus."""
    base = Path(guideline_dir)
    chunks: list[Chunk] = []
    for path in sorted(base.glob(glob)):
        text = path.read_text(encoding="utf-8")
        chunks.extend(chunk_text(text, source=path.name))
    vectors = embedding.embed([chunk.text for chunk in chunks])
    store.add(chunks, vectors)
    bm25.add(chunks)
    return chunks
