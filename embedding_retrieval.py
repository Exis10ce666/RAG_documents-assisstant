from __future__ import annotations

import hashlib
import json
import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer

from .storage import INDEX_DIR


EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_MODEL: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Load the embedding model once per backend process."""
    global _MODEL

    if _MODEL is None:
        _MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)

    return _MODEL


def normalize_text(text: str) -> str:
    text = str(text).replace("\xa0", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_chunk_text(chunk: Dict[str, Any]) -> str:
    """Robustly read text from a chunk, including older block-based chunk formats."""
    if not isinstance(chunk, dict):
        return ""

    for key in ("text", "content", "chunk_text", "page_text"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_text(value)

    blocks = chunk.get("blocks")
    if isinstance(blocks, list):
        parts: List[str] = []
        for block in blocks:
            if isinstance(block, str):
                if block.strip():
                    parts.append(block.strip())
            elif isinstance(block, dict):
                block_text = get_chunk_text(block)
                if block_text:
                    parts.append(block_text)
            else:
                block_text = str(block).strip()
                if block_text:
                    parts.append(block_text)

        if parts:
            return normalize_text("\n".join(parts))

    return ""


def safe_cache_name(cache_key: str) -> str:
    """Turn a document/cache key into a filesystem-safe filename stem."""
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", cache_key).strip("_")[:80]
    return f"{cleaned or 'index'}_{digest}"


def build_index_signature(chunks: List[Dict[str, Any]]) -> str:
    """
    Stable content signature for index invalidation.
    If chunk text or source metadata changes, the stored FAISS/TF-IDF index is rebuilt.
    """
    hasher = hashlib.sha256()

    for chunk in chunks:
        payload = {
            "document_id": chunk.get("document_id"),
            "filename": chunk.get("filename"),
            "page": chunk.get("page"),
            "source_chunk_index": chunk.get("source_chunk_index"),
            "text": get_chunk_text(chunk),
        }
        hasher.update(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        hasher.update(b"\n---chunk---\n")

    return hasher.hexdigest()


def l2_normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return vectors / norms


def min_max_normalize(scores: np.ndarray) -> np.ndarray:
    if len(scores) == 0:
        return scores

    min_score = float(np.min(scores))
    max_score = float(np.max(scores))

    if abs(max_score - min_score) < 1e-12:
        return np.ones_like(scores, dtype=np.float32)

    return ((scores - min_score) / (max_score - min_score)).astype(np.float32)


def build_hybrid_index(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Expensive step: embeds every chunk and builds FAISS + TF-IDF.
    This should run on upload/load, not every ask.
    """
    texts = [get_chunk_text(chunk) for chunk in chunks]
    texts = [text if text else "empty" for text in texts]

    model = get_embedding_model()

    dense_embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True,
    ).astype("float32")

    dense_embeddings = l2_normalize(dense_embeddings).astype("float32")

    dimension = dense_embeddings.shape[1]
    faiss_index = faiss.IndexFlatIP(dimension)
    faiss_index.add(dense_embeddings)

    try:
        tfidf_vectorizer = TfidfVectorizer(
            lowercase=True,
            analyzer="word",
            ngram_range=(1, 2),
            max_features=100_000,
        )
        sparse_matrix = tfidf_vectorizer.fit_transform(texts)
    except ValueError:
        # Fallback for unusual OCR text where word vocabulary becomes empty.
        tfidf_vectorizer = TfidfVectorizer(
            lowercase=True,
            analyzer="char_wb",
            ngram_range=(3, 5),
            max_features=100_000,
        )
        sparse_matrix = tfidf_vectorizer.fit_transform(texts)

    return {
        "chunks": chunks,
        "texts": texts,
        "dense_embeddings": dense_embeddings,
        "faiss_index": faiss_index,
        "tfidf_vectorizer": tfidf_vectorizer,
        "sparse_matrix": sparse_matrix,
    }


