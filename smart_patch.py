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


once('__version__ = "1.2.0"', '__version__ = "1.3.0"', "версия")
once(
    "from datetime import datetime, timedelta\nfrom pathlib import Path",
    "from datetime import datetime, timedelta\nfrom difflib import SequenceMatcher\nfrom pathlib import Path",
    "difflib",
)

# Do not load openpyxl at app startup; load it only on XLSX/report operations.
once(
    "from openpyxl import Workbook, load_workbook\nfrom openpyxl.styles import Alignment, Font, PatternFill\nfrom openpyxl.utils import get_column_letter\n\n",
    "",
    "ленивый openpyxl",
)
once(
    "def read_xlsx_openpyxl(path):\n    errors = []",
    "def read_xlsx_openpyxl(path):\n    from openpyxl import load_workbook\n\n    errors = []",
    "openpyxl reader",
)
once(
    "def autosize(ws):\n    for col in ws.columns:\n        letter = get_column_letter(col[0].column)",
    "def autosize(ws):\n    from openpyxl.utils import get_column_letter\n\n    for col in ws.columns:\n        letter = get_column_letter(col[0].column)",
    "autosize",
)
once(
    "def create_report(output, rows1, rows2, cols1, cols2, differences, only1, only2, matches, name1, name2):\n    t1, t2 = totals(rows1, cols1), totals(rows2, cols2)",
    "def create_report(output, rows1, rows2, cols1, cols2, differences, only1, only2, matches, name1, name2):\n    from openpyxl import Workbook\n    from openpyxl.styles import Alignment, Font, PatternFill\n\n    t1, t2 = totals(rows1, cols1), totals(rows2, cols2)",
    "report imports",
)

once(
    '''ALIASES = {
    "date": ["дата", "дата операции", "дата документа", "датадокумента", "date"],''',
    '''ALIASES = {
    "date": ["дата", "дата операции", "дата документа", "датадокумента", "date", "период"],''',
    "date aliases",
)
once(
    '''    "document": [
        "документ", "номер документа", "номердокумента", "№ документа", "номер",
        "док", "основание", "счет фактура", "счет-фактура", "накладная", "акт",
    ],''',
    '''    "document": [
        "документ", "номер документа", "номердокумента", "№ документа", "номер",
        "док", "основание", "счет фактура", "счет-фактура", "накладная", "акт",
        "содержание", "операция", "вид документа", "тип документа",
        "представление документа", "документ основание", "назначение", "расшифровка",
    ],''',
    "document aliases",
)

