#!/usr/bin/env python3
"""
job_watcher.py

Monitors your Outlook inbox and automatically creates job folders in
the Projects directory when a relevant inspection/dilapidation email arrives.

First-time setup
────────────────
1. Run:  python job_watcher.py --setup
   (saves your email credentials to watcher_credentials.json)

2. Then run:  python job_watcher.py
   Leave it running — it checks every 5 minutes.

Microsoft 365 / MFA note
─────────────────────────
If your account has two-factor authentication (most work accounts do):
  • Go to: https://account.microsoft.com/security
  • Click "Advanced security options" → "App passwords"
  • Create a new app password and use THAT instead of your normal password.
"""

import argparse
import imaplib
import email
import json
import logging
import re
import time
import importlib.util
from email.header import decode_header as _decode_header
from pathlib import Path
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECTS_DIR   = Path(r"C:\Users\AGauci\OneDrive - Integrity Inspecting Engineers\IIE\Projects")
CREDS_FILE     = Path(__file__).parent / "watcher_credentials.json"
SEEN_FILE      = Path(__file__).parent / "watcher_seen.json"
LOG_FILE       = Path(__file__).parent / "watcher.log"

IMAP_SERVER    = "outlook.office365.com"
IMAP_PORT      = 993
POLL_INTERVAL  = 300   # seconds (5 minutes)

FOLDER_RE      = re.compile(r"^(\d{6}) - (.+)$")

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── Claude prompts ────────────────────────────────────────────────────────────

CLASSIFY_PROMPT = """\
You are reviewing an email to decide if it is requesting a new engineering
inspection or dilapidation report for a property in Australia.

Return ONLY a JSON object:
{
  "is_job": true or false,
  "reason": "one short sentence"
}

Mark as true if the email is:
- Requesting a pre-construction dilapidation report
- Requesting a structural or engineering inspection
- Asking for a quote or booking for an inspection at a specific address
- A new client enquiry about an inspection job

Mark as false if it is:
- A newsletter, invoice, spam, or general correspondence
- A follow-up on an existing job (no new address mentioned)
- Internal / administrative

Email subject: {subject}
Email body:
{body}
"""

EXTRACT_PROMPT = """\
Extract the subject property address from this email.

Return ONLY a JSON object:
{
  "address": "25 Hardy St, BONDI",
  "client": "Company or person name"
}

Address format: street number + street name + comma + suburb in UPPERCASE
Example: "242 Sailors Bay Rd, NORTHBRIDGE"
If no address found, use null.

Email subject: {subject}
Email body:
{body}
"""

# ── Credentials ───────────────────────────────────────────────────────────────

def load_credentials() -> dict:
    if not CREDS_FILE.exists():
        raise FileNotFoundError(
            f"Credentials not found. Run:  python job_watcher.py --setup"
        )
    return json.loads(CREDS_FILE.read_text())


def setup_credentials():
    print("=" * 60)
    print("JOB WATCHER — FIRST TIME SETUP")
    print("=" * 60)
    print()
    print("Enter your email credentials. These are saved locally to")
    print(f"  {CREDS_FILE}")
    print("and are never sent anywhere except your mail server.")
    print()

    email_addr = input("  Your email address: ").strip()
    password   = input("  Password (or app password if you have 2FA): ").strip()

    api_key = _load_api_key()
    if not api_key:
        api_key = input("  Anthropic API key: ").strip()

    creds = {
        "email":   email_addr,
        "password": password,
        "api_key": api_key,
    }
    CREDS_FILE.write_text(json.dumps(creds, indent=2))
    print(f"\nSaved to {CREDS_FILE}")
    print("Run  python job_watcher.py  to start watching.")


def _load_api_key() -> str:
    config_path = Path(__file__).parent / "dilapidation_tool" / "config.py"
    if config_path.exists():
        try:
            spec = importlib.util.spec_from_file_location("_cfg", config_path)
            cfg = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cfg)
            return getattr(cfg, "ANTHROPIC_API_KEY", "")
        except Exception:
            pass
    return ""

# ── Seen email tracking ───────────────────────────────────────────────────────

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=2))

# ── Email helpers ─────────────────────────────────────────────────────────────

