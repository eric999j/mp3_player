"""Prompt templates for transcript analysis."""
from __future__ import annotations


ANALYSIS_SYSTEM_PROMPT = (
    "你是音訊內容分析助理。你會根據逐字稿擷取重點字詞、重點句與摘要。"
    "所有說明欄位都使用繁體中文。只回傳有效 JSON，不要 markdown。"
)


def build_analysis_prompt(transcript_text: str) -> str:
    return f"""
請分析以下逐字稿，回傳 JSON 物件，schema 必須完全符合：
{{
  "summary": "繁體中文短摘要，80 到 160 字",
  "keywords": [
    {{
      "term": "關鍵詞",
      "category": "主題/人物/專有名詞/技術詞/行動項目/其他",
      "score": 0.0,
      "reason": "為什麼重要，繁體中文"
    }}
  ],
  "highlights": [
    {{
      "text": "重要句子或片段",
      "reason": "重要原因，繁體中文"
    }}
  ],
  "actions": ["可行動事項，若沒有則空陣列"]
}}

規則：
1. keywords 請給 8 到 20 個。
2. highlights 請給 5 到 12 句。
3. score 介於 0 到 1，越重要越高。
4. 不要杜撰逐字稿不存在的內容。
5. 只輸出 JSON。

逐字稿：
{transcript_text[:16000]}
""".strip()