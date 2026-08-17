from pathlib import Path

path = Path("main.py")
text = path.read_text(encoding="utf-8")

if '__version__ = "1.7.0"' not in text:
    raise RuntimeError("Не найдена версия 1.7.0 перед lean runtime patch")
text = text.replace('__version__ = "1.7.0"', '__version__ = "1.9.0"', 1)

OVERRIDES = r'''
# ===== Lean runtime 1.9 =====
_LEAN_SUMMARY_MARKERS = (
    "сальдо нач", "сальдо конеч", "обороты за период", "всего обороты",
    "по данным", "задолженность в пользу", "акт сверки", "взаимных расчетов",
    "взаимных расчётов", "нижеподписавшиеся", "м.п.", "м. п.",
)
_LEAN_SETTLEMENT_TYPES = frozenset(("оплата", "платежное поручение", "списание"))


def read_xlsx(path):
    try:
        return read_xlsx_fallback(path)
    except Exception as fallback_error:
        try:
            return read_xlsx_openpyxl(path)
        except Exception as secondary_error:
            raise ValueError(
                "Не удалось прочитать XLSX. "
                f"ZIP/XML: {fallback_error}. Резервный режим: {secondary_error}"
            )


def _lean_text(row):
    return ntext(" | ".join(str(v) for v in row.values() if v is not None and str(v).strip()))


def _lean_dc(row, cols):
    debit = number(row.get(cols.get("debit"))) if cols.get("debit") else None
    credit = number(row.get(cols.get("credit"))) if cols.get("credit") else None
    return debit, credit


def _lean_prepare(rows, cols):
    items = []
    balances = []
    accrual = 0.0
    settlement = 0.0
    for idx, row in enumerate(rows or []):
        text_value = _lean_text(row)
        debit, credit = _lean_dc(row, cols)
        if "сальдо нач" in text_value or "сальдо конеч" in text_value or re.search(r"сальдо\s+на\s+\d", text_value):
            if debit is not None or credit is not None:
                balances.append((idx, text_value, abs((debit or 0.0) - (credit or 0.0))))
        if not text_value or any(marker in text_value for marker in _LEAN_SUMMARY_MARKERS):
            continue
        if re.search(r"(^|\|\s*)сальдо\s+на\s+\d", text_value):
            continue
        if debit is None and credit is None:
            continue
        ident = smart_identity(row, cols, idx)
        has_doc = bool(
            ident.get("type") or ident.get("number") or
            (cols.get("document") and str(row.get(cols.get("document")) or "").strip())
        )
        if not ident.get("dates") or not has_doc:
            continue
        item = {
            "index": idx,
            "type": ident.get("type") or "",
            "number": ident.get("number") or "",
            "date": ident.get("date") or "",
            "dates": ident.get("dates") or (),
            "net": ident.get("net"),
            "amount": ident.get("amount"),
        }
        items.append(item)
        if item["net"] is not None:
            if item["type"] in _LEAN_SETTLEMENT_TYPES:
                settlement += item["net"]
            else:
                accrual += item["net"]

    opening = next((v for _, t, v in balances if "сальдо нач" in t), balances[0][2] if balances else None)
    ending = next((v for _, t, v in reversed(balances) if "сальдо конеч" in t), balances[-1][2] if balances else None)
    return {
        "items": items,
        "opening": opening,
        "ending": ending,
        "accrual": abs(accrual),
        "settlement": abs(settlement),
    }


def _lean_date_distance(a, b):
    best = None
    for da in a.get("dates", ()):
        for db in b.get("dates", ()):
            try:
                delta = abs((datetime.strptime(da, "%Y-%m-%d") - datetime.strptime(db, "%Y-%m-%d")).days)
                best = delta if best is None else min(best, delta)
            except Exception:
                pass
    return best


def _lean_type_ok(a, b):
    ta, tb = a.get("type"), b.get("type")
    return not ta or not tb or type_similarity(ta, tb) >= 0.72


def _lean_amount_cents(item):
    value = item.get("amount")
    if value is None:
        return None
    try:
        return int(round(abs(float(value)) * 100))
    except Exception:
        return None


def _lean_tail(value):
    normalized = norm_doc_num(value)
    digits = "".join(ch for ch in normalized if ch.isdigit())
    return digits[-5:] if len(digits) >= 3 else normalized[-5:]


def _lean_score(a, b, mode):
    ns = num_similarity(a.get("number"), b.get("number")) if a.get("number") and b.get("number") else 0.0
    ts = type_similarity(a.get("type"), b.get("type")) if a.get("type") and b.get("type") else 0.72
    distance = _lean_date_distance(a, b)
    ds = 1.0 if distance == 0 else 0.92 if distance == 1 else 0.80 if distance is not None and distance <= 3 else 0.55 if distance is not None and distance <= 7 else 0.0
    amount_same = a.get("amount") is not None and b.get("amount") is not None and abs(a["amount"] - b["amount"]) <= 0.01
    am = 1.0 if amount_same else 0.0
    if mode == "number":
        return 0.66 * ns + 0.18 * am + 0.10 * ds + 0.06 * ts
    if mode == "payment":
        return 0.66 * am + 0.26 * ds + 0.08 * ts
    if mode == "amount_date":
        return 0.58 * am + 0.28 * ds + 0.14 * ts
    return 0.50 * ns + 0.28 * am + 0.14 * ds + 0.08 * ts


def _lean_pair(prep1, prep2):
    left = prep1["items"]
    right = prep2["items"]
    free = set(range(len(right)))
    by_number, by_amount, by_tail = {}, {}, {}
    for j, item in enumerate(right):
        if item["number"]:
            by_number.setdefault(item["number"], []).append(j)
            by_tail.setdefault(_lean_tail(item["number"]), []).append(j)
        cents = _lean_amount_cents(item)
        if cents is not None:
            by_amount.setdefault(cents, []).append(j)

    pairs = []
    unmatched_left = []
    order = sorted(range(len(left)), key=lambda i: (bool(left[i]["number"]), bool(left[i]["date"]), left[i]["amount"] is not None), reverse=True)
    for i in order:
        a = left[i]
        best = None
        best_score = 0.0
        best_reason = ""

        def consider(candidates, mode, predicate):
            nonlocal best, best_score, best_reason
            for j in candidates:
                if j not in free:
                    continue
                b = right[j]
                if not predicate(b):
                    continue
                score = _lean_score(a, b, mode)
                if score > best_score:
                    best, best_score, best_reason = j, score, mode

        if a["number"]:
            consider(
                by_number.get(a["number"], ()), "number",
                lambda b: _lean_type_ok(a, b) and ((_lean_date_distance(a, b) or 0) <= 10),
            )

        cents = _lean_amount_cents(a)
        if best is None and cents is not None and a["type"] in _LEAN_SETTLEMENT_TYPES:
            consider(
                by_amount.get(cents, ())[:80], "payment",
                lambda b: b["type"] in _LEAN_SETTLEMENT_TYPES and _lean_type_ok(a, b) and (_lean_date_distance(a, b) is not None and _lean_date_distance(a, b) <= 2),
            )

        if best is None and cents is not None and a["type"] not in _LEAN_SETTLEMENT_TYPES:
            consider(
                by_amount.get(cents, ())[:80], "amount_date",
                lambda b: b["type"] not in _LEAN_SETTLEMENT_TYPES and _lean_type_ok(a, b) and (_lean_date_distance(a, b) is not None and _lean_date_distance(a, b) <= 3),
            )

        if best is None and a["number"]:
            candidates = set(by_tail.get(_lean_tail(a["number"]), ()))
            if cents is not None:
                candidates.update(by_amount.get(cents, ()))
            consider(
                list(candidates)[:80], "fuzzy",
                lambda b: _lean_type_ok(a, b) and num_similarity(a["number"], b.get("number")) >= 0.86,
            )

        threshold = 0.70 if best_reason == "number" else 0.76
        if best is not None and best_score >= threshold:
            free.remove(best)
            pairs.append((i, best, best_score, best_reason))
        else:
            unmatched_left.append(i)

    return pairs, unmatched_left, sorted(free)


def _lean_compare(screen, tolerance):
    prep1 = getattr(screen, "_prepared1", None) or _lean_prepare(screen.rows1, screen.cols1)
    prep2 = getattr(screen, "_prepared2", None) or _lean_prepare(screen.rows2, screen.cols2)
    pairs, only1_idx, only2_idx = _lean_pair(prep1, prep2)
    differences, matches = [], []
    left, right = prep1["items"], prep2["items"]

    for i1, i2, score, reason in pairs:
        a, b = left[i1], right[i2]
        changed = []
        left_net = a.get("net")
        right_net = -b.get("net") if b.get("net") is not None else None
        if left_net is not None and right_net is not None and abs(left_net - right_net) > max(0.01, tolerance):
            kind = "credit" if a.get("type") in _LEAN_SETTLEMENT_TYPES else "debit"
            changed.append((kind, left_net, right_net, right_net - left_net))
        distance = _lean_date_distance(a, b)
        if distance is not None and distance > 1:
            changed.append(("date", a.get("date"), b.get("date"), ""))
        key = " | ".join(x for x in (a.get("type"), a.get("number"), a.get("date")) if x) or f"строка {a['index'] + 1}"
        reason_text = {
            "number": "точный номер",
            "payment": "платеж: сумма+дата",
            "amount_date": "сумма+дата",
            "fuzzy": "похожий номер",
        }.get(reason, reason)
        if changed:
            for kind, v1, v2, delta in changed:
                differences.append([
                    key, kind.upper(), "Акт 1", "Акт 2", v1, v2, delta,
                    f"РАЗЛИЧИЕ • {reason_text} • {int(score * 100)}%",
                    _recommendation(kind, True),
                ])
        else:
            matches.append([key, f"Совпадает • {reason_text} • {int(score * 100)}%"])

    only1 = [_annotate_missing(screen.rows1[left[i]["index"]], screen.cols1, "акте 2") for i in only1_idx]
    only2 = [_annotate_missing(screen.rows2[right[i]["index"]], screen.cols2, "акте 1") for i in only2_idx]
    return (differences, only1, only2, matches), prep1, prep2


def _lean_load_file(self, uri, target):
    path = None
    try:
        filename = uri_display_name(uri)
        path = uri_to_tempfile(uri)
        headers, rows, sheet = read_table(path)
        cols = {key: detect_column(headers, key) for key in ALIASES}
        prepared = _lean_prepare(rows, cols)
        if target == 1:
            self.rows1, self.headers1, self.cols1 = rows, headers, cols
            self._prepared1 = prepared
            self.file1_name = filename
            self.file1_label.text = f"Акт 1: {filename}"
            self.file1_label.color = PRIMARY
        else:
            self.rows2, self.headers2, self.cols2 = rows, headers, cols
            self._prepared2 = prepared
            self.file2_name = filename
            self.file2_label.text = f"Акт 2: {filename}"
            self.file2_label.color = PRIMARY
        self.last_result = None
        self.save_button.disabled = True
        if hasattr(self, "fns_button"):
            self.fns_button.disabled = True
        self.update_fields()
        try:
            import gc
            gc.collect()
        except Exception:
            pass
    except BaseException as exc:
        self.error(f"{type(exc).__name__}: {exc}")
    finally:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except Exception:
                pass


def _lean_run_compare(self, *_):
    if self.rows1 is None or self.rows2 is None:
        self.error("Сначала выберите оба акта сверки.")
        return
    try:
        tolerance = float(self.tolerance.text.replace(",", "."))
    except Exception:
        self.error("Укажите корректный допуск в рублях.")
        return

    self.compare_button.disabled = True
    self.save_button.disabled = True
    if hasattr(self, "fns_button"):
        self.fns_button.disabled = True
    try:
        result, prep1, prep2 = _lean_compare(self, tolerance)
        self.last_result = result
        self._prepared1, self._prepared2 = prep1, prep2
        differences, only1, only2, matches = result
        opening_diff = prep1["opening"] - prep2["opening"] if prep1["opening"] is not None and prep2["opening"] is not None else None
        accrual_diff = prep1["accrual"] - prep2["accrual"]
        settlement_diff = prep1["settlement"] - prep2["settlement"]
        ending_diff = prep1["ending"] - prep2["ending"] if prep1["ending"] is not None and prep2["ending"] is not None else None
        self.result_label.color = TEXT
        self.result_label.height = dp(190)
        self.result_label.text = (
            f"[b]Сверка завершена[/b]\n"
            f"Документов требуют проверки: {len(only1) + len(only2)}\n"
            f"Только в акте 1: {len(only1)} • Только в акте 2: {len(only2)}\n"
            f"Совпадений: {len(matches)}\n\n"
            f"Начальное сальдо: {money(opening_diff)} руб.\n"
            f"[b]Разница начислений:[/b] {money(accrual_diff)} руб.\n"
            f"[b]Разница оплат:[/b] {money(settlement_diff)} руб.\n"
            f"[b]Разница конечного сальдо:[/b] {money(ending_diff)} руб."
        )
        self.save_button.disabled = False
        if hasattr(self, "fns_button"):
            self.fns_button.disabled = False
    except BaseException as exc:
        self.result_label.color = DANGER
        self.result_label.text = f"Ошибка сравнения: {type(exc).__name__}: {exc}"
    finally:
        self.compare_button.disabled = False
        try:
            import gc
            gc.collect()
        except Exception:
            pass


MainScreen.load_file = _lean_load_file
MainScreen.run_compare = _lean_run_compare
# ===== /Lean runtime 1.9 =====
'''

marker = 'if __name__ == "__main__":'
if marker not in text:
    raise RuntimeError("Не найден конец main.py")
text = text.replace(marker, OVERRIDES + "\n\n" + marker, 1)
text = text.replace(
    'Excel-стиль • XLS / XLSX / CSV • сверка в фоне • протокол ФНС.',
    'Excel-стиль • XLS / XLSX / CSV • облегчённая сверка • протокол ФНС.',
    1,
)
path.write_text(text, encoding="utf-8")
print("Lean runtime 1.9 applied")
