from __future__ import annotations

from typing import Any, Dict, List


def page_to_blocks(page: Dict[str, Any]) -> List[str]:
    blocks = page.get("blocks")
    if isinstance(blocks, list):
        return [str(block).strip() for block in blocks if str(block).strip()]

    text = page.get("text")
    if isinstance(text, str) and text.strip():
        return [text.strip()]

    return []


def chunk_pages(
    pages: List[Dict[str, Any]],
    target_size: int = 1200,
    overlap_blocks: int = 1,
) -> List[Dict[str, Any]]:
    """
    Convert page blocks into chunks.

    target_size is character-based. overlap_blocks keeps the last N blocks from the
    previous chunk so retrieval has some context continuity.
    """
    chunks: List[Dict[str, Any]] = []
    global_chunk_index = 0

    for page in pages:
        page_no = int(page.get("page", 0))
        blocks = page_to_blocks(page)
        if not blocks:
            continue

        buffer: List[str] = []
        buffer_len = 0
        local_chunk_index = 0

        def flush_buffer() -> None:
            nonlocal buffer, buffer_len, global_chunk_index, local_chunk_index
            if not buffer:
                return

            text = "\n\n".join(buffer).strip()
            if not text:
                return

            global_chunk_index += 1
            local_chunk_index += 1

            chunks.append(
                {
                    "chunk_index": global_chunk_index,
                    "page_chunk_index": local_chunk_index,
                    "page": page_no,
                    "text": text,
                    "blocks": list(buffer),
                }
            )

            if overlap_blocks > 0:
                buffer = buffer[-overlap_blocks:]
                buffer_len = sum(len(item) for item in buffer)
            else:
                buffer = []
                buffer_len = 0

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # If one block is very large, split by characters so it still becomes searchable.
            if len(block) > target_size * 1.5:
                flush_buffer()
                start = 0
                while start < len(block):
                    part = block[start : start + target_size].strip()
                    start += target_size
                    if part:
                        global_chunk_index += 1
                        local_chunk_index += 1
                        chunks.append(
                            {
                                "chunk_index": global_chunk_index,
                                "page_chunk_index": local_chunk_index,
                                "page": page_no,
                                "text": part,
                                "blocks": [part],
                            }
                        )
                buffer = []
                buffer_len = 0
                continue

            projected_len = buffer_len + len(block) + 2
            if buffer and projected_len > target_size:
                flush_buffer()

            buffer.append(block)
            buffer_len += len(block) + 2

        flush_buffer()

    return chunks
