#!/usr/bin/env python3
"""Static site builder for iiengineer.com (Integrity Inspecting Engineers).

No dependencies. Run:  python3 build.py
Reads content/**/*.html (each starts with a <!--meta {json} --> block),
wraps them in the shared template, and writes the finished site to site/.

Content file meta keys:
  title        <title> text (50-60 chars ideal)
  description  meta description (140-160 chars ideal)
  slug         URL path without slashes at ends ("" for home, "areas/wollongong")
  h1           (areas/articles) page heading
  intro        (areas/articles) one-line lede under the heading
  date         ISO date published (articles) / last reviewed (others)
  updated      ISO date last edited (optional)
  suburbs      (areas) list of nearby suburbs named on the page
  faq          list of {"q": ..., "a": ...}  -> rendered + FAQPage schema
  nav_label    (areas) short name used in area lists
  noindex      true to keep out of sitemap / search
"""
import json, re, shutil, html
from pathlib import Path
from datetime import date

ROOT = Path(__file__).parent
SITE = ROOT / "site"
CONTENT = ROOT / "content"
CFG = json.loads((ROOT / "site.json").read_text())
BASE = CFG["url"].rstrip("/")


def load(kind):
    items = []
    for f in sorted((CONTENT / kind).glob("*.html")):
        raw = f.read_text(encoding="utf-8")
        m = re.match(r"\s*<!--meta\s*(\{.*?\})\s*-->\s*", raw, re.S)
        if not m:
            raise SystemExit(f"{f}: missing <!--meta {{...}} --> header")
        meta = json.loads(m.group(1))
        meta["body"] = raw[m.end():]
        meta["kind"] = kind
        meta["src"] = str(f.relative_to(ROOT))
        items.append(meta)
    return items


pages, areas, articles = load("pages"), load("areas"), load("articles")
articles.sort(key=lambda a: a["date"], reverse=True)
areas.sort(key=lambda a: a.get("order", 99))


def url(slug):
    return f"{BASE}/{slug}/" if slug else f"{BASE}/"


def href(slug):
    return f"/{slug}/" if slug else "/"


def esc(s):
    return html.escape(s, quote=True)


def fmt_date(d):
    y, m, dd = map(int, d.split("-"))
    return date(y, m, dd).strftime("%-d %B %Y")


# ---------- shared fragments ----------
def business_schema():
    c = CFG
    return {
        "@type": "ProfessionalService",
        "@id": BASE + "/#business",
        "name": c["name"],
        "alternateName": c["short_name"],
        "url": BASE + "/",
        "telephone": c["phone_intl"],
        "email": c["email"],
        "image": BASE + "/og.png",
        "logo": BASE + "/favicon.svg",
        "description": c["tagline"],
        "address": {"@type": "PostalAddress", "addressLocality": c["locality"],
                    "addressRegion": "NSW", "postalCode": c["postcode"], "addressCountry": "AU"},
        "areaServed": [{"@type": "Place", "name": a} for a in c["area_served"]],
        "knowsAbout": ["Dilapidation reports", "Pre-construction dilapidation inspections",
                       "Post-construction dilapidation inspections", "Structural engineering"],
        "priceRange": "$$",
    }


def area_links(current=None):
    out = []
    for a in areas:
        if a["slug"] == current:
            continue
        out.append(f'<li><a href="{href(a["slug"])}">{esc(a["nav_label"])}</a></li>')
    return '<ul class="area-list">' + "".join(out) + "</ul>"


def article_cards(limit=None, exclude=None):
    items = [a for a in articles if a["slug"] != exclude][:limit]
    if not items:
        return ""
    out = []
    for a in items:
        out.append(
            f'<li><a href="{href(a["slug"])}"><span class="ac-title">{esc(a["h1"])}</span>'
            f'<span class="ac-intro">{esc(a["intro"])}</span>'
            f'<time datetime="{a["date"]}">{fmt_date(a["date"])}</time></a></li>')
    return '<ul class="article-list">' + "".join(out) + "</ul>"


def faq_html(faq):
    if not faq:
        return ""
    items = "".join(
        f'<details><summary>{esc(f["q"])}</summary><div><p>{f["a"]}</p></div></details>' for f in faq)
    return f'<section class="faq" aria-labelledby="faq-h"><h2 id="faq-h">Common questions</h2>{items}</section>'


