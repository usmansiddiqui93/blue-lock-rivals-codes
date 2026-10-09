#!/usr/bin/env python3
"""Static site builder for blue-lock-rivals-codes.com.

Reads data/*.json and writes a complete static site to dist/.
Standard library only (Pillow is optional: used for the share image + app icon).

    python scripts/build.py            # build into dist/
    BASE_PATH=/blue-lock-rivals-codes python scripts/build.py   # github.io preview
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
from datetime import datetime, timezone, date
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ASSETS = ROOT / "assets"
FONTS = ROOT / "scripts" / "fonts"
DIST = ROOT / "dist"

e = html.escape


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


SITE = load("site.json")
CODES = load("codes.json")
if os.environ.get("LAST_CHECKED"):  # set by the GitHub Action on every run
    CODES["last_checked"] = os.environ["LAST_CHECKED"]
STYLES = load("styles.json")
FLOWS = load("flows.json")
TIERS = load("tierlist.json")
UPDATES = load("updates.json")

NOW = datetime.now(timezone.utc)

# Sub-folder the site is served from: "" on the custom domain, "/blue-lock-rivals-codes"
# on the github.io preview. The GitHub Action sets it automatically from the Pages config.
BASE = os.environ.get("BASE_PATH", "").rstrip("/")
PREVIEW = bool(BASE)


def with_base(markup: str) -> str:
    if not BASE:
        return markup
    markup = re.sub(r'((?:href|src)=")/(?!/)', rf"\1{BASE}/", markup)
    return re.sub(r'srcset="([^"]*)"', lambda m: 'srcset="' + re.sub(r'(^|,\s*)/(?!/)', rf"\1{BASE}/", m.group(1)) + '"', markup)


def parse_dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return NOW


def nice_date(d):
    if isinstance(d, str):
        d = parse_dt(d) if "T" in d else datetime.fromisoformat(d)
    return d.strftime("%B %-d, %Y")


UPDATED = parse_dt(CODES.get("updated", NOW.isoformat()))
CHECKED = CODES.get("last_checked") or CODES.get("updated") or NOW.isoformat()
MONTH_YEAR = NOW.strftime("%B %Y")
YEAR = NOW.year
ACTIVE = CODES.get("active", [])
EXPIRED = CODES.get("expired", [])
TOTAL_SPINS = sum(int(c.get("spins") or 0) for c in ACTIVE)
TOTAL_FLOWS = sum(int(c.get("flows") or 0) for c in ACTIVE)
REGULAR_STYLES = sum(len(v) for k, v in STYLES["rarities"].items() if k != "Limited")
LIMITED_STYLES = len(STYLES["rarities"].get("Limited", []))
ABS = SITE["base_url"]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def join_and(items):
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


# --------------------------------------------------------------------------- #
# Small components
# --------------------------------------------------------------------------- #

PITCH_SVG = """<svg class="pitch" viewBox="0 0 1200 460" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
<g fill="none" stroke="#C4D2EC" stroke-width="2.5"><rect x="30" y="26" width="1140" height="408"/>
<line x1="600" y1="26" x2="600" y2="434"/><circle cx="600" cy="230" r="78"/>
<rect x="1000" y="120" width="170" height="220"/><rect x="1110" y="175" width="60" height="110"/>
<path d="M1000 182a52 52 0 0 0 0 96"/></g><circle cx="600" cy="230" r="5" fill="#C4D2EC"/></svg>"""

BRAND_MARK_OLD = ('<span class="brand-mark" aria-hidden="true"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
              'stroke="#fff" stroke-width="2.2"><circle cx="12" cy="12" r="9"/><path d="M12 7.2l4.2 3-1.6 4.8H9.4L7.8 10.2z" '
              'fill="#fff" stroke="none"/></svg></span>')


BRAND_MARK = ('<span class="brand-mark" aria-hidden="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
              'stroke="#fff" stroke-width="2.2"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.6l4 2.9-1.5 4.6h-5L8 10.5z" '
              'fill="#fff" stroke="none"/></svg></span>')


def ad(slot_name):
    if not SITE.get("ads_enabled"):
        return ""
    return (f'<div class="ad"><ins class="adsbygoogle" style="display:block" data-ad-client="{e(SITE["adsense_client"])}" '
            f'data-ad-format="auto" data-full-width-responsive="true"></ins>'
            f'<script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script></div>')


def reward_text(c):
    parts = []
    if c.get("spins"):
        parts.append(f'{int(c["spins"])} Lucky Style Spins')
    if c.get("flows"):
        parts.append(f'{int(c["flows"])} Lucky Flow Spins')
    return " and ".join(parts) or c.get("reward", "Free rewards")


def reward_chips(c):
    return e(reward_text(c))


def is_new(c):
    try:
        added = date.fromisoformat(c.get("added", "")[:10])
    except ValueError:
        return False
    return (NOW.date() - added).days <= int(SITE.get("new_code_days", 3))

ICON = {
    "codes": '<path d="M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4z"/><path d="M14 5v12" stroke-dasharray="2 2"/>',
    "tier": '<path d="M8 4h8v3a4 4 0 0 1-8 0z"/><path d="M8 5H5v1a3 3 0 0 0 3 3M16 5h3v1a3 3 0 0 1-3 3M12 11v4M8.5 19h7M10 15h4l.5 4h-5z"/>',
    "styles": '<circle cx="12" cy="7.5" r="3.5"/><path d="M5 20c.6-4 3.4-6 7-6s6.4 2 7 6"/>',
    "flows": '<path d="M3 9c3-3 6 3 9 0s6-3 9 0M3 15c3-3 6 3 9 0s6-3 9 0"/>',
    "spins": '<circle cx="12" cy="12" r="8"/><path d="M12 4v8l5 3"/><path d="M12 12 7 15"/>',
    "update": '<circle cx="12" cy="13" r="7.5"/><path d="M12 9v4l2.5 2M9.5 3h5"/>',
    "controls": '<path d="M7 9h10a4 4 0 0 1 4 4v1.5a2.5 2.5 0 0 1-4.6 1.3L15 14H9l-1.4 1.8A2.5 2.5 0 0 1 3 14.5V13a4 4 0 0 1 4-4z"/><path d="M8 11.5v2M7 12.5h2M16 12h.01M17.5 13.5h.01"/>',
    "help": '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.5a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5V14M12 17h.01"/>',
    "guides": '<path d="M5 4.5h9a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3z"/><path d="M17 7.5h2V20M8.5 9h5M8.5 12.5h5"/>',
    "chat": '<path d="M5 5.5h14a1.5 1.5 0 0 1 1.5 1.5v8a1.5 1.5 0 0 1-1.5 1.5h-7l-4.5 3.5v-3.5H5A1.5 1.5 0 0 1 3.5 15V7A1.5 1.5 0 0 1 5 5.5z"/><path d="M8.5 11h.01M12 11h.01M15.5 11h.01"/>',
    "bell": '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "play": '<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="m10 8.5 5.5 3.5-5.5 3.5z" fill="currentColor"/>',
    "copy": '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "chev": '<path d="m6 9 6 6 6-6"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    "ball": '<circle cx="12" cy="12" r="9"/><path d="m12 7.5 3.8 2.7-1.4 4.5H9.6l-1.4-4.5z"/><path d="M12 3v4.5M21 10.5l-5.2-.3M17.5 19.5l-3.1-4.8M6.5 19.5l3.1-4.8M3 10.5l5.2-.3"/>',
}


def icon(name, size=20, cls="ico"):
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICON[name]}</svg>')


NAV2 = [("codes", "Codes", "/", "NEW"), ("tier", "Tier list", "/tier-list/", ""), ("styles", "Styles", "/styles/", ""),
        ("flows", "Flows", "/flows/", ""), ("controls", "Controls", "/controls/", ""),
        ("update", "Next update", "/next-update/", "HOT"), ("help", "Codes not working", "/codes-not-working/", "")]

TILES = [("tier", "Tier list", "/tier-list/", "t1"), ("styles", "All styles", "/styles/", "t2"),
         ("flows", "All flows", "/flows/", "t3"), ("spins", "Free spins", "/free-spins/", "t4"),
         ("update", "Next update", "/next-update/", "t5"), ("controls", "Controls", "/controls/", "t6"),
         ("help", "Code not working?", "/codes-not-working/", "t7")]


def tiles():
    return ('<nav class="tiles wrap" aria-label="Popular guides">' + "".join(
        f'<a class="tile {c}" href="{u}">{icon(i, 26)}<span>{e(t)}</span></a>' for i, t, u, c in TILES) + "</nav>")


def code_box(code, big=False):
    return (f'<button class="codebox{" big" if big else ""}" type="button" data-copy="{e(code)}" aria-label="Copy code {e(code)}">'
            f'<span class="cb-label">Code</span><span class="cb-code">{e(code)}</span>'
            f'<span class="cb-copy">{icon("copy", 16)}<span class="cb-copy-txt">Copy</span></span></button>')


def feature_cards():
    if not ACTIVE:
        return ('<div class="feature-empty">No working codes right now. New codes usually arrive with the Saturday update. '
                '<a href="/next-update/">See the countdown</a>.</div>')
    cards = []
    for i, c in enumerate(ACTIVE):
        tag = '<span class="tag tag-new">NEW</span>' if is_new(c) else '<span class="tag tag-live">WORKING</span>'
        ribbon = []
        if c.get("spins"):
            ribbon.append(f'<b>+{int(c["spins"])}</b> style spins')
        if c.get("flows"):
            ribbon.append(f'<b>+{int(c["flows"])}</b> flow spins')
        ribbon_html = f'<div class="ribbon">{" · ".join(ribbon) or e(c.get("reward",""))}</div>'
        added = f'Added {e(nice_date(c["added"]))}' if c.get("added") else "Working now"
        cards.append(
            f'<li class="fcard v{i % 4}">{ribbon_html}<div class="fart" aria-hidden="true">{icon("ball", 150, "fball")}</div>'
            f'<div class="fbody">{tag}<div class="flabel">Redeem this code in Blue Lock: Rivals</div>{code_box(c["code"], True)}'
            f'<div class="fmeta">{e(reward_text(c))} · {added}</div></div></li>')
    return '<ul class="fcards">' + "".join(cards) + "</ul>"


def alerts_form(variant="panel"):
    ep = e(SITE.get("alerts_endpoint", ""))
    uid = "al-" + variant
    return f"""<div class="alerts-wrap"><form class="alerts-form {variant}" data-endpoint="{ep}" novalidate>
