import re
from difflib import SequenceMatcher

SUMMARY_MARKERS = (
    "сальдо нач", "сальдо конеч", "обороты за период", "всего обороты",
    "по данным", "задолженность в пользу", "акт сверки", "взаимных расчетов",
    "взаимных расчётов", "нижеподписавшиеся", "м.п.", "м. п.",
)

TYPE_ALIASES = (
    ("settlement", "оплата", ("оплата",)),
    ("settlement", "платежное поручение", ("платежное поручение", "платёжное поручение", "п/п")),
    ("settlement", "списание", ("списание с расчетного счета", "списание с расчётного счёта", "списание")),
    ("accrual", "корректировка", ("корректировка поступления", "корректировка отгрузки", "корректировка реализации", "корректировка")),
    ("accrual", "поступление", ("поступление товаров и услуг", "поступление товаров услуг", "поступление")),
    ("accrual", "отгрузка", ("отгрузка",)),
    ("accrual", "реализация", ("реализация товаров", "реализация услуг", "реализация")),
    ("accrual", "накладная", ("накладная", "торг-12", "торг12")),
    ("accrual", "упд", ("упд", "универсальный передаточный документ")),
    ("accrual", "счет-фактура", ("счет-фактура", "счет фактура", "счёт-фактура", "счёт фактура", "с/ф")),
    ("accrual", "акт", ("акт выполненных работ", "акт оказанных услуг", "акт")),
    ("accrual", "возврат", ("возврат поставщику", "возврат от покупателя", "возврат")),
)

VISUAL = str.maketrans({"А":"A","В":"B","Е":"E","К":"K","М":"M","Н":"H","О":"O","Р":"P","С":"C","Т":"T","У":"Y","Х":"X"})
DATE_RE = re.compile(r"(?<!\d)(?:(\d{1,2})[./\-\s]+(\d{1,2})[./\-\s]+(\d{2,4})|(\d{4})[./\-](\d{1,2})[./\-](\d{1,2}))(?!\d)")
NUM_LABEL_RE = re.compile(r"(?:№|номер|n(?:o)?\.?)\s*([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9./_-]{1,40})", re.I)
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9./_-]{1,40}")


