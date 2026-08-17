from pathlib import Path

path = Path("main.py")
text = path.read_text(encoding="utf-8")


def once(old, new, label):
    global text
    if old not in text:
        raise RuntimeError(f"Не найден участок: {label}")
    text = text.replace(old, new, 1)


def between(start_marker, end_marker, new_block, label):
    global text
    start = text.find(start_marker)
    end = text.find(end_marker, start + 1)
    if start < 0 or end < 0:
        raise RuntimeError(f"Не найден блок: {label}")
    text = text[:start] + new_block.rstrip() + "\n\n" + text[end:]


once('__version__ = "1.3.0"', '__version__ = "1.4.0"', "версия")

once(
    "def ntext(value):",
    r'''MOJIBAKE_CHARS = set("ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿ")
RUS_HINTS = (
    "поступление", "реализация", "оплата", "списание", "платеж", "платёж",
    "акт", "накладная", "счет", "счёт", "фактура", "документ", "дата",
    "номер", "дебет", "кредит", "сальдо", "контрагент", "услуг", "товар",
)


def _text_quality(value):
    value = str(value or "")
    lower = value.lower()
    cyr = sum(("а" <= ch.lower() <= "я") or ch in "Ёё" for ch in value)
    weird = sum(ch in MOJIBAKE_CHARS for ch in value)
    hints = sum(1 for word in RUS_HINTS if word in lower)
    return cyr * 2 + hints * 18 - weird * 4 - value.count("�") * 20


def repair_text(value):
    if not isinstance(value, str) or not value:
        return value
    candidates = [value]
    for source, target in (("latin1", "cp1251"), ("cp1252", "cp1251"), ("cp1251", "utf-8"), ("latin1", "utf-8")):
        try:
            candidate = value.encode(source).decode(target)
            if candidate not in candidates:
                candidates.append(candidate)
        except Exception:
            pass
    best = max(candidates, key=_text_quality)
    return best if _text_quality(best) >= _text_quality(value) + 4 else value


def repair_value(value):
    return repair_text(value) if isinstance(value, str) else value


def ntext(value):''',
    "автокоррекция кодировки",
)

once(
    'name = str(h).strip() if h is not None else ""',
    'name = repair_text(str(h)).strip() if h is not None else ""',
    "кодировка заголовков",
)
once(
    'data.append({headers[i]: raw[i] if i < len(raw) else None for i in range(len(headers))})',
    'data.append({headers[i]: repair_value(raw[i]) if i < len(raw) else None for i in range(len(headers))})',
    "кодировка значений",
)
once("for read_only in (True, False):", "for read_only in (True,):", "экономный XLSX")

between(
    "def type_similarity(a, b):",
    "def date_similarity(a, b):",
    r'''TYPE_FAMILIES = (
    frozenset(("поступление", "реализация", "накладная", "упд", "счет-фактура", "акт")),
    frozenset(("платежное поручение", "списание", "оплата")),
    frozenset(("возврат",)),
    frozenset(("корректировка",)),
)


def type_similarity(a, b):
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.90
    if any(a in family and b in family for family in TYPE_FAMILIES):
        return 0.86
    return SequenceMatcher(None, a, b).ratio()''',
    "семейства типов документов",
)

between(
    "def amount_similarity(a, b):",
    "def match_score(a, b):",
    r'''def _amount_pair_score(left_values, right_values):
    values = []
    for left, right in zip(left_values, right_values):
        if left is not None and right is not None:
            scale = max(abs(left), abs(right), 1.0)
            values.append(max(0.0, 1.0 - abs(left - right) / scale))
    return sum(values) / len(values) if values else 0.0


def amount_profile(a, b):
    same = _amount_pair_score(a["amounts"], b["amounts"])
    mirror = _amount_pair_score(a["amounts"], tuple(reversed(b["amounts"])))
    if mirror > same + 0.04:
        return mirror, "mirror"
    return same, "same"


def amount_similarity(a, b):
    return amount_profile(a, b)[0]''',
    "зеркальный дебет кредит",
)

once(
    'if not candidates and item["type"]: candidates.update(by_type.get(item["type"], ())[:160])',
    'if not candidates and item["type"]: candidates.update(by_type.get(item["type"], ())[:80])',
    "лимит кандидатов",
)

