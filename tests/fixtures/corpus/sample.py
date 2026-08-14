"""A small module used as a code-parsing fixture."""


def bm25_score(term_frequency: int, document_frequency: int, total_documents: int) -> float:
    """Return a lexical relevance score for a term."""
    k1 = 1.5
    b = 0.75
    return term_frequency * (k1 + 1) / (
        term_frequency + k1 * (1 - b + b * total_documents / document_frequency)
    )


class Retriever:
    """A lexical retriever stub for the fixture corpus."""

    def __init__(self) -> None:
        self.corpus = ["surface code", "error correction", "threshold"]

    def search(self, query: str) -> list[str]:
        return [doc for doc in self.corpus if query in doc]
