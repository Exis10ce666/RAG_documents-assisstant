from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .chunker import chunk_pages
from .embedding_retrieval import (
    build_extractive_answer,
    build_hybrid_index,
    build_index_signature,
    hybrid_search_top_k_chunks,
    load_hybrid_index_cache,
    save_hybrid_index_cache,
)
from .llm_utils import rewrite_answer_with_ollama, try_direct_extractive_answer
from .pdf_utils import extract_pdf_pages
from .schemas import AskRequest, AskResponse
from .storage import INDEX_DIR, QUERY_CACHE_DIR, UPLOAD_DIR, list_parsed_documents, load_json, save_json


app = FastAPI(title="RAG Document Assistant - Hybrid Retrieval")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


INDEX_STORE: Dict[str, Any] = {}
SEARCH_RESULT_CACHE: Dict[str, Dict[str, Any]] = {}
ALL_DOCUMENTS_INDEX_KEY = "__all_documents__"
CACHE_VERSION = "direct-answer-fix-v3"


def now() -> float:
    return time.perf_counter()


def elapsed(start: float) -> float:
    return round(time.perf_counter() - start, 4)


def response_to_dict(response: AskResponse) -> Dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    return response.dict()


def normalize_question(question: str) -> str:
    return " ".join(question.lower().strip().split())


