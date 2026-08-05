"""Turning an uploaded document into retrievable, citable chunks.

Chunks follow the document's own headings where it has them. A curriculum design
is written in sections — strand, sub-strand, outcomes — and a citation that says
"Grade 7 Integrated Science — Mixtures, Elements and Compounds" is worth far more
to a teacher than "page 4". Where there are no headings, it falls back to
paragraph grouping with an overlap so a sentence spanning a boundary is still
findable.
"""

import re

from django.utils import timezone

from .models import Chunk
from .retrieval import term_counts, tokenize

TARGET_CHARS = 1200
OVERLAP_CHARS = 150

# A heading is a short line that isn't a sentence: numbered sections, ALL CAPS,
# or Title Case without terminal punctuation.
HEADING_RE = re.compile(
    r"^\s*(?:"
    r"(?:\d+(?:\.\d+)*\s+\S.*)"          # 1.2.3 Something
    r"|(?:[A-Z][A-Z0-9 ,&\-/()']{3,80})"  # ALL CAPS
    r"|(?:(?:STRAND|SUB-?STRAND|TOPIC|UNIT|SECTION|CHAPTER)\b.*)"
    r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _is_heading(line):
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    if stripped[-1] in ".?!;:,":
        return False
    if re.match(r"^\d+(\.\d+)*\s+\S", stripped):
        return True
    letters = [c for c in stripped if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return True
    return bool(
        re.match(
            r"^(strand|sub-?strand|topic|unit|section|chapter|learning outcome)",
            stripped,
            re.IGNORECASE,
        )
    )


def split_sections(text):
    """[(heading, body)] following the document's own structure."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    sections = []
    heading = ""
    buffer = []
    for line in lines:
        if _is_heading(line):
            if buffer and any(b.strip() for b in buffer):
                sections.append((heading, "\n".join(buffer).strip()))
            heading = line.strip()
            buffer = []
        else:
            buffer.append(line)
    if buffer and any(b.strip() for b in buffer):
        sections.append((heading, "\n".join(buffer).strip()))
    return [(h, b) for h, b in sections if b]


def _split_long(body):
    """Break an over-long section on paragraph edges, with a little overlap."""
    if len(body) <= TARGET_CHARS:
        return [body]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    pieces, current = [], ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > TARGET_CHARS:
            pieces.append(current.strip())
            current = current[-OVERLAP_CHARS:] + "\n\n" + paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current.strip():
        pieces.append(current.strip())

    # A single paragraph longer than the target still has to be cut somewhere.
    final = []
    for piece in pieces:
        while len(piece) > TARGET_CHARS * 2:
            final.append(piece[:TARGET_CHARS])
            piece = piece[TARGET_CHARS - OVERLAP_CHARS:]
        final.append(piece)
    return final


def chunk_text(text):
    """[(heading, chunk)] ready to store."""
    chunks = []
    for heading, body in split_sections(text):
        for piece in _split_long(body):
            if piece.strip():
                chunks.append((heading, piece.strip()))
    if not chunks and (text or "").strip():
        chunks = [("", text.strip())]
    return chunks


def index_document(document):
    """(Re)build a document's chunks. Safe to call again after an edit."""
    document.chunks.all().delete()

    rows = []
    for ordinal, (heading, piece) in enumerate(chunk_text(document.text), start=1):
        # The heading is indexed with the body: "Sub-strand 2.1 Mixtures" is
        # exactly what a teacher searches for, and it appears nowhere else.
        counts = term_counts(f"{heading}\n{piece}" if heading else piece)
        rows.append(
            Chunk(
                document=document,
                ordinal=ordinal,
                heading=heading[:250],
                text=piece,
                term_counts=counts,
                length=sum(counts.values()) or len(tokenize(piece)),
            )
        )
    Chunk.objects.bulk_create(rows)

    document.indexed_at = timezone.now()
    document.save(update_fields=["indexed_at", "updated_at"])
    return len(rows)


def extract_text(uploaded_file):
    """Best-effort text from an upload.

    PDFs are extracted when pypdf is installed; otherwise the caller is told to
    paste the text. Returning empty is not a failure — a document with a file but
    no text simply is not indexed, and the UI says so.
    """
    name = (getattr(uploaded_file, "name", "") or "").lower()
    if name.endswith(".txt") or name.endswith(".md"):
        uploaded_file.seek(0)
        return uploaded_file.read().decode("utf-8", errors="replace")
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        uploaded_file.seek(0)
        try:
            reader = PdfReader(uploaded_file)
            return "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return ""
    return ""
