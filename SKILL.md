---
name: kdp-listing-check
description: Check an Amazon KDP book listing (title, subtitle, description, seven keywords, categories) against KDP's published metadata rules, explain what fails, and fix it. Use when an author wants to check, audit, clean up or prepare a KDP, Kindle or Amazon book listing, book description or keywords before publishing or after a rejection.
---

# KDP listing check

You check a book's Amazon KDP listing against the rules KDP publishes, then fix
what fails without changing what the book is. Counting is done by a script,
because language models miscount characters.

## 1. Collect the listing

Ask for whatever is missing, then write it to `book.json`:

```json
{
  "title": "", "subtitle": "", "series": "", "author": "",
  "contributors": [],
  "description": "paste exactly as entered in KDP, HTML included",
  "keywords": ["up to seven"],
  "categories": ["up to three"]
}
```

Keep the author's text exactly as given, including HTML and spacing. Do not
tidy it before checking: the point is to check what they would submit.

## 2. Run the checker

```
python scripts/check_listing.py book.json
```

If you cannot run code, apply `scripts/check_listing.py`'s rules by reading it,
and say plainly that character counts are approximate and must be confirmed in
KDP's own editor, which shows a live count.

## 3. Read the findings

- **FAIL** is mechanical: a count over a limit, an unsupported tag, a URL. Fix all of them.
- **WARN** is a word match. Read it in context and decide. "Free" in the title
  *Free Fall* is fine; "free" as an offer is not. "1887" as a setting is fine; a
  tour date is not. Say which warnings you dismissed and why.
- **NOTE** is information, such as unused keyword fields.

Two rules the script cannot check; check them yourself:

- Keywords, title and subtitle must not name other authors, other books, or
  brands the author does not own.
- Keywords and categories must describe what the book is actually about.

## 4. Fix and re-run

Fix the listing, keeping the author's voice and every claim true to the book:

- Description over 4,000 characters: cut, do not summarise the plot away. Remember HTML tags count.
- Unsupported tags: `<h1>`–`<h3>` become `<h4>`; anything else becomes plain text or `<b>`.
- Reviews, prices, links, dates, review requests, emoji: remove. Do not replace
  them with a reworded version of the same thing.
- Keywords that repeat the title or a category: replace with something the
  listing does not already say. KDP suggests setting, character types,
  character roles, plot themes and story tone.

Save the fixed version as `book.fixed.json` and run the checker on it. Repeat
until there is no FAIL and every remaining WARN has a stated reason.

## 5. Report

Give the author, in this order:

1. What failed and why, each with the KDP page it comes from (the script prints the link).
2. The fixed fields, ready to paste into KDP, with their final counts.
3. Warnings you kept and why they are acceptable.
4. What you did not check.

Always say what this cannot do: it has no Amazon search data, so it cannot say
which keywords shoppers type or whether the book will rank. To test a keyword,
the author types it into Amazon's search bar and looks at the suggestions and
results.

## Blurb at a set length

When a promotion site asks for a shorter description, write it, then count it:

```
python scripts/check_listing.py count blurb.txt --max-words 150
```

Rewrite until it reports `OK`. Never report a word count you did not get from the script.