def make_search_cache_key(
    *,
    search_scope: str,
    document_id: Optional[str],
    signature: str,
    question: str,
    top_k: int,
    dense_weight: float,
    sparse_weight: float,
    use_llm: bool,
) -> str:
    payload = {
        "cache_version": CACHE_VERSION,
        "search_scope": search_scope,
        "document_id": document_id,
        "signature": signature,
        "question": normalize_question(question),
        "top_k": top_k,
        "dense_weight": dense_weight,
        "sparse_weight": sparse_weight,
        "use_llm": use_llm,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def query_cache_path(cache_key: str):
    return QUERY_CACHE_DIR / f"{cache_key}.json"


def get_cached_answer(cache_key: str) -> Optional[AskResponse]:
    cached = SEARCH_RESULT_CACHE.get(cache_key)
    if cached:
        cached = dict(cached)
        cached["cache_hit"] = True
        cached.setdefault("timings", {})["cache_seconds"] = 0.0
        return AskResponse(**cached)

    path = query_cache_path(cache_key)
    if not path.exists():
        return None

    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        cached["cache_hit"] = True
        cached.setdefault("timings", {})["cache_seconds"] = 0.0
        SEARCH_RESULT_CACHE[cache_key] = cached
        return AskResponse(**cached)
    except Exception:
        return None


def save_cached_answer(cache_key: str, response: AskResponse) -> None:
    data = response_to_dict(response)
    data["cache_hit"] = False
    SEARCH_RESULT_CACHE[cache_key] = data

    try:
        query_cache_path(cache_key).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # Cache failure must never break the actual answer.
        pass


def build_or_get_index(document_id: str, chunks: list[dict[str, Any]]) -> Dict[str, Any]:
    """
    Build/load selected-document index.
    Priority:
    1. RAM cache for current backend run
    2. Disk cache from data/indexes
    3. Rebuild embeddings + FAISS + TF-IDF only if cache is missing/stale
    """
    signature = build_index_signature(chunks)
    cached = INDEX_STORE.get(document_id)

    if cached and cached.get("signature") == signature:
        return cached["index_bundle"]

    index_bundle = load_hybrid_index_cache(document_id, signature)

    if index_bundle is None:
        index_bundle = build_hybrid_index(chunks)
        save_hybrid_index_cache(document_id, signature, index_bundle)

    INDEX_STORE[document_id] = {
        "signature": signature,
        "index_bundle": index_bundle,
    }
    return index_bundle


def load_document_data(document_id: str) -> Dict[str, Any]:
    try:
        return load_json(f"{document_id}.json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc


def enrich_chunks(
    chunks: list[dict[str, Any]],
    document_id: str,
    filename: str | None,
) -> list[dict[str, Any]]:
    enriched_chunks: list[dict[str, Any]] = []
    safe_filename = filename or "Unknown PDF"

    for idx, chunk in enumerate(chunks, start=1):
        enriched_chunk = dict(chunk)
        enriched_chunk["document_id"] = document_id
        enriched_chunk["filename"] = safe_filename
        enriched_chunk["source_chunk_index"] = enriched_chunk.get("source_chunk_index", idx)
        enriched_chunks.append(enriched_chunk)

    return enriched_chunks


def load_all_document_chunks() -> tuple[list[dict[str, Any]], str]:
    documents = list_parsed_documents()

    all_chunks: list[dict[str, Any]] = []

    for meta in documents:
        document_id = meta.get("document_id")
        if not document_id:
            continue

        try:
            doc_data = load_json(f"{document_id}.json")
        except Exception:
            continue

        filename = doc_data.get("original_filename", meta.get("filename", "Unknown PDF"))
        chunks = doc_data.get("chunks", [])
        all_chunks.extend(enrich_chunks(chunks=chunks, document_id=document_id, filename=filename))

    signature = build_index_signature(all_chunks)
    return all_chunks, signature


def build_or_get_all_documents_index(
    chunks: list[dict[str, Any]],
    signature: str,
) -> Dict[str, Any]:
    cached = INDEX_STORE.get(ALL_DOCUMENTS_INDEX_KEY)

    if cached and cached.get("signature") == signature:
        return cached["index_bundle"]

    index_bundle = load_hybrid_index_cache(ALL_DOCUMENTS_INDEX_KEY, signature)

    if index_bundle is None:
        index_bundle = build_hybrid_index(chunks)
        save_hybrid_index_cache(ALL_DOCUMENTS_INDEX_KEY, signature, index_bundle)

    INDEX_STORE[ALL_DOCUMENTS_INDEX_KEY] = {
        "signature": signature,
        "index_bundle": index_bundle,
    }

    return index_bundle


def answer_from_top_chunks(
    *,
    question: str,
    top_chunks: list[dict[str, Any]],
    document_id: Optional[str],
    filename: Optional[str],
    search_scope: str,
    use_llm: bool,
    timings: Dict[str, Any],
) -> AskResponse:
    if not top_chunks:
        raise HTTPException(status_code=404, detail="Холбогдох хэсэг олдсонгүй.")

    t_extract = now()
    extractive_answer, evidence = build_extractive_answer(
        question,
        top_chunks,
        top_n_sentences=3,
    )
    timings["extractive_answer_seconds"] = elapsed(t_extract)

    answer = extractive_answer
    answer_mode = "extractive"

    # First, protect direct factual questions.
    # If the exact sentence is already found, do not let the LLM rewrite it into a nearby wrong concept.
    direct_answer = try_direct_extractive_answer(
        question=question,
        top_chunks=top_chunks,
        evidence_sentences=evidence,
    )

    if direct_answer:
        answer = direct_answer
        answer_mode = "extractive_direct"
        timings["direct_answer_used"] = True
    elif use_llm:
        t_llm = now()
        try:
            print("Calling Ollama for final answer...")
            answer = rewrite_answer_with_ollama(
                question=question,
                top_chunks=top_chunks,
                evidence_sentences=evidence,
            )
            answer_mode = "llm"
            timings["llm_used"] = True
        except Exception as exc:
            # Do not silently hide this. Return extractive fallback and expose the reason.
            print(f"Ollama failed; using extractive fallback: {exc}")
            answer = extractive_answer
            answer_mode = "extractive_fallback"
            timings["llm_used"] = False
            timings["llm_error"] = str(exc)[:500]
        timings["llm_seconds"] = elapsed(t_llm)
    else:
        timings["llm_used"] = False

    best = top_chunks[0]

    return AskResponse(
        answer=answer,
        best_chunk=best.get("text", ""),
        page=int(best.get("page", 0)),
        score=float(best.get("score", 0.0)),
        top_chunks=top_chunks,
        evidence_sentences=evidence,
        document_id=document_id or best.get("document_id"),
        filename=filename or best.get("filename"),
        search_scope=search_scope,
        answer_mode=answer_mode,
        cache_hit=False,
        timings=timings,
    )


@app.get("/")
def health_check():
    return {"message": "Backend is running"}


@app.get("/documents")
def list_documents():
    return {"documents": list_parsed_documents()}




@app.post("/cache/clear")
def clear_cache(clear_query_cache: bool = True, clear_index_cache: bool = False):
    """Clear backend caches while debugging answer quality."""
    removed_files = 0

    SEARCH_RESULT_CACHE.clear()

    if clear_query_cache:
        for path in QUERY_CACHE_DIR.glob("*.json"):
            try:
                path.unlink()
                removed_files += 1
            except Exception:
                pass

    if clear_index_cache:
        INDEX_STORE.clear()
        for pattern in ("*.faiss", "*.pkl"):
            for path in INDEX_DIR.glob(pattern):
                try:
                    path.unlink()
                    removed_files += 1
                except Exception:
                    pass

    return {
        "message": "Cache cleared.",
        "clear_query_cache": clear_query_cache,
        "clear_index_cache": clear_index_cache,
        "removed_files": removed_files,
    }


@app.post("/documents/{document_id}/load")
def load_existing_document(document_id: str):
    doc_data = load_document_data(document_id)
    chunks = doc_data.get("chunks", [])

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="This document has no chunks. Upload/parse it again.",
        )

    filename = doc_data.get("original_filename")
    enriched_chunks = enrich_chunks(chunks, document_id, filename)
    signature = build_index_signature(enriched_chunks)

    t_index = now()
    index_bundle = build_or_get_index(document_id, enriched_chunks)

    return {
        "document_id": document_id,
        "filename": filename or f"{document_id}.pdf",
        "pages": len(doc_data.get("pages", [])),
        "chunks": len(enriched_chunks),
        "index_signature": signature[:16],
        "index_seconds": elapsed(t_index),
        "message": "Existing document loaded and hybrid index is ready.",
        "cached_in_memory": bool(index_bundle),
    }


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), force_ocr: bool = False):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Одоогоор зөвхөн PDF файл дэмжинэ.",
        )

    document_id = str(uuid.uuid4())
    saved_path = UPLOAD_DIR / f"{document_id}.pdf"

    with saved_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    pages = extract_pdf_pages(saved_path, force_ocr=force_ocr)

    if not pages:
        raise HTTPException(
            status_code=400,
            detail="PDF-ээс текст уншиж чадсангүй. Сканнердсан PDF байж магадгүй.",
        )

    chunks = chunk_pages(pages, target_size=1200, overlap_blocks=1)

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="Ашиглах боломжтой chunk үүссэнгүй.",
        )

    enriched_chunks = enrich_chunks(chunks, document_id, file.filename)
    signature = build_index_signature(enriched_chunks)

    index_bundle = build_hybrid_index(enriched_chunks)
    save_hybrid_index_cache(document_id, signature, index_bundle)
    INDEX_STORE[document_id] = {
        "signature": signature,
        "index_bundle": index_bundle,
    }
    INDEX_STORE.pop(ALL_DOCUMENTS_INDEX_KEY, None)

    save_json(
        f"{document_id}.json",
        {
            "document_id": document_id,
            "original_filename": file.filename,
            "pages": pages,
            "chunks": enriched_chunks,
        },
    )

    return {
        "document_id": document_id,
        "filename": file.filename,
        "pages": len(pages),
        "chunks": len(enriched_chunks),
        "extraction_methods": sorted({p.get("extraction_method", "text") for p in pages}),
        "message": "PDF parsed, chunked, and hybrid index built successfully.",
    }


