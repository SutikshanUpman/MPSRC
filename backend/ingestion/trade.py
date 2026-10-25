"""Trade-row extraction: prose notes and PS fixed-layout tables.

SYSTEM_ARCHITECTURE 14.6 with review F02 (unit-agnostic grammar), F19 (fixed
table layout) and F36 (never derive value from volume using reference prices).

Rules that matter downstream:
- Whitespace is normalised first, and numbers split by a PDF line wrap
  ("43,\\n000") are re-joined.
- Rows are keyed on (doc, YYYY-MM), never on position.
- A row-like sentence or table line that cannot be parsed is kept as a
  TRADE_ROW_INVALID record with its raw text. Nothing is guessed or dropped.
- Repeated value+volume rows and repeated months are flagged on every copy and
  stay visible and usable. They carry `sensitivity_row` and `repeat_cases`
  ("a" same month repeated, "b" same values in a different year, "d" same
  values in another month of the same year; "c" cross-document matches are
  recorded by the pipeline), so exposure is computed with and without them.
  The marker is per row: only the exposure cells that use a flagged row are
  widened; nothing here applies to a whole table or document.
"""
import re

from .structure import normalise_ws

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
SCALES = {
    "k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "mln": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9, "trillion": 1e12,
}
CURRENCY_WORDS = {
    "$": "USD", "us$": "USD", "usd": "USD", "us dollars": "USD", "dollars": "USD", "u.s. dollars": "USD",
    "€": "EUR", "eur": "EUR", "euros": "EUR", "euro": "EUR",
    "£": "GBP", "gbp": "GBP", "pounds": "GBP", "pounds sterling": "GBP",
}
# Unambiguous mass units only. Anything else (tons, MMBtu, units, index points)
# is kept exactly as written and never converted.
MASS_UNITS = {
    "tonnes": 1, "tonne": 1, "t": 1, "mt": 1, "metric tons": 1, "metric ton": 1,
    "metric tonnes": 1, "metric tonne": 1, "kt": 1e3, "kilotonnes": 1e3,
    "kg": 1e-3, "kgs": 1e-3, "kilograms": 1e-3, "kilogrammes": 1e-3,
}
MISSING_WORDS = re.compile(r"^(n/?a|na|-+|—|–|\?|none|null|missing|unknown|not (available|reported|known|given))\.?$", re.I)
# Rows with these flags have no trustworthy number and stay out of arithmetic.
BLOCKING_FLAGS = {
    "TRADE_ROW_INVALID", "TRADE_ROW_MISSING_VALUE", "TRADE_ROW_BAD_NUMBER", "TRADE_TABLE_TRUNCATED",
}
# Rows with these flags are used, but exposure is also computed without them.
SENSITIVITY_FLAGS = {"TRADE_ROW_DUPLICATE", "TRADE_ROW_REPEATED_VALUES"}

_SCALE_RE = r"(?:thousand|million|billion|trillion|mln|mn|bn|[KkMmBb])"
_NUM_RE = r"\d[\d.,\s]*?"
_VERB = r"(?:was|were|of|stood at|reached|came to|totalled|totaled|amounted to|:|=)"
PROSE_ROW = re.compile(
    r"\bIn\s+(?P<month>[A-Za-z]+)\.?\s+(?P<year>\d{4})\s*,\s*(?:the\s+)?(?:trade\s+)?value\s+" + _VERB +
    r"\s*(?P<value>.+?)\s*,?\s+and\s+(?:the\s+)?volume\s+" + _VERB + r"\s*(?P<volume>.+?)\s*(?:\.(?=\s|$)|$)",
    re.I,
)
MONTH_YEAR = re.compile(r"\b(" + "|".join(MONTHS) + r")\.?\s+(\d{4})\b", re.I)
ROUTE_RE = re.compile(
    r"(?:Route|Trade (?:note|table))\s*:\s*(?P<o>[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)*)\s+to\s+"
    r"(?P<d>[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)*)\s*,\s*(?P<s>[A-Za-z][A-Za-z /-]*?)\s*(?:[,.;]|$)"
)


