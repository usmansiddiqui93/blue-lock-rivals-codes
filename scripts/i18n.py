"""Translation layer for blue-lock-rivals-codes.com.

How it works
------------
The English site is rendered once. Each page is then split into *segments*: the
inner HTML of every element that directly holds text (a paragraph, list item,
heading, table cell, button label...). Each segment becomes a template where

  * inline tags turn into numbered pairs   <0>...</0>
  * icons / empty tags turn into atoms      <x1/>
  * codes, style/flow names, numbers and dates turn into values  {2}

so "As of <D>, there are 3 working codes: <strong>EPICSENDOU</strong>..." becomes
"As of {0}, there are {1} working Blue Lock Rivals codes: <2>{3}</2>..." and one
translation keeps working when the codes, counts or dates change.

Translations live in data/i18n/<lang>.json as {english_template: translated_template}.
A segment without a translation (new text added later) stays in English, and
`python scripts/i18n.py report` lists what is missing per language.
"""
from __future__ import annotations

import html as H
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
I18N_DIR = ROOT / "data" / "i18n"

# code -> (url prefix, hreflang, native name, text direction)
LANGS = {
    "en": ("", "en", "English", "ltr"),
    "es": ("es", "es", "Español", "ltr"),
    "pt": ("pt", "pt-BR", "Português", "ltr"),
    "fr": ("fr", "fr", "Français", "ltr"),
    "tr": ("tr", "tr", "Türkçe", "ltr"),
    "fa": ("fa", "fa", "فارسی", "rtl"),
    "hi": ("hi", "hi", "हिन्दी", "ltr"),
    "tl": ("tl", "tl", "Filipino", "ltr"),
}

MONTHS = {
    "en": "January February March April May June July August September October November December".split(),
    "es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
    "pt": "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split(),
    "fr": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split(),
    "tr": "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split(),
    "fa": "ژانویه فوریه مارس آوریل مه ژوئن ژوئیه اوت سپتامبر اکتبر نوامبر دسامبر".split(),
    "hi": "जनवरी फ़रवरी मार्च अप्रैल मई जून जुलाई अगस्त सितंबर अक्टूबर नवंबर दिसंबर".split(),
    "tl": "Enero Pebrero Marso Abril Mayo Hunyo Hulyo Agosto Setyembre Oktubre Nobyembre Disyembre".split(),
}


def fmt_date(lang, y, m, d):
    mo = MONTHS[lang][m - 1]
    return {
        "en": f"{mo} {d}, {y}", "tl": f"{mo} {d}, {y}",
        "es": f"{d} de {mo} de {y}", "pt": f"{d} de {mo} de {y}",
        "fr": f"{d} {mo} {y}", "tr": f"{d} {mo} {y}", "fa": f"{d} {mo} {y}", "hi": f"{d} {mo} {y}",
    }[lang]


def fmt_month(lang, y, m):
    mo = MONTHS[lang][m - 1]
    return {"es": f"{mo} de {y}", "pt": f"{mo} de {y}"}.get(lang, f"{mo} {y}")


# Markers the builder writes for dates, replaced per language at the very end.
DATE_MARK = re.compile(r"⟦D:(\d{4})-(\d{2})-(\d{2})⟧")
MONTH_MARK = re.compile(r"⟦M:(\d{4})-(\d{2})⟧")


def localize_markers(text, lang):
    text = DATE_MARK.sub(lambda m: fmt_date(lang, int(m[1]), int(m[2]), int(m[3])), text)
    return MONTH_MARK.sub(lambda m: fmt_month(lang, int(m[1]), int(m[2])), text)


# Strings used by assets/app.js (looked up through window.I18N).
JS_STRINGS = [
    "Copied", "Copy", "All active codes copied", "Link copied", "No matches. Try another word.", "(your time)",
    "{0} min ago", "{0} h ago", "{0} days ago", "just now",
    "Please enter a valid email address.", "Email alerts are launching very soon. Please check back shortly.",
    "You're already subscribed. New codes will come straight to your inbox.",
    "Almost done! Check your inbox and click the link to confirm.", "Something went wrong. Please try again.",
    "Couldn't reach the server. Check your connection and try again.", "Browser notifications",
    "On iPhone/iPad: tap Share, then Add to Home Screen, open the site from there and turn notifications on.",
    "Notifications blocked",
    "Notifications are blocked for this site. Allow them in your browser's site settings to turn them on.",
    "Browser notifications are on", "Tap to turn them off.", "Turn on browser notifications",
    "Browser notifications are launching very soon. Please check back shortly.", "Working…",
    "Browser notifications are off.", "Could not turn on notifications.",
    "Done! You'll get a test notification now, then one for every new code.",
]

