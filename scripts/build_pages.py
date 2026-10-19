#!/usr/bin/env python3
"""
Builds static, Google-readable pharmacy pages for RareMed Supply from the
Supabase `directory_pharmacies` table.

Output (written to the repo root):
  pharmacies/index.html            hub page listing every state
  pharmacies/<state>/index.html    one page per state with enough pharmacies
  sitemap.xml                      homepage + all generated pages

Run locally:   python scripts/build_pages.py
Test offline:  python scripts/build_pages.py --json sample.json
No secrets needed: it reads the public Supabase URL / anon key from index.html
(the same ones the website already uses; the table is publicly readable).
"""
import html
import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://raremedsupply.com.ng"
MIN_PHARMACIES = 5          # states with fewer pharmacies don't get a page (avoids thin pages)
OUT_DIR = ROOT / "pharmacies"

INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def const(name):
    m = re.search(r"%s\s*=\s*'([^']+)'" % name, INDEX)
    return m.group(1) if m else None


SUPABASE_URL = const("SUPABASE_URL")
SUPABASE_KEY = const("SUPABASE_ANON_KEY")
GA_ID = const("window.GA_MEASUREMENT_ID") or (re.search(r"GA_MEASUREMENT_ID\s*=\s*'(G-[A-Z0-9]+)'", INDEX) or [None, None])[1]
GTM_ID = (re.search(r"'(GTM-[A-Z0-9]+)'", INDEX) or [None, None])[1]


# ---------------------------------------------------------------- data
def fetch_all():
    rows, start = [], 0
    while True:
        url = (SUPABASE_URL + "/rest/v1/directory_pharmacies"
               "?select=name,state,city,address,phone,lat,lng,updated_at&order=state.asc,name.asc")
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_KEY,
            "Authorization": "Bearer " + SUPABASE_KEY,
            "Range-Unit": "items",
            "Range": "%d-%d" % (start, start + 999),
        })
        with urllib.request.urlopen(req, timeout=60) as r:
            batch = json.loads(r.read().decode("utf-8"))
        rows += batch
        if len(batch) < 1000:
            return rows
        start += 1000


# ---------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s or ""), quote=True)


