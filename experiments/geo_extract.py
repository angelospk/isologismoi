"""Experimental geometry-first extractor. Not production; does not change extractor/.

The existing extractor refuses any Όμιλος/Εταιρεία table and needs every row
to carry exactly one amount per year column. Here each amount is assigned to
the nearest column header by x position, and a column is only used when its
scope (company) and year are both known. Everything still passes through the
existing labels, money parser and accounting identities.

Input is a list of pages: dict(width, height, words=[dict(text,x0,x1,top,bottom)]).
Words may come from a PDF text layer or from OCR.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extractor"))
from wayfinder_extract import labels  # noqa: E402
from wayfinder_extract.extract import (_derive_ebitda, _document_facts, _merge_tight,  # noqa: E402
                                      _pick_fiscal_year, _why_no_table)
from wayfinder_extract.text import is_money, normalize, parse_money  # noqa: E402
from wayfinder_extract.validate import check_identities  # noqa: E402

_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_DATEY = re.compile(r"^[\d./\-]*(?:19|20)\d{2}[\d./\-]*$")
_NOTE_REF = re.compile(r"^\d+(?:\.\d+)+$")
_GROUP = re.compile(r"^ΟΜΙΛΟΣ$|^ΕΝΟΠΟΙΗΜΕΝ")
_COMPANY = re.compile(r"^ΕΤΑΙΡΕΙΑ$|^ΕΤΑΙΡΙΑ$|^ΜΗΤΡΙΚΗ$")
_THOUSANDS = re.compile(r"ΣΕ ΧΙΛΙΑΔΕΣ|ΧΙΛΙΑΔΕΣ ΕΥΡΩ|ΧΙΛ ΕΥΡΩ|ΠΟΣΑ ΣΕ ΧΙΛ|ΕΥΡΩ 000|€ ?000")
_MILLIONS = re.compile(r"ΣΕ ΕΚΑΤΟΜΜΥΡΙΑ|ΕΚΑΤ ΕΥΡΩ|ΕΚΑΤΟΜΜΥΡΙΑ ΕΥΡΩ|ΠΟΣΑ ΣΕ ΕΚΑΤ")
_GROUP_TITLE = re.compile(r"ΕΝΟΠΟΙΗΜΕΝ|\bΟΜΙΛΟ[ΣΥ]\b|\bΟΜΙΛΩΝ\b")
_COMPANY_TITLE = re.compile(r"ΕΤΑΙΡΙΚ|ΕΤΑΙΡΕΙΑΣ|ΕΤΑΙΡΙΑΣ|ΑΤΟΜΙΚ")
MIN_CENTS_RATIO = 0.8
MIN_CENTS_TOKENS = 5
MIN_OCR_SCORE = 0.95

# Latin capitals that print exactly like Greek ones. 'Kαθαρή' with a Latin K
# defeats a label regex written in Greek.
_HOMOGLYPHS = str.maketrans("ABEZHIKMNOPTYXaiknopvx", "ΑΒΕΖΗΙΚΜΝΟΡΤΥΧαικηορνχ")
_GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")

# Common IFRS captions the ELP-oriented label table does not list.
_EXTRA_LABELS = [
    ("pre_tax_profit", re.compile(r"^ΚΕΡΔΗ ΖΗΜΙΕΣ ΠΡΟ ΦΟΡΩΝ ΕΙΣΟΔΗΜΑΤΟΣ$|^ΚΕΡΔΗ ΠΡΟ ΦΟΡΩΝ ΕΙΣΟΔΗΜΑΤΟΣ$")),
    ("net_profit", re.compile(r"^ΚΑΘΑΡΑ ΚΕΡΔΗ( ΖΗΜΙΕΣ)?( ΧΡΗΣΗΣ)?$|^ΚΑΘΑΡΑ ΚΕΡΔΗ ΖΗΜΙΕΣ ΜΕΤΑ ΑΠΟ ΦΟΡΟΥΣ$")),
]

ROW_TOLERANCE = 3.0
MAX_LABEL_LINES = 3
MAX_HEADER_TOKENS = 10


def _fix_homoglyphs(text: str) -> str:
    return text.translate(_HOMOGLYPHS) if _GREEK.search(text) else text


# "Σύνολο Ιδίων Κεφαλαίων (α)", "Σύνολο υποχρεώσεων (β)": a statement's own
# cross-reference letters, not part of the caption.
_TRAILING_REF = re.compile(r"\s*\(\s*[α-ωa-z](?:\s*[+\-]\s*[α-ωa-z])*\s*\)\s*$", re.IGNORECASE)
_OCR_JUNK = re.compile(r"[_|]+$")
_DASH = re.compile(r"^[-–—]$")  # an empty cell, printed
_CENTS = re.compile(r",\d{2}\)?-?$")


def match_label(label_norm: str):
    key = labels.match(label_norm)
    if key:
        return key
    for k, pattern in _EXTRA_LABELS:
        if pattern.match(label_norm):
            return k
    return None


def _rows(words, tolerance=ROW_TOLERANCE):
    """Group words into printed lines, left to right.

    Two words share a line when their vertical extents overlap by at least half
    of the shorter one, or their centres are within `tolerance`. A bold amount
    sits a point lower than its label; a fixed centre tolerance splits them.
    """
    rows = []
    for w in sorted(words, key=lambda w: (w["top"] + w["bottom"]) / 2):
        mid = (w["top"] + w["bottom"]) / 2
        if rows:
            r = rows[-1]
            overlap = min(r["bottom"], w["bottom"]) - max(r["top"], w["top"])
            shorter = min(r["bottom"] - r["top"], w["bottom"] - w["top"])
            if abs(mid - r["mid"]) <= tolerance or (shorter > 0 and overlap >= 0.5 * shorter):
                r["words"].append(w)  # the band stays that of the first word: no chaining
                continue
        rows.append(dict(mid=mid, top=w["top"], bottom=w["bottom"], words=[w]))
    return [_merge_tight(sorted(r["words"], key=lambda w: w["x0"])) for r in rows]


def _centre(w):
    return (w["x0"] + w["x1"]) / 2


REJECTED = "rejected"


def _yearish(text):
    """A year or date, or a token OCR may have garbled from one ('202Z', '2O23')."""
    return bool(_DATEY.match(text)) or (len(text) == 4 and sum(ch.isdigit() for ch in text) >= 3)


def _header_shaped(words):
    """A short line whose every digit-bearing token looks like a year or date.

    Used only for lines with a low-confidence OCR token: the misread token may
    no longer be a valid year, but the line still replaces the table's header.
    """
    digits = [w["text"] for w in words if any(ch.isdigit() for ch in w["text"])]
    return bool(digits) and all(_yearish(t) for t in digits)


def _header_columns(words, check_scores=True):
    """Year columns of a header line, None, or REJECTED.

    [(year, x_centre)] left to right. REJECTED is a line that has the shape of
    a header but a low-confidence OCR token: a misread year could pick the
    wrong column, and the table it introduces must not be read at all.
    """
    if len(words) > MAX_HEADER_TOKENS:
        return None
    if check_scores and any(w.get("score", 1.0) < MIN_OCR_SCORE for w in words):
        return REJECTED if _header_shaped(words) else None
    cols = []
    for w in words:
        t = w["text"]
        if any(ch.isdigit() for ch in t):
            if not _DATEY.match(t):
                return None
            years = _YEAR.findall(t)
            if len(years) != 1:
                return None
            cols.append((int(years[0]), _centre(w)))
    if len(cols) < 2:
        return None
    years = {y for y, _ in cols}
    if len(years) != 2 or abs(max(years) - min(years)) != 1:
        return None
    return cols


def _scopes_above(rows, index, cols, page_scope):
    """Assign Όμιλος/Εταιρεία to each year column from the nearest label line above."""
    for back in range(1, 4):
        if index - back < 0:
            break
        marks = []
        for w in rows[index - back]:
            n = normalize(w["text"])
            if w.get("score", 1.0) < MIN_OCR_SCORE and (_GROUP.match(n) or _COMPANY.match(n)):
                return None  # a scope label we cannot trust: do not read the table
            if _GROUP.match(n):
                marks.append(("group", _centre(w)))
            elif _COMPANY.match(n):
                marks.append(("company", _centre(w)))
        if marks:
            out = []
            for year, x in cols:
                scope = min(marks, key=lambda m: abs(m[1] - x))[0]
                out.append((year, x, scope))
            # Each scope must cover exactly the two years once.
            for s in {m[0] for m in marks}:
                ys = sorted(y for y, _, sc in out if sc == s)
                if len(ys) != 2 or len(set(ys)) != 2:
                    return None
            return out
    if len(cols) == 2:
        return [(y, x, page_scope) for y, x in cols]
    return None  # four columns and no scope labels: do not guess


def _page_scope(page_text_norm):
    """Scope of an unlabelled two-column table, from the page's own words.

    Any mention of a group ('Ομίλου', 'Ενοποιημένες') makes the page unknown:
    it could be the group's statement, so its columns are never read as the
    company's. Only a page with no group mention at all counts as single.
    """
    if _GROUP_TITLE.search(page_text_norm):
        return "unknown"
    return "single"


ASSIGN_TOLERANCE = 0.35   # of the gap between column centres
ASSIGN_MARGIN = 0.3       # the nearest column must win by this much of the gap


def _assign(cells, cols, offset=0.0):
    """Map each cell to a column, or None if any cell is ambiguous.

    A row with one cell per column is read in order, as the core extractor
    does, but only if every cell is also nearest to its own column. Otherwise
    each cell must sit clearly at one column: within ASSIGN_TOLERANCE of the
    gap, after removing the table's measured offset (amounts are usually
    right-aligned, year headers are not).
    """
    xs = sorted(x for _, x, _ in cols)
    gap = min(b - a for a, b in zip(xs, xs[1:])) if len(xs) > 1 else 200
    order_of = sorted(range(len(cols)), key=lambda i: cols[i][1])
    if len(cells) == len(cols):
        taken = {}
        for rank, w in enumerate(sorted(cells, key=_centre)):
            c = _centre(w) - offset
            nearest = min(range(len(cols)), key=lambda i: abs(cols[i][1] - c))
            if nearest != order_of[rank]:
                return None
            taken[nearest] = w
        return taken
    taken = {}
    for w in cells:
        c = _centre(w) - offset
        order = sorted(range(len(cols)), key=lambda i: abs(cols[i][1] - c))
        best = order[0]
        d_best = abs(cols[best][1] - c)
        if d_best > gap * ASSIGN_TOLERANCE:
            if d_best < gap * (1 - ASSIGN_TOLERANCE) and c > xs[0] - gap * ASSIGN_TOLERANCE:
                return None  # between two columns: could belong to either
            continue  # a note number left of the columns, or a stray token
        if len(order) > 1 and abs(cols[order[1]][1] - c) - d_best < gap * ASSIGN_MARGIN:
            return None
        if best in taken:
            return None
        taken[best] = w
    return taken


def _offset(offsets):
    if not offsets:
        return 0.0
    ordered = sorted(offsets)
    return ordered[len(ordered) // 2]


def _page_unit(rows, page_norm, doc_unit_mentioned):
    """1, 1000 or None (unknown) for the amounts printed on this page."""
    if _MILLIONS.search(page_norm):
        return None
    if _THOUSANDS.search(page_norm):
        return 1000
    if not doc_unit_mentioned:
        return 1  # the core extractor's default: statutory filings are in euro
    # Thousands are mentioned elsewhere. Only a page printed in cents throughout
    # is evidence of units; a thousands statement does not carry cents.
    money = [w for r in rows if not _header_columns(r) for w in r if is_money(w["text"])]
    if len(money) >= MIN_CENTS_TOKENS and \
            sum(bool(_CENTS.search(w["text"])) for w in money) >= MIN_CENTS_RATIO * len(money):
        return 1
    return None


def extract_pages(pages, page_texts=None):
    notes = []
    page_texts = page_texts or [" ".join(w["text"] for w in p["words"]) for p in pages]
    full_text = "\n".join(page_texts)
    facts = _document_facts(full_text)
    doc_unit_mentioned = bool(_THOUSANDS.search(normalize(full_text)) or _MILLIONS.search(normalize(full_text)))

    prepared = []
    headers = []
    for p in pages:
        words = [dict(w, text=_OCR_JUNK.sub("", _fix_homoglyphs(w["text"]))) for w in p["words"]]
        words = [w for w in words if w["text"]]
        rows = _rows(words, p.get("row_tolerance", ROW_TOLERANCE))
        prepared.append(rows)
        for r in rows:
            cols = _header_columns(r)
            if cols and cols != REJECTED:
                ys = sorted({y for y, _ in cols})
                headers.append(ys)
    fiscal_year = _pick_fiscal_year(headers, facts["period_end_years"], notes)
    if fiscal_year is None:
        text_pages = sum(1 for t in page_texts if len(t.strip()) >= 300)
        return dict(status="unparseable", reason=_why_no_table(headers, text_pages, len(pages), full_text),
                    figures={}, fiscal_year=None, currency="EUR", unit_multiplier=1,
                    ar_gemi=facts["ar_gemi"], notes=notes)

    found = {}
    multipliers = set()
    # A statement may continue onto the next page without repeating its header.
    # The header is carried one page only, only if it named no scope, and only
    # onto a page that does not mention a group. Its unit travels with it.
    carried = None
    for page_index, (p, rows) in enumerate(zip(pages, prepared)):
        page_norm = normalize(page_texts[page_index])
        scope_hint = _page_scope(page_norm)
        unit = _page_unit(rows, page_norm, doc_unit_mentioned)
        cols = None
        from_carry = False
        header_on_page = False
        offsets = []
        declares_unit = bool(_THOUSANDS.search(page_norm) or _MILLIONS.search(page_norm))
        if carried and carried["page"] == page_index - 1:
            labelled = any(s != "single" for _, _, s in carried["cols"])
            if labelled or scope_hint == "single":
                cols, offsets = carried["cols"], carried["offsets"]
                from_carry = labelled
                # The page's own unit declaration wins (millions stays refused);
                # a carried unit fills in only for a page that declares none.
                if not declares_unit:
                    unit = carried["unit"]
        carried = None
        label_buffer = []  # (label, top, bottom) of label-only lines just above
        for i, words in enumerate(rows):
            header = _header_columns(words)
            if header == REJECTED:
                cols, from_carry, offsets, label_buffer = None, False, [], []
                header_on_page = False
                notes.append(f"low-confidence header on page {page_index + 1}; table not read")
                continue
            if header:
                header_on_page = True
                cols = _scopes_above(rows, i, header, scope_hint)
                unit = _page_unit(rows, page_norm, doc_unit_mentioned)
                from_carry = False
                offsets = []
                label_buffer = []
                continue
            # Money first: '8.411' is an amount, though it also looks like note '6.1.1'.
            amounts = [w for w in words if is_money(w["text"])]
            dashes = [w for w in words if _DASH.match(w["text"])]
            label_words = [w["text"] for w in words
                           if w not in amounts and w not in dashes and not _NOTE_REF.match(w["text"])]
            label = " ".join(label_words)
            top = min(w["top"] for w in words)
            bottom = max(w["bottom"] for w in words)
            height = max(bottom - top, 1.0)
            if not amounts:
                if dashes:
                    label_buffer = []  # a complete row whose cells are empty
                elif label:
                    if label_buffer and top - label_buffer[-1][2] > 1.5 * height:
                        label_buffer = []
                    label_buffer = (label_buffer + [(label, top, bottom)])[-MAX_LABEL_LINES:]
                continue
            if cols is not None and len(amounts) == len(cols):
                full = _assign(amounts, cols, _offset(offsets))
                if full is not None and len(offsets) < 50:
                    offsets.extend(_centre(w) - cols[k][1] for k, w in full.items())
            # Join only lines that sit directly above, each within 1.5 line heights.
            usable = []
            edge = top
            for text, t, b in reversed(label_buffer):
                if edge - b > 1.5 * height:
                    break
                usable.insert(0, text)
                edge = t
            key = None
            start_n = 0 if label else 1
            for n in range(start_n, len(usable) + 1):
                candidate = " ".join(usable[len(usable) - n:] + [label]).strip()
                key = match_label(normalize(_TRAILING_REF.sub("", candidate)))
                if key:
                    label_used = candidate
                    break
            label_buffer = []
            if key is None or key in found:
                continue
            if cols is None:
                notes.append(f"{key}: no usable column header on page {page_index + 1}")
                continue
            target = [i for i, (y, _, s) in enumerate(cols) if y == fiscal_year and s in ("company", "single")]
            if len(target) != 1:
                notes.append(f"{key}: no single company column for {fiscal_year} on page {page_index + 1}")
                continue
            # Dashes are printed empty cells: they occupy a column, so a row
            # with more cells than columns collides and is refused.
            if from_carry and len(amounts) + len(dashes) != len(cols):
                # A carried Όμιλος/Εταιρεία header is trusted only on rows that
                # fill every one of its columns.
                notes.append(f"{key}: partial row under a carried scope header on page {page_index + 1}")
                continue
            taken = _assign(amounts + dashes, cols, _offset(offsets))
            if taken is not None and target[0] in taken and _DASH.match(taken[target[0]]["text"]):
                notes.append(f"{key}: empty cell in the company/{fiscal_year} column")
                continue
            if taken is None or target[0] not in taken:
                notes.append(f"{key}: amount not aligned with the company/{fiscal_year} column "
                             f"(cols {[(y, round(x), s) for y, x, s in cols]}, amounts "
                             f"{[(w['text'], round(_centre(w))) for w in amounts]})")
                continue
            w = taken[target[0]]
            if w.get("score", 1.0) < MIN_OCR_SCORE:
                notes.append(f"{key}: OCR confidence {w['score']:.2f} below {MIN_OCR_SCORE}")
                continue
            if unit is None:
                notes.append(f"{key}: unit unknown on page {page_index + 1}")
                continue
            if unit == 1000 and _CENTS.search(w["text"]):
                notes.append(f"{key}: cents in a thousands statement on page {page_index + 1}")
                continue
            multipliers.add(unit)
            found[key] = dict(value=round(parse_money(w["text"]) * unit, 2), page=page_index + 1,
                              bbox=[round(w["x0"], 2), round(w["top"], 2), round(w["x1"], 2), round(w["bottom"], 2)],
                              page_width=round(p["width"], 2), page_height=round(p["height"], 2),
                              label_matched=label_used, raw_text=w["text"], scope=cols[target[0]][2],
                              source="extracted_geo")
        # Only a header printed on this page may continue onto the next one.
        if cols is not None and header_on_page:
            carried = dict(page=page_index, cols=cols, unit=unit, offsets=offsets)

    ok, problems = check_identities({k: v["value"] for k, v in found.items()})
    if not ok:
        for k in ("total_assets", "equity", "long_term_liabilities", "short_term_liabilities",
                  "total_equity_and_liabilities", "total_liabilities"):
            found.pop(k, None)
        notes.extend(problems)
    _derive_ebitda(found, notes)
    if len(multipliers) > 1:
        notes.append("mixed units across pages; nothing published")
        found = {}
    figures = {k: v for k, v in found.items() if k in labels.PUBLIC}
    if not figures:
        return dict(status="unparseable", reason="no_recognised_line_items", figures={}, fiscal_year=fiscal_year,
                    currency="EUR", unit_multiplier=1, ar_gemi=facts["ar_gemi"], notes=notes)
    missing = [k for k in labels.REQUIRED if k not in figures]
    scopes = {v["scope"] for v in figures.values() if "scope" in v}
    return dict(status="parsed" if not missing else "partial", reason=None, ar_gemi=facts["ar_gemi"],
                fiscal_year=fiscal_year, unit_multiplier=multipliers.pop() if multipliers else 1,
                currency="EUR", scope="company" if scopes <= {"company", "single"} else None,
                figures=figures, missing=missing, notes=notes)