@app.post("/ask", response_model=AskResponse)
def ask_question(payload: AskRequest):
    request_started = now()
    search_scope = payload.search_scope.lower().strip()
    dense_weight = 0.4
    sparse_weight = 0.6

    if search_scope not in {"selected", "all"}:
        raise HTTPException(
            status_code=400,
            detail="search_scope must be either 'selected' or 'all'.",
        )

    if search_scope == "all":
        t_load = now()
        chunks, signature = load_all_document_chunks()
        timings = {"load_chunks_seconds": elapsed(t_load)}

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No parsed documents found. Upload at least one PDF first.",
            )

        top_k = 8
        cache_key = make_search_cache_key(
            search_scope="all",
            document_id=None,
            signature=signature,
            question=payload.question,
            top_k=top_k,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
            use_llm=payload.use_llm,
        )
        cached = get_cached_answer(cache_key)
        if cached:
            cached.timings["total_seconds"] = elapsed(request_started)
            return cached

        t_index = now()
        index_bundle = build_or_get_all_documents_index(chunks, signature)
        timings["index_ready_seconds"] = elapsed(t_index)

        t_search = now()
        top_chunks = hybrid_search_top_k_chunks(
            chunks,
            index_bundle,
            payload.question,
            top_k=top_k,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
        )
        timings["search_seconds"] = elapsed(t_search)

        response = answer_from_top_chunks(
            question=payload.question,
            top_chunks=top_chunks,
            document_id=None,
            filename=None,
            search_scope="all",
            use_llm=payload.use_llm,
            timings=timings,
        )
        response.timings["total_seconds"] = elapsed(request_started)
        save_cached_answer(cache_key, response)
        return response

    if not payload.document_id:
        raise HTTPException(
            status_code=400,
            detail="document_id is required when search_scope is 'selected'.",
        )

    t_load = now()
    doc_data = load_document_data(payload.document_id)
    chunks = doc_data.get("chunks", [])
    filename = doc_data.get("original_filename")
    enriched_chunks = enrich_chunks(chunks, payload.document_id, filename)
    signature = build_index_signature(enriched_chunks)
    timings = {"load_chunks_seconds": elapsed(t_load)}

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="This document has no chunks. Upload/parse it again.",
        )

    top_k = 5
    cache_key = make_search_cache_key(
        search_scope="selected",
        document_id=payload.document_id,
        signature=signature,
        question=payload.question,
        top_k=top_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
        use_llm=payload.use_llm,
    )
    cached = get_cached_answer(cache_key)
    if cached:
        cached.timings["total_seconds"] = elapsed(request_started)
        return cached

    t_index = now()
    index_bundle = build_or_get_index(payload.document_id, enriched_chunks)
    timings["index_ready_seconds"] = elapsed(t_index)

    t_search = now()
    top_chunks = hybrid_search_top_k_chunks(
        enriched_chunks,
        index_bundle,
        payload.question,
        top_k=top_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )
    timings["search_seconds"] = elapsed(t_search)

    response = answer_from_top_chunks(
        question=payload.question,
        top_chunks=top_chunks,
        document_id=payload.document_id,
        filename=filename,
        search_scope="selected",
        use_llm=payload.use_llm,
        timings=timings,
    )
    response.timings["total_seconds"] = elapsed(request_started)
    save_cached_answer(cache_key, response)
    return response


