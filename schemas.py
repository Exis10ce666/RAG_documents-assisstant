from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str
    document_id: Optional[str] = None
    search_scope: str = "selected"  # "selected" or "all"
    use_llm: bool = True  # False = much faster extractive answer only


class AskResponse(BaseModel):
    answer: str
    best_chunk: str
    page: int
    score: float
    top_chunks: List[Dict[str, Any]]
    evidence_sentences: List[Dict[str, Any]]

    document_id: Optional[str] = None
    filename: Optional[str] = None
    search_scope: str = "selected"

    answer_mode: str = "llm"  # "llm", "extractive", "extractive_direct", or "extractive_fallback"
    cache_hit: bool = False
    timings: Dict[str, Any] = Field(default_factory=dict)