def faq_schema(faq):
    return {"@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f["q"],
         "acceptedAnswer": {"@type": "Answer", "text": re.sub("<[^>]+>", "", f["a"])}} for f in faq]}


def crumbs_schema(trail):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(trail)]}


def crumbs_html(trail):
    parts = []
    for i, (n, u) in enumerate(trail):
        if i == len(trail) - 1:
            parts.append(f'<li aria-current="page">{esc(n)}</li>')
        else:
            parts.append(f'<li><a href="{u.replace(BASE, "") or "/"}">{esc(n)}</a></li>')
    return '<nav class="crumbs" aria-label="Breadcrumb"><ol>' + "".join(parts) + "</ol></nav>"


FORM = (ROOT / "partials" / "quote-form.html").read_text()
WALL = (ROOT / "partials" / "wall.svg").read_text()
CTA_RAW = (ROOT / "partials" / "cta.html").read_text()


def fill(body, ctx_slug=None):
    body = body.replace("{{CTA}}", CTA_RAW)
    reps = {
        "{{QUOTE_FORM}}": FORM,
        "{{WALL_SVG}}": WALL,
        "{{AREA_LIST}}": area_links(ctx_slug),
        "{{ARTICLE_LIST}}": article_cards(),
        "{{ARTICLE_LIST_3}}": article_cards(3, ctx_slug),
        "{{PHONE}}": CFG["phone_display"],
        "{{PHONE_TEL}}": CFG["phone_intl"],
        "{{EMAIL}}": CFG["email"],
        "{{CREDENTIALS}}": CFG["credentials"],
    }
    for k, v in reps.items():
        body = body.replace(k, v)
    return body