def _is_leap_year(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _valid_date(year, month, day):
    if not 1 <= year <= 9999 or not 1 <= month <= 12:
        return False
    month_days = (31, 29 if _is_leap_year(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return 1 <= day <= month_days[month - 1]


def _date_text(year, month, day):
    if not _valid_date(year, month, day):
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def _date_serial(value):
    try:
        year, month, day = (int(part) for part in str(value).split("-"))
    except Exception:
        return None
    if not _valid_date(year, month, day):
        return None
    adjusted_year = year - (1 if month <= 2 else 0)
    era = adjusted_year // 400
    year_of_era = adjusted_year - era * 400
    adjusted_month = month - 3 if month > 2 else month + 9
    day_of_year = (153 * adjusted_month + 2) // 5 + day - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146097 + day_of_era


def ntext(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower().replace("ё", "е"))


def number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return float(value)
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\xa0", "").replace(" ", "").replace(",", ".")
    text = re.sub(r"(руб\.?|₽|р\.)$", "", text, flags=re.I)
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return float(text)
    except Exception:
        return None


def smart_dates(value):
    if value is None:
        return ()
    if all(hasattr(value, attr) for attr in ("year", "month", "day")):
        try:
            parsed = _date_text(int(value.year), int(value.month), int(value.day))
            if parsed:
                return (parsed,)
        except Exception:
            pass
    result = []
    for match in DATE_RE.finditer(str(value)):
        try:
            if match.group(1):
                day, month, year = map(int, match.group(1, 2, 3))
                if year < 100:
                    year += 2000 if year < 70 else 1900
            else:
                year, month, day = map(int, match.group(4, 5, 6))
            parsed = _date_text(year, month, day)
            if not parsed:
                continue
            if parsed not in result:
                result.append(parsed)
        except Exception:
            pass
    return tuple(result)


def smart_type(value):
    text = ntext(value)
    for family, canonical, aliases in TYPE_ALIASES:
        if any(ntext(alias) in text for alias in aliases):
            return canonical, family
    return "", ""


def norm_doc_num(value):
    text = str(value or "").upper().translate(VISUAL)
    text = re.sub(r"^[№N\s]+", "", text)
    text = re.sub(r"[^A-ZА-Я0-9]+", "", text)
    if text.isdigit():
        return text.lstrip("0") or "0"
    return re.sub(r"^([A-ZА-Я]+)0+(?=\d)", r"\1", text)


def smart_number(value):
    text = str(value or "")
    labeled = NUM_LABEL_RE.search(text)
    if labeled:
        return norm_doc_num(labeled.group(1))
    text = DATE_RE.sub(" ", text)
    best, best_score = "", -1
    for token in TOKEN_RE.findall(text):
        if not any(ch.isdigit() for ch in token):
            continue
        raw = token.strip(" .,_-/")
        if raw.isdigit() and len(raw) == 4 and 1900 <= int(raw) <= 2100:
            continue
        normalized = norm_doc_num(raw)
        if len(normalized) < 2:
            continue
        score = min(len(normalized), 20) + (8 if any(ch.isalpha() for ch in normalized) else 0)
        if score > best_score:
            best, best_score = normalized, score
    return best


def _row_text(row):
    return ntext(" | ".join(str(v) for v in row.values() if v is not None and str(v).strip()))


def identity(row, cols, index=0):
    full = " | ".join(str(v).strip() for v in row.values() if v is not None and str(v).strip())
    doc_value = row.get(cols.get("document")) if cols.get("document") else ""
    date_value = row.get(cols.get("date")) if cols.get("date") else ""
    doc_text = str(doc_value or "")
    doc_dates = smart_dates(doc_text)
    row_dates = smart_dates(date_value)
    all_dates = []
    for item in doc_dates + row_dates + smart_dates(full):
        if item not in all_dates:
            all_dates.append(item)
    canonical, family = smart_type(doc_text)
    if not canonical:
        canonical, family = smart_type(full)
    debit = number(row.get(cols.get("debit"))) if cols.get("debit") else None
    credit = number(row.get(cols.get("credit"))) if cols.get("credit") else None
    net = None if debit is None and credit is None else (debit or 0.0) - (credit or 0.0)
    return {
        "index": index,
        "type": canonical,
        "family": family,
        "number": smart_number(doc_text) or smart_number(full),
        "date": (doc_dates or row_dates or tuple(all_dates) or ("",))[0],
        "dates": tuple(all_dates),
        "debit": debit,
        "credit": credit,
        "net": net,
        "amount": abs(net) if net is not None else None,
    }


def is_transaction(row, cols):
    text = _row_text(row)
    if not text or any(marker in text for marker in SUMMARY_MARKERS):
        return False
    if re.search(r"(^|\|\s*)сальдо\s+на\s+\d", text):
        return False
    ident = identity(row, cols)
    if ident["net"] is None:
        return False
    has_doc = bool(ident["type"] or ident["number"] or (cols.get("document") and str(row.get(cols.get("document")) or "").strip()))
    return bool(ident["dates"] and has_doc)


def prepare(rows, cols):
    items, balances = [], []
    accrual_net = settlement_net = 0.0
    for idx, row in enumerate(rows or []):
        text = _row_text(row)
        debit = number(row.get(cols.get("debit"))) if cols.get("debit") else None
        credit = number(row.get(cols.get("credit"))) if cols.get("credit") else None
        if "сальдо нач" in text or "сальдо конеч" in text or re.search(r"сальдо\s+на\s+\d", text):
            if debit is not None or credit is not None:
                balances.append((idx, text, abs((debit or 0.0) - (credit or 0.0))))
        if not is_transaction(row, cols):
            continue
        item = identity(row, cols, idx)
        items.append(item)
        if item["family"] == "settlement":
            settlement_net += item["net"] or 0.0
        else:
            accrual_net += item["net"] or 0.0
    opening = next((v for _, t, v in balances if "сальдо нач" in t), balances[0][2] if balances else None)
    ending = next((v for _, t, v in reversed(balances) if "сальдо конеч" in t), balances[-1][2] if balances else None)
    return {
        "items": items,
        "opening": opening,
        "ending": ending,
        "accrual": abs(accrual_net),
        "settlement": abs(settlement_net),
        "transaction_count": len(items),
    }


def date_distance(a, b):
    best = None
    for da in a.get("dates", ()):
        for db in b.get("dates", ()):
            left = _date_serial(da)
            right = _date_serial(db)
            if left is None or right is None:
                continue
            distance = abs(left - right)
            best = distance if best is None else min(best, distance)
    return best


def num_similarity(a, b):
    a, b = norm_doc_num(a), norm_doc_num(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    da = "".join(ch for ch in a if ch.isdigit()).lstrip("0")
    db = "".join(ch for ch in b if ch.isdigit()).lstrip("0")
    if da and da == db:
        return 0.98
    if (a.endswith(b) or b.endswith(a)) and min(len(a), len(b)) >= 3:
        return 0.95
    ratio = SequenceMatcher(None, a, b).ratio()
    if len(da) >= 4 and len(db) >= 4 and da[-4:] == db[-4:]:
        ratio = max(ratio, 0.90)
    return ratio


def compatible(a, b):
    left, right = a.get("family"), b.get("family")
    return not left or not right or left == right


def amount_cents(item):
    value = item.get("amount")
    return None if value is None else int(round(abs(float(value)) * 100))


def tail_key(value):
    normalized = norm_doc_num(value)
    digits = "".join(ch for ch in normalized if ch.isdigit())
    return digits[-5:] if len(digits) >= 3 else normalized[-5:]


def score(a, b, mode):
    ns = num_similarity(a.get("number"), b.get("number")) if a.get("number") and b.get("number") else 0.0
    distance = date_distance(a, b)
    ds = 1.0 if distance == 0 else 0.94 if distance == 1 else 0.84 if distance is not None and distance <= 3 else 0.55 if distance is not None and distance <= 7 else 0.0
    am = 1.0 if a.get("amount") is not None and b.get("amount") is not None and abs(a["amount"] - b["amount"]) <= 0.01 else 0.0
    family = 1.0 if compatible(a, b) else 0.0
    if mode == "number":
        return 0.66 * ns + 0.16 * am + 0.12 * ds + 0.06 * family
    if mode == "payment":
        return 0.68 * am + 0.26 * ds + 0.06 * family
    if mode == "amount_date":
        return 0.60 * am + 0.30 * ds + 0.10 * family
    return 0.52 * ns + 0.28 * am + 0.14 * ds + 0.06 * family


def pair(prep1, prep2):
    left, right = prep1["items"], prep2["items"]
    free = set(range(len(right)))
    by_number, by_amount, by_tail = {}, {}, {}
    for j, item in enumerate(right):
        if item["number"]:
            by_number.setdefault(item["number"], []).append(j)
            by_tail.setdefault(tail_key(item["number"]), []).append(j)
        cents = amount_cents(item)
        if cents is not None:
            by_amount.setdefault(cents, []).append(j)
    pairs, unmatched = [], []
    order = sorted(range(len(left)), key=lambda i: (bool(left[i]["number"]), left[i]["family"] == "settlement", left[i]["amount"] is not None), reverse=True)
    for i in order:
        a = left[i]
        best, best_score, reason = None, 0.0, ""

        def consider(candidates, mode, predicate):
            nonlocal best, best_score, reason
            for j in candidates:
                if j not in free:
                    continue
                b = right[j]
                if not predicate(b):
                    continue
                candidate_score = score(a, b, mode)
                if candidate_score > best_score:
                    best, best_score, reason = j, candidate_score, mode

        if a["number"]:
            consider(by_number.get(a["number"], ()), "number", lambda b: compatible(a, b) and (date_distance(a, b) is None or date_distance(a, b) <= 10))
        cents = amount_cents(a)
        if best is None and cents is not None and a["family"] == "settlement":
            consider(by_amount.get(cents, ())[:50], "payment", lambda b: b["family"] == "settlement" and (date_distance(a, b) is not None and date_distance(a, b) <= 2))
        if best is None and cents is not None and a["family"] != "settlement":
            consider(by_amount.get(cents, ())[:50], "amount_date", lambda b: b["family"] != "settlement" and compatible(a, b) and (date_distance(a, b) is not None and date_distance(a, b) <= 3))
        if best is None and a["number"]:
            candidates = set(by_tail.get(tail_key(a["number"]), ()))
            if cents is not None:
                candidates.update(by_amount.get(cents, ()))
            consider(list(candidates)[:50], "fuzzy", lambda b: compatible(a, b) and b.get("number") and num_similarity(a["number"], b["number"]) >= 0.88 and (date_distance(a, b) is None or date_distance(a, b) <= 7))
        threshold = 0.68 if reason == "number" else 0.78
        if best is not None and best_score >= threshold:
            free.remove(best)
            pairs.append((i, best, best_score, reason))
        else:
            unmatched.append(i)
    return pairs, unmatched, sorted(free)


def recommendation(kind):
    if kind == "date":
        return "Проверить дату отражения документа у обеих сторон."
    if kind in ("debit", "credit"):
        return "Проверить сумму документа и сторону Д/К."
    return "Проверить первичный документ, дату и сумму."


def annotate_missing(row, cols, side):
    out = dict(row)
    ident = identity(row, cols)
    out["Авто: тип"] = ident["type"] or "не определен"
    out["Авто: номер"] = ident["number"] or "не определен"
    out["Авто: дата"] = ident["date"] or "не определена"
    out["Авто: статус"] = f"Нет сопоставленного документа в {side}"
    out["Рекомендация"] = f"Проверить наличие документа в {side}, дату проведения и сумму."
    return out


def compare_rows(rows1, rows2, cols1, cols2, tolerance=0.01):
    prep1, prep2 = prepare(rows1, cols1), prepare(rows2, cols2)
    pairs, only1_idx, only2_idx = pair(prep1, prep2)
    differences, matches = [], []
    left, right = prep1["items"], prep2["items"]
    tolerance = max(0.01, float(tolerance))
    for i, j, similarity, reason in pairs:
        a, b = left[i], right[j]
        delta = (a["net"] or 0.0) + (b["net"] or 0.0)
        changed = []
        if abs(delta) > tolerance:
            kind = "credit" if a["family"] == "settlement" else "debit"
            changed.append((kind, a["net"], -b["net"] if b["net"] is not None else None, -delta))
        distance = date_distance(a, b)
        if distance is not None and distance > 3:
            changed.append(("date", a["date"], b["date"], ""))
        key = " | ".join(x for x in (a["type"], a["number"], a["date"]) if x) or f"строка {a['index'] + 1}"
        reason_text = {"number":"точный номер", "payment":"платеж: сумма+дата", "amount_date":"сумма+дата", "fuzzy":"похожий номер"}.get(reason, reason)
        if changed:
            for kind, value1, value2, row_delta in changed:
                differences.append([key, kind.upper(), "Акт 1", "Акт 2", value1, value2, row_delta, f"РАЗЛИЧИЕ • {reason_text} • {int(similarity * 100)}%", recommendation(kind)])
        else:
            matches.append([key, f"Совпадает • {reason_text} • {int(similarity * 100)}%"])
    only1 = [annotate_missing(rows1[left[i]["index"]], cols1, "акте 2") for i in only1_idx]
    only2 = [annotate_missing(rows2[right[i]["index"]], cols2, "акте 1") for i in only2_idx]
    return (differences, only1, only2, matches), prep1, prep2


def totals_rows(rows, cols):
    prep = prepare(rows, cols)
    return {
        "debit": prep["accrual"], "credit": prep["settlement"], "balance": prep["ending"],
        "opening": prep["opening"], "ending": prep["ending"], "accrual": prep["accrual"],
        "settlement": prep["settlement"], "transaction_count": prep["transaction_count"],
    }


def total_diffs(t1, t2):
    accrual = t1.get("accrual") - t2.get("accrual") if t1.get("accrual") is not None and t2.get("accrual") is not None else None
    settlement = t1.get("settlement") - t2.get("settlement") if t1.get("settlement") is not None and t2.get("settlement") is not None else None
    return "mirror", accrual, settlement


def find_duplicates_rows(rows, cols, side):
    groups = {}
    for idx, row in enumerate(rows or []):
        if not is_transaction(row, cols):
            continue
        ident = identity(row, cols, idx)
        if not ident["number"]:
            continue
        key = (ident["family"], ident["number"], ident["date"], round(ident["amount"] or 0.0, 2))
        groups.setdefault(key, []).append(idx + 1)
    result = []
    for (family, doc_number, date_value, amount), lines in groups.items():
        if len(lines) > 1:
            result.append([side, family, doc_number, date_value, amount, "", len(lines), ", ".join(map(str, lines))])
    return result
