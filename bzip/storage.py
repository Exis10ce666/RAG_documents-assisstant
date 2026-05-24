from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PARSED_DIR = DATA_DIR / "parsed"
UPLOAD_DIR = DATA_DIR / "uploads"
INDEX_DIR = DATA_DIR / "indexes"
QUERY_CACHE_DIR = DATA_DIR / "query_cache"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PARSED_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
INDEX_DIR.mkdir(parents=True, exist_ok=True)
QUERY_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def save_json(filename: str, data: Dict[str, Any]) -> None:
    path = PARSED_DIR / filename
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_json(filename: str) -> Dict[str, Any]:
    path = PARSED_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def list_parsed_documents() -> List[Dict[str, Any]]:
    documents: List[Dict[str, Any]] = []

    paths = sorted(
        PARSED_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pages = data.get("pages", [])
            chunks = data.get("chunks", [])

            extraction_methods = sorted(
                {
                    page.get("extraction_method", "text")
                    for page in pages
                    if isinstance(page, dict)
                }
            )

            documents.append(
                {
                    "document_id": data.get("document_id", path.stem),
                    "filename": data.get("original_filename", path.name),
                    "pages": len(pages),
                    "chunks": len(chunks),
                    "extraction_methods": extraction_methods,
                    "modified_at": path.stat().st_mtime,
                }
            )
        except Exception:
            continue

    return documents