class BadNumber(ValueError):
    pass


def join_wrapped_numbers(s):
    """Collapse whitespace and re-join numbers split by line wraps: '43,\\n000' -> '43,000'."""
    s = normalise_ws(s)
    s = re.sub(r"(\d),\s+(\d{3})(?!\d)", r"\1,\2", s)
    s = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", s)
    return s


def parse_number(s):
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s) or re.fullmatch(r"\d{1,3}( \d{3})+(\.\d+)?", s):
        return float(s.replace(",", "").replace(" ", ""))
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    raise BadNumber(s)


def parse_month(month_word, year):
    m = MONTHS.get(month_word.lower().rstrip("."))
    if not m:
        return None
    return f"{int(year):04d}-{m:02d}"


def parse_period_cell(cell):
    c = cell.strip()
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})", c)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{4})", c)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = re.fullmatch(r"([A-Za-z]+)\.?[\s-]+(\d{4})", c)
    if m:
        return parse_month(m.group(1), m.group(2))
    return None


def normalise_currency(raw):
    key = raw.strip().strip(".").lower()
    if key in CURRENCY_WORDS:
        return CURRENCY_WORDS[key]
    return raw.strip().upper() if re.fullmatch(r"[A-Za-z]{3}", raw.strip()) else raw.strip()


def parse_value(text, default_currency=None, default_scale=None):
    """Return dict(amount, currency, scale_raw) or raise BadNumber / LookupError(missing)."""
    t = text.strip().rstrip(".").strip()
    if not t or MISSING_WORDS.match(t):
        raise LookupError("missing")
    pre = re.fullmatch(r"(?P<cur>US\$|[$€£¥]|[A-Z]{3})\s*(?P<num>" + _NUM_RE + r")\s*(?P<scale>" + _SCALE_RE + r")?", t)
    post = re.fullmatch(r"(?P<num>" + _NUM_RE + r")\s*(?P<scale>" + _SCALE_RE + r")?\s+(?P<cur>[A-Za-z$€£.][A-Za-z$€£. ]*)", t)
    bare = re.fullmatch(r"(?P<num>" + _NUM_RE + r")\s*(?P<scale>" + _SCALE_RE + r")?", t)
    m = pre or post or bare
    if not m:
        if re.search(r"\d", t):
            raise BadNumber(t)
        raise LookupError("missing")
    num = parse_number(m.group("num"))
    scale_raw = m.group("scale") or default_scale
    currency = normalise_currency(m.group("cur")) if m.groupdict().get("cur") else default_currency
    if currency is None:
        raise KeyError("no currency")
    factor = SCALES.get(scale_raw.lower(), None) if scale_raw else 1.0
    if factor is None:
        raise BadNumber(t)
    return {"amount": num * factor, "currency": currency, "scale_raw": scale_raw}


def parse_volume(text, default_unit=None):
    t = text.strip().rstrip(".").strip()
    if not t or MISSING_WORDS.match(t):
        raise LookupError("missing")
    m = re.fullmatch(r"(?P<num>" + _NUM_RE + r")\s*(?:(?P<scale>thousand|million|billion)\s+)?(?P<unit>[A-Za-z%][\w %/().-]*)?", t)
    if not m:
        if re.search(r"\d", t):
            raise BadNumber(t)
        raise LookupError("missing")
    num = parse_number(m.group("num"))
    if m.group("scale"):
        num *= SCALES[m.group("scale").lower()]
    unit_raw = (m.group("unit") or default_unit or "").strip().rstrip(".")
    if not unit_raw:
        raise KeyError("no unit")
    factor = MASS_UNITS.get(unit_raw.lower())
    if factor is not None:
        return {"amount": num * factor, "unit": "tonnes", "unit_raw": unit_raw}
    return {"amount": num, "unit": unit_raw, "unit_raw": unit_raw}


