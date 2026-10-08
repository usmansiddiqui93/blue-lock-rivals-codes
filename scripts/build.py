#!/usr/bin/env python3
"""Static site builder for blue-lock-rivals-codes.com.

Reads data/*.json + content/*.html and writes a complete static site to dist/.
Standard library only, so it runs anywhere (GitHub Actions, your laptop).

    python scripts/build.py            # build into dist/
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
from datetime import datetime, timezone, date
from pathlib import Path
from email.utils import format_datetime

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONTENT = ROOT / "content"
ASSETS = ROOT / "assets"
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


def parse_dt(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return NOW


def nice_date(d):
    if isinstance(d, str):
        d = parse_dt(d) if "T" in d else datetime.fromisoformat(d)
    return d.strftime("%B %-d, %Y")


MONTH_YEAR = parse_dt(CODES.get("updated", NOW.isoformat())).strftime("%B %Y")
ACTIVE = CODES.get("active", [])
EXPIRED = CODES.get("expired", [])
TOTAL_SPINS = sum(int(c.get("spins") or 0) for c in ACTIVE)
TOTAL_FLOWS = sum(int(c.get("flows") or 0) for c in ACTIVE)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# --------------------------------------------------------------------------- #
# Components
# --------------------------------------------------------------------------- #

PITCH_SVG = """<svg class="pitch" viewBox="0 0 1200 420" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
<g fill="none" stroke="#C9D6FF" stroke-width="2">
<rect x="40" y="30" width="1120" height="360" rx="4"/><line x1="600" y1="30" x2="600" y2="390"/>
<circle cx="600" cy="210" r="70"/><circle cx="600" cy="210" r="4" fill="#C9D6FF"/>
<rect x="40" y="110" width="150" height="200"/><rect x="40" y="160" width="55" height="100"/>
<rect x="1010" y="110" width="150" height="200"/><rect x="1105" y="160" width="55" height="100"/>
<path d="M190 175a45 45 0 0 1 0 70M1010 175a45 45 0 0 0 0 70"/></g></svg>"""

BRAND_MARK = """<span class="brand-mark" aria-hidden="true"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7l4 3-1.5 4.5h-5L8 10z" fill="#fff" stroke="none"/><path d="M12 3v4M21 10l-5 0M16.5 20l-2-5.5M7.5 20l2-5.5M3 10h5"/></svg></span>"""


def ad(slot_name):
    if not SITE.get("ads_enabled"):
        return ""
    return (f'<div class="ad"><ins class="adsbygoogle" style="display:block" '
            f'data-ad-client="{e(SITE["adsense_client"])}" data-ad-format="auto" '
            f'data-full-width-responsive="true" data-slot-name="{e(slot_name)}"></ins>'
            f'<script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script></div>')


def reward_chips(c):
    out = []
    if c.get("spins"):
        out.append(f'<span class="chip spin">{int(c["spins"])} Style Spins</span>')
    if c.get("flows"):
        out.append(f'<span class="chip flow">{int(c["flows"])} Flow Spins</span>')
    if not out and c.get("reward"):
        out.append(f'<span>{e(c["reward"])}</span>')
    return "".join(out)


def is_new(c):
    try:
        added = date.fromisoformat(c.get("added", "")[:10])
    except ValueError:
        return False
    return (NOW.date() - added).days <= int(SITE.get("new_code_days", 3))


def code_cards(codes):
    if not codes:
        return ('<div class="empty"><strong>No working codes right now.</strong><br>'
                'New codes usually arrive with the weekly update — this page refreshes itself '
                'the moment one is confirmed.</div>')
    rows = []
    for c in codes:
        code = c["code"]
        new = '<span class="chip new">NEW</span>' if is_new(c) else ""
        added = f'<span class="added">Added {e(nice_date(c["added"]))}</span>' if c.get("added") else ""
        rows.append(
            f'<div class="code"><div><div class="code-name">{e(code)}</div>'
            f'<div class="code-meta">{new}{reward_chips(c)}{added}</div></div>'
            f'<button class="copy" data-copy="{e(code)}" aria-label="Copy code {e(code)}">Copy</button></div>')
    return '<div class="codes">' + "".join(rows) + "</div>"


def copy_all_button():
    if not ACTIVE:
        return ""
    allcodes = "\n".join(c["code"] for c in ACTIVE)
    return f'<button class="btn primary" data-copy="{e(allcodes)}" data-copy-all>Copy all {len(ACTIVE)} codes</button>'


def expired_chips(limit=None):
    items = EXPIRED if limit is None else EXPIRED[:limit]
    return '<div class="expired-list">' + "".join(f"<code>{e(c['code'])}</code>" for c in items) + "</div>"


def rarity_badge(r):
    return f'<span class="rarity r-{slug(r)}">{e(r)}</span>'


def styles_by_rarity():
    out = []
    for rarity, names in STYLES["rarities"].items():
        out.append(f'<div class="rgroup"><h3>{rarity_badge(rarity)} <span>{len(names)} styles</span></h3>'
                   f'<div class="pills">' + "".join(f'<span class="pill">{e(n)}</span>' for n in names) + "</div></div>")
    return "".join(out)


def styles_table():
    rows = []
    for rarity, names in STYLES["rarities"].items():
        for n in names:
            rows.append(f"<tr><td><strong>{e(n)}</strong></td><td>{rarity_badge(rarity)}</td></tr>")
    return '<div class="table-wrap"><table><thead><tr><th>Style</th><th>Rarity</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"