<label class="sr" for="{uid}">Email address</label>
<div class="af-row"><input id="{uid}" name="email" type="email" inputmode="email" autocomplete="email" placeholder="you@example.com" required>
<button type="submit">{icon("bell", 18)}<span>Notify me</span></button></div>
<input class="hp" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">
<p class="af-msg" role="status" aria-live="polite"></p>
<p class="af-note">One email per new code. Confirm by email, unsubscribe in one click. <a href="/privacy-policy.html">Privacy</a></p>
</form>
<div class="push-box {variant}" data-endpoint="{ep}" hidden>
<div class="push-or"><span>or</span></div>
<button class="push-btn" type="button">{icon("bell", 18)}<span class="push-label">Turn on browser notifications</span></button>
<p class="push-msg" role="status" aria-live="polite"></p></div></div>"""


def copy_button(code, label="Copy"):
    return f'<button class="copy" type="button" data-copy="{e(code)}" aria-label="Copy code {e(code)}">{e(label)}</button>'


def tickets(codes):
    if not codes:
        return ('<div class="empty"><strong>No working codes right now.</strong> New codes usually arrive with the '
                'Saturday update, and this list updates itself as soon as one is confirmed. '
                '<a href="/next-update/">See when the next update lands</a>.</div>')
    rows = []
    for c in codes:
        new_tag = '<span class="tag-new">New</span>' if is_new(c) else ""
        added = f' <span class="added">· added {e(nice_date(c["added"]))}</span>' if c.get("added") else ""
        rows.append(f'<li class="ticket">{code_box(c["code"])}<div class="ticket-meta">{new_tag}{reward_chips(c)}{added}</div></li>')
    return '<ul class="tickets">' + "".join(rows) + "</ul>"


def copy_all_button():
    if len(ACTIVE) < 2:
        return ""
    allcodes = "\n".join(c["code"] for c in ACTIVE)
    return f'<button class="btn" type="button" data-copy="{e(allcodes)}" data-copy-all>Copy all {len(ACTIVE)} codes</button>'


def expired_list(limit=None):
    items = EXPIRED if limit is None else EXPIRED[:limit]
    return '<ul class="expired-list">' + "".join(f"<li>{e(c['code'])}</li>" for c in items) + "</ul>"


def rarity_badge(r):
    return f'<span class="rarity r-{slug(r)}">{e(r)}</span>'


def styles_by_rarity():
    return "".join(
        f'<div class="rgroup" id="{slug(r)}"><h3>{rarity_badge(r)}<small>{len(n)} styles</small></h3><p>{e(", ".join(n))}</p></div>'
        for r, n in STYLES["rarities"].items())


def styles_table():
    rows = "".join(f"<tr><td><strong>{e(n)}</strong></td><td>{rarity_badge(r)}</td><td>{e(tier_of(n, 'styles') or '—')}</td></tr>"
                   for r, names in STYLES["rarities"].items() for n in names)
    return ('<div class="table-wrap"><table><thead><tr><th>Style</th><th>Rarity</th><th>Tier</th></tr></thead><tbody>'
            + rows + "</tbody></table></div>")


def flows_table():
    rows = "".join(f"<tr><td><strong>{e(f['name'])}</strong></td><td>{rarity_badge(f['rarity'])}</td>"
                   f"<td>{e(f['effect'])}</td><td>{e(tier_of(f['name'], 'flows') or '—')}</td></tr>" for f in FLOWS["flows"])
    return ('<div class="table-wrap"><table><thead><tr><th>Flow</th><th>Rarity</th><th>What it does</th><th>Tier</th></tr>'
            '</thead><tbody>' + rows + "</tbody></table></div>")


def tier_of(name, kind):
    for t, names in TIERS[kind].items():
        if name in names:
            return t
    return None


def rarity_of(name):
    for r, names in STYLES["rarities"].items():
        if name in names:
            return r
    return None


def tier_block(kind):
    return '<ul class="tiers">' + "".join(
        f'<li class="tier t-{e(t)}"><div class="tier-badge" aria-label="{e(t)} tier">{e(t)}</div><p>{e(", ".join(n))}</p></li>'
        for t, n in TIERS[kind].items()) + "</ul>"


def updates_timeline(limit=None):
    ups = sorted(UPDATES["updates"], key=lambda u: u["date"], reverse=True)[:limit]
    items = []
    for u in ups:
        codes = ", ".join(e(c) for c in u.get("codes", []))
        items.append(f'<li><time datetime="{e(u["date"])}">{e(nice_date(u["date"]))}</time><strong>{e(u["name"])}</strong>'
                     + (f'<span class="muted">Codes: {codes}</span>' if codes else "") + "</li>")
    return '<ul class="timeline">' + "".join(items) + "</ul>"


def faq_html(items):
    return '<div class="faq">' + "".join(f"<details><summary>{e(q)}</summary><p>{a}</p></details>" for q, a in items) + "</div>"


def toc(items):
    return ""


def block(id_, title, body):
    return f'<section class="block" id="{e(id_)}"><h2>{title}</h2>{body}</section>'


GROUP = lambda: e(SITE["roblox_group_url"])
GAME = lambda: e(SITE["roblox_url"])

REDEEM_STEPS = [
    ("Join the Blue Lock Rivals Roblox group",
     "Codes only work for members of the developer's group. Open the <a href=\"{group}\" target=\"_blank\" rel=\"noopener\">group page</a> and press Join Community."),
    ("Reach level 10", "New accounts can't redeem. A few matches is usually enough to get there."),
    ("Open the Codes menu", "Launch <a href=\"{game}\" target=\"_blank\" rel=\"noopener\">Blue Lock: Rivals</a> and press the Codes button in the lobby."),
    ("Paste the code and redeem", "Copy a code from this page, paste it into the box and press Redeem. Your spins arrive instantly."),
]


def redeem_steps():
    return '<ol class="steps">' + "".join(
        f"<li><div><strong>{e(t)}</strong>{d.format(group=GROUP(), game=GAME())}</div></li>" for t, d in REDEEM_STEPS) + "</ol>"


def guide_cards(exclude=None):
    cards = [p for p in PAGES if p.get("blurb") and p["path"] != exclude]
    return '<ul class="links two">' + "".join(
        f'<li><a href="{e(p["path"])}">{e(p["short"])}</a><span>{e(p["blurb"])}</span></li>' for p in cards) + "</ul>"


def related(page):
    picks = [p for k in (page.get("related") or []) for p in PAGES if p["path"] == k]
    if not picks:
        return ""
    return block("related", "Related guides", '<ul class="links">' + "".join(
        f'<li><a href="{e(p["path"])}">{e(p["short"])}</a><span>{e(p.get("blurb") or "Every working code right now.")}</span></li>'
        for p in picks) + "</ul>")


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #

def sidebar(page):
    a = SITE["author"]
    initials = "".join(w[0] for w in a.split()[:2]).upper()
    avatar = ('<img src="/assets/author.jpg" width="48" height="48" alt="" loading="lazy">'
              if (ASSETS / "author.jpg").exists() else e(initials))
    guides = "".join(f'<li><a href="{e(p["path"])}">{e(p["short"])}</a></li>'
                     for p in PAGES if p.get("blurb") and p["path"] != page["path"])
    alerts = "" if page["path"].startswith("/alerts/") else (
        f'<div class="panel alerts-panel"><h3>{icon("bell", 18)} Get new code alerts</h3>'
        f'<p class="status">Be first to redeem. Get an email or a browser notification the moment a new code goes live.</p>{alerts_form("side")}</div>')
    return f"""<aside>
{alerts}
<div class="panel tracker"><h3><span class="live" aria-hidden="true"></span>Code tracker</h3>
<p class="status">Last checked <b><time data-rel datetime="{e(CHECKED)}">{e(nice_date(CHECKED))}</time></b></p>
<p class="status"><b>{len(ACTIVE)}</b> working and <b>{len(EXPIRED)}</b> expired codes tracked. The list is rechecked every 30 minutes.</p>
<p class="status"><a href="/next-update/">Next update countdown</a></p></div>
{ad("sidebar")}
<div class="panel tips-panel"><h3>Quick tips</h3><ul class="tips">
<li><strong>Redeem fast.</strong> Codes can stop working within days.</li>
<li><strong>Copy, don't type.</strong> Codes are case-sensitive.</li>
<li><strong>They stack.</strong> Every working code redeems on the same account.</li>
<li><strong>Check on Saturdays.</strong> Most updates and codes land then.</li></ul></div>
<div class="panel guides-panel"><h3>Guides</h3><ul class="linklist">{guides}</ul></div>
<div class="panel author-panel"><div class="author"><div class="avatar">{avatar}</div><div>
<strong><a href="{e(SITE['author_url'])}">{e(a)}</a></strong><span class="muted role">{e(SITE['author_role'])}</span></div></div>
<p class="status" style="margin-top:12px">New codes are published only after two independent sources confirm them. <a href="{e(SITE['author_url'])}">About the author</a></p></div>
</aside>"""


def json_ld(page):
    url = ABS + page["path"]
    graph = [
        {"@type": "Organization", "@id": ABS + "/#org", "name": SITE["name"], "url": ABS + "/",
         "logo": {"@type": "ImageObject", "url": ABS + "/apple-touch-icon.png", "width": 180, "height": 180},
         "email": SITE["contact_email"]},
        {"@type": "WebSite", "@id": ABS + "/#website", "url": ABS + "/", "name": SITE["name"],
         "description": SITE.get("tagline", ""), "publisher": {"@id": ABS + "/#org"}, "inLanguage": "en"},
        {"@type": "Person", "@id": ABS + "/#author", "name": SITE["author"], "url": ABS + SITE["author_url"],
         "image": ABS + "/assets/author.jpg", "jobTitle": SITE["author_role"],
         "worksFor": {"@id": ABS + "/#org"}, **({"sameAs": [u for _, u in SITE["author_profiles"]]} if SITE.get("author_profiles") else {})},
        {"@type": page.get("schema_type", "Article"), "@id": url + "#article", "headline": page["title"],
         "description": page["description"], "url": url, "inLanguage": "en",
         "image": ABS + "/og.png", "datePublished": SITE.get("published", "2024-11-20"),
         "dateModified": (page.get("modified") or UPDATED).isoformat(),
         "author": {"@id": ABS + "/#author"}, "publisher": {"@id": ABS + "/#org"},
         "isPartOf": {"@id": ABS + "/#website"}, "mainEntityOfPage": url},
    ]
    if page.get("schema_type") == "ProfilePage":
        graph[-1]["mainEntity"] = {"@id": ABS + "/#author"}
    if page["path"] != "/":
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Blue Lock Rivals Codes", "item": ABS + "/"},
            {"@type": "ListItem", "position": 2, "name": page["short"], "item": url}]})
    if page.get("faq"):
        graph.append({"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": re.sub("<[^>]+>", "", a)}}
            for q, a in page["faq"]]})
    if page["path"] == "/" and ACTIVE:
        graph.append({"@type": "ItemList", "name": f"Working Blue Lock Rivals codes ({MONTH_YEAR})",
                      "numberOfItems": len(ACTIVE), "itemListElement": [
                          {"@type": "ListItem", "position": i + 1, "name": c["code"], "description": reward_text(c)}
                          for i, c in enumerate(ACTIVE)]})
    if page.get("howto"):
        graph.append({"@type": "HowTo", "name": "How to redeem Blue Lock Rivals codes", "totalTime": "PT2M",
                      "step": [{"@type": "HowToStep", "position": i + 1, "name": t,
                                "text": re.sub("<[^>]+>", "", d.format(group="", game=""))}
                               for i, (t, d) in enumerate(REDEEM_STEPS)]})
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


def head(page):
    url = ABS + page["path"]
    title, desc = page["title"], page["description"]
    adsense = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={e(SITE["adsense_client"])}" '
               'crossorigin="anonymous"></script>' if SITE.get("ads_enabled") else "")
    robots = "noindex,follow" if PREVIEW or page.get("noindex") else "index,follow,max-image-preview:large,max-snippet:-1"
    mod = (page.get("modified") or UPDATED).isoformat()
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{e(url)}">
<meta name="theme-color" content="#0B0B10">
<meta name="google-adsense-account" content="{e(SITE['adsense_client'])}">
<meta name="author" content="{e(SITE['author'])}">
<meta property="og:type" content="article"><meta property="og:site_name" content="{e(SITE['name'])}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}"><meta property="og:locale" content="en_US">
<meta property="og:image" content="{e(ABS)}/og.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Blue Lock Rivals codes for {e(MONTH_YEAR)}">
<meta property="article:published_time" content="{e(SITE.get('published', '2024-11-20'))}"><meta property="article:modified_time" content="{e(mod)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}"><meta name="twitter:image" content="{e(ABS)}/og.png">
<link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="alternate" type="application/rss+xml" title="New Blue Lock Rivals codes" href="/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@600;700&display=swap">
<link rel="stylesheet" href="/assets/style.css?v={int(NOW.timestamp())}">
<script type="application/ld+json">{json_ld(page)}</script>
{adsense}</head>"""