def _new_row(doc_id, layout, para_id, synthetic, raw):
    return {
        "row_key": None, "source_doc_id": doc_id, "source_layout": layout, "table_id": None,
        "native_row_number": None, "origin": None, "destination": None, "sector": None,
        "month": None, "value_amount": None, "value_currency": None, "value_scale_raw": None,
        "volume_amount": None, "volume_unit": None, "volume_unit_raw": None,
        "raw_text": raw, "paragraph": para_id, "synthetic_paragraph": synthetic,
        "parse_status": "valid", "flags": [], "reasons": [], "usable_for_arithmetic": True,
        "sensitivity_row": False, "repeat_cases": [], "repeat_months": [], "cross_doc_matches": [],
    }


def _flag(row, flag, reason=None):
    if flag not in row["flags"]:
        row["flags"].append(flag)
    if reason:
        row["reasons"].append(reason)


def _fill_value(row, text, **defaults):
    try:
        v = parse_value(text, **defaults)
        row.update(value_amount=v["amount"], value_currency=v["currency"], value_scale_raw=v["scale_raw"])
    except LookupError:
        _flag(row, "TRADE_ROW_MISSING_VALUE", "value missing")
    except KeyError:
        _flag(row, "TRADE_ROW_INVALID", "value has no currency")
    except BadNumber as e:
        _flag(row, "TRADE_ROW_BAD_NUMBER", f"value not a number: {e}")


def _fill_volume(row, text, default_unit=None):
    try:
        v = parse_volume(text, default_unit)
        row.update(volume_amount=v["amount"], volume_unit=v["unit"], volume_unit_raw=v["unit_raw"])
    except LookupError:
        _flag(row, "TRADE_ROW_MISSING_VALUE", "volume missing")
    except KeyError:
        _flag(row, "TRADE_ROW_INVALID", "volume has no unit")
    except BadNumber as e:
        _flag(row, "TRADE_ROW_BAD_NUMBER", f"volume not a number: {e}")


def route_from(texts):
    for t in texts:
        m = ROUTE_RE.search(normalise_ws(t or ""))
        if m:
            return m.group("o"), m.group("d"), m.group("s").strip().lower()
    return None, None, None


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", text) if s.strip()]


def is_trade_doc(source_type, title):
    return bool(re.search(r"trade[_ ](note|table)", source_type or "", re.I)
                or re.match(r"\s*trade (note|table)\b", title or "", re.I))


def parse_prose_rows(doc_id, paragraphs, trade_doc):
    rows = []
    for p in paragraphs:
        if p.get("is_table"):
            continue
        text = join_wrapped_numbers(p["text"])
        for sent in _sentences(text):
            m = PROSE_ROW.search(sent)
            if m:
                row = _new_row(doc_id, "prose_note", p["id"], p["synthetic"], sent)
                row["month"] = parse_month(m.group("month"), m.group("year"))
                if not row["month"]:
                    _flag(row, "TRADE_ROW_INVALID", f"unknown month {m.group('month')!r}")
                _fill_value(row, m.group("value"))
                _fill_volume(row, m.group("volume"))
                rows.append(row)
                continue
            row_like = MONTH_YEAR.search(sent) and (
                re.search(r"\b(value|volume)\b", sent, re.I)
                or (trade_doc and re.match(r"\s*In\s+[A-Za-z]+\.?\s+\d{4}\s*,", sent))
            )
            if row_like:
                row = _new_row(doc_id, "prose_note", p["id"], p["synthetic"], sent)
                my = MONTH_YEAR.search(sent)
                row["month"] = parse_month(my.group(1), my.group(2))
                _flag(row, "TRADE_ROW_INVALID", "row-like sentence matches no trade-row grammar")
                rows.append(row)
    return rows


# ---------- fixed-layout tables ----------

