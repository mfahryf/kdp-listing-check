"""Self-check: python scripts/test_check_listing.py"""
import json
import pathlib

from check_listing import check, count_main, main

EXAMPLES = pathlib.Path(__file__).resolve().parent.parent / "examples"


def load(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def messages(book, level):
    return [f'{f["field"]}: {f["message"]}' for f in check(book)[0] if f["level"] == level]


def has(found, *needles):
    return all(any(n in line for line in found) for n in needles)


# A clean listing produces nothing at all.
assert check(load("good.json"))[0] == [], check(load("good.json"))[0]

# The broken listing trips every mechanical rule.
fails = messages(load("bad.json"), "FAIL")
assert has(fails,
           "Title + subtitle is", "Sales-rank reference: bestselling",
           "Unsupported HTML: <h2>", "list has no <li>", "Website address",
           'Website address: "www.maraellison.com"', 'Email address: "mara@maraellison.com"',
           'Price information: "$0.99"', "Contains emoji", "Asks for a review", "Price information",
           "8 keywords", "4 categories"), fails
warns = messages(load("bad.json"), "WARN")
assert has(warns,
           "Generic word repeated: book", "promotional wording: free",
           "Looks like a review", "Multiple spaces", "keyword or tag list",
           "Quotation marks", "Subjective claim: best", "Amazon program name",
           "Repeats words already in the title", "Repeats words already in a category",
           'Variant of "Victorian smugglers"', "Time-sensitive: new",
           "Time-sensitive: the year 2026", "more than two keywords: mystery"), warns

# Stemming: possessives and plurals still count as repeats.
stem = {"title": "The Keeper's Daughters", "keywords": ["lighthouse keepers", "daughter"],
        "categories": ["Fiction > Mysteries"]}
assert has(messages(stem, "WARN"), "author: keeper", "author: daughter")
assert has(messages({"title": "T", "keywords": ["cozy mystery"],
                     "categories": ["Fiction > Mysteries"]}, "WARN"), "category: mystery")
assert has(messages({"title": "T", "keywords": ["historical novel"]}, "WARN"), "store: novel")

# Boundaries: exactly at the limit passes, one over fails.
assert not messages({"title": "T", "description": "x" * 4000}, "FAIL")
assert has(messages({"title": "T", "description": "x" * 4001}, "FAIL"), "4,001 characters")
assert not messages({"title": "a" * 100, "subtitle": "b" * 99}, "FAIL")
assert has(messages({"title": "a" * 100, "subtitle": "b" * 100}, "FAIL"), "200 characters")
assert not messages({"title": "T", "keywords": list("abcdefg")}, "FAIL")

# HTML counts toward the limit, and every supported tag is accepted.
ok_html = "<p><b>a</b> <i>b</i> <em>c</em> <u>d</u><br></p><h4>e</h4><h5>f</h5><h6>g</h6>" \
          "<ol><li>h</li></ol><ul><li>i</li></ul>"
assert not messages({"title": "T", "description": ok_html}, "FAIL")
assert has(messages({"title": "T", "description": "<p>" + "x" * 3995 + "</p>"}, "FAIL"),
           "4,002 characters")

# Things that must not be mistaken for violations.
quiet = {"title": "Free Fall", "description": "ISBN 978-1-234567-89-0. She was 5 < 6."}
assert not has(messages(quiet, "FAIL"), "phone")
assert has(messages(quiet, "FAIL"), "Stray angle bracket")
assert has(messages(quiet, "WARN"), "promotional wording: free")      # WARN, not FAIL
assert not messages({"title": "T", "description": "Set in 1887, by the sea."}, "WARN")

# Missing and placeholder titles.
assert has(messages({}, "FAIL"), "Title is missing")
assert has(messages({"title": "N/A"}, "FAIL"), "placeholder")
assert has(messages({"title": "!!!!"}, "FAIL"), "Punctuation only")

# Exit codes and the word counter.
assert main([str(EXAMPLES / "good.json")]) == 0
assert main([str(EXAMPLES / "bad.json"), "--json"]) == 1
assert main([str(EXAMPLES / "missing.json")]) == 2
blurb = EXAMPLES / "_count.tmp"
blurb.write_text("one two three", encoding="utf-8")
try:
    assert count_main([str(blurb), "--max-words", "3"]) == 0
    assert count_main([str(blurb), "--max-words", "2"]) == 1
    assert count_main([str(blurb), "--max-chars", "12"]) == 1
    assert count_main([str(blurb), "--max-chars", "13"]) == 0       # inclusive
    assert count_main([str(blurb), "--min-words", "4", "--max-words", "9"]) == 1
    assert count_main([str(blurb), "--min-words", "3", "--max-words", "9"]) == 0
    assert count_main([str(blurb)]) == 0                             # no limit: plain count
    blurb.write_text(json.dumps([
        {"name": "tagline", "text": "one two three", "max_chars": 13},
        {"name": "bio", "text": "one two three", "min_words": 2, "max_words": 3},
        {"name": "page", "text": "no limit here"}]), encoding="utf-8")
    assert main(["count-all", str(blurb)]) == 0
    blurb.write_text(json.dumps([{"name": "long", "text": "a b c", "max_words": 2}]),
                     encoding="utf-8")
    assert main(["count-all", str(blurb)]) == 1
    blurb.write_text("{}", encoding="utf-8")
    assert main(["count-all", str(blurb)]) == 2
finally:
    blurb.unlink()

print("\nall checks passed")
