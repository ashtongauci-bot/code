#!/usr/bin/env python3
"""SEO and link health check for the built site. Run after build.py:
    python3 tools/check.py
Exits non-zero if there are errors. Warnings are printed but don't fail."""
import json, re, sys
from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
errors, warnings = [], []


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""; self.in_title = False; self.desc = None; self.canonical = None
        self.h1 = 0; self.links = []; self.ld = []; self.in_ld = False; self.imgs_no_alt = 0
        self.noindex = False; self.ids = set()

    def handle_starttag(self, tag, a):
        a = dict(a)
        if "id" in a: self.ids.add(a["id"])
        if tag == "title": self.in_title = True
        if tag == "meta" and a.get("name") == "description": self.desc = a.get("content", "")
        if tag == "meta" and a.get("name") == "robots" and "noindex" in a.get("content", ""): self.noindex = True
        if tag == "link" and a.get("rel") == "canonical": self.canonical = a.get("href")
        if tag == "h1": self.h1 += 1
        if tag == "a" and a.get("href"): self.links.append(a["href"])
        if tag == "img" and "alt" not in a: self.imgs_no_alt += 1
        if tag == "script" and a.get("type") == "application/ld+json": self.in_ld = True; self.ld.append("")

    def handle_endtag(self, tag):
        if tag == "title": self.in_title = False
        if tag == "script": self.in_ld = False

    def handle_data(self, d):
        if self.in_title: self.title += d
        if self.in_ld: self.ld[-1] += d


def target_exists(path):
    path = path.split("#")[0].split("?")[0]
    if path in ("", "/"): return (SITE / "index.html").exists()
    p = SITE / path.lstrip("/")
    return p.is_file() or (p / "index.html").is_file()


sitemap = (SITE / "sitemap.xml").read_text()
pages = sorted(SITE.rglob("*.html"))
titles = {}
for f in pages:
    rel = "/" + str(f.relative_to(SITE)).replace("index.html", "")
    p = P(); p.feed(f.read_text(encoding="utf-8"))
    t = p.title.strip()
    if not t: errors.append(f"{rel}: missing <title>")
    elif not p.noindex and not 30 <= len(t) <= 65: warnings.append(f"{rel}: title is {len(t)} chars (aim 30-65): {t}")
    titles.setdefault(t, []).append(rel)
    if p.desc is None: errors.append(f"{rel}: missing meta description")
    elif not p.noindex and not 110 <= len(p.desc) <= 165: warnings.append(f"{rel}: description is {len(p.desc)} chars (aim 110-165)")
    if p.h1 != 1: errors.append(f"{rel}: has {p.h1} <h1> tags (need exactly 1)")
    if not p.canonical: errors.append(f"{rel}: missing canonical")
    if p.imgs_no_alt: errors.append(f"{rel}: {p.imgs_no_alt} <img> without alt")
    for block in p.ld:
        try: json.loads(block)
        except Exception as e: errors.append(f"{rel}: invalid JSON-LD ({e})")
    for h in p.links:
        if h.startswith(("http", "mailto:", "tel:")): continue
        if h.startswith("#"):
            if h[1:] and h[1:] not in p.ids: errors.append(f"{rel}: broken anchor {h}")
            continue
        if not target_exists(h): errors.append(f"{rel}: broken link {h}")
    if not p.noindex and f.name != "404.html" and p.canonical and p.canonical not in sitemap:
        errors.append(f"{rel}: indexable page missing from sitemap")
for t, rels in titles.items():
    if len(rels) > 1: errors.append(f"duplicate title on {rels}: {t}")

print(f"Checked {len(pages)} pages.")
for w in warnings: print("WARN ", w)
for e in errors: print("ERROR", e)
sys.exit(1 if errors else 0)