def header(page):
    any_new = any(is_new(c) for c in ACTIVE)
    def badge(b):
        if not b or (b == "NEW" and not any_new):
            return ""
        return f'<em class="badge b-{b.lower()}">{e(b)}</em>'
    nav = "".join(
        f'<a href="{e(u)}"{" aria-current=page" if u == page["path"] else ""}>{icon(i, 22)}<span>{e(t)}</span>{badge(b)}</a>'
        for i, t, u, b in NAV2)
    cta = f'<a class="cta" href="/free-spins/">{icon("plus", 20)}<span>Get free spins</span></a>'
    index = "".join(f'<li data-cat="guides"><a href="{e(p["path"])}">{e(p["short"])}</a></li>'
                    for p in PAGES if p["path"] not in ("/privacy-policy.html",) and not p.get("noindex"))
    index += "".join(f'<li data-cat="codes"><a href="/">Code: {e(c["code"])} ({e(reward_text(c))})</a></li>' for c in ACTIVE)
    return f"""<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="wrap topbar">
<a class="logo" href="/" title="{e(SITE['name'])}"><span class="logo-word">Blue Lock Rivals</span><span class="logo-tag">Codes</span></a>
<div class="search" role="search"><label class="sr" for="q">Search the site</label>
<input id="q" type="search" placeholder="What are you looking for?" autocomplete="off">
<label class="sr" for="qcat">Search in</label>
<div class="search-cat"><select id="qcat"><option value="">All</option><option value="codes">Codes</option><option value="guides">Guides</option></select>{icon("chev", 16)}</div>
<button class="search-btn" type="button" aria-label="Search">{icon("search", 22)}</button>
<ul class="search-results" hidden>{index}</ul></div>
<div class="actions-top">
<a class="round" href="{e(SITE['discord_url'])}" target="_blank" rel="noopener" title="Official Discord">{icon("chat", 22)}<span class="sr">Official Discord</span></a>
<a class="round" href="/alerts/" title="Get new code alerts">{icon("bell", 22)}<span class="sr">Get new code alerts</span></a>
<a class="play" href="{e(SITE['roblox_url'])}" target="_blank" rel="noopener"><span class="round">{icon("play", 22)}</span><span class="play-txt"><b>Play</b><b>on Roblox</b></span></a>
</div>
<button class="menu-btn" type="button" aria-expanded="false" aria-controls="nav">Menu</button></div>
<div class="navrow"><nav class="nav wrap" id="nav" aria-label="Main">{nav}{cta}</nav></div></header>"""


def footer():
    order = ["/", "/expired-codes/", "/how-to-redeem/", "/codes-not-working/", "/free-spins/", "/styles/", "/flows/",
             "/tier-list/", "/controls/", "/beginners-guide/", "/next-update/", "/updates/", "/alerts/", "/trello-discord/",
             "/about/", "/privacy-policy.html"]
    links = "".join(f'<a href="{e(p["path"])}">{e(p["short"])}</a>' for path in order for p in PAGES if p["path"] == path)
    return f"""<footer><div class="wrap"><nav aria-label="Footer">{links}</nav>
<p>{e(SITE['domain'])} is an independent fan site, not affiliated with Roblox Corporation, {e(SITE['developer'])}, Kodansha or the creators of Blue Lock. Contact: <a href="mailto:{e(SITE['contact_email'])}">{e(SITE['contact_email'])}</a>. © {YEAR}.</p>
</div></footer><script src="/assets/app.js" defer></script>"""


def byline(page):
    mod = page.get("modified") or UPDATED
    checked = ""
    if page["path"] == "/":
        checked = f' · Codes checked <time data-rel datetime="{e(CHECKED)}">{e(nice_date(CHECKED))}</time>'
    return (f'<p class="byline">Updated <time datetime="{e(mod.isoformat())}">{e(nice_date(mod))}</time> by '
            f'<a href="{e(SITE["author_url"])}" rel="author">{e(SITE["author"])}</a>{checked}</p>')


def hero(page):
    if page["path"] == "/":
        return f"""<section class="stage"><div class="wrap">
<div class="stage-head"><h1>Blue Lock Rivals Codes <span>({e(MONTH_YEAR)})</span></h1>
<p class="lede">Every working code for Blue Lock: Rivals on Roblox, checked every 30 minutes.</p>{byline(page)}</div>
{feature_cards()}</div></section>{tiles()}"""
    crumbs = (f'<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span aria-hidden="true">/</span>{e(page["short"])}</nav>')
    return f"""<section class="stage stage-sm"><div class="wrap"><div class="stage-head">{crumbs}<h1>{e(page["h1"])}</h1>
<p class="lede">{page["lede"]}</p>{byline(page)}</div></div></section>"""


def render(page):
    body = page["body"]() if callable(page["body"]) else page["body"]
    body += related(page)
    if page.get("sidebar", True):
        layout = f'<div class="wrap layout"><main id="main">{body}</main>{sidebar(page)}</div>'
    else:
        layout = f'<div class="wrap layout single"><main id="main">{body}</main></div>'
    return with_base(head(page) + f'<body data-base="{BASE}">' + header(page) + hero(page) + layout + footer() + "</body></html>")


# --------------------------------------------------------------------------- #
# Page bodies
# --------------------------------------------------------------------------- #

def codes_answer():
    if not ACTIVE:
        return (f'<p class="answer">There are no working Blue Lock Rivals codes right now ({e(nice_date(NOW))}). '
                'New codes usually come with the Saturday update.</p>')
    names = join_and(f"<strong>{e(c['code'])}</strong>" for c in ACTIVE)
    return (f'<p class="answer">As of {e(nice_date(NOW))}, there {"is" if len(ACTIVE) == 1 else "are"} '
            f'{len(ACTIVE)} working Blue Lock Rivals code{"" if len(ACTIVE) == 1 else "s"}: {names}. '
            f'Together they give {TOTAL_SPINS} Lucky Style Spins and {TOTAL_FLOWS} Lucky Flow Spins.</p>')


HOME_FAQ = [
    ("What are the newest Blue Lock Rivals codes?",
     "The newest codes are always at the top of the list on this page, marked New. The list is rechecked every 30 minutes."),
    ("Why do Blue Lock Rivals codes say invalid?",
     "Usually because the code expired, you already used it, you haven't joined the developer's Roblox group, or your account is below level 10. "
     "<a href=\"/codes-not-working/\">See every fix</a>."),
    ("How often do new Blue Lock Rivals codes come out?",
     "About once a week. Most updates go live on Saturday and bring two or three codes, with extra codes for milestones and events."),
    ("Do Blue Lock Rivals codes give Robux?", "No. Codes give Lucky Style Spins and Lucky Flow Spins. Anyone offering Robux or spins for a code is running a scam."),
    ("Do spins from codes expire?", "No. Once redeemed, the spins stay in your inventory until you use them. Only the code itself expires."),
    ("Can I use the same code on more than one account?", "Yes. Each code works once per Roblox account, so alts can redeem it too if they meet the group and level requirements."),
    ("Is this site official?", f"No. {e(SITE['domain'])} is an independent fan site and isn't affiliated with Roblox or the game's developer."),
]