_DELIMS = [("pipe", r"\s*\|\s*"), ("tab", r"\t"), ("multispace", r"\s{2,}"), ("comma", r"\s*,\s*")]
_COLS = {
    "row": r"^(row|#|no\.?|nr|n|row[ _]?(no|num(ber)?|#))$",
    "month": r"^(month|period|date)\b",
    "value": r"^value\b",
    "volume": r"^(volume|quantity|qty|tonnage)\b",
    "unit": r"^units?$",
    "currency": r"^currency$",
}
TABLE_HEADER_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _/-]*?)\s*:\s*(.+?)\s*$")


def _split(line, pattern):
    return [c.strip() for c in re.split(pattern, line.strip().strip("|"))]


def _map_columns(cells):
    mapping = {}
    for i, c in enumerate(cells):
        name = c.lower().strip()
        for key, pat in _COLS.items():
            if key not in mapping and re.search(pat, name):
                mapping[key] = i
                break
    return mapping


def _find_column_line(line):
    for name, pat in _DELIMS:
        cells = _split(line, pat)
        # Column names are short labels, not prose.
        if len(cells) >= 3 and all(0 < len(c) <= 32 and len(c.split()) <= 4 for c in cells):
            mapping = _map_columns(cells)
            if "month" in mapping and ("value" in mapping or "volume" in mapping):
                return name, pat, cells, mapping
    return None


def _units_from_header(header, value_col, volume_col):
    """Value currency/scale and volume unit from column names or header keys. None if unknown."""
    cur = scale = vol_unit = None

    def bits(s):
        inner = re.search(r"\(([^)]*)\)|\[([^\]]*)\]", s)
        if inner:
            return (inner.group(1) or inner.group(2)).strip()
        parts = re.split(r"[_\s]+", s.strip())
        return " ".join(parts[1:]).strip()

    vc = bits(value_col) if value_col else ""
    if vc:
        m = re.fullmatch(r"(?P<cur>US\$|[$€£¥]|[A-Za-z]{3})\s*(?P<scale>" + _SCALE_RE + r")?", vc, re.I)
        if m:
            cur, scale = normalise_currency(m.group("cur")), m.group("scale")
    oc = bits(volume_col) if volume_col else ""
    if oc:
        vol_unit = oc
    vu = header.get("VALUE_UNIT") or header.get("VALUE_UNITS")
    if vu and not cur:
        m = re.fullmatch(r"(?P<cur>US\$|[$€£¥]|[A-Za-z]{3})\s*(?P<scale>" + _SCALE_RE + r")?", vu.strip(), re.I)
        if m:
            cur, scale = normalise_currency(m.group("cur")), m.group("scale")
    vol_unit = vol_unit or header.get("VOLUME_UNIT") or header.get("VOLUME_UNITS")
    unit = header.get("UNIT") or header.get("UNITS")
    if unit and (not cur or not vol_unit):
        parts = [p.strip() for p in re.split(r"[;/|]|,\s*(?=[A-Za-z])", unit) if p.strip()]
        for p in parts:
            p2 = re.sub(r"^(value|volume)\s*[:=]?\s*", "", p, flags=re.I)
            m = re.fullmatch(r"(?P<cur>US\$|[$€£¥]|[A-Za-z]{3})\s*(?P<scale>" + _SCALE_RE + r")?", p2, re.I)
            if m and not cur and m.group("cur").lower() not in MASS_UNITS:
                cur, scale = normalise_currency(m.group("cur")), m.group("scale")
            elif not vol_unit:
                vol_unit = p2
    return cur, scale, vol_unit


def _period_months(period):
    """Expected months for a header PERIOD such as '2026-07 to 2026-12' or 'July to December 2026'."""
    if not period:
        return None
    p = normalise_ws(period)
    m = re.fullmatch(r"(\d{4})-(\d{2})\s*(?:to|-|–|until)\s*(\d{4})-(\d{2})", p)
    if m:
        a, b = (int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))
    else:
        m = re.fullmatch(r"([A-Za-z]+)\s*(\d{4})?\s*(?:to|-|–|until)\s*([A-Za-z]+)\s+(\d{4})", p)
        if not m or not MONTHS.get(m.group(1).lower()) or not MONTHS.get(m.group(3).lower()):
            return None
        a = (int(m.group(2) or m.group(4)), MONTHS[m.group(1).lower()])
        b = (int(m.group(4)), MONTHS[m.group(3).lower()])
    out, y, mo = [], a[0], a[1]
    while (y, mo) <= b and len(out) < 240:
        out.append(f"{y:04d}-{mo:02d}")
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    return out


