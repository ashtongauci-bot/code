"""
patch_vision.py — Run this once to fix the _extract_json function in vision_scheme.py
Usage:  python patch_vision.py
"""
import re
from pathlib import Path

target = Path("vision_scheme.py")
if not target.exists():
    print("ERROR: vision_scheme.py not found in current directory.")
    raise SystemExit(1)

content = target.read_text(encoding="utf-8")

# Find and replace the entire _extract_json function
old_pattern = re.compile(
    r"def _extract_json\(text: str\) -> dict:.*?(?=\ndef |\Z)",
    re.DOTALL,
)

new_function = '''def _extract_json(text: str) -> dict:
    """
    Extract a JSON object from the model response.
    Robust to prose before/after, markdown fences, and trailing commas.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(
            f"No JSON object found in Claude response.\\nRaw response:\\n{text[:2000]}"
        )
    json_str = text[start : end + 1]
    # Remove trailing commas before } or ] — strict JSON forbids them
    json_str = re.sub(r",\\s*([}\\]])", r"\\1", json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Claude response is not valid JSON.\\nExtracted:\\n{json_str[:2000]}"
        ) from exc

'''

if not old_pattern.search(content):
    print("ERROR: Could not locate _extract_json in vision_scheme.py.")
    print("The file may already be patched or have unexpected formatting.")
    raise SystemExit(1)

new_content = old_pattern.sub(new_function, content)
target.write_text(new_content, encoding="utf-8")
print("✓ vision_scheme.py patched successfully.")
print("  Run:  python -m py_compile vision_scheme.py  to verify.")
