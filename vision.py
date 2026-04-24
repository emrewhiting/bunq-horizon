"""Vision: image → {item, category, confidence}"""
import base64
import json
import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()
client = Anthropic()

VISION_PROMPT = """Look at this image and identify the main item being shown.

Return ONLY valid JSON, no prose, no markdown fences:
{
  "item": "specific name if recognizable, otherwise generic (e.g. 'Carhartt WIP Detroit jacket' or 'denim jacket')",
  "category": "ONE of: clothing, electronics, food_dining, groceries, transport, entertainment, beauty, home, other",
  "confidence": "high|medium|low",
  "brief_description": "5-10 word neutral description"
}

If no clear item is visible, return:
{"error": "no_item_detected"}
"""


def analyze_image(image_bytes: bytes) -> dict:
    """Returns {item, category, confidence, brief_description} or {error}."""
    b64 = base64.standard_b64encode(image_bytes).decode()

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": b64,
                    },
                },
                {"type": "text", "text": VISION_PROMPT},
            ],
        }],
    )

    text = resp.content[0].text.strip()

    # Strip markdown fences if Claude added them despite instructions
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip("`\n ")

    return json.loads(text)


# Test it standalone
if __name__ == "__main__":
    import sys
    image_path = sys.argv[1] if len(sys.argv) > 1 else "test_jacket.jpg"
    with open(image_path, "rb") as f:
        result = analyze_image(f.read())
    print(json.dumps(result, indent=2))