between(
    "def make_key(row, cols, occurrence):",
    "def totals(rows, cols):",
    r'''DOC_TYPES = (
    ("счет-фактура", ("счет-фактура", "счет фактура", "счёт-фактура", "счёт фактура", "с/ф")),
    ("упд", ("упд", "универсальный передаточный документ")),
    ("накладная", ("накладная", "торг-12", "торг12")),
    ("акт", ("акт выполненных работ", "акт оказанных услуг", "акт сверки", "акт")),
    ("платежное поручение", ("платежное поручение", "платёжное поручение", "п/п")),
    ("реализация", ("реализация товаров", "реализация услуг", "реализация")),
    ("поступление", ("поступление товаров", "поступление услуг", "поступление")),
    ("списание", ("списание с расчетного счета", "списание с расчётного счёта", "списание")),
    ("оплата", ("оплата поставщику", "оплата покупателя", "оплата")),
    ("возврат", ("возврат поставщику", "возврат от покупателя", "возврат")),
    ("корректировка", ("корректировка долга", "корректировка реализации", "корректировка")),
    ("счет", ("счет на оплату", "счёт на оплату", "счет", "счёт")),
)
SMART_DATE_RE = re.compile(
    r"(?<!\d)(?:(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})|(\d{4})-(\d{1,2})-(\d{1,2}))(?!\d)"
)
SMART_NUM_RE = re.compile(r"(?:№|номер|n(?:o)?\.?)\s*([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9./_-]{1,30})", re.I)
SMART_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9./_-]{1,30}")
VISUAL = str.maketrans({"А":"A","В":"B","Е":"E","К":"K","М":"M","Н":"H","О":"O","Р":"P","С":"C","Т":"T","У":"Y","Х":"X"})


def smart_date(value):
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%Y-%m-%d")
        except Exception:
            pass
    match = SMART_DATE_RE.search(str(value))
    if not match:
        return ""
    try:
        if match.group(1):
            d, m, y = map(int, match.group(1, 2, 3))
            if y < 100:
                y += 2000 if y < 70 else 1900
        else:
            y, m, d = map(int, match.group(4, 5, 6))
        return datetime(y, m, d).strftime("%Y-%m-%d")
    except Exception:
        return ""


def smart_type(value):
    text_value = ntext(value)
    for canonical, aliases in DOC_TYPES:
        if any(ntext(alias) in text_value for alias in aliases):
            return canonical
    return ""


def norm_doc_num(value):
    text_value = str(value or "").upper().translate(VISUAL)
    text_value = re.sub(r"^[№N\s]+", "", text_value)
    text_value = re.sub(r"[^A-ZА-Я0-9]+", "", text_value)
    if text_value.isdigit():
        return text_value.lstrip("0") or "0"
    return re.sub(r"^([A-ZА-Я]+)0+(?=\d)", r"\1", text_value)


def smart_number(value):
    text_value = str(value or "")
    labeled = SMART_NUM_RE.search(text_value)
    if labeled:
        return norm_doc_num(labeled.group(1))
    text_value = SMART_DATE_RE.sub(" ", text_value)
    best, best_score = "", -1
    for token in SMART_TOKEN_RE.findall(text_value):
        if not any(ch.isdigit() for ch in token):
            continue
        raw = token.strip(" .,_-/")
        if re.fullmatch(r"\d{4}", raw) and 1900 <= int(raw) <= 2100:
            continue
        normalized = norm_doc_num(raw)
        if len(normalized) < 2:
            continue
        score = min(len(normalized), 16) + (6 if any(ch.isalpha() for ch in normalized) else 0)
        score += 3 if any(ch in raw for ch in "-/_") else 0
        if score > best_score:
            best, best_score = normalized, score
    return best


def smart_identity(row, cols, index=0):
    values = [str(value).strip() for value in row.values() if value is not None and str(value).strip()]
    full = " | ".join(values)
    doc_value = row.get(cols.get("document")) if cols.get("document") else ""
    date_value = row.get(cols.get("date")) if cols.get("date") else ""
    doc_text = str(doc_value or "")
    return {
        "index": index,
        "type": smart_type(doc_text) or smart_type(full),
        "number": smart_number(doc_text) or smart_number(full),
        "date": smart_date(date_value) or smart_date(doc_text) or smart_date(full),
        "amounts": tuple(number(row.get(cols.get(kind))) if cols.get(kind) else None for kind in ("debit", "credit")),
    }


def smart_status(rows, cols, kind):
    if kind in cols and cols.get(kind):
        return cols[kind]
    probe = [smart_identity(row, cols, i) for i, row in enumerate((rows or [])[:50])]
    found = any(item.get(kind) for item in probe)
    return "Авто: из содержимого" if found else "—"


def num_similarity(a, b):
    a, b = norm_doc_num(a), norm_doc_num(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if (a.endswith(b) or b.endswith(a)) and min(len(a), len(b)) >= 3:
        return 0.95
    da = "".join(ch for ch in a if ch.isdigit()).lstrip("0")
    db = "".join(ch for ch in b if ch.isdigit()).lstrip("0")
    if da and da == db:
        return 0.97
    ratio = SequenceMatcher(None, a, b).ratio()
    if len(da) >= 4 and len(db) >= 4 and da[-4:] == db[-4:]:
        ratio = max(ratio, 0.90)
    return ratio


def type_similarity(a, b):
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.88
    return SequenceMatcher(None, a, b).ratio()


def date_similarity(a, b):
    if not a or not b:
        return 0.0
    try:
        distance = abs((datetime.strptime(a, "%Y-%m-%d") - datetime.strptime(b, "%Y-%m-%d")).days)
    except Exception:
        return 0.0
    return 1.0 if distance == 0 else 0.78 if distance == 1 else 0.55 if distance <= 3 else 0.25 if distance <= 7 else 0.0


def amount_similarity(a, b):
    values = []
    for left, right in zip(a["amounts"], b["amounts"]):
        if left is not None and right is not None:
            scale = max(abs(left), abs(right), 1.0)
            values.append(max(0.0, 1.0 - abs(left - right) / scale))
    return sum(values) / len(values) if values else 0.0


def match_score(a, b):
    ns = num_similarity(a["number"], b["number"]) if a["number"] and b["number"] else 0.0
    ts = type_similarity(a["type"], b["type"]) if a["type"] and b["type"] else 0.0
    ds = date_similarity(a["date"], b["date"]) if a["date"] and b["date"] else 0.0
    ams = amount_similarity(a, b)
    parts = []
    if a["number"] and b["number"]: parts.append((0.48, ns))
    if a["type"] and b["type"]: parts.append((0.18, ts))
    if a["date"] and b["date"]: parts.append((0.24, ds))
    if ams: parts.append((0.10, ams))
    if not parts or not (ns >= 0.72 or (ts >= 0.82 and ds >= 0.55) or (ds >= 0.78 and ams >= 0.97)):
        return 0.0
    weight = sum(w for w, _ in parts)
    return sum(w * s for w, s in parts) / weight


def date_neighbors(value):
    if not value:
        return ()
    try:
        base = datetime.strptime(value, "%Y-%m-%d").date()
        return tuple((base + timedelta(days=d)).isoformat() for d in range(-3, 4))
    except Exception:
        return ()


def pair_rows(rows1, rows2, cols1, cols2):
    ids1 = [smart_identity(row, cols1, i) for i, row in enumerate(rows1)]
    ids2 = [smart_identity(row, cols2, i) for i, row in enumerate(rows2)]
    by_date, by_tail, by_type, by_amount = {}, {}, {}, {}
    for i, item in enumerate(ids2):
        if item["date"]: by_date.setdefault(item["date"], []).append(i)
        if item["number"]: by_tail.setdefault(item["number"][-4:], []).append(i)
        if item["type"]: by_type.setdefault(item["type"], []).append(i)
        if any(v is not None for v in item["amounts"]):
            by_amount.setdefault(tuple(round(v, 2) if v is not None else None for v in item["amounts"]), []).append(i)

    free = set(range(len(rows2)))
    pairs = []
    order = sorted(range(len(rows1)), key=lambda i: (bool(ids1[i]["number"]), bool(ids1[i]["date"]), bool(ids1[i]["type"])), reverse=True)
    for i1 in order:
        item = ids1[i1]
        candidates = set()
        for day in date_neighbors(item["date"]): candidates.update(by_date.get(day, ()))
        if item["number"]: candidates.update(by_tail.get(item["number"][-4:], ()))
        if any(v is not None for v in item["amounts"]):
            key = tuple(round(v, 2) if v is not None else None for v in item["amounts"])
            candidates.update(by_amount.get(key, ()))
        if not candidates and item["type"]: candidates.update(by_type.get(item["type"], ())[:160])
        if not candidates and len(rows2) <= 180: candidates.update(free)

        best, best_score = None, 0.0
        for i2 in candidates:
            if i2 in free:
                score = match_score(item, ids2[i2])
                if score > best_score:
                    best, best_score = i2, score
        if best is not None and best_score >= 0.66:
            pairs.append((i1, best, best_score, item, ids2[best]))
            free.remove(best)

    matched1 = {p[0] for p in pairs}
    return pairs, [i for i in range(len(rows1)) if i not in matched1], sorted(free)


def doc_equal(a, b):
    na, nb = smart_number(a), smart_number(b)
    ta, tb = smart_type(a), smart_type(b)
    return bool(na and nb and num_similarity(na, nb) >= 0.84 and (not ta or not tb or type_similarity(ta, tb) >= 0.72)) or equal(a, b)


def compare(rows1, rows2, cols1, cols2, tolerance):
    paired, only1_idx, only2_idx = pair_rows(rows1, rows2, cols1, cols2)
    fields = [(kind, cols1[kind], cols2[kind]) for kind in ("date", "document", "debit", "credit", "balance", "counterparty") if cols1.get(kind) and cols2.get(kind)]
    differences, matches = [], []

    for i1, i2, score, id1, id2 in paired:
        r1, r2, changed = rows1[i1], rows2[i2], []
        for kind, c1, c2 in fields:
            a, b = r1.get(c1), r2.get(c2)
            same = doc_equal(a, b) if kind == "document" else date_key(a) == date_key(b) if kind == "date" else equal(a, b, tolerance)
            if not same:
                na, nb = number(a), number(b)
                changed.append((kind, c1, c2, a, b, nb - na if na is not None and nb is not None else ""))

        key = " | ".join(x for x in (id1["type"], id1["number"], id1["date"]) if x) or f"строка {i1 + 1}"
        if changed:
            for kind, c1, c2, a, b, delta in changed:
                differences.append([key, kind.upper(), c1, c2, a, b, delta, f"РАЗЛИЧИЕ • совпадение {int(score * 100)}%"])
        else:
            matches.append([key, f"Совпадает • {int(score * 100)}%"])

    return differences, [rows1[i].copy() for i in only1_idx], [rows2[i].copy() for i in only2_idx], matches''',
    "smart matching",
)

