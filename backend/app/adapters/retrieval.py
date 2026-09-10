"""Policy retrieval behind an interface.

Local deterministic keyword retrieval first; pgvector is EXT-110, deferred.
An official policy corpus is EXT-108, PROPOSED, so the index is empty until a
source list is approved.

Every retrieved chunk carries a citation. A recommendation without a citation
must not be shown as policy-backed.
"""

from typing import Any, Dict, List, Protocol, Sequence


class PolicyRetriever(Protocol):
    name: str

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        ...


class KeywordRetriever:
    """Deterministic keyword overlap. No model, no download, no network."""

    name = "keyword"

    def __init__(self, chunks: Sequence[Dict[str, Any]] = ()) -> None:
        self._chunks = list(chunks)

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        terms = {t for t in query.casefold().split() if len(t) > 2}
        scored = []
        for chunk in self._chunks:
            keywords = {k.casefold() for k in chunk.get("keywords", [])}
            overlap = len(terms & keywords)
            if overlap:
                scored.append((overlap, chunk))
        scored.sort(key=lambda pair: (-pair[0], pair[1].get("citation", "")))
        return [chunk for _, chunk in scored[:limit]]


def get_retriever(name: str) -> PolicyRetriever:
    # POLICY_RETRIEVER=local selects the deterministic keyword index. The
    # "external" value is reserved for a vector store, which is EXT-110 and
    # deferred, so it is refused rather than silently downgraded.
    if name in ("local", "keyword"):
        return KeywordRetriever()
    raise ValueError(f"retriever {name!r} is not available; pgvector is EXT-110, deferred")