def parse_fixed_tables(doc_id, paragraphs):
    """Find PS fixed-layout tables. Returns (rows, tables, doc_flags)."""
    lines = []
    for p in paragraphs:
        for ln in p["text"].split("\n"):
            if ln.strip():
                lines.append((ln, p))
    rows, tables, doc_flags = [], [], []
    i = 0
    while i < len(lines):
        found = _find_column_line(lines[i][0])
        if not found:
            i += 1
            continue
        _, pat, cols, mapping = found
        header, j = {}, i - 1
        while j >= 0:
            hm = TABLE_HEADER_LINE.match(lines[j][0])
            if not hm or _find_column_line(lines[j][0]):
                break
            header[re.sub(r"[\s/-]+", "_", hm.group(1).strip().upper())] = hm.group(2)
            j -= 1
        for _, p in lines[max(j + 1, 0):i + 1]:
            p["is_table"] = True
        cur, scale, vol_unit = _units_from_header(
            header, cols[mapping["value"]] if "value" in mapping else None,
            cols[mapping["volume"]] if "volume" in mapping else None)
        table = {
            "table_id": header.get("TABLE_ID") or header.get("TABLE") or header.get("ID"),
            "header": header, "columns": cols, "delimiter": pat, "flags": [],
            "value_currency": cur, "value_scale": scale, "volume_unit": vol_unit,
        }
        pair = header.get("COUNTRY_PAIR") or header.get("PAIR") or header.get("ROUTE") or ""
        pm = re.split(r"\s*(?:->|→|>|\bto\b|/|-|–)\s*", pair.strip(), maxsplit=1) if pair else []
        origin = header.get("ORIGIN") or (pm[0] if len(pm) == 2 else None)
        dest = header.get("DESTINATION") or (pm[1] if len(pm) == 2 else None)
        sector = (header.get("SECTOR") or "").strip().lower() or None
        k = i + 1
        table_rows = []
        while k < len(lines):
            line, p = lines[k]
            cells = _split(line, pat)
            if len(cells) < 2 or TABLE_HEADER_LINE.match(line) and not re.match(r"^\s*\d", line):
                break
            p["is_table"] = True
            row = _new_row(doc_id, "fixed_table", p["id"], p["synthetic"], line.strip())
            row.update(table_id=table["table_id"], origin=origin, destination=dest, sector=sector)
            if len(cells) < len(cols):
                _flag(row, "TRADE_TABLE_TRUNCATED", f"row has {len(cells)} of {len(cols)} columns")
                if "TRADE_TABLE_TRUNCATED" not in table["flags"]:
                    table["flags"].append("TRADE_TABLE_TRUNCATED")
            get = lambda key: cells[mapping[key]] if key in mapping and mapping[key] < len(cells) else None
            rn = get("row")
            if rn is not None:
                try:
                    row["native_row_number"] = int(rn)
                except ValueError:
                    _flag(row, "TRADE_ROW_BAD_NUMBER", f"row number {rn!r}")
            mcell = get("month")
            row["month"] = parse_period_cell(mcell) if mcell else None
            if not row["month"]:
                _flag(row, "TRADE_ROW_INVALID", f"month not parseable: {mcell!r}")
            row_cur = get("currency") or cur
            row_unit = get("unit") or vol_unit
            if "value" in mapping:
                vcell = get("value")
                if vcell is None:
                    _flag(row, "TRADE_ROW_MISSING_VALUE", "value cell absent")
                elif row_cur is None and not re.search(r"[A-Za-z$€£¥]", vcell):
                    _flag(row, "TRADE_ROW_INVALID", "value currency unknown")
                else:
                    _fill_value(row, vcell, default_currency=row_cur, default_scale=scale)
            if "volume" in mapping:
                ocell = get("volume")
                if ocell is None:
                    _flag(row, "TRADE_ROW_MISSING_VALUE", "volume cell absent")
                elif row_unit is None and not re.search(r"[A-Za-z]", ocell):
                    _flag(row, "TRADE_ROW_INVALID", "volume unit unknown")
                else:
                    _fill_volume(row, ocell, default_unit=row_unit)
            table_rows.append(row)
            k += 1
        expected = _period_months(header.get("PERIOD"))
        if expected:
            have = {r["month"] for r in table_rows if r["month"]}
            missing = [m for m in expected if m not in have]
            if missing:
                table["flags"].append("TRADE_TABLE_MISSING_MONTH")
                table["missing_months"] = missing
        if not table_rows:
            doc_flags.append("TRADE_TABLE_UNPARSED")
            table["flags"].append("TRADE_TABLE_UNPARSED")
        tables.append(table)
        rows += table_rows
        i = k
    if not tables and any(re.match(r"\s*TABLE[_ ]?ID\s*:", ln, re.I) for ln, _ in lines):
        doc_flags.append("TRADE_TABLE_UNPARSED")
    return rows, tables, doc_flags