def home_body():
    return (toc([("codes", "Working codes"), ("redeem", "How to redeem"), ("not-working", "Code not working?"),
                 ("release", "When new codes drop"), ("expired", "Expired codes"), ("faq", "FAQ")])
            + block("codes", "Working Blue Lock Rivals codes today",
                    codes_answer() + tickets(ACTIVE) + f'<div class="actions">{copy_all_button()}</div>')
            + f'<section class="alerts-band" id="alerts"><div><h2>Never miss a code</h2><p>Get an email or a browser notification the moment a new Blue Lock Rivals code drops. Free, one alert per code, turn it off anytime.</p></div>{alerts_form("band")}</section>'
            + ad("in-content")
            + block("redeem", "How to redeem codes in Blue Lock Rivals",
                    redeem_steps() + '<p style="margin-top:16px">More detail, including where the Codes button is on mobile and console, is in the <a href="/how-to-redeem/">full redeem guide</a>.</p>')
            + block("not-working", "Why your code isn't working",
                    '<div class="prose"><p>Almost every failed code comes down to one of five things:</p><ul>'
                    '<li>You haven\'t joined the developer\'s <a href="' + GROUP() + '" target="_blank" rel="noopener">Roblox group</a>.</li>'
                    '<li>Your account is below level 10.</li><li>The code has expired.</li>'
                    '<li>You already redeemed it on this account.</li><li>A typo or wrong capital letter.</li></ul>'
                    '<p>The <a href="/codes-not-working/">codes not working guide</a> walks through each fix.</p></div>')
            + block("release", "When are new codes released?",
                    '<div class="prose"><p>The developer usually releases new codes with each weekly update, which normally goes live on '
                    '<strong>Saturday around 10 AM Pacific time</strong>. Codes also appear for like and visit milestones, apologies for delays, and seasonal events.</p>'
                    '<p>Check the <a href="/next-update/">next update countdown</a> for the exact time in your time zone, or the <a href="/updates/">update log</a> to see which codes came with each update.</p></div>'
                    + updates_timeline(3))
            + block("expired", "Expired Blue Lock Rivals codes",
                    f'<p>These {len(EXPIRED)} codes no longer work. They are listed so you don\'t waste time trying them.</p>'
                    + expired_list(24)
                    + f'<details class="more"><summary>Show all {len(EXPIRED)} expired codes</summary>{expired_list()}</details>')
            + block("guides", "Guides", guide_cards())
            + block("faq", "Blue Lock Rivals codes FAQ", faq_html(HOME_FAQ)))


NOT_WORKING_FAQ = [
    ("Why does it say I must be in the group?",
     f"Blue Lock: Rivals only accepts codes from members of the developer's Roblox group. <a href=\"{GROUP()}\" target=\"_blank\" rel=\"noopener\">Join it</a>, then rejoin the game."),
    ("I joined the group and it still fails. Why?", "Leave the game and join a new server. The group check happens when you load in, so the old session doesn't know you joined."),
    ("Why did a code work for my friend but not me?", "Usually your friend redeemed it before it expired, or you've used it already on your account. It can also be the group or level 10 requirement on your account only."),
]


def not_working_body():
    fixes = [
        ("group", "You haven't joined the group", f'This is the most common cause. Open the <a href="{GROUP()}" target="_blank" rel="noopener">Blue Lock Rivals Roblox group</a>, press Join Community, then leave and rejoin the game so it picks up your membership.'),
        ("level", "You're below level 10", "The Codes menu only accepts codes from level 10 onwards. Play a few matches, then try again."),
        ("expired", "The code expired", 'Codes can stop working without warning, sometimes within a day. Check the <a href="/expired-codes/">expired list</a>. If it\'s there, it won\'t come back.'),
        ("used", "You already redeemed it", "Each code works once per account. If you used it before, the game rejects it even though it still works for others."),
        ("typo", "A typo or wrong capitals", "Codes are case-sensitive and some include symbols like <code>!</code>. Use the Copy button on this site, and check there's no space at the end."),
        ("server", "The server hasn't updated", "Right after an update, older servers may not know about new codes yet. Join a fresh server and try again."),
    ]
    out = toc([(i, t) for i, t, _ in fixes] + [("faq", "FAQ")])
    out += block("checklist", "Quick checklist",
                 '<div class="prose"><ol>' + "".join(f'<li><a href="#{i}">{e(t)}</a></li>' for i, t, _ in fixes) + "</ol>"
                 f'<p>Want codes that work right now? There are <a href="/">{len(ACTIVE)} working codes</a> today.</p></div>')
    for i, t, d in fixes:
        out += block(i, e(t), f'<div class="prose"><p>{d}</p></div>')
    out += block("faq", "Still not working?", faq_html(NOT_WORKING_FAQ))
    return out


REDEEM_FAQ = [
    ("How do I join the Blue Lock Rivals group?",
     f"Open the <a href=\"{GROUP()}\" target=\"_blank\" rel=\"noopener\">group page on Roblox</a> and press Join Community. It's free and instant."),
    ("What level do you need to redeem codes?", "Level 10. Below that, the Codes menu rejects every code."),
    ("Where do you put codes in Blue Lock Rivals?", "In the Codes menu in the lobby. Press the Codes button, paste the code in the box and press Redeem."),
    ("Can I redeem codes on mobile or console?", "Yes. The Codes button is in the lobby on PC, phone, tablet, Xbox and PlayStation."),
]


def redeem_body():
    return (toc([("steps", "Steps"), ("group", "Join the group"), ("platforms", "PC, mobile and console"),
                 ("requirements", "Requirements"), ("faq", "Troubleshooting")])
            + block("steps", "How to redeem codes in Blue Lock Rivals", redeem_steps())
            + block("group", "How to join the Blue Lock Rivals group",
                    f'<div class="prose"><p>The group requirement catches out more players than anything else. Open the <a href="{GROUP()}" target="_blank" rel="noopener">Blue Lock Rivals Unofficial Fans group</a> on Roblox and press <strong>Join Community</strong>. Then leave and rejoin the game. Your membership is checked when you load in.</p></div>')
            + block("platforms", "Where to put codes on PC, mobile and console",
                    '<div class="prose"><p>The Codes button sits in the lobby menu on every platform. On <strong>PC</strong>, click it and paste with Ctrl+V. On <strong>mobile</strong>, tap it, long-press the box and choose Paste. On <strong>Xbox and PlayStation</strong>, select it and type the code with the on-screen keyboard, carefully matching capitals.</p></div>')
            + block("requirements", "Requirements checklist",
                    '<div class="prose"><ul><li>Member of the official Roblox group</li><li>Account level 10 or higher</li>'
                    '<li>The code is on the <a href="/">working list</a> and you haven\'t used it before</li>'
                    '<li>Copied exactly, including any <code>!</code></li></ul>'
                    '<p>Still stuck? Read <a href="/codes-not-working/">why codes don\'t work</a>.</p></div>')
            + block("faq", "Troubleshooting", faq_html(REDEEM_FAQ)))


def spins_body():
    return (toc([("ways", "Every free source"), ("lucky", "Lucky vs normal"), ("chances", "Chances and pity"),
                 ("level", "Level up faster"), ("before", "Before you spin"), ("scripts", "Spin scripts")])
            + block("ways", "Every way to get free spins in Blue Lock Rivals",
                    f'<div class="prose"><h3>Redeem codes</h3><p>The fastest source. Each new code usually gives 5 Lucky Style Spins, 5 Lucky Flow Spins, or both. Right now the <a href="/">working codes</a> add up to <strong>{TOTAL_SPINS} style spins and {TOTAL_FLOWS} flow spins</strong>.</p>'
                    '<h3>Play matches for Yen</h3><p>Matches pay out Yen, the in-game currency. A normal Flow spin costs 2,000 Yen, so regular play keeps you rolling for free.</p>'
                    '<h3>Quests and level rewards</h3><p>Levelling up and event quests regularly award spins. Check the quest board after every update.</p>'
                    '<h3>Live events</h3><p>Seasonal events and mid-week drops often include extra spins and limited-time styles.</p>'
                    '<h3>Robux</h3><p>Spin bundles can be bought, but never need to be. If you do buy, wait for a fresh update so your rolls cover the newest styles.</p></div>')
            + block("lucky", "Lucky spins vs normal spins",
                    '<div class="prose"><p>Lucky spins, the kind codes give, roll with much better odds of high-rarity results than normal spins. Save them for when you actually want an upgrade.</p></div>')
            + block("chances", "Spin chances and pity",
                    '<div class="prose"><p>World Class and Master styles are rare drops, well under 1% on a normal spin, and Lucky spins raise those odds substantially. Flows have a pity system: <strong>after 50 Flow spins you\'re guaranteed at least a Legendary</strong>.</p>'
                    '<p>The developer adjusts rates between updates, so check the in-game spin screen for the exact current odds.</p></div>')
            + block("level", "How to level up fast for more rewards",
                    '<div class="prose"><ul><li>Play full matches. Leaving early cuts your rewards.</li><li>Complete daily and event quests first; they pay far more than single matches.</li>'
                    '<li>Play with friends so you can coordinate, win more and finish quests together.</li><li>Reach level 10 early, since that unlocks code redemption.</li></ul></div>')
            + block("before", "Before you spin",
                    '<div class="prose"><ul><li><strong>Lock your slot</strong> if you own a style you want to keep, or a spin can replace it.</li>'
                    '<li>Check the <a href="/tier-list/">tier list</a> so you know which results are worth keeping.</li>'
                    '<li>Spin right after a Saturday update for a shot at the newest style.</li></ul></div>')
            + block("scripts", "Are spin scripts or generators safe?",
                    '<div class="prose"><p>No. "Infinite spins" scripts and spin generators break Roblox rules and can get your account banned. Many of them are built to steal accounts. The only free spins are from codes, play, quests and events.</p></div>'))


