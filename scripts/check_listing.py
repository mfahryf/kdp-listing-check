#!/usr/bin/env python3
"""Check an Amazon KDP book listing against KDP's published metadata rules.

    python check_listing.py book.json            # text report
    python check_listing.py book.json --json     # machine-readable
    python check_listing.py count blurb.txt --max-words 150
    python check_listing.py count email.txt --min-words 120 --max-words 200
    python check_listing.py count-all pieces.json   # many pieces, one line each

Limits are inclusive: --max-words 150 accepts exactly 150.
Exit code: 0 = no FAIL, 1 = at least one FAIL, 2 = bad input.

FAIL = mechanical certainty (a count, a tag, a URL). WARN = a word match that
needs a human or model to read it in context ("free" in "Free Fall" is fine).
No dependencies. Rules checked against the KDP help pages on 2026-11-11; the
pages are linked in every finding so you can re-check them.
"""
import argparse
import html
import json
import re
import sys

SRC = {
    "metadata": "https://kdp.amazon.com/en_US/help/topic/G201097560",
    "keywords": "https://kdp.amazon.com/en_US/help/topic/G201298500",
    "description": "https://kdp.amazon.com/en_US/help/topic/G201189630",
}

DESCRIPTION_MAX = 4000        # HTML tags count toward it
TITLE_SUBTITLE_MAX = 199      # "fewer than 200 characters"
TITLE_SKIM = 60               # KDP: customers skim past longer titles
KEYWORDS_MAX = 7
CATEGORIES_MAX = 3
# Not on the KDP help pages; widely reported as the size of each keyword box.
KEYWORD_BOX_CHARS = 50

ALLOWED_TAGS = {"br", "p", "b", "em", "i", "u", "h4", "h5", "h6", "ol", "ul", "li"}
TAG = re.compile(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9]*)\b[^<>]*>")

PLACEHOLDERS = {"unknown", "n/a", "na", "blank", "none", "null", "not applicable"}
GENERIC_TITLE_WORDS = {"notebook", "journal", "gift", "gifts", "book", "books"}
RANK = ["bestselling", "best selling", "best-selling", "bestseller", "best seller",
        "#1", "number one", "top 100"]
PROMO = ["free", "sale", "on sale", "discount", "bargain", "deal", "% off", "cheap"]
SUBJECTIVE = ["best", "greatest", "amazing", "awesome", "incredible", "must read",
              "must-read", "top rated", "award winning", "award-winning"]
TIME_SENSITIVE = ["new", "new release", "on sale", "available now", "coming soon",
                  "this week", "today only", "limited time"]
GENERIC_KEYWORDS = ["book", "books", "ebook", "ebooks", "novel", "novels"]
AMAZON_PROGRAMS = ["kindle unlimited", "kdp select", "kindle", "kdp", "prime reading"]
STOPWORDS = {"the", "a", "an", "of", "and", "in", "to", "for", "on", "with", "at", "by"}

