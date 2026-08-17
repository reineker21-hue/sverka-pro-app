from pathlib import Path

path = Path("main.py")
text = path.read_text(encoding="utf-8")

if '__version__ = "1.5.0"' not in text:
    raise RuntimeError("Не найдена версия 1.5.0")
text = text.replace('__version__ = "1.5.0"', '__version__ = "1.6.0"', 1)

OVERRIDES = r'''
# ===== Accuracy engine 1.6 =====
_ACCURACY_SUMMARY_MARKERS = (
    "сальдо нач", "сальдо конеч", "обороты за период", "всего обороты",
    "по данным", "задолженность в пользу", "акт сверки", "взаимных расчетов",
    "взаимных расчётов", "нижеподписавшиеся", "м.п.", "м. п.",
)
_ACCURACY_SETTLEMENT_TYPES = frozenset(("оплата", "платежное поручение", "списание"))


def smart_dates(value):
    if value is None:
        return []
    if hasattr(value, "strftime"):
        try:
            return [value.strftime("%Y-%m-%d")]
        except Exception:
            pass
    value = str(value)
    result = []
    patterns = (
        (re.compile(r"(?<!\d)(\d{1,2})[./\-\s]+(\d{1,2})[./\-\s]+(\d{2,4})(?!\d)"), False),
        (re.compile(r"(?<!\d)(\d{4})[./\-](\d{1,2})[./\-](\d{1,2})(?!\d)"), True),
    )
    for pattern, year_first in patterns:
        for match in pattern.finditer(value):
            try:
                if year_first:
                    y, m, d = map(int, match.groups())
                else:
                    d, m, y = map(int, match.groups())
                    if y < 100:
                        y += 2000 if y < 70 else 1900
                parsed = datetime(y, m, d).strftime("%Y-%m-%d")
                if parsed not in result:
                    result.append(parsed)
            except Exception:
                pass
    return result


def smart_date(value):
    values = smart_dates(value)
    return values[0] if values else ""


def smart_identity(row, cols, index=0):
    values = [str(v).strip() for v in row.values() if v is not None and str(v).strip()]
    full = " | ".join(values)
    doc_value = row.get(cols.get("document")) if cols.get("document") else ""
    date_value = row.get(cols.get("date")) if cols.get("date") else ""
    doc_text = str(doc_value or "")
    doc_dates = smart_dates(doc_text)
    row_dates = smart_dates(date_value)
    dates = []
    for item in doc_dates + row_dates + smart_dates(full):
        if item and item not in dates:
            dates.append(item)
    debit = number(row.get(cols.get("debit"))) if cols.get("debit") else None
    credit = number(row.get(cols.get("credit"))) if cols.get("credit") else None
    net = (debit or 0.0) - (credit or 0.0) if debit is not None or credit is not None else None
    return {
        "index": index,
        "type": smart_type(doc_text) or smart_type(full),
        "number": smart_number(doc_text) or smart_number(full),
        "date": (doc_dates or row_dates or dates or [""])[0],
        "dates": tuple(dates),
        "amounts": (debit, credit),
        "net": net,
        "amount": abs(net) if net is not None else None,
    }


def _accuracy_text(row):
    return ntext(" | ".join(str(v) for v in row.values() if v is not None and str(v).strip()))


def is_transaction_row(row, cols):
    value = _accuracy_text(row)
    if not value or any(marker in value for marker in _ACCURACY_SUMMARY_MARKERS):
        return False
    if re.search(r"(^|\|\s*)сальдо\s+на\s+\d", value):
        return False
    if not any(number(row.get(cols.get(k))) is not None for k in ("debit", "credit") if cols.get(k)):
        return False
    ident = smart_identity(row, cols)
    has_doc = bool(ident["type"] or ident["number"] or (cols.get("document") and str(row.get(cols.get("document")) or "").strip()))
    return bool(ident["dates"] and has_doc)


def _accuracy_settlement(item):
    return item.get("type") in _ACCURACY_SETTLEMENT_TYPES


def _accuracy_date_distance(a, b):
    result = None
    for da in a.get("dates", ()):
        for db in b.get("dates", ()):
            try:
                distance = abs((datetime.strptime(da, "%Y-%m-%d") - datetime.strptime(db, "%Y-%m-%d")).days)
                result = distance if result is None else min(result, distance)
            except Exception:
                pass
    return result


def _accuracy_amount_equal(a, b, tolerance=0.01):
    x, y = a.get("amount"), b.get("amount")
    return x is not None and y is not None and abs(x - y) <= max(0.01, tolerance)


def _accuracy_type_ok(a, b):
    ta, tb = a.get("type"), b.get("type")
    return not ta or not tb or type_similarity(ta, tb) >= 0.72


def _accuracy_score(a, b, stage):
    ns = num_similarity(a.get("number"), b.get("number")) if a.get("number") and b.get("number") else 0.0
    ts = type_similarity(a.get("type"), b.get("type")) if a.get("type") and b.get("type") else 0.75
    distance = _accuracy_date_distance(a, b)
    ds = 1.0 if distance == 0 else 0.92 if distance == 1 else 0.82 if distance == 2 else 0.72 if distance == 3 else 0.45 if distance is not None and distance <= 7 else 0.0
    am = 1.0 if _accuracy_amount_equal(a, b) else 0.0
    if stage == "number":
        return 0.70 * ns + 0.18 * am + 0.08 * ds + 0.04 * ts
    if stage == "payment":
        return 0.62 * am + 0.28 * ds + 0.10 * ts
    return 0.48 * ns + 0.30 * am + 0.14 * ds + 0.08 * ts


def _accuracy_assign(edges, free1, free2, pairs):
    for score, i1, i2, reason, a, b in sorted(edges, key=lambda x: x[0], reverse=True):
        if i1 in free1 and i2 in free2:
            free1.remove(i1)
            free2.remove(i2)
            pairs.append((i1, i2, score, a, b, reason))


def pair_rows(rows1, rows2, cols1, cols2):
    tx1 = [i for i, row in enumerate(rows1) if is_transaction_row(row, cols1)]
    tx2 = [i for i, row in enumerate(rows2) if is_transaction_row(row, cols2)]
    id1 = {i: smart_identity(rows1[i], cols1, i) for i in tx1}
    id2 = {i: smart_identity(rows2[i], cols2, i) for i in tx2}
    free1, free2, pairs = set(tx1), set(tx2), []

    by_number = {}
    for j in tx2:
        if id2[j].get("number"):
            by_number.setdefault(id2[j]["number"], []).append(j)
    edges = []
    for i in tx1:
        a = id1[i]
        for j in by_number.get(a.get("number"), ()): 
            b = id2[j]
            distance = _accuracy_date_distance(a, b)
            if _accuracy_type_ok(a, b) and (distance is None or distance <= 7):
                edges.append((_accuracy_score(a, b, "number"), i, j, "точный номер", a, b))
    _accuracy_assign(edges, free1, free2, pairs)

    edges = []
    for i in tuple(free1):
        a = id1[i]
        if not _accuracy_settlement(a):
            continue
        for j in tuple(free2):
            b = id2[j]
            distance = _accuracy_date_distance(a, b)
            if _accuracy_settlement(b) and _accuracy_type_ok(a, b) and _accuracy_amount_equal(a, b) and distance is not None and distance <= 1:
                edges.append((_accuracy_score(a, b, "payment"), i, j, "платеж: дата+сумма", a, b))
    _accuracy_assign(edges, free1, free2, pairs)

    edges = []
    for i in tuple(free1):
        a = id1[i]
        if _accuracy_settlement(a):
            continue
        for j in tuple(free2):
            b = id2[j]
            if _accuracy_settlement(b) or not _accuracy_type_ok(a, b):
                continue
            ns = num_similarity(a.get("number"), b.get("number")) if a.get("number") and b.get("number") else 0.0
            distance = _accuracy_date_distance(a, b)
            if ns >= 0.88 and (_accuracy_amount_equal(a, b) or (distance is not None and distance <= 3)):
                score = _accuracy_score(a, b, "fuzzy")
                if score >= 0.78:
                    edges.append((score, i, j, "похожий номер", a, b))
    _accuracy_assign(edges, free1, free2, pairs)
    return pairs, sorted(free1), sorted(free2)


def compare(rows1, rows2, cols1, cols2, tolerance):
    paired, only1_idx, only2_idx = pair_rows(rows1, rows2, cols1, cols2)
    differences, matches = [], []
    for i1, i2, score, a, b, reason in paired:
        changed = []
        left = a.get("net")
        right = -b.get("net") if b.get("net") is not None else None
        if left is not None and right is not None and abs(left - right) > max(0.01, tolerance):
            kind = "credit" if _accuracy_settlement(a) else "debit"
            changed.append((kind, "Экономический оборот акта 1", "Экономический оборот акта 2", left, right, right - left))
        if a.get("dates") and b.get("dates"):
            distance = _accuracy_date_distance(a, b)
            if distance is not None and distance > 1:
                changed.append(("date", cols1.get("date") or "Дата", cols2.get("date") or "Дата", a.get("date"), b.get("date"), ""))
        key = " | ".join(x for x in (a.get("type"), a.get("number"), a.get("date")) if x) or f"строка {i1 + 1}"
        if changed:
            for kind, c1, c2, v1, v2, delta in changed:
                differences.append([key, kind.upper(), c1, c2, v1, v2, delta, f"РАЗЛИЧИЕ • {reason} • {int(score * 100)}%", _recommendation(kind, True)])
        else:
            matches.append([key, f"Совпадает • {reason} • {int(score * 100)}%"])
    only1 = [_annotate_missing(rows1[i], cols1, "акте 2") for i in only1_idx]
    only2 = [_annotate_missing(rows2[i], cols2, "акте 1") for i in only2_idx]
    return differences, only1, only2, matches


def _accuracy_dc(row, cols):
    d = number(row.get(cols.get("debit"))) if cols.get("debit") else None
    c = number(row.get(cols.get("credit"))) if cols.get("credit") else None
    return d, c


def totals(rows, cols):
    tx = [row for row in rows if is_transaction_row(row, cols)]
    accrual = settlement = 0.0
    for row in tx:
        item = smart_identity(row, cols)
        if item.get("net") is None:
            continue
        if _accuracy_settlement(item):
            settlement += item["net"]
        else:
            accrual += item["net"]

    balances = []
    for pos, row in enumerate(rows):
        value = _accuracy_text(row)
        if "сальдо нач" in value or "сальдо конеч" in value or re.search(r"сальдо\s+на\s+\d", value):
            d, c = _accuracy_dc(row, cols)
            if d is not None or c is not None:
                balances.append((pos, value, abs((d or 0.0) - (c or 0.0))))
    opening = next((v for _, t, v in balances if "сальдо нач" in t), balances[0][2] if balances else None)
    ending = next((v for _, t, v in reversed(balances) if "сальдо конеч" in t), balances[-1][2] if balances else None)

    return {
        "debit": abs(accrual),
        "credit": abs(settlement),
        "balance": ending,
        "opening": opening,
        "ending": ending,
        "accrual": abs(accrual),
        "settlement": abs(settlement),
        "transaction_count": len(tx),
    }


def reconcile_total_diffs(t1, t2):
    debit = t1.get("accrual") - t2.get("accrual") if t1.get("accrual") is not None and t2.get("accrual") is not None else None
    credit = t1.get("settlement") - t2.get("settlement") if t1.get("settlement") is not None and t2.get("settlement") is not None else None
    return "mirror", debit, credit


def find_duplicates(rows, cols, side):
    groups = {}
    for idx, row in enumerate(rows):
        if not is_transaction_row(row, cols):
            continue
        ident = smart_identity(row, cols, idx)
        if not ident["number"]:
            continue
        amounts = tuple(round(v, 2) if v is not None else None for v in ident["amounts"])
        key = (ident["type"], ident["number"], ident["date"], amounts)
        groups.setdefault(key, []).append(idx + 1)
    result = []
    for (doc_type, number_value, date_value, amounts), lines in groups.items():
        if len(lines) > 1:
            result.append([side, doc_type, number_value, date_value, amounts[0], amounts[1], len(lines), ", ".join(map(str, lines))])
    return result


def _accuracy_run_compare(self, *_):
    if self.rows1 is None or self.rows2 is None:
        self.error("Сначала выберите оба акта сверки.")
        return
    try:
        tolerance = float(self.tolerance.text.replace(",", "."))
        result = compare(self.rows1, self.rows2, self.cols1, self.cols2, tolerance)
        self.last_result = result
        self.save_button.disabled = False
        if hasattr(self, "fns_button"):
            self.fns_button.disabled = False
        differences, only1, only2, matches = result
        t1, t2 = totals(self.rows1, self.cols1), totals(self.rows2, self.cols2)
        _, accrual_diff, settlement_diff = reconcile_total_diffs(t1, t2)
        opening_diff = t1["opening"] - t2["opening"] if t1.get("opening") is not None and t2.get("opening") is not None else None
        ending_diff = t1["ending"] - t2["ending"] if t1.get("ending") is not None and t2.get("ending") is not None else None
        self.result_label.color = TEXT
        self.result_label.height = dp(190)
        self.result_label.text = (
            f"[b]Точная автосверка 1.6[/b]\n"
            f"[b]Расхождения документов:[/b] {len(only1) + len(only2)}\n"
            f"Только в акте 1: {len(only1)} • Только в акте 2: {len(only2)}\n"
            f"Совпадений: {len(matches)}\n\n"
            f"Начальное сальдо: {money(opening_diff)} руб.\n"
            f"[b]Разница начислений:[/b] {money(accrual_diff)} руб.\n"
            f"[b]Разница оплат:[/b] {money(settlement_diff)} руб.\n"
            f"[b]Разница конечного сальдо:[/b] {money(ending_diff)} руб."
        )
    except Exception as exc:
        self.error(str(exc))


MainScreen.run_compare = _accuracy_run_compare
# ===== /Accuracy engine 1.6 =====
'''

marker = 'if __name__ == "__main__":'
if marker not in text:
    raise RuntimeError("Не найден конец main.py")
text = text.replace(marker, OVERRIDES + "\n\n" + marker, 1)

text = text.replace(
    'XLS / XLSX / CSV • автосверка • протокол расхождений по структуре ФНС в Excel.',
    'XLS / XLSX / CSV • точная сверка • платежи по дате+сумме • протокол ФНС.',
    1,
)

path.write_text(text, encoding="utf-8")
print("Accuracy engine 1.6 applied")