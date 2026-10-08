#!/usr/bin/env python3
"""Automatic code tracker for Blue Lock: Rivals.

Every run:
  1. Reads each page in data/sources.json (respecting robots.txt).
  2. Extracts only code strings + reward counts (no article text is stored).
  3. Publishes a new code only when >= min_confirmations sources list it as
     active and no source lists it as expired.
  4. Expires a code when >= expire_votes sources list it as expired, or when
     every healthy source has stopped listing it for miss_runs_before_expire runs.
  5. Tracks the game's update name from its Roblox title and logs new updates.

Safety rails: if one run tries to add or expire an unusual number of codes
(a parser broke, a site redesigned), it changes nothing and exits non-zero so
the GitHub Action shows a red X instead of publishing garbage.

Standard library only.

    python scripts/update_codes.py            # live run, writes data/*.json
    python scripts/update_codes.py --dry-run  # print what would change
    python scripts/update_codes.py --fixtures tests/fixtures   # offline test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
import urllib.robotparser
from collections import Counter, defaultdict
from datetime import datetime, timezone, date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "BLRCodesBot/1.0 (+https://blue-lock-rivals-codes.com/about/)"
TIMEOUT = 25

# --------------------------------------------------------------------------- #
# HTML → ordered text blocks
# --------------------------------------------------------------------------- #

BLOCK_TAGS = {"p", "li", "tr", "h1", "h2", "h3", "h4", "h5", "div", "section", "td", "th", "dd", "dt", "summary"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5"}
SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "form", "button", "select", "aside"}


class Blocks(HTMLParser):
    """Turns a page into a list of (kind, text) where kind is heading|item|row|text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self.buf: list[str] = []
        self.kind = "text"
        self.skip = 0
        self.cells: list[str] | None = None
        self.cell_buf: list[str] = []

    def flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text:
            self.blocks.append((self.kind, text))
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "tr":
            self.flush()
            self.cells = []
            return
        if tag in ("td", "th") and self.cells is not None:
            self.cell_buf = []
            return
        if tag in BLOCK_TAGS:
            self.flush()
            self.kind = "heading" if tag in HEADING_TAGS else "item" if tag == "li" else "text"
        if tag == "br":
            self.buf.append(" ")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ("td", "th") and self.cells is not None:
            self.cells.append(re.sub(r"\s+", " ", "".join(self.cell_buf)).strip())
            self.cell_buf = []
            return
        if tag == "tr" and self.cells is not None:
            cells = [c for c in self.cells if c]
            if cells:
                self.blocks.append(("row", " | ".join(cells)))
            self.cells = None
            return
        if tag in BLOCK_TAGS:
            self.flush()
            self.kind = "text"

    def handle_data(self, data):
        if self.skip:
            return
        if self.cells is not None:
            self.cell_buf.append(data)
        else:
            self.buf.append(data)

    def close(self):
        super().close()
        self.flush()


# --------------------------------------------------------------------------- #
# Code extraction
# --------------------------------------------------------------------------- #

CODE_RE = re.compile(r"^[`*\s]*(?:(?:\d{1,3}[.)]|#)\s+)?[`*\s]*([A-Za-z0-9][A-Za-z0-9!@#.?\-_]{2,31})[`*]*(?:\s*(?:[-–—:|]|\(|$)\s*(.*))?$")
REWARD_HINT = re.compile(r"\b(spins?|flows?|yen|cash|reward|lucky|style)\b", re.I)
EXPIRED_HEAD = re.compile(r"\b(expired|inactive|no longer work|old codes|retired|invalid)\b", re.I)
ACTIVE_HEAD = re.compile(r"\b(active|working|new|valid|latest|all)\b.*\bcodes?\b|\bcodes?\b.*\b(active|working)\b", re.I)
STOPWORDS = {
    "CODE", "CODES", "REWARD", "REWARDS", "ACTIVE", "EXPIRED", "WORKING", "COPY", "COPIED", "NEW", "REDEEM",
    "LUCKY", "SPINS", "FLOWS", "STYLE", "STYLES", "FLOW", "FIVE", "NONE", "YES", "NO", "EXPIRY", "DATE", "ADDED",
    "LOAD", "MORE", "SHOW", "HIDE", "UPDATE", "UPDATED", "ROBLOX", "BLUE", "LOCK", "RIVALS", "THE", "AND", "HOW",
    "WHAT", "WHY", "WHERE", "NOTE", "TIP", "TIPS", "FAQ", "HERE", "EXPIRES", "UNKNOWN", "TBA", "STATUS",
}