def flows_table():
    rows = "".join(f"<tr><td><strong>{e(f['name'])}</strong></td><td>{rarity_badge(f['rarity'])}</td><td>{e(f['effect'])}</td></tr>"
                   for f in FLOWS["flows"])
    return '<div class="table-wrap"><table><thead><tr><th>Flow</th><th>Rarity</th><th>What it does</th></tr></thead><tbody>' + rows + "</tbody></table></div>"


def tier_block(kind):
    out = []
    for t, names in TIERS[kind].items():
        out.append(f'<div class="tier t-{e(t)}"><b>{e(t)}</b><div class="pills">' +
                   "".join(f'<span class="pill">{e(n)}</span>' for n in names) + "</div></div>")
    return '<div class="tiers">' + "".join(out) + "</div>"


def updates_timeline(limit=None):
    ups = sorted(UPDATES["updates"], key=lambda u: u["date"], reverse=True)
    if limit:
        ups = ups[:limit]
    items = []
    for u in ups:
        codes = ", ".join(f"<code>{e(c)}</code>" for c in u.get("codes", []))
        items.append(f'<li><time datetime="{e(u["date"])}">{e(nice_date(u["date"]))}</time>'
                     f'<strong>{e(u["name"])}</strong>' + (f'<span class="muted">Codes: {codes}</span>' if codes else "") + "</li>")
    return '<ul class="timeline">' + "".join(items) + "</ul>"


REDEEM_STEPS = """<ol class="steps">
<li><div><strong>Join the developer's Roblox group</strong>Codes are locked until you're a member of the official community group. <a href="{group}" rel="noopener" target="_blank">Join it here</a>.</div></li>
<li><div><strong>Reach level 10</strong>Brand-new accounts can't redeem yet. A few matches gets you there.</div></li>
<li><div><strong>Open Codes in the lobby</strong>Launch <a href="{roblox}" rel="noopener" target="_blank">Blue Lock: Rivals</a> and tap the Codes button in the lobby menu.</div></li>
<li><div><strong>Paste and redeem</strong>Use the Copy button on this page — codes are case-sensitive — then hit Redeem. Spins land in your account instantly.</div></li>
</ol>"""


def redeem_steps():
    return REDEEM_STEPS.format(group=e(SITE["roblox_group_url"]), roblox=e(SITE["roblox_url"]))


def guides_cards():
    cards = [(p["title_short"], p["blurb"], p["path"]) for p in PAGES if p.get("in_guides")]
    return '<div class="cards">' + "".join(
        f'<a class="gcard" href="{e(path)}"><strong>{e(t)}</strong><span>{e(b)}</span></a>' for t, b, path in cards) + "</div>"


def sidebar():
    last = CODES.get("last_checked") or CODES.get("updated")
    a = SITE["author"]
    initials = "".join(w[0] for w in a.split()[:2]).upper()
    avatar = f'<img src="/author.png" alt="" onerror="this.remove()">' if (ROOT / "assets" / "author.png").exists() else ""
    return f"""<aside>
<div class="card"><h3>Code tracker status</h3>
<p class="status">Last checked <b><time data-rel datetime="{e(last)}">{e(nice_date(last))}</time></b><br>
<b>{len(ACTIVE)}</b> active · <b>{len(EXPIRED)}</b> expired</p>
<p class="status">This site checks for new codes every 30 minutes, around the clock.</p>
<a class="btn" href="/feed.xml">RSS feed</a> <a class="btn" href="{e(SITE['discord_url'])}" rel="noopener" target="_blank">Game Discord</a></div>
{ad("sidebar")}
<div class="card"><h3>Quick tips</h3><ul class="tips">
<li><strong>Redeem fast.</strong> Codes can die within days of release.</li>
<li><strong>Case matters.</strong> Copy instead of typing.</li>
<li><strong>They stack.</strong> Every active code works on the same account.</li>
<li><strong>Saturdays are code days.</strong> Most updates (and codes) land on the weekend.</li>
</ul></div>
<div class="card"><h3>Guides</h3><ul class="linklist">
{''.join(f'<li><a href="{e(p["path"])}">{e(p["title_short"])}</a></li>' for p in PAGES if p.get("in_sidebar"))}
</ul></div>
<div class="card"><div class="author"><div class="avatar">{avatar or e(initials)}</div><div>
<div class="muted" style="font-size:12.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em">Maintained by</div>
<strong>{e(a)}</strong><div class="muted" style="font-size:14px">{e(SITE['author_role'])}</div></div></div>
<p class="status" style="margin-top:12px">New codes are collected automatically and published only once at least two independent sources confirm them.</p>
<button class="btn" data-share>Share this page</button></div>
</aside>"""


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #

