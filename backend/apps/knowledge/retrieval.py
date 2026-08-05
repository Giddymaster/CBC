"""Retrieval over the curriculum knowledge base.

Lexical BM25 by default: it needs no API key, no vector database and no network,
which matters for a system that has to work in a school with intermittent
connectivity. Embeddings are supported when a provider is configured, and are
blended with the lexical score — but nothing here depends on them.

What makes this more than a search box is **authority weighting**. Two documents
can both answer a question; if one is an MoE circular and the other is a school
handout, the MoE passage must come first and must be the one the model is told
to follow. `apps.schools.moe.AUTHORITY_RANK` is the single definition of that
order.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from django.db.models import Q

from apps.schools.moe import AUTHORITY_LABELS, authority_rank

from .models import Chunk, Document

# Words that carry no retrieval signal in this domain.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "that", "the", "this", "to", "was",
    "were", "will", "with", "which", "should", "shall", "can", "may", "these",
    "their", "there", "they", "you", "your", "we", "our", "how", "what", "when",
}

TOKEN_RE = re.compile(r"[a-z0-9]+")

# BM25 constants — standard defaults; the corpus is small enough that tuning
# these would be premature.
K1 = 1.5
B = 0.75

# How much the source's standing lifts a passage. A full authority step (school
# -> MoE) roughly doubles the score, which is enough to reorder near-ties without
# letting a vaguely-relevant MoE passage beat a precisely-relevant school one.
AUTHORITY_WEIGHT = 0.6


def tokenize(text):
    return [
        token
        for token in TOKEN_RE.findall((text or "").lower())
        if token not in STOPWORDS and len(token) > 1
    ]


def term_counts(text):
    return dict(Counter(tokenize(text)))


@dataclass
class Passage:
    """One retrieved chunk, with everything needed to cite and rank it."""

    chunk_id: int
    document_id: int
    document_title: str
    heading: str
    text: str
    authority: str
    authority_label: str
    authority_rank: int
    is_national: bool
    lexical_score: float
    score: float
    grades: list = field(default_factory=list)

    def as_citation(self):
        where = f" — {self.heading}" if self.heading else ""
        return f"{self.document_title}{where} [{self.authority_label}]"

    def to_dict(self):
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document": self.document_title,
            "heading": self.heading,
            "text": self.text,
            "authority": self.authority,
            "authority_label": self.authority_label,
            "national": self.is_national,
            "score": round(self.score, 4),
            "citation": self.as_citation(),
        }


def visible_documents(school):
    """National documents plus this school's own. Never another tenant's."""
    qs = Document.objects.select_related("source", "learning_area")
    if school is None:
        return qs.filter(school__isnull=True)
    return qs.filter(Q(school__isnull=True) | Q(school=school))


def search(
    query,
    *,
    school,
    learning_area=None,
    grade=None,
    kinds=None,
    limit=8,
):
    """Rank passages for a query, highest authority first among near-equals.

    Returns [] rather than raising when the knowledge base is empty — callers
    fall back to ungrounded behaviour and say so.
    """
    query_terms = tokenize(query)
    if not query_terms:
        return []

    documents = visible_documents(school)
    if learning_area is not None:
        # A document with no learning area is general and still applies.
        documents = documents.filter(
            Q(learning_area=learning_area) | Q(learning_area__isnull=True)
        )
    if kinds:
        documents = documents.filter(kind__in=kinds)

    doc_map = {d.id: d for d in documents}
    if not doc_map:
        return []

    if grade is not None:
        doc_map = {
            doc_id: doc for doc_id, doc in doc_map.items() if doc.covers_grade(grade)
        }
        if not doc_map:
            return []

    chunks = list(Chunk.objects.filter(document_id__in=doc_map.keys()))
    if not chunks:
        return []

    total = len(chunks)
    avg_length = sum(c.length or len(tokenize(c.text)) for c in chunks) / total or 1

    # Document frequency per query term, over chunks. Iterate the *distinct*
    # terms: a query repeating a word ("strand sub-strand") would otherwise
    # count that word twice per chunk, pushing n above the corpus size and
    # driving the IDF negative.
    distinct_terms = set(query_terms)
    doc_freq = Counter()
    for chunk in chunks:
        counts = chunk.term_counts or term_counts(chunk.text)
        for term in distinct_terms:
            if term in counts:
                doc_freq[term] += 1

    query_weight = Counter(query_terms)
    passages = []
    for chunk in chunks:
        counts = chunk.term_counts or term_counts(chunk.text)
        length = chunk.length or sum(counts.values()) or 1
        lexical = 0.0
        for term, q_count in query_weight.items():
            freq = counts.get(term, 0)
            if not freq:
                continue
            n = doc_freq[term]
            # Floor at zero: a term in every chunk carries no signal, but it
            # must never subtract from a passage's score.
            idf = max(0.0, math.log(1 + (total - n + 0.5) / (n + 0.5)))
            denom = freq + K1 * (1 - B + B * length / avg_length)
            lexical += q_count * idf * (freq * (K1 + 1)) / denom
        if lexical <= 0:
            continue

        document = doc_map[chunk.document_id]
        rank = authority_rank(document.authority)
        # Normalised 0..1 so the multiplier is stable if new authorities appear.
        weighted = lexical * (1 + AUTHORITY_WEIGHT * (rank / 100))

        passages.append(
            Passage(
                chunk_id=chunk.id,
                document_id=document.id,
                document_title=document.title,
                heading=chunk.heading,
                text=chunk.text,
                authority=document.authority,
                authority_label=AUTHORITY_LABELS.get(document.authority, "Other"),
                authority_rank=rank,
                is_national=document.is_national,
                lexical_score=lexical,
                score=weighted,
                grades=document.grades or [],
            )
        )

    # Score first, then authority as the tie-break — so an MoE passage wins a
    # close call but never displaces a clearly better-matching one.
    passages.sort(key=lambda p: (-p.score, -p.authority_rank))
    return passages[:limit]


def authority_spread(passages):
    """Which authorities answered, and which one governs.

    This is not semantic contradiction detection — it does not read the passages
    and decide they disagree. It reports that sources of *different standing* all
    matched, which is the signal a human needs to check, and names the one that
    governs if they do conflict.
    """
    if not passages:
        return {"authorities": [], "governing": None, "mixed": False}

    seen = {}
    for passage in passages:
        seen.setdefault(passage.authority, 0)
        seen[passage.authority] += 1

    ordered = sorted(seen, key=lambda code: -authority_rank(code))
    return {
        "authorities": [
            {
                "code": code,
                "label": AUTHORITY_LABELS.get(code, "Other"),
                "passages": seen[code],
                "rank": authority_rank(code),
            }
            for code in ordered
        ],
        "governing": ordered[0],
        "governing_label": AUTHORITY_LABELS.get(ordered[0], "Other"),
        "mixed": len(ordered) > 1,
    }


def build_context(passages, *, max_chars=12000):
    """Passages as numbered, cited context for a prompt.

    Highest authority is presented first and labelled, so the instruction to
    prefer it has something concrete to point at.
    """
    blocks = []
    used = 0
    for index, passage in enumerate(
        sorted(passages, key=lambda p: (-p.authority_rank, -p.score)), start=1
    ):
        block = (
            f"[{index}] {passage.as_citation()}\n{passage.text.strip()}\n"
        )
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n".join(blocks)