between(
    "    def update_fields(self):",
    "    def run_compare(self, *_):",
    r'''    def update_fields(self):
        self.fields_grid.clear_widgets()
        if self.rows1 is None and self.rows2 is None:
            self.fields_grid.add_widget(text_label("Поля появятся после загрузки файлов", size=12, color=MUTED, height=36))
            self.fields_grid.add_widget(Label(text="", size_hint_y=None, height=dp(36)))
            return
        for kind, title in (
            ("date", "Дата"), ("document", "Документ"), ("type", "Тип документа"),
            ("debit", "Дебет"), ("credit", "Кредит"), ("balance", "Сальдо"), ("counterparty", "Контрагент"),
        ):
            if kind in ("date", "document"):
                c1, c2 = smart_status(self.rows1 or [], self.cols1, kind), smart_status(self.rows2 or [], self.cols2, kind)
            elif kind == "type":
                c1 = "Авто: из содержимого" if any(smart_identity(row, self.cols1)["type"] for row in (self.rows1 or [])[:50]) else "—"
                c2 = "Авто: из содержимого" if any(smart_identity(row, self.cols2)["type"] for row in (self.rows2 or [])[:50]) else "—"
            else:
                c1, c2 = self.cols1.get(kind) or "—", self.cols2.get(kind) or "—"
            self.fields_grid.add_widget(self.field_label(f"{title} • Акт 1", c1, primary=True))
            self.fields_grid.add_widget(self.field_label(f"{title} • Акт 2", c2))''',
    "smart fields",
)