def head(page):
    url = SITE["base_url"] + page["path"]
    title = page["title"]
    desc = page["description"]
    adsense = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={e(SITE["adsense_client"])}" crossorigin="anonymous"></script>'
               if SITE.get("ads_enabled") else "")
    jsonld = json.dumps(page.get("jsonld") or [], ensure_ascii=False)
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(url)}">
<meta name="theme-color" content="#FFFFFF">
<meta name="google-adsense-account" content="{e(SITE['adsense_client'])}">
<meta property="og:type" content="article"><meta property="og:site_name" content="{e(SITE['name'])}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}"><meta property="og:image" content="{e(SITE['base_url'])}/og.png">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(desc)}">
<meta property="article:modified_time" content="{e(CODES.get('updated',''))}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="New Blue Lock Rivals codes" href="/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800&family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/style.css?v={int(NOW.timestamp())}">
<script type="application/ld+json">{jsonld}</script>
{adsense}
</head>"""


def header(page):
    links = "".join(
        f'<a href="{e(href)}"{" aria-current=page" if href == page["path"] else ""}>{e(label)}</a>'
        for label, href in SITE["nav"])
    return f"""<header class="top"><div class="wrap">
<a class="brand" href="/">{BRAND_MARK}<span>Blue Lock Rivals <b>Codes</b></span></a>
<button class="menu-btn" aria-expanded="false" aria-controls="nav">Menu</button>
<nav class="nav" id="nav" aria-label="Main">{links}</nav></div></header>"""


def footer():
    links = [(p["title_short"], p["path"]) for p in PAGES if p["path"] != "/"]
    return f"""<footer><div class="wrap">
<nav aria-label="Footer">{''.join(f'<a href="{e(h)}">{e(t)}</a>' for t, h in links)}</nav>
<div><strong>{e(SITE['domain'])}</strong> is an independent fan site. It is not affiliated with Roblox Corporation, {e(SITE['developer'])}, Kodansha or the creators of Blue Lock. All trademarks belong to their respective owners.</div>
<div>© {NOW.year} {e(SITE['name'])} · <a href="mailto:{e(SITE['contact_email'])}">{e(SITE['contact_email'])}</a></div>
</div></footer><script src="/assets/app.js" defer></script>"""


def hero(page):
    if page["path"] == "/":
        return f"""<section class="hero">{PITCH_SVG}<div class="wrap">
<span class="eyebrow"><span class="dot"></span>Checked <time data-rel datetime="{e(CODES.get('last_checked',''))}">today</time></span>
<h1>Blue Lock Rivals Codes <em>({e(MONTH_YEAR)})</em></h1>
<p class="lede">Every working code for Blue Lock: Rivals on Roblox, with free Lucky Style Spins and Lucky Flow Spins. New codes appear here automatically within minutes of release.</p>
<div class="stats"><div class="stat"><strong>{len(ACTIVE)}</strong><span>Active codes</span></div>
<div class="stat"><strong>{TOTAL_SPINS}</strong><span>Free style spins</span></div>
<div class="stat"><strong>{TOTAL_FLOWS}</strong><span>Free flow spins</span></div></div>
</div></section>"""
    return f"""<section class="hero page-hero">{PITCH_SVG}<div class="wrap">
<div class="crumbs"><a href="/">Home</a> / {e(page['title_short'])}</div>
<h1>{page['h1']}</h1><p class="lede">{page['lede']}</p></div></section>"""


def render(page):
    body = page["body"]() if callable(page["body"]) else page["body"]
    side = sidebar() if page.get("sidebar", True) else ""
    grid = f'<div class="grid wrap"><main>{body}</main>{side}</div>' if side else f'<div class="wrap" style="padding:30px 20px 60px"><main>{body}</main></div>'
    return head(page) + "<body>" + header(page) + hero(page) + grid + footer() + "</body></html>"


# --------------------------------------------------------------------------- #
# Page content
# --------------------------------------------------------------------------- #

def faq_html(items):
    return '<div class="faq">' + "".join(f"<details><summary>{e(q)}</summary><p>{a}</p></details>" for q, a in items) + "</div>"


def faq_ld(items):
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q,
                            "acceptedAnswer": {"@type": "Answer", "text": re.sub("<[^>]+>", "", a)}} for q, a in items]}


HOME_FAQ = [
    ("Where do Blue Lock Rivals codes come from?",
     f"The developer, {e(SITE['developer'])}, posts them in the official Discord, in the Roblox group and alongside weekly update announcements. Codes usually celebrate an update, a reworked style or a community milestone."),
    ("Why isn't my code working?",
     "The usual causes are: the code has already expired, you've redeemed it before on this account, you haven't joined the developer's Roblox group, your account is below level 10, or there's a typo. Codes are case-sensitive, so use the Copy button."),
    ("How often are new codes released?",
     "Roughly every week. Most updates go live on Saturday and bring two or three new codes with them; mid-week events and milestones add the occasional extra."),
    ("What do codes give you?",
     "Almost always Lucky Style Spins (rolls for a new Style) and Lucky Flow Spins (rolls for a new Flow). Lucky spins have much better odds of high-rarity results than normal spins."),
    ("Do spins from codes expire?",
     "No. Once a code is redeemed, the spins stay in your inventory until you use them. Only the code itself expires."),
    ("Can I use one code on several accounts?",
     "Yes. Each code works once per Roblox account, so every alt can redeem it — as long as each meets the group and level requirements."),
    ("Is this site official?",
     f"No. {e(SITE['domain'])} is an independent fan site and isn't affiliated with Roblox or the game's developer."),
]


def home_body():
    return f"""