def save_hybrid_index_cache(cache_key: str, signature: str, index_bundle: Dict[str, Any]) -> None:
    """Persist FAISS + TF-IDF to disk so restart does not force re-embedding chunks."""
    stem = safe_cache_name(cache_key)
    faiss_path = INDEX_DIR / f"{stem}.faiss"
    meta_path = INDEX_DIR / f"{stem}.pkl"

    faiss.write_index(index_bundle["faiss_index"], str(faiss_path))

    metadata = {
        "signature": signature,
        "chunks": index_bundle["chunks"],
        "texts": index_bundle["texts"],
        "dense_embeddings": index_bundle["dense_embeddings"],
        "tfidf_vectorizer": index_bundle["tfidf_vectorizer"],
        "sparse_matrix": index_bundle["sparse_matrix"],
    }

    with meta_path.open("wb") as file:
        pickle.dump(metadata, file, protocol=pickle.HIGHEST_PROTOCOL)


def load_hybrid_index_cache(cache_key: str, signature: str) -> Optional[Dict[str, Any]]:
    """Load a persisted index only if its content signature still matches."""
    stem = safe_cache_name(cache_key)
    faiss_path = INDEX_DIR / f"{stem}.faiss"
    meta_path = INDEX_DIR / f"{stem}.pkl"

    if not faiss_path.exists() or not meta_path.exists():
        return None

    try:
        with meta_path.open("rb") as file:
            metadata = pickle.load(file)

        if metadata.get("signature") != signature:
            return None

        faiss_index = faiss.read_index(str(faiss_path))

        return {
            "chunks": metadata["chunks"],
            "texts": metadata["texts"],
            "dense_embeddings": metadata["dense_embeddings"],
            "faiss_index": faiss_index,
            "tfidf_vectorizer": metadata["tfidf_vectorizer"],
            "sparse_matrix": metadata["sparse_matrix"],
        }
    except Exception:
        return None


def dense_search(index_bundle: Dict[str, Any], question: str, candidate_k: int) -> Dict[int, float]:
    """Embed the current question and search the already-built FAISS index."""
    model = get_embedding_model()

    query_embedding = model.encode(
        [question],
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True,
    ).astype("float32")

    query_embedding = l2_normalize(query_embedding).astype("float32")

    faiss_index = index_bundle["faiss_index"]
    total_chunks = len(index_bundle["texts"])
    k = min(candidate_k, total_chunks)

    scores, indices = faiss_index.search(query_embedding, k)

    result: Dict[int, float] = {}
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        result[int(idx)] = float(score)

    return result


def sparse_search(index_bundle: Dict[str, Any], question: str, candidate_k: int) -> Dict[int, float]:
    tfidf_vectorizer = index_bundle["tfidf_vectorizer"]
    sparse_matrix = index_bundle["sparse_matrix"]

    query_vector = tfidf_vectorizer.transform([question])
    raw_scores = (sparse_matrix @ query_vector.T).toarray().ravel()

    if len(raw_scores) == 0:
        return {}

    k = min(candidate_k, len(raw_scores))
    top_indices = np.argsort(raw_scores)[::-1][:k]

    result: Dict[int, float] = {}
    for idx in top_indices:
        result[int(idx)] = float(raw_scores[idx])

    return result


def merge_hybrid_scores(
    dense_scores: Dict[int, float],
    sparse_scores: Dict[int, float],
    dense_weight: float,
    sparse_weight: float,
) -> List[Tuple[int, float, float, float]]:
    all_indices = sorted(set(dense_scores.keys()) | set(sparse_scores.keys()))
    if not all_indices:
        return []

    dense_values = np.array([dense_scores.get(idx, 0.0) for idx in all_indices], dtype=np.float32)
    sparse_values = np.array([sparse_scores.get(idx, 0.0) for idx in all_indices], dtype=np.float32)

    dense_norm = min_max_normalize(dense_values)
    sparse_norm = min_max_normalize(sparse_values)

    merged: List[Tuple[int, float, float, float]] = []
    for pos, idx in enumerate(all_indices):
        dense_score = float(dense_norm[pos])
        sparse_score = float(sparse_norm[pos])
        hybrid_score = dense_weight * dense_score + sparse_weight * sparse_score
        merged.append((idx, float(hybrid_score), dense_score, sparse_score))

    merged.sort(key=lambda item: item[1], reverse=True)
    return merged