def _decode(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    parts = _decode_header(value)
    out = []
    for part, enc in parts:
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(part)
    return " ".join(out)


def _body(msg) -> str:
    """Extract plain-text body from an email.message.Message object."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="replace")
    return ""


def fetch_unread(imap: imaplib.IMAP4_SSL, seen: set) -> list[dict]:
    """Return list of unread emails not already in seen set."""
    imap.select("INBOX")
    _, data = imap.search(None, "UNSEEN")
    uids = data[0].split()
    results = []
    for uid in uids:
        uid_str = uid.decode()
        if uid_str in seen:
            continue
        _, msg_data = imap.fetch(uid, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        results.append({
            "uid":     uid_str,
            "subject": _decode(msg.get("Subject", "")),
            "from":    _decode(msg.get("From", "")),
            "body":    _body(msg)[:3000],  # cap at 3000 chars for the API
        })
    return results

# ── Claude helpers ────────────────────────────────────────────────────────────

def _claude(client, prompt: str) -> dict:
    import anthropic
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt
                   + "\n\nRespond with ONLY the JSON object."}],
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    return json.loads(raw)


def is_job_email(client, subject: str, body: str) -> tuple[bool, str]:
    try:
        result = _claude(client, CLASSIFY_PROMPT.format(subject=subject, body=body))
        return bool(result.get("is_job")), result.get("reason", "")
    except Exception as e:
        log.warning(f"  classify failed: {e}")
        return False, ""


def extract_details(client, subject: str, body: str) -> dict:
    try:
        return _claude(client, EXTRACT_PROMPT.format(subject=subject, body=body))
    except Exception as e:
        log.warning(f"  extract failed: {e}")
        return {}

# ── Folder creation ───────────────────────────────────────────────────────────

def next_job_number() -> int:
    if not PROJECTS_DIR.exists():
        return 260001
    numbers = [
        int(m.group(1))
        for f in PROJECTS_DIR.iterdir()
        if f.is_dir() and (m := FOLDER_RE.match(f.name))
    ]
    return max(numbers) + 1 if numbers else 260001


def create_folder(address: str) -> Path:
    number = next_job_number()
    name = f"{number} - {address}"
    path = PROJECTS_DIR / name
    path.mkdir(parents=True, exist_ok=True)
    return path

# ── Main loop ─────────────────────────────────────────────────────────────────

def watch(creds: dict):
    import anthropic
    claude = anthropic.Anthropic(api_key=creds["api_key"], timeout=30.0)
    seen   = load_seen()

    log.info("Job watcher started.")
    log.info(f"Monitoring: {creds['email']}")
    log.info(f"Projects:   {PROJECTS_DIR}")
    log.info(f"Polling every {POLL_INTERVAL // 60} minutes. Press Ctrl+C to stop.")
    print()

    while True:
        try:
            log.info("Checking inbox...")
            with imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT) as imap:
                imap.login(creds["email"], creds["password"])
                emails = fetch_unread(imap, seen)

            log.info(f"  {len(emails)} new unread email(s) to check.")

            for em in emails:
                log.info(f"  → [{em['from']}] {em['subject']}")
                is_job, reason = is_job_email(claude, em["subject"], em["body"])

                if not is_job:
                    log.info(f"     Skipped — {reason}")
                    seen.add(em["uid"])
                    save_seen(seen)
                    continue

                log.info(f"     Job email detected — {reason}")
                details = extract_details(claude, em["subject"], em["body"])
                address = details.get("address")
                client_name = details.get("client", "")

                if not address:
                    log.warning("     Could not extract address — skipping (check watcher.log)")
                    seen.add(em["uid"])
                    save_seen(seen)
                    continue

                folder = create_folder(address)
                log.info(f"     ✓ Created: {folder.name}")
                if client_name:
                    log.info(f"       Client: {client_name}")

                seen.add(em["uid"])
                save_seen(seen)

        except imaplib.IMAP4.error as e:
            log.error(f"IMAP error: {e}")
        except Exception as e:
            log.error(f"Unexpected error: {e}")

        log.info(f"Next check in {POLL_INTERVAL // 60} minutes...")
        time.sleep(POLL_INTERVAL)


def main():
    parser = argparse.ArgumentParser(description="Auto job folder creator")
    parser.add_argument("--setup", action="store_true", help="Configure credentials")
    args = parser.parse_args()

    if args.setup:
        setup_credentials()
        return

    try:
        creds = load_credentials()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    try:
        watch(creds)
    except KeyboardInterrupt:
        log.info("Watcher stopped.")


if __name__ == "__main__":
    import sys
    main()