SKIP_TAGS = {"script", "style", "noscript", "template"}
ATOMIC_TAGS = {"svg", "img", "br", "input", "select", "time"}  # kept verbatim inside sentences
NO_TRANSLATE_CLASSES = {"cb-code", "ticket-code", "fcode", "expired-list", "latest-code", "langsw"}
ATTRS = ("title", "alt", "placeholder", "aria-label")
META_KEYS = {("name", "description"), ("property", "og:title"), ("property", "og:description"),
             ("property", "og:image:alt"), ("name", "twitter:title"), ("name", "twitter:description")}
LD_TEXT_KEYS = {"name", "headline", "description", "text", "jobTitle"}
NON_PAGE_PREFIXES = ("/assets/", "/api/", "/feed.xml", "/sitemap.xml", "/favicon", "/icon-", "/apple-touch",
                     "/og.png", "/sw.js", "/site.webmanifest", "/robots.txt", "/ads.txt", "/author.png")
NON_PAGE_EXT = (".png", ".jpg", ".jpeg", ".svg", ".xml", ".json", ".js", ".css", ".txt", ".webmanifest", ".ico")


class Segmenter:
    """Turns text into templates by swapping protected values for {n} placeholders."""

    def __init__(self, protected_names):
        names = sorted({n for n in protected_names if n and len(n) >= 2}, key=len, reverse=True)
        alt = "|".join(re.escape(n) for n in names)
        parts = [r"⟦[DM]:[\d-]+⟧"]
        if alt:
            parts.append(rf"(?<![\w])(?:{alt})(?![\w])")
        parts.append(r"\d+(?:[.,:]\d+)*")
        self.rx = re.compile("|".join(parts))

    def text(self, s, slots):
        out, pos = [], 0
        for m in self.rx.finditer(s):
            out.append(s[pos:m.start()])
            k = len(slots)
            slots.append(("val", m.group(0)))
            out.append("{%d}" % k)
            pos = m.end()
        out.append(s[pos:])
        return "".join(out)

    def element(self, el, slots):
        out = []
        for ch in el.children:
            if isinstance(ch, Comment):
                continue
            if isinstance(ch, NavigableString):
                out.append(self.text(str(ch), slots))
                continue
            if not isinstance(ch, Tag):
                continue
            classes = set(ch.get("class") or [])
            if (ch.name in ATOMIC_TAGS or not ch.get_text(strip=True) or classes & NO_TRANSLATE_CLASSES
                    or ch.get("translate") == "no"):
                k = len(slots)
                slots.append(("atom", str(ch)))
                out.append("<x%d/>" % k)
            else:
                k = len(slots)
                slots.append(("tag", open_tag(ch), ch.name))
                out.append("<%d>" % k + self.element(ch, slots) + "</%d>" % k)
        return "".join(out)


def open_tag(t):
    attrs = []
    for k, v in t.attrs.items():
        if isinstance(v, list):
            v = " ".join(v)
        attrs.append(k if v is None else f'{k}="{H.escape(str(v), quote=True)}"')
    return "<" + t.name + ("".join(" " + a for a in attrs)) + ">"


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def worth_translating(template):
    bare = re.sub(r"<\d+>|</\d+>|<x\d+/>|\{\d+\}", "", template)
    return bool(re.search(r"[^\W\d_]{2,}", bare))


TOKEN = re.compile(r"<(\d+)>|</(\d+)>|<x(\d+)/>|\{(\d+)\}")


def placeholders(t):
    return sorted(m.group(0) for m in TOKEN.finditer(t))