<section id="active"><div class="section-label">Working now</div>
<h2>All active Blue Lock Rivals codes</h2>
<p>Every code below has been confirmed working by at least two independent sources. Redeem all of them — rewards stack.</p>
<div class="toolbar">{copy_all_button()}<a class="btn" href="/how-to-redeem/">How to redeem →</a></div>
{code_cards(ACTIVE)}
</section>
{ad("in-content")}
<section id="redeem"><div class="section-label">Guide</div><h2>How to redeem codes in Blue Lock Rivals</h2>{redeem_steps()}</section>
<section id="expired"><div class="section-label">Archive</div><h2>Expired codes</h2>
<p>These no longer work. They're kept here so you don't waste time trying them.</p>
{expired_chips(40)}
<details class="more"><summary>Show all {len(EXPIRED)} expired codes</summary>{expired_chips()}</details>
<p style="margin-top:14px"><a href="/expired-codes/">Full expired codes archive →</a></p></section>
<section><div class="section-label">Recent updates</div><h2>Latest game updates</h2>{updates_timeline(4)}
<p><a href="/updates/">Full update log →</a></p></section>
<section><div class="section-label">Guides</div><h2>Spend your spins well</h2>
<p>Codes hand you spins — these guides help you decide what to keep.</p>{guides_cards()}</section>
<section id="faq"><div class="section-label">Help</div><h2>Frequently asked questions</h2>{faq_html(HOME_FAQ)}</section>"""


def expired_body():
    return f"""<section><h2>Every expired Blue Lock Rivals code</h2>
<p>{len(EXPIRED)} codes have been retired so far. When a working code dies, it moves here automatically. If a code you found elsewhere is on this list, it won't redeem.</p>
{expired_chips()}</section>
<section><h2>Looking for working codes?</h2><p>Head back to the <a href="/">active codes list</a> — there are {len(ACTIVE)} working right now.</p></section>"""


REDEEM_FAQ = [
    ("What does \"You must be in the group\" mean?",
     f"The game requires you to join the developer's Roblox community before codes work. <a href=\"{e(SITE['roblox_group_url'])}\" target=\"_blank\" rel=\"noopener\">Join the group</a>, rejoin the game and try again."),
    ("What level do I need?", "Level 10. Play a handful of matches and you'll get there quickly."),
    ("The code says invalid — what now?", "Check it isn't on the expired list, make sure you haven't redeemed it before, and paste it rather than typing it. Watch for zero vs. letter O and trailing spaces."),
    ("Can I redeem on mobile or console?", "Yes. The Codes button is in the lobby on every platform: PC, phone, tablet and Xbox/PlayStation."),
]


def redeem_body():
    return f"""<section><h2>Step by step</h2>{redeem_steps()}</section>
<section><h2>Requirements checklist</h2><div class="prose"><ul>
<li>You're a member of the official Roblox group.</li>
<li>Your account is level 10 or higher.</li>
<li>The code is on the <a href="/">active list</a> and you haven't used it before.</li>
<li>You've copied it exactly, including any punctuation like <code>!</code>.</li></ul></div></section>
<section><h2>Troubleshooting</h2>{faq_html(REDEEM_FAQ)}</section>"""


def spins_body():
    return f"""<section><h2>Every way to get spins</h2><div class="prose">
<h3>1. Redeem codes (fastest)</h3>
<p>Each new code usually gives 5 Lucky Style Spins, 5 Lucky Flow Spins, or both. Right now the <a href="/">active codes</a> add up to <strong>{TOTAL_SPINS} style spins and {TOTAL_FLOWS} flow spins</strong>.</p>
<h3>2. Play matches and earn Yen</h3>
<p>Matches pay out Yen, the game's soft currency. A normal Flow spin costs 2,000 Yen, so grinding matches is the steady, free way to keep rolling.</p>
<h3>3. Level up and complete quests</h3>
<p>Levelling and event quests regularly hand out spins. Check the quest board whenever a new update lands.</p>
<h3>4. Join live events</h3>
<p>Seasonal events (Halloween, winter, Easter) and mid-week "W Wednesday" drops often include limited spins and limited-edition styles.</p>
<h3>5. Robux (optional)</h3>
<p>Spin bundles can be bought with Robux. You never have to — but if you do, wait for a fresh update so your rolls cover the newest styles.</p></div></section>
<section><h2>Lucky spins vs. normal spins</h2><div class="prose">
<p>Lucky spins (the kind codes give) roll with much higher odds of Legendary-and-above results than normal spins. Save them for when you're actually hunting an upgrade, and don't burn them on a style you already like.</p>
<p>Flows also have a pity system: after 50 Flow spins without one, you're guaranteed a Legendary or better.</p></div></section>
<section><h2>Before you spin</h2><div class="prose"><ul>
<li><strong>Lock your slot</strong> if you already own a style you want to keep — otherwise a spin can overwrite it.</li>
<li>Check the <a href="/tier-list/">tier list</a> so you know which results are worth keeping.</li>
<li>New codes drop with Saturday updates — spinning right after an update gives you a shot at the newest style.</li></ul></div></section>"""


def styles_body():
    counts = {r: len(n) for r, n in STYLES["rarities"].items()}
    total = sum(v for k, v in counts.items() if k != "Limited")
    return f"""<section><h2>What are Styles?</h2><div class="prose">