between(
    "def compare(rows1, rows2, cols1, cols2, tolerance):",
    "def totals(rows, cols):",
    r'''def _recommendation(kind, mirror=False):
    if kind == "date":
        return "Проверить дату документа; возможен сдвиг даты проведения/получения."
    if kind == "document":
        return "Проверить номер и тип документа; возможны разные префиксы или связанный первичный документ."
    if kind in ("debit", "credit"):
        return "Проверить сумму и сторону Д/К." + (" Стороны актов определены как зеркальные." if mirror else "")
    if kind == "balance":
        return "Проверить начальное/конечное сальдо и период сверки."
    if kind == "counterparty":
        return "Проверить контрагента, договор или аналитический разрез."
    return "Проверить исходные документы."


def _annotate_missing(row, cols, side):
    out = row.copy()
    ident = smart_identity(row, cols)
    out["Авто: тип"] = ident["type"] or "не определен"
    out["Авто: номер"] = ident["number"] or "не определен"
    out["Авто: дата"] = ident["date"] or "не определена"
    out["Авто: статус"] = f"Нет сопоставленной строки в {side}"
    out["Рекомендация"] = f"Проверить наличие документа в {side}, период, договор и дату отражения."
    return out


def compare(rows1, rows2, cols1, cols2, tolerance):
    paired, only1_idx, only2_idx = pair_rows(rows1, rows2, cols1, cols2)
    differences, matches = [], []

    for i1, i2, score, id1, id2 in paired:
        r1, r2, changed = rows1[i1], rows2[i2], []
        _, amount_mode = amount_profile(id1, id2)
        mirror = amount_mode == "mirror"

        for kind in ("date", "document", "balance", "counterparty"):
            c1, c2 = cols1.get(kind), cols2.get(kind)
            if not c1 or not c2:
                continue
            a, b = r1.get(c1), r2.get(c2)
            if kind == "document":
                same = doc_equal(a, b)
            elif kind == "date":
                da, db = smart_date(a) or date_key(a), smart_date(b) or date_key(b)
                same = bool(da and db and da == db) or equal(a, b, tolerance)
            else:
                same = equal(a, b, tolerance)
            if not same:
                na, nb = number(a), number(b)
                changed.append((kind, c1, c2, a, b, nb - na if na is not None and nb is not None else ""))

        amount_fields = (
            ("debit", cols1.get("debit"), cols2.get("credit") if mirror else cols2.get("debit")),
            ("credit", cols1.get("credit"), cols2.get("debit") if mirror else cols2.get("credit")),
        )
        for kind, c1, c2 in amount_fields:
            if not c1 or not c2:
                continue
            a, b = r1.get(c1), r2.get(c2)
            if not equal(a, b, tolerance):
                na, nb = number(a), number(b)
                changed.append((kind, c1, c2, a, b, nb - na if na is not None and nb is not None else ""))

        key = " | ".join(x for x in (id1["type"], id1["number"], id1["date"]) if x) or f"строка {i1 + 1}"
        mode_note = " • зеркальные Д/К" if mirror else ""
        if changed:
            for kind, c1, c2, a, b, delta in changed:
                differences.append([
                    key, kind.upper(), c1, c2, a, b, delta,
                    f"РАЗЛИЧИЕ • совпадение {int(score * 100)}%{mode_note}",
                    _recommendation(kind, mirror),
                ])
        else:
            matches.append([key, f"Совпадает • {int(score * 100)}%{mode_note}"])

    only1 = [_annotate_missing(rows1[i], cols1, "акте 2") for i in only1_idx]
    only2 = [_annotate_missing(rows2[i], cols2, "акте 1") for i in only2_idx]
    return differences, only1, only2, matches''',
    "автоматизированная сверка",
)

once(
    '''def money(value):
    if value is None:
        return "—"
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")''',
    r'''def reconcile_total_diffs(t1, t2):
    same_ok = all(t1.get(k) is not None and t2.get(k) is not None for k in ("debit", "credit"))
    if not same_ok:
        return "same", None, None
    same_error = abs(t2["debit"] - t1["debit"]) + abs(t2["credit"] - t1["credit"])
    mirror_error = abs(t2["credit"] - t1["debit"]) + abs(t2["debit"] - t1["credit"])
    if mirror_error + 0.01 < same_error:
        return "mirror", t2["credit"] - t1["debit"], t2["debit"] - t1["credit"]
    return "same", t2["debit"] - t1["debit"], t2["credit"] - t1["credit"]


def find_duplicates(rows, cols, side):
    groups = {}
    for idx, row in enumerate(rows):
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


def money(value):
    if value is None:
        return "—"
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")''',
    "итоги и дубликаты",
)

once(
    '''    t1, t2 = totals(rows1, cols1), totals(rows2, cols2)

    def diff(kind):
        return t2[kind] - t1[kind] if t1[kind] is not None and t2[kind] is not None else None''',
    '''    t1, t2 = totals(rows1, cols1), totals(rows2, cols2)
    total_mode, debit_diff, credit_diff = reconcile_total_diffs(t1, t2)
    duplicates = find_duplicates(rows1, cols1, "Акт 1") + find_duplicates(rows2, cols2, "Акт 2")

    def diff(kind):
        if kind == "debit":
            return debit_diff
        if kind == "credit":
            return credit_diff
        return t2[kind] - t1[kind] if t1[kind] is not None and t2[kind] is not None else None''',
    "умные итоги отчета",
)

