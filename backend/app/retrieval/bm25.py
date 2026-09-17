"""Small in-memory BM25 with an inverted index and deterministic tie-breaking.

Parameters (k1=1.5, b=0.75) and the IDF form match the retrieval experiments
that produced the validated module-recall numbers; do not change them without
re-running those measurements.
"""

import math
from collections import Counter, defaultdict

from app.retrieval.text import tokenize

K1 = 1.5
B = 0.75


class BM25Index:
    def __init__(self, doc_ids: list[str], docs: list[str]):
        if len(doc_ids) != len(docs):
            raise ValueError("doc_ids and docs must align")
        self.doc_ids = list(doc_ids)
        self.doc_len: list[int] = []
        self.inverted: dict[str, list[tuple[int, int]]] = defaultdict(list)
        df: dict[str, int] = defaultdict(int)
        for i, doc in enumerate(docs):
            freq = Counter(tokenize(doc))
            self.doc_len.append(sum(freq.values()))
            for word, tf in freq.items():
                df[word] += 1
                self.inverted[word].append((i, tf))
        n = len(docs)
        self.avgdl = (sum(self.doc_len) / n) if n else 0.0
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}

    def __len__(self) -> int:
        return len(self.doc_ids)

    def has_token(self, token: str) -> bool:
        return token in self.idf

    def max_possible_score(self, query: str) -> float:
        """Upper bound of `search` for this query: each matched token's
        contribution saturates at idf·(k1+1) as tf → ∞. Dividing a real top
        score by this gives a query-length-independent 'strength' in (0, 1]."""
        return sum(self.idf[t] * (K1 + 1) for t in set(tokenize(query)) if t in self.idf)

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        """Top-k (doc_id, score). Docs with zero score are never returned, so a
        query with no known tokens yields an empty list, not arbitrary docs."""
        if k <= 0 or not self.doc_ids:
            return []
        scores: dict[int, float] = defaultdict(float)
        for token in tokenize(query):
            postings = self.inverted.get(token)
            if not postings:
                continue
            idf = self.idf[token]
            for i, tf in postings:
                norm = K1 * (1 - B + B * (self.doc_len[i] / self.avgdl)) if self.avgdl else K1
                scores[i] += idf * (tf * (K1 + 1)) / (tf + norm)
        # Deterministic: score desc, then doc id asc.
        ranked = sorted(scores.items(), key=lambda item: (-item[1], self.doc_ids[item[0]]))
        return [(self.doc_ids[i], s) for i, s in ranked[:k]]
