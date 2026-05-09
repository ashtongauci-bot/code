#!/usr/bin/env python3
"""
new_job.py

Paste a client email → Claude extracts the address → scans the Projects
folder for the highest job number → creates the next numbered job folder.

Usage:  python new_job.py

Folder naming convention: 260076 - 25 Hardy St, BONDI
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

PROJECTS_DIR = Path(
    r"C:\Users\AGauci\OneDrive - Integrity Inspecting Engineers\IIE\Projects"
)

# Matches "260076 - 25 Hardy St, BONDI"
FOLDER_RE = re.compile(r"^(\d{6}) - (.+)$")

EXTRACT_PROMPT = """\
Extract the subject property address from this client email.

Return ONLY a JSON object with no markdown:
{
  "address": "25 Hardy St, BONDI"
}

Rules:
- Format: street number + street name + comma + suburb in UPPERCASE
- Examples: "242 Sailors Bay Rd, NORTHBRIDGE" / "14 Cook Ave, CRONULLA"
- If no address is found, use null

Email:
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_api_key() -> str:
    """Try to read ANTHROPIC_API_KEY from the dilapidation tool config."""
    config_path = Path(__file__).parent / "dilapidation_tool" / "config.py"
    if config_path.exists():
        try:
            spec = importlib.util.spec_from_file_location("_cfg", config_path)
            cfg = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cfg)
            key = getattr(cfg, "ANTHROPIC_API_KEY", "")
            if key:
                return key
        except Exception:
            pass
    return ""


def _get_email() -> str:
    print("=" * 60)
    print("NEW JOB FOLDER CREATOR")
    print("=" * 60)
    print()
    print("Paste the client email below.")
    print("When done, type  ---END---  on its own line and press Enter.")
    print()
    lines = []
    while True:
        line = input()
        if line.strip() == "---END---":
            break
        lines.append(line)
    return "\n".join(lines)


def _extract_address(email_text: str) -> str | None:
    try:
        import anthropic
    except ImportError:
        print("  anthropic package not installed — skipping AI extraction")
        return None

    api_key = _load_api_key() or input("  Anthropic API key: ").strip()
    if not api_key:
        return None

    print("\nExtracting address with Claude...")
    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=30.0)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": EXTRACT_PROMPT + email_text
                           + "\n\nRespond with ONLY the JSON object.",
            }],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw).get("address")
    except Exception as e:
        print(f"  Claude extraction failed: {e}")
        return None


def _next_job_number() -> int:
    """Scan Projects folder and return max job number + 1."""
    if not PROJECTS_DIR.exists():
        return 260001  # fallback starting point

    numbers = [
        int(m.group(1))
        for f in PROJECTS_DIR.iterdir()
        if f.is_dir() and (m := FOLDER_RE.match(f.name))
    ]
    return max(numbers) + 1 if numbers else 260001


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not PROJECTS_DIR.exists():
        print(f"Warning: Projects directory not found:\n  {PROJECTS_DIR}\n")

    email_text = _get_email()
    if not email_text.strip():
        print("No email provided. Exiting.")
        return

    # Extract address
    address = _extract_address(email_text)
    if not address:
        print()
        address = input("  Enter address manually (e.g. 25 Hardy St, BONDI): ").strip()
    if not address:
        print("No address provided. Exiting.")
        return

    job_number = _next_job_number()
    folder_name = f"{job_number} - {address}"

    print()
    print("─" * 60)
    print(f"  Job number : {job_number}")
    print(f"  Address    : {address}")
    print(f"  Folder     : {folder_name}")
    print("─" * 60)
    print()

    confirm = input("Create folder? Press Enter to confirm, or 'n' to cancel: ").strip()
    if confirm.lower() == "n":
        print("Cancelled.")
        return

    folder_path = PROJECTS_DIR / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)
    print(f"\nCreated:\n  {folder_path}")


if __name__ == "__main__":
    main()