def styles_body():
    return (toc([("what", "What styles are"), ("by-rarity", "By rarity"), ("list", "Full list"),
                 ("limited", "Limited styles"), ("nel", "NEL styles"), ("ladder", "Rarity ladder")])
            + block("what", "What are styles in Blue Lock Rivals?",
                    f'<div class="prose"><p>A style is your player kit. It sets your three active abilities (C, V and B on PC), your awakening, and which flows suit you best. You get styles by spinning, and rarer styles are stronger and harder to roll.</p>'
                    f'<p>There are <strong>{REGULAR_STYLES} regular styles</strong> across six rarities, plus <strong>{LIMITED_STYLES} limited event styles</strong>.</p></div>')
            + block("by-rarity", "Every Blue Lock Rivals style by rarity", styles_by_rarity())
            + ad("in-content")
            + block("list", "Blue Lock Rivals styles list",
                    styles_table() + f'<p class="muted">Rarities last verified {e(nice_date(STYLES["verified"]))}. Tiers are from our <a href="/tier-list/">tier list</a>.</p>')
            + block("limited", "Limited event styles",
                    '<div class="prose"><p>Limited styles are seasonal versions, such as Halloween and winter variants, that can only be rolled while their event runs. When the event ends they leave the spin pool, so roll during the event if you want one.</p></div>')
            + block("nel", "How to get NEL styles",
                    '<div class="prose"><p>NEL styles are upgraded versions of familiar characters and all sit at World Class rarity, below only Master. They come from the style spin pool, so the best way to get one is to stack Lucky Style Spins from <a href="/">codes</a> and spin them together.</p></div>')
            + block("ladder", "Rarity ladder",
                    f'<div class="prose"><p>From most common to rarest: {rarity_badge("Rare")} {rarity_badge("Epic")} {rarity_badge("Legendary")} {rarity_badge("Mythic")} {rarity_badge("World Class")} {rarity_badge("Master")}. {rarity_badge("Limited")} styles are event exclusives.</p></div>'))


def flows_body():
    return (toc([("what", "What flows are"), ("list", "All flows"), ("best", "Best flow by role"), ("get", "How to get flows")])
            + block("what", "What are flows in Blue Lock Rivals?",
                    '<div class="prose"><p>Flows are temporary power-ups. A flow meter fills as you play, and once it reaches 30% you can activate it (G on PC) for boosts like extra speed, harder shots, extra dribbles or shorter cooldowns.</p></div>')
            + block("list", f"All {len(FLOWS['flows'])} Blue Lock Rivals flows",
                    flows_table() + f'<p class="muted">Last verified {e(nice_date(FLOWS["verified"]))}.</p>')
            + ad("in-content")
            + block("best", "Best flow for each playstyle",
                    '<div class="prose"><ul><li><strong>Strikers:</strong> Emperor, Destructive Impulses and Godspeed boost shot power and speed.</li>'
                    '<li><strong>Dribblers:</strong> Butterfly Dancer and Bee Freestyle add dribbles and stronger ankle breaks.</li>'
                    '<li><strong>Playmakers:</strong> Awakened Genius, Contrarian and Genius give Flow to teammates.</li>'
                    '<li><strong>Defenders:</strong> King\'s Authority and Snake shorten tackle cooldowns.</li>'
                    '<li><strong>Style-specific:</strong> Trap pairs with Nagi, Singularity with NEL Nagi, and Master of all Trades with Chameleon users.</li></ul>'
                    '<p>For the overall ranking, see the <a href="/tier-list/#flows">flow tier list</a>.</p></div>')
            + block("get", "How to get flows and flow pity",
                    '<div class="prose"><p>Flow spins cost 2,000 Yen each, or use Lucky Flow Spins from <a href="/">codes</a>. After 50 Flow spins without one, you\'re guaranteed a Legendary or better.</p></div>'))


def tier_body():
    s, f = TIERS["styles"], TIERS["flows"]
    best = s["S"][0] if s.get("S") else ""
    mythic = [n for t in ("S", "A", "B") for n in s.get(t, []) if rarity_of(n) == "Mythic"]
    nel = [n for t in ("S", "A", "B") for n in s.get(t, []) if n.startswith("NEL ")]
    legendary = [n for t in ("S", "A", "B", "C") for n in s.get(t, []) if rarity_of(n) in ("Legendary", "Epic")]
    return (toc([("styles", "Style tier list"), ("best", "Best style"), ("best-mythic", "Best Mythic"),
                 ("best-nel", "Best NEL"), ("f2p", "Best free pick"), ("flows", "Flow tier list"), ("team", "Best team")])
            + block("styles", f"Blue Lock Rivals style tier list ({e(MONTH_YEAR)})",
                    f'<p class="muted">{e(TIERS["note"])} Last reviewed {e(nice_date(TIERS["updated"]))}.</p>' + tier_block("styles"))
            + block("best", "Best style in Blue Lock Rivals",
                    f'<div class="prose"><p><strong>{e(best)}</strong> tops the list right now, with {e(join_and(s["S"][1:4]))} close behind. S-tier styles are World Class or Master rarity, so they are rare rolls. Stack Lucky Style Spins from <a href="/">codes</a> before going for one.</p></div>')
            + block("best-mythic", "Best Mythic style",
                    f'<div class="prose"><p>{e(join_and(mythic[:3]))} are the strongest Mythic picks. Mythic styles are far easier to roll than World Class and still compete in ranked.</p></div>')
            + block("best-nel", "Best NEL style",
                    f'<div class="prose"><p>Of the NEL styles, {e(join_and(nel[:3]))} rank highest. All NEL styles are World Class rarity.</p></div>')
            + block("f2p", "Best free-to-play pick",
                    f'<div class="prose"><p>If you haven\'t rolled anything rare yet, {e(join_and(legendary[:3]))} are the best of the common rarities. They are easier to roll and good enough to learn the game with.</p></div>')
            + ad("in-content")
            + block("flows", "Blue Lock Rivals flow tier list", tier_block("flows")
                    + f'<p style="margin-top:14px">{e(join_and(f["S"]))} are the strongest flows. See <a href="/flows/">what every flow does</a>.</p>')
            + block("team", "Best team composition",
                    '<div class="prose"><p>A strong five usually has <strong>two finishers</strong> (shot-power styles with Emperor or Destructive Impulses), <strong>one or two playmakers</strong> carrying a team-Flow flow like Awakened Genius, and <strong>one defender</strong> with a tackle-cooldown flow like King\'s Authority or Snake.</p>'
                    '<p>Balance changes land almost weekly, so treat rankings as a guide. A well-played B-tier style beats a badly played S-tier one.</p></div>'))


def controls_body():
    rows = [("Move", "W A S D"), ("Aim", "Mouse"), ("Shoot (hold to charge)", "Left mouse button"),
            ("Dribble", "Q"), ("Tackle", "F"), ("Style abilities", "C, V, B"), ("Activate flow", "G")]
    table = ('<div class="table-wrap"><table><thead><tr><th>Action</th><th>PC key</th></tr></thead><tbody>'
             + "".join(f"<tr><td><strong>{e(a)}</strong></td><td><code>{e(b)}</code></td></tr>" for a, b in rows) + "</tbody></table></div>")
    note = '<p class="muted">Bindings can change between weekly updates. Open Settings in-game to see your exact layout.</p>'
    return (toc([("pc", "PC"), ("xbox", "Xbox"), ("playstation", "PS5 and PS4"), ("mobile", "Mobile"), ("settings", "Best settings")])
            + block("pc", "Blue Lock Rivals PC controls", table + note)
            + block("xbox", "Blue Lock Rivals Xbox controls",
                    '<div class="prose"><p>The left stick moves your player and the right stick controls the camera. Shooting, passing and dribbling sit on the triggers and bumpers, and your three style abilities and flow are on the face buttons and D-pad. Press the menu button and open Settings to see the full map for your controller.</p></div>')
            + block("playstation", "Blue Lock Rivals PS5 and PS4 controls",
                    '<div class="prose"><p>Blue Lock: Rivals plays on PlayStation through the Roblox app with the same layout as Xbox: movement on the left stick, camera on the right, actions on the triggers, bumpers and face buttons. Your exact bindings are listed in the in-game Settings menu.</p></div>')
            + block("mobile", "Blue Lock Rivals mobile controls",
                    '<div class="prose"><p>A virtual joystick on the left moves you, and on-screen buttons on the right handle shooting, dribbling, tackling, your three style abilities and flow. Every button can be resized and moved in Settings.</p></div>')
            + block("settings", "Best controller and mobile settings",
                    '<div class="prose"><ul><li><strong>PC:</strong> turn on shift lock so the camera stays behind you. Aiming shots and passes is much easier.</li>'
                    '<li><strong>Mobile:</strong> move C, V and B within reach of your right thumb so you never let go of the joystick. A Bluetooth controller is the biggest upgrade you can make.</li>'
                    '<li><strong>Console:</strong> raise camera sensitivity a notch so you can check behind you quickly.</li>'
                    '<li><strong>Everyone:</strong> practise in a private server to learn each style\'s cooldowns without risking your rank.</li></ul></div>'))