<p>A Style is your player kit. It decides your three active abilities (C, V and B on PC), your awakening and which Flows suit you. You get Styles by spinning, and higher rarities are both stronger and much harder to roll.</p>
<p>There are currently <strong>{total} regular Styles</strong> across six rarities, plus <strong>{counts.get('Limited', 0)} limited-time</strong> seasonal versions.</p></div></section>
<section><h2>All Styles by rarity</h2>{styles_by_rarity()}</section>
{ad("in-content")}
<section><h2>Full Style list</h2>{styles_table()}<p class="muted">Rarities last verified {e(nice_date(STYLES['verified']))}.</p></section>
<section><h2>Rarity ladder</h2><div class="prose"><p>From most common to rarest:
{rarity_badge('Rare')} → {rarity_badge('Epic')} → {rarity_badge('Legendary')} → {rarity_badge('Mythic')} → {rarity_badge('World Class')} → {rarity_badge('Master')}.
{rarity_badge('Limited')} styles are event exclusives that can only be rolled while their event is running.</p>
<p>Want to know which ones are actually good? See the <a href="/tier-list/">tier list</a>.</p></div></section>"""


def flows_body():
    return f"""<section><h2>What are Flows?</h2><div class="prose">
<p>Flows are temporary power-ups. A Flow meter fills as you play; once it reaches at least 30% you can activate it (G on PC) for boosts like extra speed, harder shots, extra dribbles or shorter cooldowns. Pick a Flow that matches what your Style already does well.</p>
<p>Flow spins cost 2,000 Yen each (or use Lucky Flow Spins from <a href="/">codes</a>). After 50 spins you're guaranteed at least a Legendary.</p></div></section>
<section><h2>All {len(FLOWS['flows'])} Flows</h2>{flows_table()}<p class="muted">Last verified {e(nice_date(FLOWS['verified']))}.</p></section>
{ad("in-content")}
<section><h2>Choosing a Flow</h2><div class="prose"><ul>
<li><strong>Strikers:</strong> Emperor, Destructive Impulses and Godspeed boost shot power and speed.</li>
<li><strong>Dribblers:</strong> Butterfly Dancer and Bee Freestyle add dribbles and stronger ankle breaks.</li>
<li><strong>Playmakers:</strong> Awakened Genius, Contrarian and Genius feed Flow to teammates.</li>
<li><strong>Defenders:</strong> King's Authority and Snake shorten tackle cooldowns.</li>
<li><strong>Style-specific picks:</strong> Trap pairs with Nagi; Singularity is built around NEL Nagi; Master of all Trades suits Chameleon users.</li></ul>
<p>See how they rank on the <a href="/tier-list/">tier list</a>.</p></div></section>"""


def tier_body():
    return f"""<section><h2>Style tier list</h2><p class="muted">{e(TIERS['note'])} Last reviewed {e(nice_date(TIERS['updated']))}.</p>{tier_block('styles')}</section>
{ad("in-content")}
<section><h2>Flow tier list</h2>{tier_block('flows')}</section>
<section><h2>How to read this list</h2><div class="prose">
<p><strong>S</strong> picks define the current meta and win games on their own. <strong>A</strong> is excellent and often a better fit for specific roles. <strong>B</strong> is solid. <strong>C</strong> works if you know it well. <strong>D</strong> is reroll material.</p>
<p>Balance changes land almost every week, so treat this as a guide rather than a law — a well-played B-tier style beats a badly played S-tier one.</p>
<p>Need more rolls? Grab the <a href="/">latest codes</a> or read the <a href="/free-spins/">free spins guide</a>.</p></div></section>"""


def controls_body():
    rows = [("Move", "W A S D"),
            ("Aim", "Mouse"),
            ("Shoot (hold to charge)", "Left mouse button (M1)"),
            ("Dribble", "Q"),
            ("Tackle", "F"),
            ("Style abilities", "C · V · B"),
            ("Activate Flow", "G")]
    table = ('<div class="table-wrap"><table><thead><tr><th>Action</th><th>PC key</th></tr></thead><tbody>' +
             "".join(f"<tr><td><strong>{e(a)}</strong></td><td><code>{e(b)}</code></td></tr>" for a, b in rows) +
             "</tbody></table></div>")
    return f"""<section><h2>PC controls</h2>{table}
<p class="muted">These are the commonly reported defaults. The game is updated weekly and keys can be remapped, so check Settings → Controls in-game for your exact layout.</p></section>
<section><h2>Mobile and controller</h2><div class="prose">
<p><strong>Mobile:</strong> a virtual joystick moves you, and on-screen buttons handle shooting, dribbling, tackling, your three Style abilities and Flow. Every button can be resized and repositioned in Settings.</p>
<p><strong>Controller (Xbox, PlayStation, or Bluetooth on mobile):</strong> the left stick moves, the right stick controls the camera, and actions sit on the triggers, bumpers and face buttons. Open Settings in-game to see the full map for your pad.</p></div></section>
<section><h2>Control tips</h2><div class="prose"><ul>
<li><strong>Use shift lock</strong> on PC — aiming shots and passes is far easier with the camera locked behind you.</li>
<li><strong>Mobile players:</strong> move the ability buttons in Settings so your thumb can reach C, V and B without letting go of the joystick. A Bluetooth controller is the biggest upgrade you can make.</li>
<li><strong>Save Flow</strong> for a moment that matters — a counter-attack or the last minute — rather than popping it on kickoff.</li>
<li><strong>Practice in a private server</strong> to learn each style's cooldowns without hurting your rank.</li></ul></div></section>"""