def rebuild(template, slots):
    out, pos = [], 0
    for m in TOKEN.finditer(template):
        out.append(H.escape(template[pos:m.start()], quote=False))
        if m.group(1) is not None:
            out.append(slots[int(m.group(1))][1])
        elif m.group(2) is not None:
            out.append("</%s>" % slots[int(m.group(2))][2])
        elif m.group(3) is not None:
            out.append(slots[int(m.group(3))][1])
        else:
            out.append(H.escape(slots[int(m.group(4))][1], quote=False))
        pos = m.end()
    out.append(H.escape(template[pos:], quote=False))
    return "".join(out)


def rebuild_text(template, slots):
    return TOKEN.sub(lambda m: slots[int(m.group(4))][1] if m.group(4) is not None else m.group(0), template)


def iter_segments(root):
    """Yield elements whose own children include real text."""
    for ch in root.children:
        if not isinstance(ch, Tag) or ch.name in SKIP_TAGS:
            continue
        if set(ch.get("class") or []) & NO_TRANSLATE_CLASSES or ch.get("translate") == "no":
            continue
        if ch.name in ATOMIC_TAGS:
            continue
        if any(isinstance(c, NavigableString) and not isinstance(c, Comment) and c.strip() for c in ch.children):
            yield ch
        else:
            yield from iter_segments(ch)


class Page:
    """One rendered English page, ready to be extracted or translated."""

    def __init__(self, html_text, seg: Segmenter):
        self.soup = BeautifulSoup(html_text, "html.parser")
        self.seg = seg

    # -- collection --------------------------------------------------------
    def units(self):
        """Every translatable unit: (kind, element/target, template, slots)."""
        out = []
        body = self.soup.body
        for el in iter_segments(body):
            slots = []
            t = norm(self.seg.element(el, slots))
            if worth_translating(t):
                out.append(("html", el, t, slots))
        for el in body.find_all(True):
            for a in ATTRS:
                if el.has_attr(a) and isinstance(el[a], str):
                    slots = []
                    t = norm(self.seg.text(el[a], slots))
                    if worth_translating(t):
                        out.append(("attr", (el, a), t, slots))
        head = self.soup.head
        if head.title and head.title.string:
            slots = []
            t = norm(self.seg.text(head.title.string, slots))
            out.append(("title", head.title, t, slots))
        for m in head.find_all("meta"):
            for key in ("name", "property"):
                if (key, m.get(key)) in META_KEYS and m.get("content"):
                    slots = []
                    t = norm(self.seg.text(m["content"], slots))
                    if worth_translating(t):
                        out.append(("attr", (m, "content"), t, slots))
        return out

    def ld_strings(self):
        found = []
        for s in self.soup.find_all("script", type="application/ld+json"):
            data = json.loads(s.string)

            def walk(o):
                if isinstance(o, dict):
                    for k, v in o.items():
                        if k in LD_TEXT_KEYS and isinstance(v, str):
                            slots = []
                            t = norm(self.seg.text(v, slots))
                            if worth_translating(t):
                                found.append(t)
                        else:
                            walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)
            walk(data)
        return found


def is_page_path(path):
    if not path.startswith("/") or path.startswith("//"):
        return False
    bare = path.split("#")[0].split("?")[0]
    if bare.startswith(NON_PAGE_PREFIXES) or bare.lower().endswith(NON_PAGE_EXT):
        return False
    return True


def lang_path(lang, path):
    prefix = LANGS[lang][0]
    return path if not prefix else "/" + prefix + path


