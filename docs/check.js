// KDP listing check, browser/Node port of scripts/check_listing.py.
// Keep the two in step: scripts/test_web_parity.py fails if their findings differ.
(function (root) {
  "use strict";

  const SRC = {
    metadata: "https://kdp.amazon.com/en_US/help/topic/G201097560",
    keywords: "https://kdp.amazon.com/en_US/help/topic/G201298500",
    description: "https://kdp.amazon.com/en_US/help/topic/G201189630",
  };

  const DESCRIPTION_MAX = 4000;      // HTML tags count toward it
  const TITLE_SUBTITLE_MAX = 199;    // "fewer than 200 characters"
  const TITLE_SKIM = 60;
  const KEYWORDS_MAX = 7;
  const CATEGORIES_MAX = 3;
  const KEYWORD_BOX_CHARS = 50;      // not on the KDP help pages; widely reported

  const ALLOWED_TAGS = ["br", "p", "b", "em", "i", "u", "h4", "h5", "h6", "ol", "ul", "li"];
  const TAG = () => /<\s*\/?\s*([a-zA-Z][a-zA-Z0-9]*)\b[^<>]*>/g;

  const PLACEHOLDERS = ["unknown", "n/a", "na", "blank", "none", "null", "not applicable"];
  const GENERIC_TITLE_WORDS = ["notebook", "journal", "gift", "gifts", "book", "books"];
  const RANK = ["bestselling", "best selling", "best-selling", "bestseller", "best seller",
    "#1", "number one", "top 100"];
  const PROMO = ["free", "sale", "on sale", "discount", "bargain", "deal", "% off", "cheap"];
  const SUBJECTIVE = ["best", "greatest", "amazing", "awesome", "incredible", "must read",
    "must-read", "top rated", "award winning", "award-winning"];
  const TIME_SENSITIVE = ["new", "new release", "on sale", "available now", "coming soon",
    "this week", "today only", "limited time"];
  const GENERIC_KEYWORDS = ["book", "books", "ebook", "ebooks", "novel", "novels"];
  const AMAZON_PROGRAMS = ["kindle unlimited", "kdp select", "kindle", "kdp", "prime reading"];
  const STOPWORDS = ["the", "a", "an", "of", "and", "in", "to", "for", "on", "with", "at", "by"];

  const URL_RE = /(?:https?:\/\/|www\.)[\w./-]*\w|(?<!@)\b[\w-]+\.(?:com|net|org|io|co|uk|me|info|biz|ly)\b/i;
  const EMAIL = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/;
  const PHONE = () => /\+?\d[\d\s().-]{8,}\d/g;
  const EMOJI = /[\u{1F000}-\u{1FAFF}️]/u;
  const SYMBOL = /[☀-➿]/;
  const REVIEW_REQUEST = /\b(?:leave|write|post|drop)\b.{0,30}\breviews?\b|please review|rate this book/i;
  const TESTIMONIAL = /["“][^"”]{8,}["”]\s*[-–—]\s*\w|\b\d(?:\.\d)?\s*(?:stars?\b|\/\s*5\b)/i;
  const PRICE = /[$£€]\s?\d+(?:[.,]\d+)?|\b\d+(?:\.\d{2})?\s?(?:usd|dollars|cents)\b/i;
  const DATE = /\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b|\b20\d\d\b/i;
  const STUFFING_LABEL = /\b(?:keywords?|tags?)\s*:/i;

  const len = (s) => Array.from(s).length;             // code points, like Python
  const commas = (n) => n.toLocaleString("en-US");
  const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  function phrasesIn(phrases, text) {
    return phrases.filter((p) =>
      new RegExp("(?<![\\p{L}\\p{N}_])" + escapeRe(p) + "(?![\\p{L}\\p{N}_])", "iu").test(text));
  }

  function tokens(text) {
    const out = new Set();
    for (let w of text.toLowerCase().match(/[a-z0-9']+/g) || []) {
      w = w.replace(/^'+|'+$/g, "");
      if (w.endsWith("'s")) w = w.slice(0, -2);
      if (w.endsWith("ies") && w.length > 4) w = w.slice(0, -3) + "y";
      else if (w.endsWith("s") && !w.endsWith("ss") && w.length > 3) w = w.slice(0, -1);
      if (w.length > 2 && !STOPWORDS.includes(w)) out.add(w);
    }
    return out;
  }

  const normalise = (kw) =>
    kw.toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/s\b/g, "").replace(/ /g, "");

  const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
  function unescapeHtml(s) {
    return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (all, body) => {
      if (body[0] === "#") {
        const code = body[1].toLowerCase() === "x" ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10);
        return Number.isFinite(code) && code <= 0x10FFFF ? String.fromCodePoint(code) : all;
      }
      return Object.prototype.hasOwnProperty.call(ENTITIES, body.toLowerCase()) ? ENTITIES[body.toLowerCase()] : all;
    });
  }

  const str = (v) => (v ? String(v) : "");
  const list = (v) => (Array.isArray(v) ? v : []);

  function checkListing(book) {
    const findings = [];
    const add = (level, field, message, source) =>
      findings.push({ level, field, message, source: SRC[source] });

    const title = str(book.title).trim();
    const subtitle = str(book.subtitle).trim();
    const series = str(book.series).trim();
    const author = str(book.author).trim();
    const contributors = list(book.contributors).map(String);
    const description = str(book.description);
    const keywords = list(book.keywords).map((k) => String(k).trim()).filter(Boolean);
    const categories = list(book.categories).map((c) => String(c).trim()).filter(Boolean);
    let hit, m;

    // --- title, subtitle, series: same rules ---
    if (!title) add("FAIL", "title", "Title is missing.", "metadata");
    for (const [field, text] of [["title", title], ["subtitle", subtitle], ["series", series]]) {
      if (!text) continue;
      if (PLACEHOLDERS.includes(text.toLowerCase()))
        add("FAIL", field, `"${text}" is a placeholder, not a title.`, "metadata");
      if (!/[\p{L}\p{N}_]/u.test(text)) add("FAIL", field, "Punctuation only.", "metadata");
      if (TAG().test(text)) add("FAIL", field, "Contains HTML tags.", "metadata");
      if ((hit = phrasesIn(RANK, text)).length)
        add("FAIL", field, `Sales-rank reference: ${hit.join(", ")}.`, "metadata");
      if ((hit = phrasesIn(PROMO, text)).length)
        add("WARN", field, `Possible promotional wording: ${hit.join(", ")}. ` +
          "Fine if it is part of the real title.", "metadata");
    }
    const titleWords = `${title} ${subtitle}`.toLowerCase().match(/[a-z]+/g) || [];
    const repeated = [...new Set(titleWords.filter((w) =>
      GENERIC_TITLE_WORDS.includes(w) && titleWords.filter((x) => x === w).length > 1))].sort();
    if (repeated.length) add("WARN", "title", `Generic word repeated: ${repeated.join(", ")}.`, "metadata");
    const combined = len(title) + len(subtitle);
    if (combined > TITLE_SUBTITLE_MAX)
      add("FAIL", "title", `Title + subtitle is ${combined} characters; must be fewer than 200.`, "metadata");
    if (len(title) > TITLE_SKIM)
      add("WARN", "title", `Title is ${len(title)} characters; KDP says customers ` +
        `skim past titles longer than ${TITLE_SKIM}.`, "keywords");

    // --- author, contributors ---
    for (const [field, text] of [["author", author], ...contributors.map((c) => ["contributors", c])])
      if (TAG().test(text)) add("FAIL", field, "Contains HTML tags.", "metadata");

    // --- description ---
    if (!description.trim()) add("WARN", "description", "No description.", "description");
    if (len(description) > DESCRIPTION_MAX)
      add("FAIL", "description", `${commas(len(description))} characters; limit is ` +
        `${commas(DESCRIPTION_MAX)} and HTML tags count.`, "description");
    const badTags = [...new Set([...description.matchAll(TAG())].map((x) => x[1].toLowerCase()))]
      .filter((t) => !ALLOWED_TAGS.includes(t)).sort();
    if (badTags.length)
      add("FAIL", "description", "Unsupported HTML: " + badTags.map((t) => `<${t}>`).join(", ") +
        ". Supported: " + [...ALLOWED_TAGS].sort().join(", ") + ".", "description");
    for (const x of description.matchAll(/<\s*(ul|ol)\b[^<>]*>(.*?)<\s*\/\s*\1\s*>/gis))
      if (!x[2].toLowerCase().includes("<li"))
        add("FAIL", "description", `<${x[1].toLowerCase()}> list has no <li> items.`, "description");
    const plain = unescapeHtml(description.replace(TAG(), " "));
    if (/[<>]/.test(plain))
      add("FAIL", "description", "Stray angle bracket (<, >, <<, <>) outside a supported tag.", "description");
    if (/\S {2,}\S/.test(description))
      add("WARN", "description", "Multiple spaces between words are not displayed.", "description");
    if ((m = plain.match(URL_RE))) add("FAIL", "description", `Website address: "${m[0]}".`, "description");
    if ((m = plain.match(EMAIL))) add("FAIL", "description", `Email address: "${m[0]}".`, "description");
    for (const x of plain.matchAll(PHONE())) {
      const digits = x[0].replace(/\D/g, "");
      if (digits.length >= 10 && digits.length <= 15 && !/^97[89]/.test(digits))   // not an ISBN
        add("FAIL", "description", `Looks like a phone number: "${x[0]}".`, "description");
    }
    if (EMOJI.test(plain)) add("FAIL", "description", "Contains emoji.", "description");
    else if (SYMBOL.test(plain))
      add("WARN", "description", "Contains pictographic symbols; KDP prohibits " +
        "Unicode emojis and these may count.", "description");
    if ((m = plain.match(REVIEW_REQUEST)))
      add("FAIL", "description", `Asks for a review: "${m[0]}".`, "description");
    if ((m = plain.match(TESTIMONIAL)))
      add("WARN", "description", `Looks like a review, quote or rating: "` +
        `${Array.from(m[0]).slice(0, 60).join("")}". Not allowed if it is one.`, "description");
    if ((m = plain.match(PRICE))) add("FAIL", "description", `Price information: "${m[0]}".`, "description");
    if ((hit = phrasesIn([...RANK, ...PROMO, ...TIME_SENSITIVE.slice(1)], plain)).length)
      add("WARN", "description", "Possible promotional, price, availability or " +
        `time-sensitive wording: ${[...new Set(hit)].sort().join(", ")}.`, "description");
    if ((m = plain.match(DATE)))
      add("WARN", "description", `Date "${m[0]}": time-sensitive information ` +
        "is not allowed (a story's setting is fine).", "description");
    const stuffed = description.split(/<[^<>]*>|\n/).some((line) => {       // one block per tag/line
      const n = (line.match(/,/g) || []).length;
      return n >= 6 && line.split(/\s+/).filter(Boolean).length / (n + 1) <= 3;
    });
    if (STUFFING_LABEL.test(plain) || stuffed)
      add("WARN", "description", "Looks like a keyword or tag list; KDP prohibits " +
        "keywords and tag phrases in the description.", "description");

    // --- keywords ---
    if (keywords.length > KEYWORDS_MAX)
      add("FAIL", "keywords", `${keywords.length} keywords; KDP has ${KEYWORDS_MAX} fields.`, "keywords");
    const metadataWords = tokens([title, subtitle, series, author, ...contributors].join(" "));
    const categoryWords = tokens(categories.join(" "));
    const overlapWith = (kw, words) => [...tokens(kw)].filter((t) => words.has(t)).sort();
    const seen = new Map();
    for (const kw of keywords) {
      const field = `keyword "${kw}"`;
      let overlap;
      if (TAG().test(kw)) add("FAIL", field, "Contains HTML tags.", "metadata");
      if ((hit = phrasesIn(RANK, kw)).length)
        add("FAIL", field, `Sales-rank reference: ${hit.join(", ")}.`, "metadata");
      if ((hit = phrasesIn(PROMO, kw)).length)
        add("WARN", field, `Promotional wording: ${hit.join(", ")}.`, "metadata");
      if (/["“”]/.test(kw)) add("WARN", field, "Quotation marks limit the search match.", "keywords");
      if ((hit = phrasesIn(SUBJECTIVE, kw)).length)
        add("WARN", field, `Subjective claim: ${hit.join(", ")}.`, "keywords");
      if ((hit = phrasesIn(TIME_SENSITIVE, kw)).length)
        add("WARN", field, `Time-sensitive: ${hit.join(", ")}.`, "keywords");
      if ((m = kw.match(/\b20\d\d\b/))) add("WARN", field, `Time-sensitive: the year ${m[0]}.`, "keywords");
      if ((hit = phrasesIn(GENERIC_KEYWORDS, kw)).length)
        add("WARN", field, `Common to every item in the store: ${hit.join(", ")}.`, "keywords");
      if ((hit = phrasesIn(AMAZON_PROGRAMS, kw)).length)
        add("WARN", field, `Amazon program name: ${hit.join(", ")}.`, "keywords");
      if ((overlap = overlapWith(kw, metadataWords)).length)
        add("WARN", field, "Repeats words already in the title, series or author: " +
          `${overlap.join(", ")}.`, "keywords");
      if ((overlap = overlapWith(kw, categoryWords)).length)
        add("WARN", field, `Repeats words already in a category: ${overlap.join(", ")}.`, "keywords");
      if (len(kw) > KEYWORD_BOX_CHARS)
        add("WARN", field, `${len(kw)} characters; each keyword box is reported to ` +
          `hold ${KEYWORD_BOX_CHARS} (not stated on the KDP help page).`, "keywords");
      const key = normalise(kw);
      if (seen.has(key))
        add("WARN", field, `Variant of "${seen.get(key)}" (spacing, punctuation, case or plural).`, "keywords");
      else seen.set(key, kw);
    }
    const spread = keywords.flatMap((kw) => [...tokens(kw)]);
    const crowded = [...new Set(spread.filter((t) => spread.filter((x) => x === t).length > 2))].sort();
    if (crowded.length)
      add("WARN", "keywords", `Word used in more than two keywords: ${crowded.join(", ")}. ` +
        "Spend the fields on different words.", "keywords");
    if (keywords.length < KEYWORDS_MAX)
      add("NOTE", "keywords", `${KEYWORDS_MAX - keywords.length} of ${KEYWORDS_MAX} keyword fields unused.`, "keywords");

    // --- categories ---
    if (categories.length > CATEGORIES_MAX)
      add("FAIL", "categories", `${categories.length} categories; up to ${CATEGORIES_MAX} allowed.`, "metadata");
    if (!categories.length) add("NOTE", "categories", "No categories listed.", "metadata");

    return {
      findings,
      counts: {
        title_subtitle_chars: combined, title_subtitle_max: TITLE_SUBTITLE_MAX,
        description_chars: len(description), description_max: DESCRIPTION_MAX,
        keywords: keywords.length, keywords_max: KEYWORDS_MAX,
        categories: categories.length, categories_max: CATEGORIES_MAX,
      },
    };
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { checkListing };
  else root.checkListing = checkListing;
})(typeof self !== "undefined" ? self : this);
