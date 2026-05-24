from __future__ import annotations

from typing import List, Dict, Any, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def search_best_chunk(
    chunks: List[Dict[str, Any]],
    question: str,
) -> Tuple[Dict[str, Any], float]:
    """
    Use TF-IDF + cosine similarity to find the best chunk.
    """
    texts = [chunk["text"] for chunk in chunks]

    vectorizer = TfidfVectorizer()
    doc_matrix = vectorizer.fit_transform(texts)
    q_vector = vectorizer.transform([question])

    sims = cosine_similarity(q_vector, doc_matrix)[0]
    best_idx = sims.argmax()
    best_score = float(sims[best_idx])
    best_chunk = chunks[best_idx]

    return best_chunk, best_score