def localize(html_text, page_path, lang, table, seg, abs_base, missing=None):
    """Return the page translated into `lang` (English when lang == 'en')."""
    page = Page(html_text, seg)
    soup = page.soup
    prefix, hreflang, _, direction = LANGS[lang]

    def tr(template):
        if lang == "en":
            return None
        got = table.get(template)
        if got is None:
            if missing is not None:
                missing.add(template)
            return None
        if placeholders(got) != placeholders(template):
            if missing is not None:
                missing.add(template)
            return None
        return got

    # 1. links to other pages -> same-language versions
    if prefix:
        for el in soup.find_all(href=True):
            if "data-keep-lang" in el.attrs:
                continue
            href = el["href"]
            if href.startswith(abs_base + "/"):
                p = href[len(abs_base):]
                if is_page_path(p):
                    el["href"] = abs_base + lang_path(lang, p)
            elif is_page_path(href):
                el["href"] = lang_path(lang, href)
        for m in soup.find_all("meta", property="og:url"):
            p = m["content"][len(abs_base):]
            m["content"] = abs_base + lang_path(lang, p)

    # 2. text
    for kind, target, template, slots in page.units():
        got = tr(template)
        if got is None:
            continue
        if kind == "html":
            target.clear()
            frag = BeautifulSoup(rebuild(got, slots), "html.parser")
            for node in list(frag.contents):
                target.append(node)
        elif kind == "attr":
            el, a = target
            el[a] = rebuild_text(got, slots)
        elif kind == "title":
            target.string = rebuild_text(got, slots)

    # 3. structured data
    for s in soup.find_all("script", type="application/ld+json"):
        data = json.loads(s.string)

        def walk(o):
            if isinstance(o, dict):
                for k, v in list(o.items()):
                    if k in LD_TEXT_KEYS and isinstance(v, str):
                        slots = []
                        t = norm(seg.text(v, slots))
                        got = tr(t) if worth_translating(t) else None
                        if got:
                            o[k] = rebuild_text(got, slots)
                    elif prefix and k in ("url", "item", "mainEntityOfPage", "@id") and isinstance(v, str) \
                            and v.startswith(abs_base + "/"):
                        p = v[len(abs_base):]
                        if k != "@id" or "#article" in v:
                            if is_page_path(p.split("#")[0] or "/"):
                                o[k] = abs_base + lang_path(lang, p)
                    else:
                        walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(data)
        if prefix:
            data.setdefault("@graph", [])
            for node in data["@graph"]:
                if node.get("@type") in ("Article", "WebPage", "AboutPage", "ProfilePage", "WebSite"):
                    node["inLanguage"] = hreflang
        s.string = json.dumps(data, ensure_ascii=False)

    # 4. <html lang dir>, hreflang alternates, fonts, JS strings
    soup.html["lang"] = hreflang
    if direction == "rtl":
        soup.html["dir"] = "rtl"
    head = soup.head
    for code, (pfx, hl, _, _) in LANGS.items():
        link = soup.new_tag("link", rel="alternate", hreflang=hl, href=abs_base + lang_path(code, page_path))
        head.append(link)
    head.append(soup.new_tag("link", rel="alternate", hreflang="x-default", href=abs_base + page_path))
    font = {"fa": "Vazirmatn:wght@400;600;700;800", "hi": "Noto+Sans+Devanagari:wght@400;600;700;800"}.get(lang)
    if font:
        head.append(soup.new_tag("link", rel="stylesheet",
                                 href=f"https://fonts.googleapis.com/css2?family={font}&display=swap"))
    if lang != "en":
        js = {k: table["js:" + k] for k in JS_STRINGS if table.get("js:" + k)}
        tag = soup.new_tag("script")
        tag.string = "window.I18N=" + json.dumps(js, ensure_ascii=False) + ";"
        head.append(tag)

    # 5. language switcher (links to this page in every language)
    slot = soup.find(id="langsw")
    if slot is not None:
        items = []
        for code, (pfx, hl, native, _) in LANGS.items():
            cur = ' aria-current="true"' if code == lang else ""
            items.append(f'<li><a data-keep-lang hreflang="{hl}" lang="{hl}" href="{lang_path(code, page_path)}"{cur}>{native}</a></li>')
        slot.append(BeautifulSoup(
            f'<summary aria-label="Language">{(prefix or "en").upper()}</summary><ul>{"".join(items)}</ul>',
            "html.parser"))

    return localize_markers(str(soup), lang)


# ---------------------------------------------------------------------------
# CLI helpers: extract source strings / report coverage
# ---------------------------------------------------------------------------

def load_table(lang):
    p = I18N_DIR / f"{lang}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    src = json.loads((I18N_DIR / "source.json").read_text(encoding="utf-8"))
    if cmd == "report":
        keys = set(src)
        for code in LANGS:
            if code == "en":
                continue
            t = load_table(code)
            bad = [k for k in keys if k in t and placeholders(t[k]) != placeholders(k)]
            miss = [k for k in keys if k not in t]
            print(f"{code}: {len(keys) - len(miss) - len(bad)}/{len(keys)} translated, {len(miss)} missing, {len(bad)} broken")