once(
    '''    summary = [
        ["СРАВНЕНИЕ АС — ИТОГ", ""], ["Акт 1", name1], ["Акт 2", name2],''',
    '''    summary = [
        ["СРАВНЕНИЕ АС — ИТОГ", ""],
        ["Статус автосверки", "СОГЛАСОВАНО АВТОМАТИЧЕСКИ" if not differences and not only1 and not only2 and not duplicates else "ТРЕБУЕТ ПРОВЕРКИ"],
        ["Режим Д/К", "Зеркальный (Д акт 1 ↔ К акт 2)" if total_mode == "mirror" else "Прямой"],
        ["Акт 1", name1], ["Акт 2", name2],''',
    "статус отчета",
)

once(
    '''    wsd.append(["Ключ", "Поле", "Колонка акта 1", "Колонка акта 2", "Акт 1", "Акт 2", "Разница", "Статус"])''',
    '''    wsd.append(["Ключ", "Поле", "Колонка акта 1", "Колонка акта 2", "Акт 1", "Акт 2", "Разница", "Статус", "Рекомендация"])''',
    "рекомендация в различиях",
)

once(
    '''    write_rows("ТОЛЬКО АКТ 1", only1)
    write_rows("ТОЛЬКО АКТ 2", only2)
    wsm = wb.create_sheet("СОВПАДЕНИЯ")''',
    '''    write_rows("ТОЛЬКО АКТ 1", only1)
    write_rows("ТОЛЬКО АКТ 2", only2)

    ws_check = wb.create_sheet("ПРОВЕРИТЬ")
    ws_check.append(["Приоритет", "Причина", "Документ / ключ", "Рекомендация"])
    for row in differences:
        priority = "ВЫСОКИЙ" if row[1] in ("DEBIT", "CREDIT", "BALANCE") else "СРЕДНИЙ"
        ws_check.append([priority, row[1], row[0], row[8] if len(row) > 8 else "Проверить документ"])
    for row in only1:
        ws_check.append(["ВЫСОКИЙ", "Только в акте 1", row.get("Авто: номер", ""), row.get("Рекомендация", "")])
    for row in only2:
        ws_check.append(["ВЫСОКИЙ", "Только в акте 2", row.get("Авто: номер", ""), row.get("Рекомендация", "")])
    for dup in duplicates:
        ws_check.append(["ВЫСОКИЙ", f"Возможный дубль: {dup[0]}", f"{dup[1]} {dup[2]} от {dup[3]}", f"Проверить {dup[6]} одинаковых строк: {dup[7]}"])

    ws_dup = wb.create_sheet("ДУБЛИКАТЫ")
    ws_dup.append(["Акт", "Тип", "Номер", "Дата", "Дебет", "Кредит", "Количество", "Строки"])
    if duplicates:
        for row in duplicates:
            ws_dup.append(row)
    else:
        ws_dup.append(["Дубликаты не найдены"])

    wsm = wb.create_sheet("СОВПАДЕНИЯ")''',
    "листы проверки и дублей",
)

once(
    '''            t1, t2 = totals(self.rows1, self.cols1), totals(self.rows2, self.cols2)
            debit = t2["debit"] - t1["debit"] if t1["debit"] is not None and t2["debit"] is not None else None
            credit = t2["credit"] - t1["credit"] if t1["credit"] is not None and t2["credit"] is not None else None''',
    '''            t1, t2 = totals(self.rows1, self.cols1), totals(self.rows2, self.cols2)
            total_mode, debit, credit = reconcile_total_diffs(t1, t2)
            mode_text = "Зеркальный Д/К" if total_mode == "mirror" else "Прямой Д/К"''',
    "итоги интерфейса",
)

once(
    '''                f"[b]Умное сопоставление включено[/b]\\n"
                f"[b]Расхождения:[/b] {diff_rows}\\n"''',
    '''                f"[b]Автосверка 1.4 включена[/b]\\n"
                f"Режим сумм: {mode_text}\\n"
                f"[b]Расхождения:[/b] {diff_rows}\\n"''',
    "статус интерфейса",
)

once(
    'height=dp(132),\n            halign="left",\n            valign="top",',
    'height=dp(154),\n            halign="left",\n            valign="top",',
    "высота результата",
)

once(
    'actions.add_widget(text_label("XLS / XLSX / CSV • тип, номер и дата распознаются из содержимого строки.", size=11, color=MUTED, height=38, valign="top"))',
    'actions.add_widget(text_label("XLS / XLSX / CSV • автокодировка • умное сопоставление • контроль дублей.", size=11, color=MUTED, height=38, valign="top"))',
    "подпись функций",
)

path.write_text(text, encoding="utf-8")
print("Automation patch applied: encoding repair + mirrored D/C + triage + duplicates + v1.4.0")