@app.post("/debug/search")
def debug_search(payload: AskRequest):
    search_scope = payload.search_scope.lower().strip()

    if search_scope == "all":
        chunks, signature = load_all_document_chunks()

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No parsed documents found. Upload at least one PDF first.",
            )

        index_bundle = build_or_get_all_documents_index(chunks, signature)
        top_chunks = hybrid_search_top_k_chunks(
            chunks,
            index_bundle,
            payload.question,
            top_k=8,
            dense_weight=0.4,
            sparse_weight=0.6,
        )

        return {
            "question": payload.question,
            "search_scope": "all",
            "top_k": 8,
            "top_chunks": top_chunks,
        }

    if not payload.document_id:
        raise HTTPException(
            status_code=400,
            detail="document_id is required when search_scope is 'selected'.",
        )

    doc_data = load_document_data(payload.document_id)
    chunks = doc_data.get("chunks", [])

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="This document has no chunks. Upload/parse it again.",
        )

    filename = doc_data.get("original_filename")
    enriched_chunks = enrich_chunks(chunks, payload.document_id, filename)
    index_bundle = build_or_get_index(payload.document_id, enriched_chunks)

    top_chunks = hybrid_search_top_k_chunks(
        enriched_chunks,
        index_bundle,
        payload.question,
        top_k=5,
        dense_weight=0.4,
        sparse_weight=0.6,
    )

    return {
        "question": payload.question,
        "search_scope": "selected",
        "top_k": 5,
        "document_id": payload.document_id,
        "filename": filename,
        "top_chunks": top_chunks,
    }