def looks_like_code(tok: str) -> bool:
    letters = sum(ch.isalpha() for ch in tok)
    if letters < 3 or tok.upper() in STOPWORDS:
        return False
    # Codes are written in caps or CamelCase; plain lowercase words are prose.
    if tok.islower():
        return False
    upper = sum(ch.isupper() for ch in tok)
    if upper < 2:
        return False
    return True


def parse_reward(text: str) -> tuple[int, int]:
    """Return (style_spins, flow_spins) from free-form reward text."""
    t = text.lower().replace("five", "5").replace("ten", "10").replace("three", "3").replace("two", "2")
    spins = flows = 0
    for num, what in re.findall(r"(\d+)\s*(?:x\s*)?(?:lucky\s*)?(style\s*spins?|spins?|flow\s*spins?|flows?)", t):
        if "flow" in what:
            flows += int(num)
        else:
            spins += int(num)
    return spins, flows


def extract(html_text: str) -> dict:
    """Return {"active": {KEY: {"code","reward"}}, "expired": {KEY: code}}."""
    p = Blocks()
    p.feed(html_text)
    p.close()
    mode = None  # None | "active" | "expired"
    active: dict[str, dict] = {}
    expired: dict[str, str] = {}
    for kind, text in p.blocks:
        if kind == "heading" or (kind == "text" and len(text) < 90 and text.rstrip(":").endswith(("codes", "Codes", "CODES"))):
            if EXPIRED_HEAD.search(text):
                mode = "expired"
            elif ACTIVE_HEAD.search(text) or "code" in text.lower():
                mode = "active"
            elif kind == "heading":
                mode = None
            continue
        if mode is None or kind not in ("item", "row", "text") or len(text) > 160:
            continue
        if kind == "row":
            cells = [c.strip(" `*") for c in text.split(" | ")]
            if cells and cells[0].isdigit():
                cells = cells[1:]
            if not cells:
                continue
            m = CODE_RE.match(cells[0])
            tok, rest = (m.group(1), " ".join(cells[1:])) if m else (None, "")
        else:
            if kind == "text" and mode == "active":
                continue  # loose paragraphs in the active section are prose
            m = CODE_RE.match(text)
            tok, rest = (m.group(1), m.group(2) or "") if m else (None, "")
        if not tok or not looks_like_code(tok):
            continue
        key = tok.upper()
        if mode == "active":
            if not REWARD_HINT.search(rest):
                continue  # an active entry must say what it gives
            active[key] = {"code": tok, "reward": rest.strip(" -–—:|()").split(" Copy")[0][:80]}
        elif mode == "expired":
            if rest and len(rest.split()) > 8:
                continue
            expired[key] = tok
    for k in list(active):
        if k in expired:  # a page listing both is contradicting itself; trust neither
            active.pop(k)
    return {"active": active, "expired": expired}


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def allowed(url: str) -> bool:
    host = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(host + "/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                rp.parse(r.read().decode("utf-8", "replace").splitlines())
            _robots[host] = rp
        except Exception:
            _robots[host] = None  # unreachable robots.txt → treat as allowed
    rp = _robots[host]
    return True if rp is None else rp.can_fetch(UA, url)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json",
                                               "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")


def roblox_title(place_id: int) -> str | None:
    try:
        u = json.loads(fetch(f"https://apis.roblox.com/universes/v1/places/{place_id}/universe"))["universeId"]
        g = json.loads(fetch(f"https://games.roblox.com/v1/games?universeIds={u}"))
        return g["data"][0]["name"]
    except Exception as ex:
        print(f"  ! Roblox title lookup failed: {ex}")
        return None


def update_name_from_title(title: str) -> str | None:
    m = re.match(r"\s*\[([^\]]+)\]", title or "")
    if not m:
        return None
    name = re.sub(r"[^\w\s'&!.\-]", "", m.group(1)).strip()
    name = re.sub(r"^(UPD|UPDATE)\s*", "", name, flags=re.I).strip()
    return name.title() if name.isupper() else name or None


# --------------------------------------------------------------------------- #
# Reconcile
# --------------------------------------------------------------------------- #