def beginners_body():
    return (toc([("first-hour", "Your first hour"), ("level", "Level up fast"), ("basics", "Fundamentals"), ("pro", "Get better")])
            + block("first-hour", "Your first hour in Blue Lock Rivals", """<ol class="steps">
<li><div><strong>Redeem every code</strong>Join the group, reach level 10 and redeem the <a href="/">working codes</a> for free Lucky spins.</div></li>
<li><div><strong>Roll for a style</strong>Use Lucky Style Spins first. Keep anything Mythic or better and lock the slot.</div></li>
<li><div><strong>Roll for a flow</strong>Match it to your style: shooting flows for strikers, dribble flows for wingers.</div></li>
<li><div><strong>Learn your abilities</strong>Check each ability's cooldown and practise in a casual or private match.</div></li>
<li><div><strong>Move to ranked when ready</strong>Ranked affects your standing, so learn positioning in casual games first.</div></li></ol>""")
            + block("level", "How to level up fast",
                    '<div class="prose"><ul><li>Finish matches rather than leaving early.</li><li>Clear daily and event quests first; they pay the most.</li>'
                    '<li>Queue with friends to win more and finish quests together.</li></ul></div>')
            + block("basics", "Gameplay fundamentals",
                    '<div class="prose"><ul><li><strong>Pass early.</strong> Release the ball before a defender closes in.</li>'
                    '<li><strong>Know your role.</strong> Some styles finish, some create, some defend. Play to your kit.</li>'
                    '<li><strong>Recover before you tackle.</strong> Get goal-side first; tackles from behind rarely work.</li>'
                    '<li><strong>Time your flow.</strong> Save it for a counter-attack or the closing minutes.</li>'
                    '<li><strong>Spread out.</strong> Five players on one ball means nobody is open.</li></ul></div>')
            + block("pro", "How to get better at Blue Lock Rivals",
                    '<div class="prose"><ul><li>Master one style before switching. Knowing its cooldowns matters more than its tier.</li>'
                    '<li>Watch where defenders are before you receive the ball, not after.</li>'
                    '<li>Check the <a href="/tier-list/">tier list</a> after each update, since balance changes are frequent.</li>'
                    '<li>Set up your <a href="/controls/">controls</a> so every ability is reachable without looking.</li></ul></div>'))


def next_update_body():
    latest = sorted(UPDATES["updates"], key=lambda u: u["date"], reverse=True)[0] if UPDATES["updates"] else None
    latest_html = (f'<p>The latest update was <strong>{e(latest["name"])}</strong> on {e(nice_date(latest["date"]))}.'
                   + (f' It came with {len(latest.get("codes", []))} codes.' if latest.get("codes") else "") + "</p>") if latest else ""
    zones = [("India (IST)", "Asia/Kolkata"), ("UK (London)", "Europe/London"), ("Central Europe", "Europe/Berlin"),
             ("US East (ET)", "America/New_York"), ("US West (PT)", "America/Los_Angeles"), ("Philippines", "Asia/Manila"),
             ("Brazil (Sao Paulo)", "America/Sao_Paulo"), ("Australia (Sydney)", "Australia/Sydney")]
    ztable = ('<div class="table-wrap"><table><thead><tr><th>Region</th><th>Expected update time</th></tr></thead><tbody>'
              + "".join(f'<tr><td>{e(n)}</td><td data-zone="{e(z)}">Saturday, 10 AM Pacific</td></tr>' for n, z in zones)
              + "</tbody></table></div>")
    return (toc([("countdown", "Countdown"), ("time", "Time in your zone"), ("what", "What comes with it"), ("latest", "Latest update")])
            + block("countdown", "Next Blue Lock Rivals update countdown",
                    f'<div data-countdown data-weekday="6" data-hour="{int(SITE.get("update_hour_pt", 10))}">'
                    '<div class="countdown" aria-live="polite"><div class="cd"><b data-d>-</b><span>Days</span></div>'
                    '<div class="cd"><b data-h>-</b><span>Hours</span></div><div class="cd"><b data-m>-</b><span>Minutes</span></div>'
                    '<div class="cd"><b data-s>-</b><span>Seconds</span></div></div>'
                    '<p>The next Blue Lock Rivals update is expected on <strong data-local>Saturday at 10 AM Pacific time</strong>.</p></div>'
                    '<p class="muted">This is the usual weekly slot. The developer sometimes delays an update by a few hours or skips a week, and announces that in the official Discord.</p>')
            + block("time", "Blue Lock Rivals update time in your time zone",
                    '<p>Updates normally go live on Saturday at 10 AM Pacific time. Here is that time around the world:</p>' + ztable)
            + block("what", "What comes with an update",
                    '<div class="prose"><ul><li><strong>New codes</strong>, usually two or three, which appear on <a href="/">our codes list</a> within about 30 minutes.</li>'
                    '<li>New or reworked styles and flows.</li><li>Balance changes that can shake up the <a href="/tier-list/">tier list</a>.</li>'
                    '<li>Bug fixes and quality-of-life changes.</li></ul>'
                    '<p>Some updates are teased with codes like "next week" or "soon" that hint at what\'s coming.</p></div>')
            + block("latest", "Latest Blue Lock Rivals update",
                    latest_html + updates_timeline(5) + '<p><a href="/updates/">Full update log</a></p>'))


def updates_body():
    return (block("log", "Blue Lock Rivals update log",
                  '<p>New updates are logged automatically when the game\'s title on Roblox changes. Most go live on Saturday. '
                  'See the <a href="/next-update/">next update countdown</a> for the upcoming one.</p>' + updates_timeline()))


def expired_body():
    return (block("all", f"All {len(EXPIRED)} expired Blue Lock Rivals codes",
                  f'<p>None of these codes work any more. When a working code dies it moves here automatically. Looking for codes that work? There are <a href="/">{len(ACTIVE)} working codes</a> right now.</p>'
                  + expired_list()))


def links_body():
    return (toc([("discord", "Discord"), ("trello", "Trello"), ("wiki", "Wiki"), ("group", "Roblox group"), ("safety", "Staying safe")])
            + block("discord", "Blue Lock Rivals Discord server",
                    f'<div class="prose"><p>The official <a href="{e(SITE["discord_url"])}" target="_blank" rel="noopener">Blue Lock Rivals Discord</a> is where the developer posts update news, patch notes and new codes first. It is also the best place to find teammates.</p></div>')
            + block("trello", "Blue Lock Rivals Trello board",
                    f'<div class="prose"><p>The <a href="{e(SITE["trello_url"])}" target="_blank" rel="noopener">Trello board</a> is a reference for styles, flows, mechanics and controls. It is a quick way to look up how a move works.</p></div>')
            + block("wiki", "Blue Lock Rivals wiki",
                    '<div class="prose"><p>For quick reference, this site keeps up-to-date lists of every <a href="/styles/">style</a> and <a href="/flows/">flow</a> with rarities, plus a <a href="/tier-list/">tier list</a> and an <a href="/updates/">update log</a>.</p></div>')
            + block("group", "Blue Lock Rivals Roblox group",
                    f'<div class="prose"><p>You must join the <a href="{GROUP()}" target="_blank" rel="noopener">official Roblox group</a> to redeem codes. The game page is <a href="{GAME()}" target="_blank" rel="noopener">here on Roblox</a>, and its title always shows the current update.</p></div>')
            + block("safety", "Staying safe",
                    '<div class="prose"><ul><li>Codes are always free. Anyone selling codes or spin generators is scamming you.</li>'
                    '<li>Only enter your Roblox password on roblox.com.</li><li>Only trust Discord invites linked from the official game or group page.</li></ul></div>'))


def guides_body():
    return block("all", "All Blue Lock Rivals guides", guide_cards("/guides/"))


def author_body():
    guides = [p for p in PAGES if p.get("blurb")]
    links = "".join(f'<li><a href="{e(u)}" rel="me noopener" target="_blank">{e(n)}</a></li>'
                    for n, u in SITE.get("author_profiles", []))
    return (block("profile", "About Muhammad Usman Siddiqui",
                  f'''<div class="profile"><img class="profile-photo" src="/assets/author-portrait.jpg" width="240" height="300"
alt="Photo of {e(SITE["author"])}" loading="eager"><div class="prose">
<p><strong>{e(SITE["author"])}</strong> is a Blue Lock: Rivals player and the person behind {e(SITE["name"])}. He started the site so players could find every working code in one place, without digging through Discord threads and outdated lists.</p>
<p>He maintains the automated code tracker, which checks for new codes every 30 minutes and publishes one only after two independent sources confirm it. He also writes and updates the guides on styles, flows, the tier list and controls after each weekly update.</p>
<p>Spotted a wrong code or an outdated guide? Email <a href="mailto:{e(SITE["contact_email"])}">{e(SITE["contact_email"])}</a>.</p>
{"<h3>Find him online</h3><ul>" + links + "</ul>" if links else ""}
</div></div>''')
            + block("written", "Guides by Muhammad Usman Siddiqui",
                    '<ul class="links">' + "".join(
                        f'<li><a href="{e(p["path"])}">{e(p["short"])}</a><span>{e(p["blurb"])}</span></li>' for p in guides) + "</ul>"))


ALERTS_FAQ = [
    ("How often will I get emails?", "Only when a new code goes live, usually once or twice a week. Each code is emailed once."),
    ("Do I have to confirm?", "Yes. After you sign up we send a confirmation email. You're only subscribed once you click the link in it."),
    ("How do I unsubscribe?", "Every email has an unsubscribe link at the bottom. One click and you're off the list."),
    ("How do browser notifications work?", "Click Turn on browser notifications and allow them when your browser asks. You'll get a pop-up for every new code, even when this site isn't open. Click the same button again to turn them off. On iPhone and iPad, add the site to your Home Screen first."),
    ("What do you do with my email?", "We only use it to send new code alerts. It's never sold or shared. See the <a href=\"/privacy-policy.html\">privacy policy</a>."),
]


def alerts_body():
    return (block("signup", "Get new Blue Lock Rivals codes by email or notification",
                  '<p>Enter your email and we\'ll send you every new code the moment it goes live, so you can redeem it before it expires.</p>'
                  + alerts_form("page")
                  + '<div class="prose" style="margin-top:18px"><ul><li>One email per new code, nothing else</li>'
                  '<li>Free, and confirmed by email first</li><li>Unsubscribe in one click from any email</li></ul>'
                  '<p>Prefer a feed reader? Use the <a href="/feed.xml">RSS feed</a> instead.</p></div>')
            + block("faq", "Email alerts FAQ", faq_html(ALERTS_FAQ)))


