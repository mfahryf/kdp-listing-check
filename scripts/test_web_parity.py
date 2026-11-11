"""The web checker (docs/check.js) must report exactly what check_listing.py reports.

    python scripts/test_web_parity.py      # needs Node.js
"""
import json
import pathlib
import subprocess

from check_listing import check

ROOT = pathlib.Path(__file__).resolve().parent.parent
EX = ROOT / "examples"

CASES = [json.loads((EX / n).read_text(encoding="utf-8")) for n in ("good.json", "bad.json")] + [
    {},
    {"title": "N/A"},
    {"title": "!!!!", "subtitle": "<b>x</b>", "series": "A Free Series"},
    {"title": "T", "description": "x" * 4000},
    {"title": "T", "description": "<p>" + "x" * 3995 + "</p>"},
    {"title": "a" * 100, "subtitle": "b" * 100},
    {"title": "T" * 61, "author": "<i>Me</i>", "contributors": ["Ann <b>B</b>", "C"]},
    {"title": "Free Fall", "description": "ISBN 978-1-234567-89-0. She was 5 < 6.  Two  spaces."},
    {"title": "T", "description": "Call +1 (555) 010-9999 or see my-site.co now. 4.5 stars! "
                                  "Only 3 dollars. On sale this week, March 3. ★ “Wonderful read here” — Bob"},
    {"title": "T", "description": "<ol><li>a</li></ol><ul>none</ul><h3>x</h3><div>y</div>&lt;ok&gt; &amp; &#169;"},
    {"title": "T", "description": "a, b, c, d, e, f, g, h\nTags: one"},
    {"title": "The Keeper's Daughters", "keywords": ["lighthouse keepers", "daughter", "80 GB", "80gb",
                                                    "cozy mysteries", "x" * 51, "<b>k</b>", "#1 best novel 2026"],
     "categories": ["Fiction > Mysteries", "A", "B", "C"]},
    {"title": "Café Été", "keywords": ["mystery one", "mystery two", "mystery three", "  ", "“quoted”"],
     "description": "Emoji \U0001F600 here. Please review!"},
    {"title": 123, "subtitle": None, "keywords": [1, 2], "categories": None, "description": None},
]

runner = ("const {checkListing} = require(process.argv[1]);"
          "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>"
          "process.stdout.write(JSON.stringify(JSON.parse(s).map(checkListing))))")
out = subprocess.run(["node", "-e", runner, str(ROOT / "docs" / "check.js")],
                     input=json.dumps(CASES), capture_output=True, text=True, encoding="utf-8")
assert out.returncode == 0, out.stderr
web = json.loads(out.stdout)

for i, (case, got) in enumerate(zip(CASES, web)):
    findings, counts = check(case)
    assert got["counts"] == counts, (i, got["counts"], counts)
    if got["findings"] != findings:
        py = [f'{f["level"]} {f["field"]}: {f["message"]}' for f in findings]
        js = [f'{f["level"]} {f["field"]}: {f["message"]}' for f in got["findings"]]
        raise AssertionError(f"case {i} differs\n only python: {[x for x in py if x not in js]}"
                             f"\n only web: {[x for x in js if x not in py]}")

print(f"web checker matches the Python checker on {len(CASES)} cases")