def beginners_body():
    return f"""<section><h2>Your first hour</h2><ol class="steps">
<li><div><strong>Redeem every code</strong>Join the group, reach level 10 and redeem the <a href="/">active codes</a> for free Lucky spins.</div></li>
<li><div><strong>Roll for a Style</strong>Use Lucky Style Spins first. Anything Mythic or above is worth keeping — lock the slot.</div></li>
<li><div><strong>Roll for a Flow</strong>Match your Flow to your Style: shooting Flows for strikers, dribble Flows for wingers.</div></li>
<li><div><strong>Learn your three abilities</strong>Read each ability's cooldown and practise them in a casual or private match.</div></li>
<li><div><strong>Move to Ranked when ready</strong>Ranked affects your standing — learn positioning in casual games first.</div></li></ol></section>
<section><h2>Gameplay fundamentals</h2><div class="prose"><ul>
<li><strong>Pass early.</strong> Release the ball before a defender closes in — getting tackled costs your team more than a safe pass.</li>
<li><strong>Know your role.</strong> Some styles are finishers, some are playmakers, some are defenders. Play to your kit.</li>
<li><strong>Recover before you tackle.</strong> After losing the ball, get goal-side first; diving in from behind rarely works.</li>
<li><strong>Time your Flow.</strong> Activating it at the right moment wins more games than activating it often.</li>
<li><strong>Don't all chase the ball.</strong> Spread out — five players on one ball means nobody is open.</li></ul></div></section>
<section><h2>Keep going</h2>{guides_cards()}</section>"""


def links_body():
    return f"""<section><h2>Official channels</h2><div class="prose">
<p>These are the places the developer actually posts news and codes. Bookmark them — or let this site watch them for you.</p></div>
<div class="cards">
<a class="gcard" href="{e(SITE['discord_url'])}" target="_blank" rel="noopener"><strong>Discord server</strong><span>Update announcements, codes and patch notes appear here first.</span></a>
<a class="gcard" href="{e(SITE['trello_url'])}" target="_blank" rel="noopener"><strong>Trello board</strong><span>Community reference for styles, flows, mechanics and controls.</span></a>
<a class="gcard" href="{e(SITE['roblox_group_url'])}" target="_blank" rel="noopener"><strong>Roblox group</strong><span>Joining is required to redeem codes.</span></a>
<a class="gcard" href="{e(SITE['roblox_url'])}" target="_blank" rel="noopener"><strong>Game page</strong><span>Play Blue Lock: Rivals on Roblox. The title shows the current update.</span></a></div></section>
<section><h2>Staying safe</h2><div class="prose"><ul>
<li>Codes are always free. Anyone selling codes or "spin generators" is scamming you.</li>
<li>Never enter your Roblox password anywhere except roblox.com.</li>
<li>Only trust Discord links shared from the official game page or group.</li></ul></div></section>"""


def updates_body():
    return f"""<section><h2>Update history</h2>
<p>New updates are logged automatically when the game's title on Roblox changes. Most updates go live on Saturday.</p>
{updates_timeline()}</section>"""


def guides_body():
    return f"""<section><h2>All guides</h2>{guides_cards()}</section>"""


def about_body():
    return f"""<section><h2>About this site</h2><div class="prose">
<p>{e(SITE['name'])} exists for one reason: so you never miss a free code for Blue Lock: Rivals. It's run by {e(SITE['author'])}, a long-time player of the game.</p>
<h3>How codes are found</h3>
<p>An automated tracker checks the official channels and a number of established code trackers every 30 minutes. A new code is only published once <strong>at least two independent sources</strong> list it, which keeps typos and fake codes off the page. When sources report a code as dead — or it disappears everywhere — it moves to the expired list automatically.</p>
<p>Spotted a mistake? Email <a href="mailto:{e(SITE['contact_email'])}">{e(SITE['contact_email'])}</a> and it'll be fixed.</p>
<h3>Independence</h3><p>This is an unofficial fan site. It isn't affiliated with Roblox Corporation, {e(SITE['developer'])}, Kodansha or the creators of Blue Lock.</p></div></section>"""


def privacy_body():
    return f"""<section><div class="prose">
<p><em>Last updated {e(nice_date(NOW.isoformat()))}</em></p>
<h3>What we collect</h3><p>This site has no accounts, no sign-ups and no forms. We don't collect your name or email unless you email us yourself.</p>
<h3>Hosting logs</h3><p>The site is hosted on GitHub Pages. GitHub may log technical data such as IP addresses for security and operations. See GitHub's privacy statement for details.</p>
<h3>Advertising</h3><p>If advertising is enabled, Google AdSense and its partners may use cookies to serve ads based on your visits to this and other websites. You can opt out of personalised advertising at <a href="https://adssettings.google.com" rel="noopener" target="_blank">Google Ads Settings</a>.</p>
<h3>Local storage</h3><p>Copying a code uses your browser's clipboard only; nothing is sent to us.</p>
<h3>Children</h3><p>We don't knowingly collect any personal information from anyone, including children under 13.</p>
<h3>Contact</h3><p>Questions? Email <a href="mailto:{e(SITE['contact_email'])}">{e(SITE['contact_email'])}</a>.</p></div></section>"""