def alerts_done_body(kind):
    if kind == "confirmed":
        return block("done", "You're subscribed",
                     '<p>Thanks for confirming. The next time a new Blue Lock Rivals code goes live, it\'ll land in your inbox.</p>'
                     '<p><a class="btn" href="/">See today\'s working codes</a></p>')
    return block("done", "You're unsubscribed",
                 '<p>You won\'t get any more code alerts. Changed your mind? You can <a href="/alerts/">subscribe again</a> anytime.</p>'
                 '<p><a class="btn" href="/">See today\'s working codes</a></p>')


def about_body():
    return block("about", "About this site",
                 f'<div class="prose"><p>{e(SITE["name"])} exists so you never miss a free code for Blue Lock: Rivals. It is run by <a href="{e(SITE["author_url"])}">{e(SITE["author"])}</a>, a long-time player.</p>'
                 '<h3>How codes are checked</h3><p>An automated tracker checks the developer\'s channels and several established code trackers every 30 minutes. A new code is published only when <strong>at least two independent sources</strong> list it as working. When sources report a code as dead, or it disappears everywhere, it moves to the expired list automatically.</p>'
                 f'<p>Spotted a mistake? Email <a href="mailto:{e(SITE["contact_email"])}">{e(SITE["contact_email"])}</a> and it will be fixed.</p>'
                 f'<h3>Independence</h3><p>This is an unofficial fan site. It is not affiliated with Roblox Corporation, {e(SITE["developer"])}, Kodansha or the creators of Blue Lock.</p></div>')


def privacy_body():
    return block("privacy", "Privacy policy",
                 f'<div class="prose"><h3>What we collect</h3><p>This site has no accounts. The only personal data we collect is your email address, and only if you sign up for code alerts.</p>'
                 '<h3>Email alerts</h3><p>If you subscribe, we store your email address, the date you signed up and confirmed, and your subscription status. We use it only to send you an email when a new Blue Lock Rivals code is released. You are subscribed only after you click the link in our confirmation email (double opt-in).</p>'
                 '<h3>Browser notifications</h3><p>If you turn on browser notifications, your browser gives us a technical address for its notification service (no name or email). We store it only to send new-code alerts and delete it when you turn notifications off or the browser stops accepting them.</p>'
                 '<p>Subscriber data is stored with Supabase in the European Union (Frankfurt), and emails are sent through Resend. We never sell or share your email. Every email includes a one-click unsubscribe link. To have your data deleted entirely, email us at the address below.</p>'
                 '<h3>Hosting</h3><p>The site is hosted on GitHub Pages. GitHub may log technical data such as IP addresses for security. See GitHub\'s privacy statement for details.</p>'
                 '<h3>Advertising</h3><p>If advertising is enabled, Google AdSense and its partners may use cookies to show ads based on your visits to this and other sites. You can opt out of personalised ads at <a href="https://adssettings.google.com" target="_blank" rel="noopener">Google Ads Settings</a>.</p>'
                 '<h3>Clipboard</h3><p>Copy buttons use your browser\'s clipboard only. Nothing is sent to us.</p>'
                 '<h3>Children</h3><p>We don\'t knowingly collect personal information from anyone, including children under 13.</p>'
                 f'<h3>Contact</h3><p>Email <a href="mailto:{e(SITE["contact_email"])}">{e(SITE["contact_email"])}</a>.</p></div>')


# --------------------------------------------------------------------------- #
# Page registry (titles and descriptions follow the content brief)
# --------------------------------------------------------------------------- #

CORE = ["/how-to-redeem/", "/codes-not-working/", "/free-spins/", "/tier-list/"]

PAGES = [
    dict(path="/", out="index.html", short="Working codes",
         title=f"Blue Lock Rivals Codes ({MONTH_YEAR}) – New Codes Today",
         description=f"All {len(ACTIVE)} working Blue Lock Rivals codes for {MONTH_YEAR}, checked every 30 minutes. Redeem them for free Lucky Style Spins and Lucky Flow Spins.",
         body=home_body, faq=HOME_FAQ, schema_type="WebPage", modified=NOW),
    dict(path="/codes-not-working/", out="codes-not-working/index.html", short="Codes not working",
         title="Blue Lock Rivals Codes Not Working? 6 Fixes",
         h1="Blue Lock Rivals codes not working?",
         lede="Getting \"invalid\" or \"must be in group\"? Here's what causes each error and how to fix it in under a minute.",
         description="Getting 'invalid' or 'must be in group' errors? Here's why Blue Lock Rivals codes fail and how to fix each one in under a minute.",
         body=not_working_body, faq=NOT_WORKING_FAQ, blurb="Every error and its fix.",
         related=["/how-to-redeem/", "/", "/expired-codes/"]),
    dict(path="/how-to-redeem/", out="how-to-redeem/index.html", short="How to redeem",
         title=f"How to Redeem Blue Lock Rivals Codes ({YEAR} Guide)",
         h1="How to redeem Blue Lock Rivals codes",
         lede="Four quick steps, plus the group and level requirements that trip most players up.",
         description="How to redeem Blue Lock Rivals codes on PC, mobile and console, how to join the required Roblox group, and how to fix invalid code errors.",
         body=redeem_body, faq=REDEEM_FAQ, howto=True, blurb="Steps, the group requirement and fixes.",
         related=["/codes-not-working/", "/", "/free-spins/"]),
    dict(path="/free-spins/", out="free-spins/index.html", short="Free spins",
         title="How to Get Free Lucky Spins in Blue Lock Rivals",
         h1="How to get free spins in Blue Lock Rivals",
         lede="Every free source of Lucky Style Spins and Flow Spins, how spin chances work, and how not to waste them.",
         description="All the ways to get free Lucky Spins in Blue Lock Rivals: codes, Yen, quests and events, plus spin chances, flow pity and how to level up fast.",
         body=spins_body, blurb="Codes, Yen, quests, events and pity.", related=["/", "/tier-list/", "/styles/"]),
    dict(path="/styles/", out="styles/index.html", short="Styles",
         title=f"All Blue Lock Rivals Styles List & Rarities ({YEAR})",
         h1="Blue Lock Rivals styles list",
         lede=f"All {REGULAR_STYLES} regular styles and {LIMITED_STYLES} limited event styles, grouped by rarity from Rare to Master.",
         description=f"Full Blue Lock Rivals styles list: all {REGULAR_STYLES + LIMITED_STYLES} styles with rarities, from Rare to Master, including NEL and limited event styles.",
         body=styles_body, blurb="Every style and its rarity.", related=["/tier-list/", "/flows/", "/free-spins/"]),
    dict(path="/flows/", out="flows/index.html", short="Flows",
         title="All Blue Lock Rivals Flows: Effects & Rarities",
         h1="Every Blue Lock Rivals flow",
         lede="What each flow does, how rare it is, and the best flow for your playstyle.",
         description=f"All {len(FLOWS['flows'])} Blue Lock Rivals flows with effects and rarities, the best flow for each playstyle, and how flow spins and pity work.",
         body=flows_body, blurb="Effects, rarities and best pairings.", related=["/tier-list/", "/styles/", "/free-spins/"]),
    dict(path="/tier-list/", out="tier-list/index.html", short="Tier list",
         title=f"Blue Lock Rivals Tier List ({MONTH_YEAR}): Best Styles",
         h1="Blue Lock Rivals tier list",
         lede="The best styles and flows in the current meta, ranked S to D, with picks for every budget.",
         description=f"Blue Lock Rivals tier list for {MONTH_YEAR}: the best styles and flows ranked S to D, plus the best Mythic, NEL and free-to-play picks.",
         body=tier_body, blurb="Best styles and flows, S to D.", related=["/styles/", "/flows/", "/free-spins/"]),
    dict(path="/controls/", out="controls/index.html", short="Controls",
         title="Blue Lock Rivals Controls: PC, Xbox, PS5 & Mobile",
         h1="Blue Lock Rivals controls",
         lede="Controls for PC, Xbox, PlayStation and mobile, plus the settings that make the biggest difference.",
         description="Blue Lock Rivals controls for PC, Xbox, PS5, PS4 and mobile, with keybinds for shooting, dribbling, tackling and flow, and the best settings.",
         body=controls_body, blurb="PC, console and mobile layouts.", related=["/beginners-guide/", "/tier-list/", "/"]),
    dict(path="/beginners-guide/", out="beginners-guide/index.html", short="Beginner's guide",
         title="How to Play Blue Lock Rivals: Beginner's Guide",
         h1="How to play Blue Lock Rivals",
         lede="What to do in your first hour, how to level up fast, and the fundamentals that win matches.",
         description="New to Blue Lock Rivals? How to play, level up fast, pick the right style and flow, and the fundamentals that win more matches.",
         body=beginners_body, blurb="First steps and core tips.", related=["/controls/", "/tier-list/", "/free-spins/"]),
    dict(path="/next-update/", out="next-update/index.html", short="Next update",
         title="Blue Lock Rivals Next Update: Countdown & Time",
         h1="Blue Lock Rivals next update",
         lede="A live countdown to the next weekly update, in your time zone.",
         description="When is the next Blue Lock Rivals update? Live countdown in your time zone, the usual release time, and the codes that drop with it.",
         body=next_update_body, blurb="Live countdown and release time.", related=["/updates/", "/", "/trello-discord/"]),
    dict(path="/updates/", out="updates/index.html", short="Update log",
         title="Blue Lock Rivals Update Log & Patch History",
         h1="Blue Lock Rivals update log", lede="Every recent update and the codes that came with it.",
         description="History of Blue Lock Rivals updates with release dates and the codes released with each one.",
         body=updates_body, blurb="Every update and its codes.", related=["/next-update/", "/", "/expired-codes/"]),
    dict(path="/expired-codes/", out="expired-codes/index.html", short="Expired codes",
         title=f"All Expired Blue Lock Rivals Codes ({len(EXPIRED)} Codes)",
         h1="Expired Blue Lock Rivals codes", lede="Every code that no longer works, so you can stop trying them.",
         description=f"The full list of {len(EXPIRED)} expired Blue Lock Rivals codes that no longer work, updated automatically.",
         body=expired_body, blurb="Codes that no longer work.", related=["/", "/codes-not-working/", "/next-update/"]),
    dict(path="/trello-discord/", out="trello-discord/index.html", short="Discord and Trello",
         title="Blue Lock Rivals Discord, Trello & Wiki Links",
         h1="Blue Lock Rivals Discord, Trello and wiki",
         lede="The official places the developer posts updates and codes.",
         description="Official Blue Lock Rivals Discord server, Trello board, wiki pages and Roblox group, where updates and codes are announced.",
         body=links_body, blurb="Official Discord, Trello and group.", related=["/next-update/", "/", "/styles/"]),
    dict(path="/guides/", out="guides/index.html", short="All guides", title="Blue Lock Rivals Guides",
         h1="Blue Lock Rivals guides", lede="Everything beyond codes: styles, flows, controls and more.",
         description="All Blue Lock Rivals guides: styles, flows, tier list, controls, free spins, next update and beginner tips.",
         body=guides_body),
    dict(path="/author/muhammad-usman-siddiqui/", out="author/muhammad-usman-siddiqui/index.html",
         short="Muhammad Usman Siddiqui", title="Muhammad Usman Siddiqui – Author Profile",
         h1="Muhammad Usman Siddiqui", lede="Blue Lock: Rivals player and maintainer of Blue Lock Rivals Codes.",
         description="Muhammad Usman Siddiqui runs Blue Lock Rivals Codes, tracking every new code and writing the site's style, flow and tier list guides.",
         body=author_body, schema_type="ProfilePage"),
    dict(path="/alerts/", out="alerts/index.html", short="Email alerts",
         title="Blue Lock Rivals Code Alerts: Email & Browser Notifications",
         h1="Blue Lock Rivals code alerts", lede="Get an email or a browser notification the moment a new code drops.",
         description="Free Blue Lock Rivals code alerts by email or browser notification. Get told the moment a new code goes live, one alert per code, turn off anytime.",
         body=alerts_body, faq=ALERTS_FAQ, blurb="New codes straight to your inbox.", related=["/", "/next-update/", "/how-to-redeem/"]),
    dict(path="/alerts/confirmed/", out="alerts/confirmed/index.html", short="Subscribed", title="You're subscribed",
         h1="You're subscribed", lede="New codes will now come straight to your inbox.", description="Email alerts confirmed.",
         body=lambda: alerts_done_body("confirmed"), noindex=True, sidebar=False),
    dict(path="/alerts/unsubscribed/", out="alerts/unsubscribed/index.html", short="Unsubscribed", title="You're unsubscribed",
         h1="You're unsubscribed", lede="You won't get any more code alerts.", description="Unsubscribed from email alerts.",
         body=lambda: alerts_done_body("unsubscribed"), noindex=True, sidebar=False),
    dict(path="/about/", out="about/index.html", short="About", title=f"About {SITE['name']}",
         h1="About this site", lede="Who runs it and how codes are checked.",
         description="Who runs Blue Lock Rivals Codes and how new codes are found and verified.", body=about_body,
         schema_type="AboutPage"),
    dict(path="/privacy-policy.html", out="privacy-policy.html", short="Privacy policy", title="Privacy Policy",
         h1="Privacy policy", lede="Short version: we don't collect personal data.",
         description=f"Privacy policy for {SITE['domain']}.", body=privacy_body, sidebar=False),
]

