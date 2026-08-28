from __future__ import annotations

import re

from pydantic import BaseModel

_HEADING_RE = re.compile(r"^(#{1,6}\s+.+|\d+[\.、]\s+\S+)")
_SENT_SPLIT = re.compile(r"(?<=[。！？；\.\!\?;])\s*")


class Chunk(BaseModel):
    """A retrievable text segment produced by :func:`chunk_text`."""

    text: str
    source: str = ""
    section: str = ""
    index: int = 0


def chunk_text(text: str, max_chars: int = 500, source: str = "") -> list[Chunk]:
    """Split Chinese-friendly guidelines/reports into bounded chunks.

    Splits on markdown/numbered headings and blank lines; long paragraphs are
    further broken on sentence boundaries so no chunk exceeds ``max_chars``.
    """
    chunks: list[Chunk] = []
    section = ""
    buffer: list[str] = []
    idx = 0

    def flush(section_name: str) -> None:
        nonlocal idx
        para = "\n".join(buffer).strip()
        if not para:
            return
        if len(para) <= max_chars:
            chunks.append(Chunk(text=para, source=source, section=section_name, index=idx))
            idx += 1
            return
        for piece in _SENT_SPLIT.split(para):
            piece = piece.strip()
            if not piece:
                continue
            if len(piece) > max_chars:
                for i in range(0, len(piece), max_chars):
                    chunks.append(
                        Chunk(
                            text=piece[i : i + max_chars],
                            source=source,
                            section=section_name,
                            index=idx,
                        )
                    )
                    idx += 1
            else:
                chunks.append(Chunk(text=piece, source=source, section=section_name, index=idx))
                idx += 1

    for line in text.splitlines():
        if _HEADING_RE.match(line):
            flush(section)
            buffer = []
            section = line.lstrip("#").strip()
            continue
        if line.strip() == "":
            flush(section)
            buffer = []
            continue
        buffer.append(line)
    flush(section)
    return chunks
