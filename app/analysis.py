"""Local fallback transcript analysis and timestamp alignment."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any


STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "you", "are", "was", "were", "have", "has",
    "not", "but", "they", "their", "there", "about", "into", "your", "will", "would", "can", "could",
    "我們", "你們", "他們", "以及", "因為", "所以", "這個", "那個", "就是", "如果", "可以", "沒有",
    "一個", "自己", "大家", "可能", "其實", "然後", "但是", "或者", "非常", "比較", "是不是",
}


def split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[。！？!?\.])\s+|[\r\n]+", text or "")
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def estimate_chunks(text: str, duration_ms: int) -> list[dict[str, Any]]:
    sentences = split_sentences(text)
    if not sentences:
        return []
    total_chars = sum(max(1, len(sentence)) for sentence in sentences)
    cursor = 0
    chunks: list[dict[str, Any]] = []
    safe_duration = max(duration_ms, len(sentences) * 2000)
    for sentence in sentences:
        ratio = max(1, len(sentence)) / total_chars
        length_ms = max(1200, int(safe_duration * ratio))
        chunks.append({"start_ms": cursor, "end_ms": cursor + length_ms, "text": sentence})
        cursor += length_ms
    return chunks


def flatten_transcript(chunks: list[dict[str, Any]]) -> str:
    return "\n".join(str(chunk.get("text", "")).strip() for chunk in chunks if str(chunk.get("text", "")).strip())


def _candidate_terms(text: str) -> list[str]:
    english_terms = re.findall(r"[A-Za-z][A-Za-z0-9'_-]{2,}", text)
    cjk_terms = re.findall(r"[\u4e00-\u9fff]{2,6}", text)
    terms = [term.strip().lower() for term in english_terms] + [term.strip() for term in cjk_terms]
    return [term for term in terms if term and term not in STOPWORDS]


def find_timestamps(term: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    normalized_term = term.lower()
    for chunk in chunks:
        text = str(chunk.get("text", ""))
        if normalized_term in text.lower():
            matches.append({
                "start_ms": int(chunk.get("start_ms", 0) or 0),
                "end_ms": int(chunk.get("end_ms", 0) or 0),
                "context": text,
            })
    return matches


def local_keyword_analysis(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    transcript_text = flatten_transcript(chunks)
    counter = Counter(_candidate_terms(transcript_text))
    common_terms = counter.most_common(16)
    max_count = common_terms[0][1] if common_terms else 1
    keywords = []
    for term, count in common_terms:
        keywords.append({
            "term": term,
            "category": "其他",
            "score": round(count / max_count, 3),
            "reason": "此詞在逐字稿中出現頻率較高。",
            "occurrences": count,
            "timestamps": find_timestamps(term, chunks),
        })
    sorted_chunks = sorted(chunks, key=lambda chunk: len(str(chunk.get("text", ""))), reverse=True)
    highlights = []
    for chunk in sorted_chunks[:8]:
        highlights.append({
            "text": str(chunk.get("text", "")),
            "start_ms": int(chunk.get("start_ms", 0) or 0),
            "end_ms": int(chunk.get("end_ms", 0) or 0),
            "reason": "此片段資訊量較高，適合作為複習重點。",
        })
    summary_source = transcript_text.replace("\n", " ")[:180]
    return {
        "summary": summary_source + ("..." if len(transcript_text) > 180 else ""),
        "keywords": keywords,
        "highlights": sorted(highlights, key=lambda item: item["start_ms"]),
        "actions": [],
        "source": "local_fallback",
    }


def align_model_analysis(model_result: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = local_keyword_analysis(chunks)
    result = {
        "summary": str(model_result.get("summary") or fallback.get("summary") or ""),
        "keywords": [],
        "highlights": [],
        "actions": model_result.get("actions") if isinstance(model_result.get("actions"), list) else [],
        "source": "llm",
    }
    raw_keywords = model_result.get("keywords", [])
    if isinstance(raw_keywords, list):
        for raw_item in raw_keywords:
            if not isinstance(raw_item, dict):
                continue
            term = str(raw_item.get("term", "")).strip()
            if not term:
                continue
            timestamps = find_timestamps(term, chunks)
            result["keywords"].append({
                "term": term,
                "category": str(raw_item.get("category", "其他") or "其他"),
                "score": float(raw_item.get("score", 0.5) or 0.5),
                "reason": str(raw_item.get("reason", "") or ""),
                "occurrences": len(timestamps),
                "timestamps": timestamps,
            })
    raw_highlights = model_result.get("highlights", [])
    if isinstance(raw_highlights, list):
        for raw_item in raw_highlights:
            if not isinstance(raw_item, dict):
                continue
            text = str(raw_item.get("text", "")).strip()
            if not text:
                continue
            timestamp = find_best_chunk(text, chunks)
            result["highlights"].append({
                "text": text,
                "start_ms": timestamp.get("start_ms", 0),
                "end_ms": timestamp.get("end_ms", 0),
                "reason": str(raw_item.get("reason", "") or ""),
            })
    if not result["keywords"]:
        result["keywords"] = fallback["keywords"]
    if not result["highlights"]:
        result["highlights"] = fallback["highlights"]
    return result


def find_best_chunk(text: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    needle_terms = set(_candidate_terms(text))
    best_chunk = chunks[0] if chunks else {"start_ms": 0, "end_ms": 0, "text": ""}
    best_score = -1
    for chunk in chunks:
        chunk_terms = set(_candidate_terms(str(chunk.get("text", ""))))
        score = len(needle_terms & chunk_terms)
        if score > best_score:
            best_score = score
            best_chunk = chunk
    return best_chunk