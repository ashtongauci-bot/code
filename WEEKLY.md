# Weekly website update: instructions for Claude

This repo is the website for Integrity Inspecting Engineers (iiengineer.com), a dilapidation
report business run by a Chartered Professional Engineer (CPEng, NER). It covers Wollongong /
the Illawarra / Shoalhaven and all of Greater Sydney equally. Phone 0450 787 971.
The site offers **dilapidation inspections only** (pre- and post-construction). Do not add
other services.

Netlify deploys the `site/` folder automatically when this branch is pushed. Nothing is live
until you commit and push.

## Each week, do all four

1. **One new article** — take the first unchecked topic from the backlog below.
2. **One new suburb/area page** — take the first unchecked area from the backlog below.
3. **SEO health check** — `python3 build.py && python3 tools/check.py`. Fix every ERROR. Fix
   WARNs where it's a real improvement. Also review: internal links from new pages to related
   pages (at least 2 each way), the home page article list, and that `site.json` `css_version`
   is bumped if `static/styles.css` changed.
4. **Email a summary** to ashtongauci@gmail.com (Gmail connector): subject
   "IIE website: weekly update <date>", listing pages added (with live URLs), fixes made,
   and anything that needs Ash's input. If Gmail isn't available, write the summary into
   `updates/<date>.md` and commit it.

Then: tick the backlog items, add a line to the changelog at the bottom, commit with a
clear message, and push to the same branch.

## How content works

- Content lives in `content/articles/` and `content/areas/` as `.html` files. Each starts with a
  `<!--meta {json} -->` header; copy an existing file as the pattern. Keys are documented at the
  top of `build.py`.
- `slug` must be `articles/<kebab-case>` or `areas/<kebab-case>`. Never change an existing slug.
- `date` = today (ISO). When you materially revise an existing page, set `updated` too.
- Placeholders available in content: `{{PHONE}}`, `{{PHONE_TEL}}`, `{{EMAIL}}`, `{{CTA}}`,
  `{{AREA_LIST}}`, `{{SYDNEY_LIST}}`, `{{ILLAWARRA_LIST}}`, `{{QUOTE_FORM}}`.
- Area pages need `"region": "sydney"` or `"region": "illawarra"` and an `order` number.
- No photos on the site (Ash's decision). Don't add any images, stock or otherwise.
- The logo is in `brand/` and `static/logo*.png`. Don't change it.
- Never edit files in `site/` by hand; always run `python3 build.py`.

## Writing rules (these protect the business, follow them exactly)

- Australian English. Plain, direct, written for builders, developers and homeowners.
- 600–1,100 words for articles, 350–600 for area pages, plus 2–3 FAQ entries in the meta.
- Title 30–65 chars ending in "| IIE" where it fits; description 110–165 chars; one H1.
- Each area page must contain genuinely local content: the kind of building work happening
  there, ground/site conditions, housing stock, the council by name. Never produce a page
  that is another area page with the suburb names swapped. Google penalises that.
- **Never invent** prices, turnaround times, testimonials, reviews, project examples, client
  names, statistics, or credentials. Credentials you may state: CPEng, NER, professional
  indemnity insured.
- Don't quote specific council clauses, legislation section numbers or standards unless you
  have verified them with a web search this session and they are current.
- Don't claim the site ranks for anything or promise outcomes.
- Every page links to `/quote/` (the `{{CTA}}` band is added automatically on articles/areas).

## Backlog: articles

- [x] What is a dilapidation report, and when do you need one?
- [x] Dilapidation reports for swimming pool excavation
- [x] Pre- vs post-construction dilapidation reports
- [ ] What to do if your neighbour's building work cracks your house
- [ ] Dilapidation reports for demolition: what builders need before the excavator arrives
- [ ] Rock breaking and vibration: protecting neighbouring homes on Illawarra sites
- [ ] How to read a dilapidation report (with a sample defect schedule explained)
- [ ] Should a neighbour let the builder's engineer inspect their home?
- [ ] Dilapidation reports for strata buildings next to a development
- [ ] Crack widths explained: hairline, fine, moderate and severe
- [ ] Dilapidation reports for road, drainage and civil works
- [ ] Mine subsidence districts in the Illawarra and what they mean for building nearby
- [ ] Dilapidation reports for duplex and dual occupancy builds
- [ ] Party walls in terraces: what gets inspected and why
- [ ] Basement excavation and dewatering: risks to neighbouring properties
- [ ] Dilapidation reports for granny flats and secondary dwellings
- [ ] How long before works should a dilapidation report be done?
- [ ] What happens if a neighbour refuses access for a dilapidation inspection
- [ ] Dilapidation reports for council and public assets (kerbs, footpaths, pits)
- [ ] Dilapidation reports for piling works
- [ ] Builder's checklist: council dilapidation conditions in Wollongong and Shellharbour
- [ ] Dilapidation reports for Sydney basement excavation in sandstone
- [ ] Terrace renovations in the Inner West: protecting the house next door

## Backlog: area pages

- [x] Wollongong
- [x] Shellharbour
- [x] Kiama
- [x] Nowra and Shoalhaven
- [x] Sydney (hub page listing all Sydney areas)
- [x] Sutherland Shire
- [x] St George
- [x] Inner West
- [x] Eastern Suburbs
- [x] North Shore
- [x] Parramatta and the Hills
- [x] Canterbury-Bankstown
- [x] Campbelltown and Macarthur

Alternate between Sydney and Wollongong/Illawarra each week (Ash covers both equally).

- [ ] Northern Beaches (areas/northern-beaches) — sydney
- [ ] Dapto (areas/dapto) — illawarra
- [ ] Ryde and Hunters Hill (areas/ryde) — sydney
- [ ] Thirroul and the Northern Suburbs (areas/northern-suburbs-wollongong) — illawarra
- [ ] Liverpool and Fairfield (areas/liverpool) — sydney
- [ ] Wollongong CBD (areas/wollongong-cbd) — illawarra
- [ ] Hills District: Castle Hill, Kellyville, Norwest (areas/hills-district) — sydney
- [ ] Shell Cove (areas/shell-cove) — illawarra
- [ ] City of Sydney: Surry Hills, Redfern, Alexandria (areas/city-of-sydney) — sydney
- [ ] Albion Park (areas/albion-park) — illawarra
- [ ] Strathfield, Burwood and Canada Bay (areas/inner-west-strathfield) — sydney
- [ ] Figtree and Unanderra (areas/figtree) — illawarra
- [ ] Penrith and Blue Mountains foothills (areas/penrith) — sydney
- [ ] Gerringong (areas/gerringong) — illawarra
- [ ] Blacktown and Rouse Hill (areas/blacktown) — sydney
- [ ] Calderwood and Tullimbar (areas/calderwood) — illawarra
- [ ] Hornsby and Ku-ring-gai (areas/hornsby) — sydney
- [ ] Helensburgh (areas/helensburgh) — illawarra
- [ ] Botany and Mascot (areas/botany) — sydney
- [ ] Berry (areas/berry) — illawarra
- [ ] Ulladulla and Milton (areas/ulladulla) — illawarra
- [ ] Huskisson and Vincentia (areas/jervis-bay) — illawarra

When a backlog runs out, add 10 new well-chosen items to it (based on what's already
published and what people in the area search for) and carry on.

## Changelog

- 2026-10-18 — Site launched: home, quote form, 5 area pages, 3 articles.
- 2026-10-18 — New logo, phone 0450 787 971, 8 Sydney area pages. (Real photos added then removed at Ash's request.)
