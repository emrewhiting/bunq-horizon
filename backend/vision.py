# image -> {item, category, confidence}. one call, one job.

from __future__ import annotations

import base64
import json
import os

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# keep in sync with carbon_factors_kg_per_eur in bunq_data.json
CATEGORIES = [
    "clothing", "electronics", "food_dining", "groceries",
    "transport", "entertainment", "beauty", "home", "other",
]

PROMPT = (
    "Look at this image and identify the main purchasable item.\n\n"
    "Return ONLY valid JSON, no prose, no fences:\n"
    "{\n"
    '  "item": "specific name if recognisable, else generic e.g. \\"denim jacket\\" or '
    '\\"Carhartt WIP Detroit jacket\\"",\n'
    f'  "category": "ONE of: {", ".join(CATEGORIES)}",\n'
    '  "confidence": "high|medium|low",\n'
    '  "brief_description": "5-10 word neutral description"\n'
    "}\n\n"
    'If no clear item, return: {"error": "no_item_detected"}'
)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip("`\n ")


def _keyword_fallback(filename: str | None) -> dict:
    # used when there's no anthropic key. tags itself as source=fallback
    # so the UI can show that vision didn't actually run
    name = (filename or "").lower()
    pairs = [
        ("jacket",  "clothing"), ("coat",    "clothing"),
        ("shoe",    "clothing"), ("sneaker", "clothing"),
        ("burger",  "food_dining"), ("pizza",  "food_dining"),
        ("coffee",  "food_dining"), ("latte",  "food_dining"),
        ("phone",   "electronics"), ("laptop", "electronics"),
        ("book",    "entertainment"), ("ticket", "entertainment"),
    ]
    for kw, cat in pairs:
        if kw in name:
            return {
                "item": kw,
                "category": cat,
                "confidence": "low",
                "brief_description": f"identified by filename ({kw})",
                "source": "fallback",
            }
    return {
        "item": (name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ") or "item"),
        "category": "other",
        "confidence": "low",
        "brief_description": "could not identify",
        "source": "fallback",
    }


def analyze_image(image_bytes: bytes, mime: str = "image/jpeg",
                  filename: str | None = None) -> dict:
    # returns {item, category, confidence, brief_description, source}
    # without an api key it falls back to filename-keyword matching
    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        return _keyword_fallback(filename)

    try:
        from anthropic import Anthropic
    except ImportError:
        return _keyword_fallback(filename)

    try:
        client = Anthropic()
        b64 = base64.standard_b64encode(image_bytes).decode()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": mime, "data": b64}},
                    {"type": "text", "text": PROMPT},
                ],
            }],
        )
        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text = block.text
                break
        result = json.loads(_strip_fences(text))
        if "error" in result:
            return _keyword_fallback(filename)
        if result.get("category") not in CATEGORIES:
            result["category"] = "other"
        result["source"] = "claude"
        return result
    except Exception as e:
        print(f"[vision] {e}")
        return _keyword_fallback(filename)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "test.jpg"
    with open(path, "rb") as f:
        print(json.dumps(analyze_image(f.read(), filename=path), indent=2))