def render(meta):
    slug = meta["slug"]
    kind = meta["kind"]
    canonical = url(slug)
    graph = [business_schema(),
             {"@type": "WebSite", "@id": BASE + "/#site", "url": BASE + "/", "name": CFG["name"]}]
    trail = [("Home", BASE + "/")]

    body = fill(meta["body"], slug)

    if kind == "areas":
        trail += [("Service areas", url("areas")), (meta["nav_label"], canonical)]
        graph.append({"@type": "Service", "serviceType": "Dilapidation report",
                      "name": meta["h1"], "provider": {"@id": BASE + "/#business"},
                      "areaServed": [{"@type": "Place", "name": s} for s in [meta["nav_label"]] + meta.get("suburbs", [])],
                      "url": canonical})
        main = (f'<article class="doc">{crumbs_html(trail)}<header class="doc-head"><h1>{esc(meta["h1"])}</h1>'
                f'<p class="lede">{esc(meta["intro"])}</p></header>'
                f'<div class="prose">{body}</div>{faq_html(meta.get("faq"))}</article>'
                f'{fill(CTA_RAW)}<section class="band"><div class="wrap"><h2>Other areas we cover</h2>{area_links(slug)}</div></section>')
    elif kind == "articles":
        trail += [("Articles", url("articles")), (meta["h1"], canonical)]
        graph.append({"@type": "Article", "headline": meta["h1"], "description": meta["description"],
                      "datePublished": meta["date"], "dateModified": meta.get("updated", meta["date"]),
                      "author": {"@type": "Organization", "@id": BASE + "/#business", "name": CFG["name"]},
                      "publisher": {"@id": BASE + "/#business"}, "mainEntityOfPage": canonical,
                      "image": BASE + "/og.png"})
        upd = meta.get("updated")
        dates = f'Published <time datetime="{meta["date"]}">{fmt_date(meta["date"])}</time>'
        if upd and upd != meta["date"]:
            dates += f', updated <time datetime="{upd}">{fmt_date(upd)}</time>'
        more = article_cards(3, slug)
        main = (f'<article class="doc">{crumbs_html(trail)}<header class="doc-head"><h1>{esc(meta["h1"])}</h1>'
                f'<p class="lede">{esc(meta["intro"])}</p><p class="byline">{dates}. Written by {esc(CFG["name"])}, {esc(CFG["credentials"])}.</p></header>'
                f'<div class="prose">{body}</div>{faq_html(meta.get("faq"))}</article>{fill(CTA_RAW)}'
                + (f'<section class="band"><div class="wrap"><h2>More reading</h2>{more}</div></section>' if more else ""))
    else:
        if slug:
            trail.append((meta.get("crumb", meta["title"].split("|")[0].strip()), canonical))
            graph.append(crumbs_schema(trail))
        main = body
        if meta.get("faq"):
            main = main.replace("{{FAQ}}", faq_html(meta["faq"]))

    if kind in ("areas", "articles"):
        graph.append(crumbs_schema(trail))
    if meta.get("faq"):
        graph.append(faq_schema(meta["faq"]))

    schema = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=1)
    robots = '<meta name="robots" content="noindex">' if meta.get("noindex") else '<meta name="robots" content="index, follow, max-image-preview:large">'
    og_type = "article" if kind == "articles" else "website"

    nav = [("Dilapidation reports", "/#reports"), ("Service areas", "/areas/"), ("Articles", "/articles/")]
    nav_html = "".join(f'<li><a href="{h}">{n}</a></li>' for n, h in nav)

    return f"""<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(meta["title"])}</title>
<meta name="description" content="{esc(meta["description"])}">
<link rel="canonical" href="{canonical}">
{robots}
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{esc(CFG["name"])}">
<meta property="og:title" content="{esc(meta["title"])}">
<meta property="og:description" content="{esc(meta["description"])}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{BASE}/og.png">
<meta property="og:locale" content="en_AU">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#1D2B33">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&display=swap">
<link rel="stylesheet" href="/styles.css?v={CFG["css_version"]}">
<script type="application/ld+json">
{schema}
</script>
</head>
<body class="k-{kind}">
<a class="skip" href="#main">Skip to content</a>
<header class="site-head">
 <div class="wrap head-row">
  <a class="brand" href="/" aria-label="{esc(CFG["name"])} home">
   <svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><rect x="1" y="1" width="30" height="30" rx="3" fill="var(--slate)"/><path d="M8 24V8M14 24V8M20 8l4 8-4 8" stroke="var(--paint)" stroke-width="3" fill="none" stroke-linecap="square"/></svg>
   <span class="brand-name">Integrity Inspecting Engineers</span>
  </a>
  <nav class="main-nav" aria-label="Main"><ul>{nav_html}</ul></nav>
  <div class="head-cta">
   <a class="tel" href="tel:{CFG["phone_intl"]}">{CFG["phone_display"]}</a>
   <a class="btn btn-paint" href="/quote/">Request a quote</a>
  </div>
 </div>
</header>
<main id="main">
{main}
</main>
<footer class="site-foot">
 <div class="wrap foot-grid">
  <div>
   <p class="foot-name">Integrity Inspecting Engineers</p>
   <p>Dilapidation reports by a {esc(CFG["credentials_long"])}. Based in {esc(CFG["locality"])}, covering the Illawarra, Shoalhaven and Sydney.</p>
  </div>
  <div>
   <p class="foot-h">Contact</p>
   <p><a href="tel:{CFG["phone_intl"]}">{CFG["phone_display"]}</a><br><a href="mailto:{CFG["email"]}">{CFG["email"]}</a></p>
  </div>
  <div>
   <p class="foot-h">Areas</p>
   {area_links()}
  </div>
  <div>
   <p class="foot-h">Site</p>
   <ul class="area-list"><li><a href="/quote/">Request a quote</a></li><li><a href="/articles/">Articles</a></li><li><a href="/privacy/">Privacy</a></li></ul>
  </div>
 </div>
 <div class="wrap foot-base"><p>&copy; {date.today().year} Integrity Inspecting Engineers. {esc(CFG.get("abn_line", ""))}</p></div>
</footer>
<script src="/site.js" defer></script>
</body>
</html>
"""


def build():
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(ROOT / "static", SITE)
    all_items = pages + areas + articles
    seen = set()
    sitemap = []
    for m in all_items:
        if m["slug"] in seen:
            raise SystemExit(f"duplicate slug {m['slug']}")
        seen.add(m["slug"])
        out = SITE / m["slug"] / "index.html" if m["slug"] not in ("404",) else SITE / "404.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(m), encoding="utf-8")
        if not m.get("noindex") and m["slug"] != "404":
            sitemap.append((url(m["slug"]), m.get("updated", m.get("date", CFG["launch_date"]))))
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, d in sitemap:
        xml.append(f"  <url><loc>{u}</loc><lastmod>{d}</lastmod></url>")
    xml.append("</urlset>")
    (SITE / "sitemap.xml").write_text("\n".join(xml) + "\n")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /thanks/\n\nSitemap: {BASE}/sitemap.xml\n")
    print(f"Built {len(all_items)} pages -> {SITE}")


if __name__ == "__main__":
    build()
