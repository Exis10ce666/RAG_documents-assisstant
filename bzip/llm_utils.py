from __future__ import annotations

import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import requests


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:12b")

FALLBACK_ANSWER = "I don't have enough information in the uploaded file to answer this."

CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")


# ---------------------------------------------------------------------
# Basic text helpers
# ---------------------------------------------------------------------

def clean_text(text: str) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", str(text))
    text = text.replace("\xa0", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_for_match(text: str) -> str:
    text = clean_text(text).lower()
    text = text.replace("ё", "е")
    text = re.sub(r"[\u2018\u2019]", "'", text)
    text = re.sub(r"[\u201c\u201d]", '"', text)
    text = re.sub(r"[^0-9a-zа-яөүёүө\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_chunk_text(chunk: Dict[str, Any]) -> str:
    """
    Robustly read chunk text.

    Some routes pass chunks with chunk["text"]. Other older parsing code may keep
    text inside chunk["blocks"]. This function supports both so the LLM never
    receives empty context when the chunk actually has text.
    """
    if not isinstance(chunk, dict):
        return ""

    for key in ("text", "content", "chunk_text", "page_text"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return clean_text(value)

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
            return clean_text("\n\n".join(parts))

    return ""


# ---------------------------------------------------------------------
# Language helpers
# ---------------------------------------------------------------------

def is_mongolian_or_cyrillic(text: str) -> bool:
    if not text:
        return False

    cyrillic_count = len(CYRILLIC_RE.findall(text))
    alpha_count = sum(ch.isalpha() for ch in text)

    if alpha_count == 0:
        return False

    return cyrillic_count / alpha_count >= 0.25


def get_response_language(question: str) -> str:
    if is_mongolian_or_cyrillic(question):
        return "Mongolian"
    return "the same language as the user's question"


# ---------------------------------------------------------------------
# Direct extractive answer
# ---------------------------------------------------------------------

MONGOLIAN_STOPWORDS = {
    "юу", "вэ", "нь", "бол", "байна", "байдаг", "ямар", "гэж", "заасан",
    "зааж", "бэ", "уу", "үү", "аль", "хэн", "хаана", "хэзээ", "хэдэн",
    "тухай", "гэсэн", "болон", "ба", "эсвэл", "энэ", "тэр", "дээр", "доорх",
    "2024", "оны", "онд", "дугаар", "дүрэмд", "ийн", "ын", "ний", "нэрийг",
}

ENGLISH_STOPWORDS = {
    "the", "is", "are", "what", "who", "when", "where", "which", "of", "a", "an",
    "in", "on", "for", "to", "and", "or", "does", "do", "did", "was", "were",
}

IMPORTANT_PHRASES = [
    "хөгжлийн алсын хараа",
    "алсын хараа",
    "эрхэм зорилго",
    "үнэт зүйл",
    "унэт зүйл",
    "оноосон нэр",
    "англи нэр",
    "англи хэлээр",
    "товчилсон нэр",
    "цахим хуудасны нэр",
    "mongolian university of science and technology",
    "must",
    "зорилго",
    "зорилт",
    "тодорхойлолт",
    "байршил",
    "хугацаа",
    "огноо",
    "нэр",
]

DIRECT_MARKERS = [
    "юу вэ",
    "гэж юу вэ",
    "аль вэ",
    "хэдэн",
    "хэзээ",
    "хаана",
    "хэн",
    "нэр",
    "нэрийг",
    "товчилсон",
    "алсын хараа",
    "эрхэм зорилго",
    "үнэт зүйл",
    "зорилго",
    "зорилт",
    "тодорхойлолт",
    "заасан",
    "заадаг",
    "бич",
    "нэрлэ",
]


def is_direct_fact_question(question: str) -> bool:
    q = normalize_for_match(question)
    return any(marker in q for marker in DIRECT_MARKERS)


def tokenize_for_match(text: str) -> List[str]:
    normalized = normalize_for_match(text)
    tokens = re.findall(r"[0-9a-zа-яөүёүө\-]+", normalized)
    stopwords = MONGOLIAN_STOPWORDS | ENGLISH_STOPWORDS
    return [token for token in tokens if len(token) >= 2 and token not in stopwords]


def get_focus_phrases(question: str) -> List[str]:
    q = normalize_for_match(question)
    found: List[str] = []

    for phrase in IMPORTANT_PHRASES:
        phrase_norm = normalize_for_match(phrase)
        if phrase_norm and phrase_norm in q:
            found.append(phrase_norm)

    # Add meaningful tokens as backup.
    for token in tokenize_for_match(question):
        if token not in found:
            found.append(token)

    return found


def split_into_sentences(text: str) -> List[str]:
    text = clean_text(text)
    if not text:
        return []

    candidates: List[str] = []

    # PDF text is often line/block based. Preserve line boundaries first.
    for block in re.split(r"\n\s*\n|\n", text):
        block = clean_text(block)
        if not block:
            continue

        # Split long block by sentence punctuation, but do not destroy short definition lines.
        pieces = re.split(r"(?<=[.!?。！？])\s+", block)
        for piece in pieces:
            piece = clean_text(piece)
            if len(piece) >= 8:
                candidates.append(piece)

    return candidates


def score_sentence_for_question(question: str, sentence: str) -> float:
    q = normalize_for_match(question)
    s = normalize_for_match(sentence)

    if not q or not s:
        return 0.0

    score = 0.0
    focus_phrases = get_focus_phrases(question)

    for phrase in focus_phrases:
        if not phrase:
            continue
        if phrase in s:
            score += 5.0 if " " in phrase else 1.5

    q_tokens = set(tokenize_for_match(question))
    s_tokens = set(tokenize_for_match(sentence))
    overlap = q_tokens & s_tokens
    score += len(overlap) * 1.2

    # Definition lines often use colon/quotes.
    if ":" in sentence or "“" in sentence or "”" in sentence or '"' in sentence:
        score += 1.0

    # Strong exact cases.
    if "англи" in q and "товчил" in q:
        if "mongolian university of science and technology" in s:
            score += 10.0
        if "must" in s:
            score += 8.0
        if "товчил" in s:
            score += 4.0

    if "алсын хараа" in q and "алсын хараа" in s:
        score += 10.0

    if "эрхэм зорилго" in q and "эрхэм зорилго" in s:
        score += 10.0

    if "үнэт зүйл" in q and ("үнэт зүйл" in s or "унэт зүйл" in s):
        score += 10.0

    # Penalize nearby but wrong concepts.
    concept_terms = ["алсын хараа", "эрхэм зорилго", "үнэт зүйл", "зорилго"]
    asked_concepts = [term for term in concept_terms if term in q]
    for asked in asked_concepts:
        for other in concept_terms:
            if other != asked and other in s and asked not in s:
                score -= 6.0

    return score


def get_chunk_number(item: Dict[str, Any], default: int = 1) -> int:
    for key in ("chunk_rank", "rank"):
        value = item.get(key)
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return default


def quote_or_name(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match:
        return clean_text(match.group(0))
    return None


def extract_specific_answer_from_sentence(question: str, sentence: str, chunk_number: int) -> str:
    q = normalize_for_match(question)
    original = clean_text(sentence)

    # Case: English name + acronym of MUST.
    if "англи" in q and ("товчил" in q or "нэр" in q):
        english_name = quote_or_name(
            original,
            r"Mongolian\s+University\s+of\s+Science\s+and\s+Technology",
        )
        acronym_match = re.search(r"[“\"]?\bMUST\b[”\"]?", original)
        acronym = "MUST" if acronym_match else None

        if english_name and acronym:
            return (
                f"ШУТИС-ийн англи нэрийг “{english_name}”, "
                f"товчилсон нэрийг “{acronym}” гэж заасан. [Chunk {chunk_number}]"
            )

        if english_name:
            return f"ШУТИС-ийн англи нэрийг “{english_name}” гэж заасан. [Chunk {chunk_number}]"

    # Case: vision statement.
    if "алсын хараа" in q:
        quote_matches = re.findall(r"[“\"]([^”\"]{4,250})[”\"]", original)
        if quote_matches:
            # Usually the vision itself is the last quoted phrase in the sentence.
            vision = clean_text(quote_matches[-1])
            return f"ШУТИС-ийн хөгжлийн алсын хараа нь “{vision}” гэж заасан. [Chunk {chunk_number}]"

    # Generic direct fact: return the exact sentence found in the document.
    if len(original) > 500:
        original = original[:500].rstrip() + "..."
    return f"{original} [Chunk {chunk_number}]"


def build_direct_candidates(
    question: str,
    top_chunks: List[Dict[str, Any]],
    evidence_sentences: Optional[List[Dict[str, Any]]] = None,
) -> List[Tuple[float, str, int, str]]:
    candidates: List[Tuple[float, str, int, str]] = []

    # Evidence sentences from build_extractive_answer are already selected by retrieval.
    if evidence_sentences:
        for pos, evidence in enumerate(evidence_sentences, start=1):
            sentence = evidence.get("text") or evidence.get("sentence") or ""
            sentence = clean_text(sentence)
            if not sentence:
                continue
            chunk_number = get_chunk_number(evidence, default=pos)
            score = score_sentence_for_question(question, sentence)
            # Evidence already has retrieval support, so give it a small boost.
            score += 2.0
            candidates.append((score, sentence, chunk_number, "evidence"))

    for chunk_number, chunk in enumerate(top_chunks, start=1):
        text = get_chunk_text(chunk)
        if not text:
            continue
        for sentence in split_into_sentences(text):
            score = score_sentence_for_question(question, sentence)
            candidates.append((score, sentence, chunk_number, "chunk"))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates


def try_direct_extractive_answer(
    question: str,
    top_chunks: List[Dict[str, Any]],
    evidence_sentences: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """
    Return an exact answer before calling Ollama when the question is a direct fact.

    This solves the problem where retrieval finds the right sentence but the LLM rewrites
    it into a nearby wrong concept.
    """
    if not is_direct_fact_question(question):
        return None

    candidates = build_direct_candidates(question, top_chunks, evidence_sentences)
    if not candidates:
        return None

    best_score, best_sentence, best_chunk_number, _source = candidates[0]

    # Direct exact cases are allowed with a lower threshold because evidence already proved the hit.
    q = normalize_for_match(question)
    s = normalize_for_match(best_sentence)

    exact_english_name_hit = (
        "англи" in q
        and "товчил" in q
        and "mongolian university of science and technology" in s
        and "must" in s
    )
    exact_vision_hit = "алсын хараа" in q and "алсын хараа" in s
    exact_mission_hit = "эрхэм зорилго" in q and "эрхэм зорилго" in s
    exact_value_hit = "үнэт зүйл" in q and ("үнэт зүйл" in s or "унэт зүйл" in s)

    if not any([exact_english_name_hit, exact_vision_hit, exact_mission_hit, exact_value_hit]) and best_score < 5.0:
        return None

    return extract_specific_answer_from_sentence(question, best_sentence, best_chunk_number)


# ---------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------

def format_chunks_for_prompt(top_chunks: List[Dict[str, Any]]) -> str:
    formatted: List[str] = []

    for i, chunk in enumerate(top_chunks, start=1):
        filename = chunk.get("filename") or "Selected document"
        document_id = chunk.get("document_id") or "-"
        page = chunk.get("page", "-")
        source_chunk_index = chunk.get("source_chunk_index", i)
        text = get_chunk_text(chunk)

        if not text:
            text = "[EMPTY CHUNK TEXT - backend did not pass text correctly]"

        formatted.append(
            f"""
[Chunk {i}]
Source file: {filename}
Document ID: {document_id}
Original chunk: {source_chunk_index}
Page: {page}

{text}
""".strip()
        )

    return "\n\n".join(formatted)


def build_system_prompt(response_language: str) -> str:
    return f"""
You are a strict document QA assistant for a RAG system.

Answer the user's question using ONLY the provided context chunks.

Critical language rule:
- The final answer MUST be written in {response_language}.
- If the user asks in Mongolian/Cyrillic, answer in Mongolian.
- Do not answer a Mongolian question in English.

Evidence rules:
1. Use only the provided context chunks.
2. Do not use outside knowledge.
3. Do not invent, assume, or guess missing information.
4. If the answer is not clearly supported by the chunks, reply exactly:
   "{FALLBACK_ANSWER}"
5. Always cite supporting chunks using the format [Chunk 1], [Chunk 2].
6. If multiple chunks support the answer, cite all relevant chunks.
7. If chunks disagree, say the evidence conflicts and cite the conflicting chunks.

Strict specificity rules:
1. Answer the exact thing the user asked.
2. Do NOT replace one concept with a related concept.
3. If the user asks about "Алсын хараа", answer only the sentence about "Алсын хараа".
4. If the user asks about "англи нэр" or "товчилсон нэр", answer only those names.
5. Do NOT mix "Алсын хараа", "Эрхэм зорилго", "Зорилго", and "Үнэт зүйл" unless the user explicitly asks to compare or list them.
6. If an exact answer sentence exists in the context, quote or closely paraphrase that exact sentence.
7. Preserve names, dates, numbers, quoted phrases, and technical terms exactly.

Answer style:
1. Keep the answer short and direct.
2. Usually 1-2 sentences is enough.
3. Maximum 3-4 sentences unless the user specifically asks for a long explanation, list, comparison, or summary.
4. Do not write long summaries.
5. Do not use headings unless the user asks for a summary.
6. Do not use bullet points unless the user asks for a list.
7. Put chunk citation(s) at the end of the sentence they support.

Important:
- If the answer is visible in the context, answer it directly.
- If evidence is insufficient, output ONLY the fallback sentence.
""".strip()


def rewrite_answer_with_ollama(
    question: str,
    top_chunks: List[Dict[str, Any]],
    evidence_sentences: Optional[List[Dict[str, Any]]] = None,
) -> str:
    if not top_chunks:
        return FALLBACK_ANSWER

    # Safety layer: direct fact questions should not be rewritten by the LLM.
    direct_answer = try_direct_extractive_answer(question, top_chunks, evidence_sentences)
    if direct_answer:
        return direct_answer

    response_language = get_response_language(question)
    system_prompt = build_system_prompt(response_language)
    context_text = format_chunks_for_prompt(top_chunks)

    user_prompt = f"""
Question:
{question}

Context chunks:
{context_text}

Answer requirements:
- Answer in {response_language}.
- Use only the context chunks.
- Answer the exact requested concept, not a related concept.
- If the exact answer sentence is present, use that exact sentence.
- Keep it maximum 3-4 sentences.
- Cite chunks like [Chunk 1].
- Do not write a long summary.
- If the context does not clearly answer the question, output only:
  "{FALLBACK_ANSWER}"

Answer:
""".strip()

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "top_p": 0.7,
                "top_k": 20,
                "num_predict": 180,
                "num_ctx": 4096,
            },
        },
        timeout=180,
    )

    response.raise_for_status()
    data = response.json()
    answer = data.get("message", {}).get("content", "").strip()

    # Remove thinking tags if using a model that emits them.
    answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()

    if not answer:
        return FALLBACK_ANSWER

    return answer