once(
'''        if not self.cols1.get("document") and not self.cols1.get("date"):
            self.error("В акте 1 не найдено поле «Документ» или «Дата».")
            return
        if not self.cols2.get("document") and not self.cols2.get("date"):
            self.error("В акте 2 не найдено поле «Документ» или «Дата».")
            return
''',
'''        # Тип, номер и дата документа могут быть определены из текста любой колонки строки.
''',
"remove strict columns",
)
once(
    'brand_text.add_widget(text_label("Сверка актов без лишних действий", size=12, color=MUTED, height=24))',
    'brand_text.add_widget(text_label("Умное сопоставление актов и документов", size=12, color=MUTED, height=24))',
    "subtitle",
)
once(
    'actions.add_widget(text_label("Поддерживаются XLS, XLSX и CSV. Выгрузки из 1С обрабатываются автоматически.", size=11, color=MUTED, height=38, valign="top"))',
    'actions.add_widget(text_label("XLS / XLSX / CSV • тип, номер и дата распознаются из содержимого строки.", size=11, color=MUTED, height=38, valign="top"))',
    "footer",
)
once(
'''            self.result_label.text = (
                f"[b]Расхождения:[/b] {diff_rows}\\n"''',
'''            self.result_label.text = (
                f"[b]Умное сопоставление включено[/b]\\n"
                f"[b]Расхождения:[/b] {diff_rows}\\n"''',
    "result status",
)

path.write_text(text, encoding="utf-8")
print("Smart matching patch applied: v1.3.0")