def load(name, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def majority(values):
    values = [v for v in values if v]
    return Counter(values).most_common(1)[0][0] if values else ""


def reconcile(codes: dict, state: dict, results: dict[str, dict], cfg: dict, today: str) -> dict:
    """Pure function: returns a report dict and mutates codes/state in place."""
    min_conf = int(cfg.get("min_confirmations", 2))
    exp_votes = int(cfg.get("expire_votes", 2))
    miss_limit = int(cfg.get("miss_runs_before_expire", 12))

    healthy = {s: r for s, r in results.items() if r and (r["active"] or r["expired"])}
    act_votes: dict[str, list] = defaultdict(list)
    exp_vote: dict[str, list] = defaultdict(list)
    for src, r in healthy.items():
        for k, v in r["active"].items():
            act_votes[k].append((src, v))
        for k, v in r["expired"].items():
            exp_vote[k].append((src, v))

    active_keys = {c["code"].upper(): c for c in codes["active"]}
    expired_keys = {c["code"].upper() for c in codes["expired"]}
    added, expired_now, archived = [], [], []
    misses = state.setdefault("misses", {})

    # 1) New codes
    for k, votes in act_votes.items():
        if k in active_keys or k in expired_keys:
            continue
        if len({s for s, _ in votes}) >= min_conf and not exp_vote.get(k):
            code_str = majority([v["code"] for _, v in votes])
            reward = majority([v["reward"] for _, v in votes])
            spins, flows = Counter(), Counter()
            for _, v in votes:
                s, f = parse_reward(v["reward"])
                spins[s] += 1
                flows[f] += 1
            s, f = spins.most_common(1)[0][0], flows.most_common(1)[0][0]
            pretty = " + ".join(x for x in [f"{s} Lucky Style Spins" if s else "", f"{f} Lucky Flow Spins" if f else ""] if x) or reward
            added.append({"code": code_str, "reward": pretty, "spins": s, "flows": f, "added": today,
                          "sources": sorted({src for src, _ in votes})})

    # 2) Expire codes
    for k, c in active_keys.items():
        votes = {s for s, _ in exp_vote.get(k, [])}
        still_listed = {s for s, _ in act_votes.get(k, [])}
        reason = None
        if len(votes) >= exp_votes:
            reason = f"listed as expired by {', '.join(sorted(votes))}"
        elif len(healthy) >= min_conf and not still_listed:
            misses[k] = misses.get(k, 0) + 1
            if misses[k] >= miss_limit:
                reason = f"missing from all sources for {misses[k]} runs"
        else:
            misses.pop(k, None)
        if reason:
            expired_now.append((c, reason))

    # 3) Grow the archive with codes several sources agree are dead
    known = expired_keys | set(active_keys) | {a["code"].upper() for a in added}
    for k, votes in exp_vote.items():
        if k not in known and len({s for s, _ in votes}) >= exp_votes:
            archived.append({"code": majority([v for _, v in votes])})

    return {"healthy": sorted(healthy), "added": added, "expired": expired_now, "archived": archived}


def apply(codes, state, report, now_iso):
    for c, _ in report["expired"]:
        codes["active"] = [a for a in codes["active"] if a["code"].upper() != c["code"].upper()]
        entry = {"code": c["code"], "added": c.get("added"), "expired": now_iso[:10]}
        codes["expired"].insert(0, {k: v for k, v in entry.items() if v})
        state["misses"].pop(c["code"].upper(), None)
    for a in report["added"]:
        codes["active"].insert(0, a)
    codes["expired"].extend(report["archived"])
    if report["added"] or report["expired"] or report["archived"]:
        codes["updated"] = now_iso


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #

def notify_discord(added, site_url):
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not hook or not added:
        return
    lines = "\n".join(f"**`{a['code']}`** — {a['reward']}" for a in added)
    body = json.dumps({"username": "Blue Lock Rivals Codes",
                       "content": f"⚽ New Blue Lock Rivals code{'s' if len(added) > 1 else ''}!\n{lines}\n{site_url}"}).encode()
    try:
        req = urllib.request.Request(hook, data=body, headers={"Content-Type": "application/json", "User-Agent": UA})
        urllib.request.urlopen(req, timeout=TIMEOUT).read()
        print("  ✓ Discord notified")
    except Exception as ex:
        print(f"  ! Discord notify failed: {ex}")


def ping_indexnow(site):
    """Tell Bing/Yandex (IndexNow) the codes pages changed. Skipped on the github.io preview."""
    key, base = site.get("indexnow_key"), site.get("base_url", "")
    if not key or not base or os.environ.get("BASE_PATH"):
        return
    host = urlparse(base).netloc
    urls = [base + p for p in ("/", "/expired-codes/", "/updates/", "/next-update/")]
    body = json.dumps({"host": host, "key": key, "keyLocation": f"{base}/{key}.txt", "urlList": urls}).encode()
    try:
        req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                                     headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": UA})
        urllib.request.urlopen(req, timeout=TIMEOUT).read()
        print("  ✓ IndexNow pinged")
    except Exception as ex:
        print(f"  ! IndexNow ping failed: {ex}")


def gh_output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fixtures", help="read <dir>/<slug>.html instead of fetching (offline tests)")
    ap.add_argument("--force", action="store_true", help="bypass the max adds/expires safety rail")
    args = ap.parse_args()

    cfg = load("sources.json", {})
    site = load("site.json", {})
    codes = load("codes.json", {"active": [], "expired": []})
    state = load("state.json", {"misses": {}})
    state_before = json.dumps(state, sort_keys=True)
    updates = load("updates.json", {"updates": []})
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_iso = now.isoformat().replace("+00:00", "Z")
    today = now.date().isoformat()

    results = {}
    for s in cfg.get("sources", []):
        if not s.get("enabled", True):
            continue
        name = s["name"]
        try:
            if args.fixtures:
                f = Path(args.fixtures) / (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + ".html")
                if not f.exists():
                    continue
                page = f.read_text(encoding="utf-8")
            else:
                if not allowed(s["url"]):
                    print(f"  - {name}: robots.txt disallows, skipped")
                    continue
                page = fetch(s["url"])
            r = extract(page)
            results[name] = r
            print(f"  ✓ {name}: {len(r['active'])} active, {len(r['expired'])} expired")
        except (urllib.error.URLError, TimeoutError, OSError) as ex:
            print(f"  ! {name}: {ex}")
            results[name] = None

    report = reconcile(codes, state, results, cfg, today)
    print(f"Healthy sources: {len(report['healthy'])}/{len(results)}")

    if len(report["healthy"]) < int(cfg.get("min_confirmations", 2)):
        print("Not enough healthy sources this run — no changes made.")
        gh_output(changed="false")
        return 0

    too_many = (len(report["added"]) > int(cfg.get("max_adds_per_run", 6)) or
                len(report["expired"]) > int(cfg.get("max_expires_per_run", 8)))
    if too_many and not args.force:
        print(f"::error::Safety rail tripped: {len(report['added'])} adds / {len(report['expired'])} expiries in one run. "
              "A source page probably changed layout. Nothing was written. Re-run with --force if this is real.")
        for a in report["added"]:
            print(f"   would add {a['code']} ({', '.join(a['sources'])})")
        for c, why in report["expired"]:
            print(f"   would expire {c['code']} ({why})")
        gh_output(changed="false")
        return 2

    for a in report["added"]:
        print(f"  + NEW {a['code']} — {a['reward']}  [{', '.join(a['sources'])}]")
    for c, why in report["expired"]:
        print(f"  - EXPIRED {c['code']} ({why})")
    if report["archived"]:
        print(f"  ~ archived {len(report['archived'])} previously unknown expired codes")

    # Game update tracking
    upd_changed = False
    if not args.fixtures and site.get("roblox_place_id"):
        title = roblox_title(site["roblox_place_id"])
        name = update_name_from_title(title) if title else None
        if name and name != state.get("update_name"):
            print(f"  ★ Game update detected: {name}")
            if state.get("update_name") is not None:  # skip on very first run
                updates["updates"].insert(0, {"date": today, "name": name, "codes": []})
            state["update_name"] = name
            upd_changed = True
    if report["added"] and updates["updates"]:
        latest = updates["updates"][0]
        if (date.fromisoformat(today) - date.fromisoformat(latest["date"])).days <= 3:
            latest.setdefault("codes", []).extend(a["code"] for a in report["added"])
            upd_changed = True

    apply(codes, state, report, now_iso)
    changed = bool(report["added"] or report["expired"] or report["archived"] or upd_changed)

    if args.dry_run:
        print("Dry run — nothing written.")
        gh_output(changed="false")
        return 0

    state.pop("last_run", None)
    state_changed = json.dumps(state, sort_keys=True) != state_before
    if state_changed:
        save("state.json", state)
    if changed:
        save("codes.json", codes)
        save("updates.json", updates)
        notify_discord(report["added"], site.get("base_url", ""))
        ping_indexnow(site)
    gh_output(changed=str(changed).lower(), state_changed=str(state_changed).lower(), added=",".join(a["code"] for a in report["added"]))
    print("Changes written." if changed else "No code changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