def finalise_rows(rows, citation_for):
    """Cross-row checks per document, then keys, status and citations."""
    by_month, by_values = {}, {}
    for r in rows:
        if r["month"]:
            by_month.setdefault(r["month"], []).append(r)
        if r["value_amount"] is not None and r["volume_amount"] is not None:
            key = (r["value_amount"], r["value_currency"], r["volume_amount"], r["volume_unit"])
            by_values.setdefault(key, []).append(r)
    def case(r, other):
        if r["month"] == other["month"]:
            return "a"
        if (r["month"] or "")[:4] != (other["month"] or "")[:4]:
            return "b"
        return "d"

    for group in by_month.values():
        if len(group) > 1:
            for r in group:
                _flag(r, "TRADE_ROW_DUPLICATE", f"month {r['month']} appears {len(group)} times")
                if "a" not in r["repeat_cases"]:
                    r["repeat_cases"].append("a")
    for group in by_values.values():
        if len(group) > 1:
            months = sorted(r["month"] or "?" for r in group)
            for r in group:
                _flag(r, "TRADE_ROW_REPEATED_VALUES", "same value and volume as " + ", ".join(months))
                for other in group:
                    if other is not r:
                        r["repeat_months"].append(other["month"])
                        c = case(r, other)
                        if c not in r["repeat_cases"]:
                            r["repeat_cases"].append(c)
    used = set()
    for n, r in enumerate(rows):
        key = f"{r['source_doc_id']}|{r['month'] or 'unparsed-%d' % n}"
        if key in used:          # repeat case "a": same month twice keeps both rows addressable
            key = f"{key}#{n}"
        used.add(key)
        r["row_key"] = key
        if any(f in ("TRADE_ROW_INVALID",) for f in r["flags"]):
            r["parse_status"] = "invalid"
        elif r["flags"]:
            r["parse_status"] = "flagged"
        r["usable_for_arithmetic"] = not (set(r["flags"]) & BLOCKING_FLAGS)
        r["sensitivity_row"] = bool(set(r["flags"]) & SENSITIVITY_FLAGS)
        r["repeat_cases"].sort()
        r["citation"] = citation_for(r["paragraph"])
    return rows


def missing_month_gaps(rows):
    """Months absent inside the span each year's prose rows cover."""
    years = {}
    for r in rows:
        if r["month"] and r["source_layout"] == "prose_note":
            y, m = r["month"].split("-")
            years.setdefault(y, set()).add(int(m))
    gaps = []
    for y, ms in years.items():
        gaps += [f"{y}-{m:02d}" for m in range(min(ms), max(ms) + 1) if m not in ms]
    return sorted(gaps)