def make_result_chunk(
    original_chunk: Dict[str, Any],
    rank: int,
    hybrid_score: float,
    dense_score: float,
    sparse_score: float,
) -> Dict[str, Any]:
    result = dict(original_chunk)
    text = get_chunk_text(original_chunk)

    result["text"] = text
    result["rank"] = rank
    result["score"] = float(hybrid_score)
    result["hybrid_score"] = float(hybrid_score)
    result["dense_score"] = float(dense_score)
    result["sparse_score"] = float(sparse_score)

    result.setdefault("page", original_chunk.get("page", 0))
    result.setdefault("filename", original_chunk.get("filename", "Unknown PDF"))
    result.setdefault("document_id", original_chunk.get("document_id", "-"))
    result.setdefault("source_chunk_index", original_chunk.get("source_chunk_index", rank))

    return result


def hybrid_search_top_k_chunks(
    chunks: List[Dict[str, Any]],
    index_bundle: Dict[str, Any],
    question: str,
    top_k: int = 5,
    dense_weight: float = 0.4,
    sparse_weight: float = 0.6,
) -> List[Dict[str, Any]]:
    if not chunks:
        return []

    indexed_chunks = index_bundle.get("chunks", chunks)
    candidate_k = min(max(top_k * 6, 20), len(indexed_chunks))

    dense_scores = dense_search(index_bundle=index_bundle, question=question, candidate_k=candidate_k)
    sparse_scores = sparse_search(index_bundle=index_bundle, question=question, candidate_k=candidate_k)

    merged_scores = merge_hybrid_scores(
        dense_scores=dense_scores,
        sparse_scores=sparse_scores,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )

    top_results: List[Dict[str, Any]] = []

    for rank, (idx, hybrid_score, dense_score, sparse_score) in enumerate(merged_scores[:top_k], start=1):
        if idx < 0 or idx >= len(indexed_chunks):
            continue
        top_results.append(
            make_result_chunk(
                original_chunk=indexed_chunks[idx],
                rank=rank,
                hybrid_score=hybrid_score,
                dense_score=dense_score,
                sparse_score=sparse_score,
            )
        )

    return top_results


def split_sentences(text: str) -> List[str]:
    text = normalize_text(text)
    if not text:
        return []

    pieces = re.split(r"(?<=[.!?。！？])\s+", text)
    sentences = [piece.strip() for piece in pieces if piece.strip()]

    if len(sentences) <= 1:
        sentences = [line.strip() for line in text.splitlines() if line.strip()]

    return sentences


def simple_keyword_score(question: str, sentence: str) -> float:
    q_tokens = set(re.findall(r"[\w\u0400-\u04FF]+", question.lower()))
    s_tokens = set(re.findall(r"[\w\u0400-\u04FF]+", sentence.lower()))

    if not q_tokens or not s_tokens:
        return 0.0

    overlap = q_tokens & s_tokens
    return len(overlap) / max(len(q_tokens), 1)


def build_extractive_answer(
    question: str,
    top_chunks: List[Dict[str, Any]],
    top_n_sentences: int = 3,
) -> Tuple[str, List[Dict[str, Any]]]:
    candidates: List[Dict[str, Any]] = []

    for chunk_rank, chunk in enumerate(top_chunks, start=1):
        text = get_chunk_text(chunk)
        sentences = split_sentences(text)

        for sentence in sentences:
            score = simple_keyword_score(question, sentence)
            if score <= 0:
                continue

            candidates.append(
                {
                    "text": sentence,
                    "sentence": sentence,
                    "score": float(score),
                    "page": chunk.get("page", 0),
                    "chunk_rank": chunk_rank,
                    "filename": chunk.get("filename", "Unknown PDF"),
                    "document_id": chunk.get("document_id", "-"),
                    "source_chunk_index": chunk.get("source_chunk_index", chunk_rank),
                }
            )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    evidence = candidates[:top_n_sentences]

    if evidence:
        answer = " ".join(item["text"] for item in evidence)
        return answer, evidence

    if top_chunks:
        best = top_chunks[0]
        answer = get_chunk_text(best)[:800]
        evidence = [
            {
                "text": answer,
                "sentence": answer,
                "score": float(best.get("score", 0.0)),
                "page": best.get("page", 0),
                "chunk_rank": 1,
                "filename": best.get("filename", "Unknown PDF"),
                "document_id": best.get("document_id", "-"),
                "source_chunk_index": best.get("source_chunk_index", 1),
            }
        ]
        return answer, evidence

    return "I don't have enough information in the uploaded file to answer this.", []