def article_ld(page):
    return {"@context": "https://schema.org", "@type": "Article", "headline": page["title"],
            "dateModified": CODES.get("updated"), "author": {"@type": "Person", "name": SITE["author"]},
            "publisher": {"@type": "Organization", "name": SITE["name"]},
            "mainEntityOfPage": SITE["base_url"] + page["path"]}


PAGES = [
    dict(path="/", out="index.html", title=f"Blue Lock Rivals Codes ({MONTH_YEAR}) – All Working Codes",
         title_short="Active Codes",
         description=f"All {len(ACTIVE)} working Blue Lock Rivals codes for {MONTH_YEAR}. Free Lucky Style Spins and Flow Spins, checked every 30 minutes.",
         body=home_body, blurb="Every working code right now."),
    dict(path="/expired-codes/", out="expired-codes/index.html", title="Expired Blue Lock Rivals Codes – Full Archive",
         title_short="Expired Codes", h1="Expired Blue Lock Rivals codes",
         lede="Every code that no longer works, so you can stop trying them.",
         description=f"The full list of {len(EXPIRED)} expired Blue Lock Rivals codes that no longer work.",
         body=expired_body, blurb="Codes that no longer work.", in_sidebar=True),
    dict(path="/how-to-redeem/", out="how-to-redeem/index.html", title="How to Redeem Blue Lock Rivals Codes (Fix 'Invalid' Errors)",
         title_short="How to Redeem", h1="How to redeem Blue Lock Rivals codes",
         lede="Four quick steps, the two requirements most people miss, and fixes for every error message.",
         description="Step-by-step guide to redeeming Blue Lock Rivals codes, including the group and level 10 requirements and fixes for invalid code errors.",
         body=redeem_body, blurb="Steps, requirements and error fixes.", in_guides=True, in_sidebar=True, faq=REDEEM_FAQ),
    dict(path="/free-spins/", out="free-spins/index.html", title="How to Get Free Spins in Blue Lock Rivals",
         title_short="Free Spins", h1="How to get free spins in Blue Lock Rivals",
         lede="Every free source of Style and Flow spins — and how to avoid wasting them.",
         description="All the ways to get free Lucky Style Spins and Flow Spins in Blue Lock Rivals: codes, Yen, quests, events and pity.",
         body=spins_body, blurb="Codes, Yen, quests, events and pity.", in_guides=True, in_sidebar=True),
    dict(path="/styles/", out="styles/index.html", title="All Blue Lock Rivals Styles & Rarities (Full List)",
         title_short="Styles", h1="Every Blue Lock Rivals Style",
         lede="The complete Style list, grouped by rarity from Rare to Master, including limited event styles.",
         description="Complete list of every Style in Blue Lock Rivals with its rarity: Rare, Epic, Legendary, Mythic, World Class, Master and Limited.",
         body=styles_body, blurb="Every style and its rarity.", in_guides=True, in_sidebar=True),
    dict(path="/flows/", out="flows/index.html", title="All Blue Lock Rivals Flows – Rarities & Effects",
         title_short="Flows", h1="Every Blue Lock Rivals Flow",
         lede="What each Flow does, how rare it is, and which ones fit your Style.",
         description=f"All {len(FLOWS['flows'])} Flows in Blue Lock Rivals with rarities and effects, plus how Flow spins and pity work.",
         body=flows_body, blurb="Effects, rarities and best pairings.", in_guides=True, in_sidebar=True),
    dict(path="/tier-list/", out="tier-list/index.html", title="Blue Lock Rivals Tier List – Best Styles & Flows",
         title_short="Tier List", h1="Blue Lock Rivals tier list",
         lede="The best Styles and Flows in the current meta, ranked S to D.",
         description="Blue Lock Rivals tier list ranking every Style and Flow from S to D for the current meta.",
         body=tier_body, blurb="Best styles and flows, S to D.", in_guides=True, in_sidebar=True),
    dict(path="/controls/", out="controls/index.html", title="Blue Lock Rivals Controls – PC, Mobile & Controller",
         title_short="Controls", h1="Blue Lock Rivals controls",
         lede="Default keybinds for PC, controller and mobile, plus tips for every platform.",
         description="Blue Lock Rivals controls and keybinds for PC, mobile and controller, with tips for shooting, dribbling and using Flow.",
         body=controls_body, blurb="Keybinds for every platform.", in_guides=True, in_sidebar=True),
    dict(path="/beginners-guide/", out="beginners-guide/index.html", title="Blue Lock Rivals Beginner's Guide – Tips to Win More",
         title_short="Beginner's Guide", h1="Blue Lock Rivals beginner's guide",
         lede="What to do in your first hour, and the fundamentals that win matches.",
         description="New to Blue Lock Rivals? Redeem codes, roll the right Style and Flow, and learn the fundamentals that win matches.",
         body=beginners_body, blurb="First steps and core tips.", in_guides=True, in_sidebar=True),
    dict(path="/trello-discord/", out="trello-discord/index.html", title="Blue Lock Rivals Trello, Discord & Official Links",
         title_short="Trello & Discord", h1="Blue Lock Rivals Trello & Discord",
         lede="The official places the developer posts updates and codes.",
         description="Official Blue Lock Rivals Discord, Trello board, Roblox group and game links — where codes are announced.",
         body=links_body, blurb="Official Discord, Trello and group.", in_guides=True, in_sidebar=True),
    dict(path="/updates/", out="updates/index.html", title="Blue Lock Rivals Update Log & Patch History",
         title_short="Update Log", h1="Blue Lock Rivals update log",
         lede="Every recent update and the codes that came with it.",
         description="History of Blue Lock Rivals updates with release dates and the codes released with each one.",
         body=updates_body, blurb="Every update and its codes.", in_guides=True, in_sidebar=True),
    dict(path="/guides/", out="guides/index.html", title="Blue Lock Rivals Guides", title_short="Guides",
         h1="Blue Lock Rivals guides", lede="Everything beyond codes: styles, flows, controls and more.",
         description="All Blue Lock Rivals guides: styles, flows, tier list, controls, free spins and beginner tips.",
         body=guides_body, blurb=""),
    dict(path="/about/", out="about/index.html", title=f"About {SITE['name']}", title_short="About",
         h1="About this site", lede="Who runs it and how codes are verified.",
         description="How Blue Lock Rivals Codes finds and verifies new codes.", body=about_body, blurb=""),
    dict(path="/privacy-policy.html", out="privacy-policy.html", title="Privacy Policy", title_short="Privacy Policy",
         h1="Privacy policy", lede="Short version: we don't collect personal data.",
         description=f"Privacy policy for {SITE['domain']}.", body=privacy_body, blurb="", sidebar=False),
]