URL = re.compile(r"(?:https?://|www\.)[\w./-]*\w"
                 r"|(?<!@)\b[\w-]+\.(?:com|net|org|io|co|uk|me|info|biz|ly)\b", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
EMOJI = re.compile("[\U0001F000-\U0001FAFF️]")
SYMBOL = re.compile("[☀-➿]")
REVIEW_REQUEST = re.compile(
    r"\b(?:leave|write|post|drop)\b.{0,30}\breviews?\b|please review|rate this book", re.I)
TESTIMONIAL = re.compile(
    r"[\"“][^\"”]{8,}[\"”]\s*[-–—]\s*\w|\b\d(?:\.\d)?\s*(?:stars?\b|/\s*5\b)", re.I)
PRICE = re.compile(r"[$£€]\s?\d+(?:[.,]\d+)?|\b\d+(?:\.\d{2})?\s?(?:usd|dollars|cents)\b", re.I)
DATE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b|\b20\d\d\b", re.I)
STUFFING_LABEL = re.compile(r"\b(?:keywords?|tags?)\s*:", re.I)


def phrases_in(phrases, text):
    """Phrases that occur in text as whole words (works for '#1' and '% off')."""
    return [p for p in phrases
            if re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", text, re.I)]


def tokens(text):
    """Significant words, crudely stemmed so "Keeper's"/"keepers" match "keeper"."""
    out = set()
    for w in re.findall(r"[a-z0-9']+", text.lower()):
        w = w.strip("'")
        if w.endswith("'s"):
            w = w[:-2]
        if w.endswith("ies") and len(w) > 4:
            w = w[:-3] + "y"
        elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            w = w[:-1]
        if len(w) > 2 and w not in STOPWORDS:
            out.add(w)
    return out


def normalise(keyword):
    """Collapse spacing, punctuation, case and plural variants ("80 GB" == "80gb")."""
    return re.sub(r"s\b", "", re.sub(r"[^a-z0-9 ]", "", keyword.lower())).replace(" ", "")


def check(book):
    """Return (findings, counts). A finding is {level, field, message, source}."""
    findings = []

    def add(level, field, message, source):
        findings.append({"level": level, "field": field, "message": message,
                         "source": SRC[source]})

    title = str(book.get("title") or "").strip()
    subtitle = str(book.get("subtitle") or "").strip()
    series = str(book.get("series") or "").strip()
    author = str(book.get("author") or "").strip()
    contributors = [str(c) for c in book.get("contributors") or []]
    description = str(book.get("description") or "")
    keywords = [str(k).strip() for k in book.get("keywords") or [] if str(k).strip()]
    categories = [str(c).strip() for c in book.get("categories") or [] if str(c).strip()]

    # --- title, subtitle, series: same rules ---
    if not title:
        add("FAIL", "title", "Title is missing.", "metadata")
    for field, text in (("title", title), ("subtitle", subtitle), ("series", series)):
        if not text:
            continue
        if text.lower() in PLACEHOLDERS:
            add("FAIL", field, f'"{text}" is a placeholder, not a title.', "metadata")
        if not re.search(r"\w", text):
            add("FAIL", field, "Punctuation only.", "metadata")
        if TAG.search(text):
            add("FAIL", field, "Contains HTML tags.", "metadata")
        if hit := phrases_in(RANK, text):
            add("FAIL", field, f"Sales-rank reference: {', '.join(hit)}.", "metadata")
        if hit := phrases_in(PROMO, text):
            add("WARN", field, f"Possible promotional wording: {', '.join(hit)}. "
                "Fine if it is part of the real title.", "metadata")
    title_words = re.findall(r"[a-z]+", f"{title} {subtitle}".lower())
    repeated = sorted({w for w in title_words
                       if w in GENERIC_TITLE_WORDS and title_words.count(w) > 1})
    if repeated:
        add("WARN", "title", f"Generic word repeated: {', '.join(repeated)}.", "metadata")
    combined = len(title) + len(subtitle)
    if combined > TITLE_SUBTITLE_MAX:
        add("FAIL", "title", f"Title + subtitle is {combined} characters; "
            f"must be fewer than 200.", "metadata")
    if len(title) > TITLE_SKIM:
        add("WARN", "title", f"Title is {len(title)} characters; KDP says customers "
            f"skim past titles longer than {TITLE_SKIM}.", "keywords")

    # --- author, contributors ---
    for field, text in [("author", author)] + [("contributors", c) for c in contributors]:
        if TAG.search(text):
            add("FAIL", field, "Contains HTML tags.", "metadata")

    # --- description ---
    if not description.strip():
        add("WARN", "description", "No description.", "description")
    if len(description) > DESCRIPTION_MAX:
        add("FAIL", "description", f"{len(description):,} characters; limit is "
            f"{DESCRIPTION_MAX:,} and HTML tags count.", "description")
    bad_tags = sorted({m.group(1).lower() for m in TAG.finditer(description)} - ALLOWED_TAGS)
    if bad_tags:
        add("FAIL", "description", "Unsupported HTML: "
            + ", ".join(f"<{t}>" for t in bad_tags) + ". Supported: "
            + ", ".join(sorted(ALLOWED_TAGS)) + ".", "description")
    for m in re.finditer(r"<\s*(ul|ol)\b[^<>]*>(.*?)<\s*/\s*\1\s*>", description, re.I | re.S):
        if "<li" not in m.group(2).lower():
            add("FAIL", "description", f"<{m.group(1).lower()}> list has no <li> items.",
                "description")
    plain = html.unescape(TAG.sub(" ", description))
    if re.search(r"[<>]", plain):
        add("FAIL", "description", "Stray angle bracket (<, >, <<, <>) outside a "
            "supported tag.", "description")
    if re.search(r"\S {2,}\S", description):
        add("WARN", "description", "Multiple spaces between words are not displayed.",
            "description")
    if m := URL.search(plain):
        add("FAIL", "description", f'Website address: "{m.group(0)}".', "description")
    if m := EMAIL.search(plain):
        add("FAIL", "description", f'Email address: "{m.group(0)}".', "description")
    for m in PHONE.finditer(plain):
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 15 and not digits.startswith(("978", "979")):  # not an ISBN
            add("FAIL", "description", f'Looks like a phone number: "{m.group(0)}".',
                "description")
    if EMOJI.search(plain):
        add("FAIL", "description", "Contains emoji.", "description")
    elif SYMBOL.search(plain):
        add("WARN", "description", "Contains pictographic symbols; KDP prohibits "
            "Unicode emojis and these may count.", "description")
    if m := REVIEW_REQUEST.search(plain):
        add("FAIL", "description", f'Asks for a review: "{m.group(0)}".', "description")
    if m := TESTIMONIAL.search(plain):
        add("WARN", "description", f'Looks like a review, quote or rating: '
            f'"{m.group(0)[:60]}". Not allowed if it is one.', "description")
    if m := PRICE.search(plain):
        add("FAIL", "description", f'Price information: "{m.group(0)}".', "description")
    if hit := phrases_in(RANK + PROMO + TIME_SENSITIVE[1:], plain):
        add("WARN", "description", "Possible promotional, price, availability or "
            f"time-sensitive wording: {', '.join(sorted(set(hit)))}.", "description")
    if m := DATE.search(plain):
        add("WARN", "description", f'Date "{m.group(0)}": time-sensitive information '
            "is not allowed (a story's setting is fine).", "description")
    if STUFFING_LABEL.search(plain) or any(
            line.count(",") >= 6 and len(line.split()) / (line.count(",") + 1) <= 3
            for line in re.split(r"<[^<>]*>|\n", description)):  # one block per tag/line
        add("WARN", "description", "Looks like a keyword or tag list; KDP prohibits "
            "keywords and tag phrases in the description.", "description")

    # --- keywords ---
    if len(keywords) > KEYWORDS_MAX:
        add("FAIL", "keywords", f"{len(keywords)} keywords; KDP has {KEYWORDS_MAX} "
            "fields.", "keywords")
    metadata_words = tokens(" ".join([title, subtitle, series, author] + contributors))
    category_words = tokens(" ".join(categories))
    seen = {}
    for kw in keywords:
        field = f'keyword "{kw}"'
        if TAG.search(kw):
            add("FAIL", field, "Contains HTML tags.", "metadata")
        if hit := phrases_in(RANK, kw):
            add("FAIL", field, f"Sales-rank reference: {', '.join(hit)}.", "metadata")
        if hit := phrases_in(PROMO, kw):
            add("WARN", field, f"Promotional wording: {', '.join(hit)}.", "metadata")
        if re.search(r"[\"“”]", kw):
            add("WARN", field, "Quotation marks limit the search match.", "keywords")
        if hit := phrases_in(SUBJECTIVE, kw):
            add("WARN", field, f"Subjective claim: {', '.join(hit)}.", "keywords")
        if hit := phrases_in(TIME_SENSITIVE, kw):
            add("WARN", field, f"Time-sensitive: {', '.join(hit)}.", "keywords")
        if m := re.search(r"\b20\d\d\b", kw):
            add("WARN", field, f"Time-sensitive: the year {m.group(0)}.", "keywords")
        if hit := phrases_in(GENERIC_KEYWORDS, kw):
            add("WARN", field, f'Common to every item in the store: {", ".join(hit)}.',
                "keywords")
        if hit := phrases_in(AMAZON_PROGRAMS, kw):
            add("WARN", field, f"Amazon program name: {', '.join(hit)}.", "keywords")
        if overlap := sorted(tokens(kw) & metadata_words):
            add("WARN", field, "Repeats words already in the title, series or author: "
                f"{', '.join(overlap)}.", "keywords")
        if overlap := sorted(tokens(kw) & category_words):
            add("WARN", field, f"Repeats words already in a category: "
                f"{', '.join(overlap)}.", "keywords")
        if len(kw) > KEYWORD_BOX_CHARS:
            add("WARN", field, f"{len(kw)} characters; each keyword box is reported to "
                f"hold {KEYWORD_BOX_CHARS} (not stated on the KDP help page).", "keywords")
        key = normalise(kw)
        if key in seen:
            add("WARN", field, f'Variant of "{seen[key]}" (spacing, punctuation, case '
                "or plural).", "keywords")
        seen.setdefault(key, kw)
    spread = [t for kw in keywords for t in tokens(kw)]
    if crowded := sorted({t for t in spread if spread.count(t) > 2}):
        add("WARN", "keywords", "Word used in more than two keywords: "
            f"{', '.join(crowded)}. Spend the fields on different words.", "keywords")
    if len(keywords) < KEYWORDS_MAX:
        add("NOTE", "keywords", f"{KEYWORDS_MAX - len(keywords)} of {KEYWORDS_MAX} "
            "keyword fields unused.", "keywords")

    # --- categories ---
    if len(categories) > CATEGORIES_MAX:
        add("FAIL", "categories", f"{len(categories)} categories; up to "
            f"{CATEGORIES_MAX} allowed.", "metadata")
    if not categories:
        add("NOTE", "categories", "No categories listed.", "metadata")

    counts = {
        "title_subtitle_chars": combined, "title_subtitle_max": TITLE_SUBTITLE_MAX,
        "description_chars": len(description), "description_max": DESCRIPTION_MAX,
        "keywords": len(keywords), "keywords_max": KEYWORDS_MAX,
        "categories": len(categories), "categories_max": CATEGORIES_MAX,
    }
    return findings, counts


def report(book, findings, counts):
    order = {"FAIL": 0, "WARN": 1, "NOTE": 2}
    lines = [f'KDP listing check: {book.get("title") or "(no title)"}', ""]
    for f in sorted(findings, key=lambda f: order[f["level"]]):
        lines.append(f'{f["level"]}  {f["field"]}: {f["message"]}')
        lines.append(f'      {f["source"]}')
    c = counts
    lines += ["" if findings else "No problems found.",
              f'Counts: title+subtitle {c["title_subtitle_chars"]}/{c["title_subtitle_max"]}'
              f' | description {c["description_chars"]:,}/{c["description_max"]:,}'
              f' | keywords {c["keywords"]}/{c["keywords_max"]}'
              f' | categories {c["categories"]}/{c["categories_max"]}',
              "Result: " + ", ".join(
                  f'{sum(f["level"] == lvl for f in findings)} {lvl}' for lvl in order),
              "This checks KDP's published rules. It has no Amazon search data and "
              "cannot tell whether a listing will sell."]
    return "\n".join(lines)


def read(path):
    if path == "-":
        return sys.stdin.buffer.read().decode("utf-8-sig")
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def count_main(argv):
    p = argparse.ArgumentParser(prog="check_listing.py count",
                                description="Count words and characters in a text file.")
    p.add_argument("file", help="text file, or - for stdin")
    p.add_argument("--max-words", type=int, help="at most this many words")
    p.add_argument("--min-words", type=int, help="at least this many words")
    p.add_argument("--max-chars", type=int, help="at most this many characters")
    a = p.parse_args(argv)
    ok, line = measure(read(a.file), a.min_words, a.max_words, a.max_chars)
    print(line)
    return 0 if ok else 1


def measure(text, min_words=None, max_words=None, max_chars=None):
    """Return (within limits, report line). No limits given -> a plain COUNT."""
    text = text.strip()
    words, chars = len(text.split()), len(text)
    over = (max_words is not None and words > max_words) or \
           (max_chars is not None and chars > max_chars)
    under = min_words is not None and words < min_words
    limits = "".join(f" ({label} {n} {unit})" for label, n, unit in
                     (("min", min_words, "words"), ("max", max_words, "words"),
                      ("max", max_chars, "characters")) if n is not None)
    status = "OVER" if over else "UNDER" if under else "OK" if limits else "COUNT"
    return not (over or under), f"{status}  {words} words, {chars} characters{limits}"


def count_all_main(argv):
    """count-all pieces.json: count many pieces in one run.

    The file is a list of {"name", "text"} objects, each with optional
    "min_words", "max_words", "max_chars". Prints one line per piece.
    """
    try:
        pieces = json.loads(read(argv[0]))
        if not isinstance(pieces, list):
            raise ValueError("top level is not a list")
        lines =[(p["name"], measure(p["text"], p.get("min_words"), p.get("max_words"),
                                     p.get("max_chars"))) for p in pieces]
    except (IndexError, OSError, ValueError, KeyError, TypeError) as e:
        print(f"count-all needs a JSON list of {{name, text}} objects: {e!r}",
              file=sys.stderr)
        return 2
    for name, (_, line) in lines:
        print(f"{name}: {line}")
    return 0 if all(ok for _, (ok, _) in lines) else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["count"]:
        return count_main(argv[1:])
    if argv[:1] == ["count-all"]:
        return count_all_main(argv[1:])
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("file", help="book JSON file, or - for stdin")
    p.add_argument("--json", action="store_true", help="print findings as JSON")
    a = p.parse_args(argv)
    try:
        book = json.loads(read(a.file))
        if not isinstance(book, dict):
            raise ValueError("top level must be an object")
    except (OSError, ValueError) as e:
        print(f"Cannot read listing: {e}", file=sys.stderr)
        return 2
    findings, counts = check(book)
    if a.json:
        print(json.dumps({"findings": findings, "counts": counts}, indent=2,
                         ensure_ascii=False))
    else:
        print(report(book, findings, counts))
    return 1 if any(f["level"] == "FAIL" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