for p in PAGES:
    if p["path"] not in ("/", "/about/", "/privacy-policy.html", "/guides/", "/author/muhammad-usman-siddiqui/") and not p.get("noindex") and "related" not in p:
        p["related"] = CORE[:3]


# --------------------------------------------------------------------------- #
# Extra outputs
# --------------------------------------------------------------------------- #

def sitemap():
    urls = []
    for p in [x for x in PAGES if not x.get("noindex")]:
        mod = (p.get("modified") or UPDATED).date().isoformat()
        urls.append(f"<url><loc>{e(ABS + p['path'])}</loc><lastmod>{mod}</lastmod></url>")
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{"".join(urls)}</urlset>'


def feed():
    items = []
    for c in sorted([c for c in ACTIVE + EXPIRED if c.get("added")], key=lambda c: c["added"], reverse=True)[:30]:
        dt = datetime.fromisoformat(c["added"][:10]).replace(tzinfo=timezone.utc)
        items.append(f"<item><title>New Blue Lock Rivals code: {e(c['code'])}</title><link>{e(ABS)}/</link>"
                     f"<guid isPermaLink=\"false\">blr-{e(c['code'])}</guid><pubDate>{format_datetime(dt)}</pubDate>"
                     f"<description>{e(reward_text(c))}</description></item>")
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{e(SITE["name"])}</title>'
            f'<link>{e(ABS)}/</link><description>New Blue Lock Rivals codes as soon as they release.</description>'
            f'<lastBuildDate>{format_datetime(NOW)}</lastBuildDate>{"".join(items)}</channel></rss>')


FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><path d="M6 0h26l-6 32H0z" fill="#E8263F"/>'
           '<circle cx="16" cy="16" r="8" fill="none" stroke="#fff" stroke-width="2.4"/><path d="M16 11.2l3.8 2.7-1.4 4.4h-4.8l-1.4-4.4z" fill="#fff"/></svg>')


def make_images():
    """Share image (1200x630) and app icon, drawn fresh each build so counts and month stay current."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("  (Pillow not installed: skipping og.png / apple-touch-icon.png)")
        return
    bold = FONTS / "BarlowCondensed-ExtraBoldItalic.ttf"
    semi = FONTS / "BarlowCondensed-Bold.ttf"
    F = lambda path, size: ImageFont.truetype(str(path), size)
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), "#0B0B10")
    d = ImageDraw.Draw(im)
    glow = Image.new("RGB", (W, H), "#0B0B10")
    gd = ImageDraw.Draw(glow)
    for r, col in ((520, (60, 22, 30)), (380, (110, 34, 34)), (240, (170, 52, 40))):
        gd.ellipse([W - 260 - r, -120 - r // 3, W - 260 + r, -120 + r + r // 2], fill=col)
    from PIL import ImageFilter
    im = Image.blend(im, glow.filter(ImageFilter.GaussianBlur(90)), 0.9)
    d = ImageDraw.Draw(im)
    d.text((80, 92), "BLUE LOCK RIVALS", font=F(bold, 92), fill="white")
    d.text((80, 186), "CODES", font=F(bold, 190), fill="#FF6A1A")
    d.text((86, 410), MONTH_YEAR.upper(), font=F(semi, 54), fill="#C9CBD6")
    y = 500
    d.rounded_rectangle([80, y, 80 + 380, y + 74], radius=14, fill="#E8263F")
    d.text((104, y + 12), f"+{TOTAL_SPINS} STYLE SPINS", font=F(bold, 46), fill="white")
    d.rounded_rectangle([480, y, 480 + 360, y + 74], radius=14, fill="#3866FF")
    d.text((504, y + 12), f"+{TOTAL_FLOWS} FLOW SPINS", font=F(bold, 46), fill="white")
    d.rounded_rectangle([860, y, 860 + 260, y + 74], radius=14, fill="#17A35E")
    d.text((884, y + 12), f"{len(ACTIVE)} CODES", font=F(bold, 46), fill="white")
    im.save(DIST / "og.png", optimize=True)

    icon = Image.new("RGB", (180, 180), "#E8263F")
    di = ImageDraw.Draw(icon)
    di.ellipse([42, 42, 138, 138], outline="white", width=10)
    di.polygon([(90, 64), (112, 80), (104, 106), (76, 106), (68, 80)], fill="white")
    icon.save(DIST / "apple-touch-icon.png")
    for size in (192, 512):
        icon.resize((size, size)).save(DIST / f"icon-{size}.png")


def not_found():
    page = dict(path="/404.html", short="Not found", title="Page not found", h1="Offside", noindex=True,
                lede="That page doesn't exist, but the codes do.", description="Page not found.",
                body=lambda: block("go", "Where to next", '<p><a class="btn primary" href="/">See all working codes</a></p>' + guide_cards()),
                sidebar=False)
    return render(page)


def build():
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    for f in ASSETS.iterdir():
        if f.is_file():
            target = DIST / f"assets/{f.name}"
            shutil.copy2(f, target)
    for p in PAGES:
        out = DIST / p["out"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(p), encoding="utf-8")
    (DIST / "404.html").write_text(not_found(), encoding="utf-8")
    (DIST / "sitemap.xml").write_text(sitemap(), encoding="utf-8")
    (DIST / "feed.xml").write_text(feed(), encoding="utf-8")
    (DIST / "favicon.svg").write_text(FAVICON, encoding="utf-8")
    robots = ("User-agent: *\nDisallow: /\n" if PREVIEW else f"User-agent: *\nAllow: /\n\nSitemap: {ABS}/sitemap.xml\n")
    (DIST / "robots.txt").write_text(robots, encoding="utf-8")
    (DIST / "CNAME").write_text(SITE["domain"] + "\n", encoding="utf-8")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")
    (DIST / "site.webmanifest").write_text(json.dumps({
        "name": SITE["name"], "short_name": "BLR Codes", "start_url": (BASE or "") + "/", "display": "standalone",
        "background_color": "#F3F6FB", "theme_color": "#0A1633",
        "icons": [{"src": f"{BASE}/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": f"{BASE}/icon-512.png", "sizes": "512x512", "type": "image/png"}]}, indent=1), encoding="utf-8")
    pub = SITE.get("adsense_client", "").replace("ca-", "")
    if pub:
        (DIST / "ads.txt").write_text(f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")
    if SITE.get("indexnow_key"):
        (DIST / f"{SITE['indexnow_key']}.txt").write_text(SITE["indexnow_key"], encoding="utf-8")
    api = DIST / "api"
    api.mkdir()
    (api / "codes.json").write_text(json.dumps({"updated": CODES.get("updated"), "last_checked": CHECKED, "active": ACTIVE,
                                                 "expired": [c["code"] for c in EXPIRED]}, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copy2(ASSETS / "sw.js", DIST / "sw.js")
    make_images()
    print(f"Built {len(PAGES) + 1} pages -> dist/  ({len(ACTIVE)} active, {len(EXPIRED)} expired){'  [preview: ' + BASE + ']' if PREVIEW else ''}")


if __name__ == "__main__":
    build()