def slugify(s):
    s = re.sub(r"\(.*?\)", lambda m: " " + m.group(0)[1:-1] + " ", s.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def display_state(state):
    if state.upper().startswith("FCT"):
        return "FCT Abuja"
    return state


def title_state(state):
    d = display_state(state)
    return d if d == "FCT Abuja" else d + " State"


def first_phone(p):
    return re.sub(r"[^\d+]", "", re.split(r"[;,/]", p or "")[0])


def area_of(row, state):
    c = (row.get("city") or "").strip()
    first = c.split(" / ")[0].strip() if c else ""
    return first or display_state(state)


def maps_link(row):
    q = " ".join(x for x in [row.get("name"), row.get("address"), row.get("city"), row.get("state")] if x)
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(q)


# ---------------------------------------------------------------- page chrome
def head_tracking():
    out = ""
    if GTM_ID:
        out += ("<!-- Google Tag Manager -->\n<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':\n"
                "new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],\n"
                "j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=\n"
                "'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);\n"
                "})(window,document,'script','dataLayer','%s');</script>\n<!-- End Google Tag Manager -->\n" % GTM_ID)
    if GA_ID:
        out += ("<script async src=\"https://www.googletagmanager.com/gtag/js?id=%s\"></script>\n"
                "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
                "gtag('js',new Date());gtag('config','%s');</script>\n" % (GA_ID, GA_ID))
    return out


def body_tracking():
    if not GTM_ID:
        return ""
    return ('<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=%s" height="0" width="0" '
            'style="display:none;visibility:hidden"></iframe></noscript>\n' % GTM_ID)


CSS = """
:root{--cobalt:#1d4ed8;--sky:#0ea5e9;--navy:#0f172a;--g500:#64748b;--g600:#475569;--g200:#e2e8f0;--g100:#f1f5f9}
*{box-sizing:border-box}body{margin:0;font-family:'Inter',system-ui,sans-serif;color:var(--navy);background:#f8fafc;line-height:1.55}
a{color:var(--cobalt)}header.top{background:#fff;border-bottom:1px solid var(--g200)}
.wrap{max-width:860px;margin:0 auto;padding:0 18px}
.bar{display:flex;align-items:center;justify-content:space-between;padding-top:14px;padding-bottom:14px}
.logo{font-family:'Plus Jakarta Sans','Inter',sans-serif;font-weight:800;font-size:19px;color:var(--navy);text-decoration:none}
.logo span{color:var(--sky)}
.btn{display:inline-block;background:linear-gradient(135deg,var(--cobalt),var(--sky));color:#fff;text-decoration:none;font-weight:700;border:0;border-radius:12px;padding:12px 18px;font-size:15px;cursor:pointer}
nav.crumbs{font-size:13px;color:var(--g500);padding:16px 0 4px}nav.crumbs a{color:var(--g600)}
h1{font-family:'Plus Jakarta Sans','Inter',sans-serif;font-size:clamp(26px,5vw,38px);line-height:1.15;margin:8px 0 12px;letter-spacing:-.5px}
h2{font-family:'Plus Jakarta Sans','Inter',sans-serif;font-size:20px;margin:30px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--g200)}
.lead{color:var(--g600);font-size:16px;margin:0 0 18px}
.search{display:flex;gap:8px;margin:18px 0 8px}.search input{flex:1;min-width:0;padding:13px 14px;border:2px solid var(--g200);border-radius:12px;font:inherit;font-size:16px}
.note{background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;border-radius:12px;padding:12px 14px;font-size:13.5px;margin:16px 0}
ul.list{list-style:none;margin:0;padding:0}ul.list li.ph{background:#fff;border:1px solid var(--g200);border-radius:14px;padding:13px 15px;margin-bottom:9px}
.nm{font-weight:800}.ad,.tel{font-size:14.5px;color:var(--g600);margin-top:2px}.muted{color:#94a3b8}
.links{margin-top:8px;display:flex;gap:14px;flex-wrap:wrap;font-size:14px;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin-top:14px}
.grid a{display:flex;justify-content:space-between;gap:8px;background:#fff;border:1px solid var(--g200);border-radius:12px;padding:13px 14px;text-decoration:none;color:var(--navy);font-weight:700}
.grid a span{color:var(--g500);font-weight:600;font-size:13px}
footer{margin-top:40px;border-top:1px solid var(--g200);background:#fff;padding:22px 0;font-size:13px;color:var(--g500)}
"""


def page(title, desc, canonical, body, jsonld):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
{head_tracking()}<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="theme-color" content="#0ea5e9">
<link rel="icon" type="image/png" href="/og-image.png">
<meta property="og:type" content="website">
<meta property="og:site_name" content="RareMed Supply">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{SITE}/og-image.png">
<meta property="og:locale" content="en_NG">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Plus+Jakarta+Sans:wght@800&display=swap" rel="stylesheet">
<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
<style>{CSS}</style>
</head>
<body>
{body_tracking()}<header class="top"><div class="wrap bar"><a class="logo" href="/">RareMed <span>Supply</span></a><a class="btn" href="/">Search medicines</a></div></header>
<main class="wrap">
{body}
</main>
<footer><div class="wrap">RareMed Supply does not sell or dispense medications. It is a digital platform that helps patients find pharmacies. All purchases and dispensing are handled by licensed pharmacies. Pharmacy details are collected from public sources and from pharmacies registered with RareMed Supply and may be out of date, so please confirm with the pharmacy before you visit.<br><br><a href="/">raremedsupply.com.ng</a> &middot; <a href="/pharmacies/">All states</a></div></footer>
</body>
</html>
"""


# ---------------------------------------------------------------- builders
def state_page(state, rows):
    disp, ttl = display_state(state), title_state(state)
    slug = slugify(state)
    url = f"{SITE}/pharmacies/{slug}/"
    n = len(rows)
    with_phone = sum(1 for r in rows if r.get("phone"))

    groups = {}
    for r in rows:
        groups.setdefault(area_of(r, state), []).append(r)

    parts = []
    for area in sorted(groups, key=lambda a: (a == disp, a.lower())):
        items = []
        for r in sorted(groups[area], key=lambda r: (r.get("name") or "").lower()):
            addr = esc(r.get("address")) if r.get("address") else '<span class="muted">Address not available yet</span>'
            if r.get("phone"):
                tel = first_phone(r["phone"])
                phone = f'<a href="tel:{esc(tel)}">{esc(r["phone"])}</a>' if tel else esc(r["phone"])
            else:
                phone = '<span class="muted">Phone number not available yet</span>'
            links = ""
            if r.get("address"):
                links = f'<div class="links"><a href="{esc(maps_link(r))}" target="_blank" rel="noopener">Directions</a></div>'
            items.append(f'<li class="ph"><div class="nm">{esc(r.get("name"))}</div><div class="ad">{addr}</div><div class="tel">{phone}</div>{links}</li>')
        parts.append(f'<h2>{esc(area)} ({len(items)})</h2>\n<ul class="list">\n' + "\n".join(items) + "\n</ul>")

    body = f"""<nav class="crumbs"><a href="/">Home</a> &rsaquo; <a href="/pharmacies/">Pharmacies</a> &rsaquo; {esc(disp)}</nav>
<h1>Pharmacies in {esc(ttl)}, Nigeria</h1>
<p class="lead">{n} pharmacies in {esc(disp)}{f", {with_phone} with a phone number" if with_phone else ""}. Need a specific medicine? Search it below and RareMed Supply will show which pharmacies near you have it.</p>
<form class="search" action="/" method="get"><input type="search" name="q" placeholder="Search a medicine, e.g. Amoxicillin" required minlength="2" aria-label="Medicine name"><button class="btn" type="submit">Search</button></form>
<div class="note">This list comes from public online directories and from pharmacies registered with RareMed Supply. Details may be out of date, so please call the pharmacy to confirm before you travel. Are you a pharmacy owner? <a href="/#pharmacy">Register your pharmacy free</a> to keep your details and stock up to date.</div>
{chr(10).join(parts)}"""

    title = f"Pharmacies in {ttl}, Nigeria | RareMed Supply"
    desc = (f"Directory of {n} pharmacies in {disp}: names, addresses and phone numbers. "
            "Search a medicine and find which pharmacies near you have it. Free on RareMed Supply.")
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Pharmacies", "item": SITE + "/pharmacies/"},
            {"@type": "ListItem", "position": 3, "name": disp, "item": url}]},
        {"@type": "ItemList", "name": f"Pharmacies in {ttl}", "numberOfItems": n,
         "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": r.get("name")}
                             for i, r in enumerate(sorted(rows, key=lambda r: (r.get("name") or "").lower()))]}]}
    return slug, page(title, desc, url, body, jsonld)


def hub_page(states):
    url = SITE + "/pharmacies/"
    total = sum(c for _, _, c in states)
    cards = "".join(f'<a href="/pharmacies/{esc(slug)}/">{esc(disp)} <span>{c}</span></a>' for disp, slug, c in states)
    body = f"""<nav class="crumbs"><a href="/">Home</a> &rsaquo; Pharmacies</nav>
<h1>Pharmacies in Nigeria, by state</h1>
<p class="lead">Browse {total} pharmacies across {len(states)} states, with addresses and phone numbers where available. Or search a medicine to see which pharmacies near you have it.</p>
<form class="search" action="/" method="get"><input type="search" name="q" placeholder="Search a medicine, e.g. Amoxicillin" required minlength="2" aria-label="Medicine name"><button class="btn" type="submit">Search</button></form>
<div class="grid">{cards}</div>"""
    title = "Pharmacies in Nigeria by State | RareMed Supply"
    desc = f"Browse {total} pharmacies across Nigeria by state, with addresses and phone numbers. Search a medicine and find pharmacies near you. Free on RareMed Supply."
    jsonld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": "Pharmacies", "item": url}]}
    return page(title, desc, url, body, jsonld)


def write_sitemap(entries):
    old = ROOT / "sitemap.xml"
    home_lastmod = None
    if old.exists():
        m = re.search(r"<loc>%s/</loc>\s*<lastmod>([^<]+)</lastmod>" % re.escape(SITE), old.read_text(encoding="utf-8"))
        home_lastmod = m.group(1) if m else None
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    xml.append("  <url>\n    <loc>%s/</loc>\n%s    <changefreq>weekly</changefreq>\n    <priority>1.0</priority>\n  </url>"
               % (SITE, ("    <lastmod>%s</lastmod>\n" % home_lastmod) if home_lastmod else ""))
    for loc, lastmod, prio in entries:
        xml.append("  <url>\n    <loc>%s</loc>\n%s    <changefreq>weekly</changefreq>\n    <priority>%s</priority>\n  </url>"
                   % (loc, ("    <lastmod>%s</lastmod>\n" % lastmod) if lastmod else "", prio))
    xml.append("</urlset>\n")
    old.write_text("\n".join(xml), encoding="utf-8")


# ---------------------------------------------------------------- main
def main():
    if "--json" in sys.argv:
        rows = json.loads(Path(sys.argv[sys.argv.index("--json") + 1]).read_text(encoding="utf-8"))
    else:
        rows = fetch_all()
    if not rows:
        print("No pharmacies returned - leaving existing pages untouched.")
        sys.exit(1)

    by_state = {}
    for r in rows:
        if r.get("state") and r.get("name"):
            by_state.setdefault(r["state"], []).append(r)

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    hub, sm = [], []
    for state in sorted(by_state, key=lambda s: display_state(s).lower()):
        rs = by_state[state]
        if len(rs) < MIN_PHARMACIES:
            continue
        slug, content = state_page(state, rs)
        (OUT_DIR / slug).mkdir(parents=True, exist_ok=True)
        (OUT_DIR / slug / "index.html").write_text(content, encoding="utf-8")
        hub.append((display_state(state), slug, len(rs)))
        last = max((r.get("updated_at") or "")[:10] for r in rs) or None
        sm.append((f"{SITE}/pharmacies/{slug}/", last, "0.8"))

    (OUT_DIR / "index.html").write_text(hub_page(hub), encoding="utf-8")
    hub_last = max((e[1] or "" for e in sm), default="") or None
    write_sitemap([(f"{SITE}/pharmacies/", hub_last, "0.9")] + sm)
    print("Built hub + %d state pages (%d pharmacies)." % (len(hub), sum(c for _, _, c in hub)))


if __name__ == "__main__":
    main()