for p in PAGES:
    p.setdefault("jsonld", [])
    p["jsonld"] = [article_ld(p)]
    if p["path"] == "/":
        p["jsonld"].append(faq_ld(HOME_FAQ))
    if p.get("faq"):
        p["jsonld"].append(faq_ld(p["faq"]))
    if p["path"] != "/":
        p["jsonld"].append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE["base_url"] + "/"},
            {"@type": "ListItem", "position": 2, "name": p["title_short"], "item": SITE["base_url"] + p["path"]}]})


# --------------------------------------------------------------------------- #
# Extra outputs
# --------------------------------------------------------------------------- #

def sitemap():
    lastmod = CODES.get("updated", NOW.isoformat())[:10]
    urls = "".join(f"<url><loc>{e(SITE['base_url'] + p['path'])}</loc><lastmod>{lastmod}</lastmod>"
                   f"<changefreq>{'hourly' if p['path'] == '/' else 'weekly'}</changefreq></url>" for p in PAGES)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


def feed():
    items = []
    for c in sorted(ACTIVE + [x for x in EXPIRED if x.get("added")], key=lambda c: c.get("added", ""), reverse=True)[:30]:
        if not c.get("added"):
            continue
        dt = datetime.fromisoformat(c["added"][:10]).replace(tzinfo=timezone.utc)
        items.append(f"<item><title>New code: {e(c['code'])}</title><link>{e(SITE['base_url'])}/</link>"
                     f"<guid isPermaLink=\"false\">blr-{e(c['code'])}</guid><pubDate>{format_datetime(dt)}</pubDate>"
                     f"<description>{e(c.get('reward', ''))}</description></item>")
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{e(SITE["name"])}</title>'
            f'<link>{e(SITE["base_url"])}/</link><description>New Blue Lock Rivals codes as soon as they release.</description>'
            f'<lastBuildDate>{format_datetime(NOW)}</lastBuildDate>{"".join(items)}</channel></rss>')


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#1D4EFF"/><circle cx="16" cy="16" r="9" fill="none" stroke="#fff" stroke-width="2.2"/><path d="M16 10.5l4.2 3-1.6 4.8h-5.2l-1.6-4.8z" fill="#fff"/></svg>"""


def not_found():
    page = dict(path="/404.html", title="Page not found", title_short="Not found", h1="Offside.",
                lede="That page doesn't exist — but the codes do.", description="Page not found.",
                body=lambda: '<section><p><a class="btn primary" href="/">See all active codes →</a></p></section>',
                sidebar=False, jsonld=[])
    return render(page)


def build():
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    for f in ASSETS.iterdir():
        if f.is_file():
            target = DIST / ("author.png" if f.name == "author.png" else f"assets/{f.name}")
            shutil.copy2(f, target)
    for p in PAGES:
        out = DIST / p["out"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(p), encoding="utf-8")
    (DIST / "404.html").write_text(not_found(), encoding="utf-8")
    (DIST / "sitemap.xml").write_text(sitemap(), encoding="utf-8")
    (DIST / "feed.xml").write_text(feed(), encoding="utf-8")
    (DIST / "favicon.svg").write_text(FAVICON, encoding="utf-8")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE['base_url']}/sitemap.xml\n", encoding="utf-8")
    (DIST / "CNAME").write_text(SITE["domain"] + "\n", encoding="utf-8")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")
    pub = SITE.get("adsense_client", "").replace("ca-", "")
    if pub:
        (DIST / "ads.txt").write_text(f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")
    api = DIST / "api"
    api.mkdir()
    (api / "codes.json").write_text(json.dumps({"updated": CODES.get("updated"), "last_checked": CODES.get("last_checked"),
                                                 "active": ACTIVE, "expired": [c["code"] for c in EXPIRED]},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    og = ASSETS / "og.png"
    if og.exists():
        shutil.copy2(og, DIST / "og.png")
    print(f"Built {len(PAGES) + 1} pages → {DIST.relative_to(ROOT)}/  ({len(ACTIVE)} active, {len(EXPIRED)} expired)")


if __name__ == "__main__":
    build()
