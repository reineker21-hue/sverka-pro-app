import os
import re
import tempfile
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from jnius import autoclass

__version__ = "1.0.1"
APP_NAME = "Сверка PRO"

BG = (0.95, 0.97, 0.99, 1)
WHITE = (1, 1, 1, 1)
TEXT = (0.09, 0.13, 0.20, 1)
MUTED = (0.40, 0.45, 0.52, 1)
BLUE = (0.145, 0.388, 0.922, 1)
GREEN = (0.086, 0.639, 0.290, 1)


def ntext(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower().replace("ё", "е"))


def nheader(value):
    return re.sub(r"[^a-zа-я0-9]+", "", ntext(value))


def number(value):
    if value is None:
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


def date_key(value):
    if value is None or str(value).strip() == "":
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$", text)
    if m:
        d, mo, y = m.groups()
        if len(y) == 2:
            y = "20" + y
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return ntext(value)


def equal(a, b, tolerance=0.01):
    if a is None and b is None:
        return True
    if ntext(a) == ntext(b):
        return True
    na, nb = number(a), number(b)
    return na is not None and nb is not None and abs(na - nb) <= tolerance


ALIASES = {
    "date": ["дата", "дата операции", "дата документа", "датадокумента", "date"],
    "document": [
        "документ", "номер документа", "номердокумента", "№ документа", "номер",
        "док", "основание", "счет фактура", "счет-фактура", "накладная", "акт",
    ],
    "debit": ["дебет", "дебет оборот", "оборот дебет", "дебетовый оборот", "приход"],
    "credit": ["кредит", "кредит оборот", "оборот кредит", "кредитовый оборот", "расход"],
    "balance": ["сальдо", "остаток", "баланс", "конечное сальдо", "конечный остаток"],
    "counterparty": ["контрагент", "поставщик", "покупатель", "организация", "наименование", "партнер"],
}


def detect_column(headers, kind):
    best = None
    score_best = 0
    aliases = [nheader(x) for x in ALIASES[kind]]
    for h in headers:
        nh = nheader(h)
        score = 0
        for alias in aliases:
            if nh == alias:
                score = max(score, 100)
            elif alias and alias in nh:
                score = max(score, 70)
            elif nh and nh in alias:
                score = max(score, 50)
        if score > score_best:
            score_best = score
            best = h
    return best


def read_csv(path):
    import csv

    last = None
    for enc in ("utf-8-sig", "cp1251", "utf-8"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
                except Exception:
                    dialect = csv.excel
                rows = list(csv.reader(f, dialect))
            if not rows:
                raise ValueError("CSV-файл пуст.")
            headers, used = [], {}
            for i, h in enumerate(rows[0]):
                name = h.strip() or f"Колонка {i + 1}"
                used[name] = used.get(name, 0) + 1
                if used[name] > 1:
                    name = f"{name}_{used[name]}"
                headers.append(name)
            data = []
            for row in rows[1:]:
                if any(str(x).strip() for x in row):
                    data.append({headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))})
            return headers, data, "CSV"
        except Exception as exc:
            last = exc
    raise last or ValueError("Не удалось прочитать CSV.")


def read_xlsx(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            try:
                raw_headers = next(rows)
            except StopIteration:
                continue
            headers, used = [], {}
            for i, h in enumerate(raw_headers or []):
                name = str(h).strip() if h is not None else ""
                name = name or f"Колонка {i + 1}"
                used[name] = used.get(name, 0) + 1
                if used[name] > 1:
                    name = f"{name}_{used[name]}"
                headers.append(name)
            data = []
            for raw in rows:
                if raw and any(x is not None and str(x).strip() for x in raw):
                    data.append({headers[i]: raw[i] if i < len(raw) else None for i in range(len(headers))})
            if data:
                return headers, data, ws.title
    finally:
        wb.close()
    raise ValueError("В XLSX не найден непустой лист с таблицей.")


def read_table(path):
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        return read_csv(path)
    if ext == ".xlsx":
        return read_xlsx(path)
    raise ValueError("Поддерживаются XLSX и CSV. Файл XLS сначала сохраните как XLSX.")


def make_key(row, cols, occurrence):
    doc = ntext(row.get(cols.get("document"))) if cols.get("document") else ""
    dt = date_key(row.get(cols.get("date"))) if cols.get("date") else ""
    if doc or dt:
        return f"{doc}|{dt}"
    debit = number(row.get(cols.get("debit"))) if cols.get("debit") else None
    credit = number(row.get(cols.get("credit"))) if cols.get("credit") else None
    return f"amount|{debit}|{credit}|{occurrence}"


def build_index(rows, cols):
    result, count = {}, {}
    for i, row in enumerate(rows):
        base = make_key(row, cols, i)
        n = count.get(base, 0)
        count[base] = n + 1
        result[f"{base}||{n}"] = i
    return result


def compare(rows1, rows2, cols1, cols2, tolerance):
    idx1, idx2 = build_index(rows1, cols1), build_index(rows2, cols2)
    pairs = []
    for kind in ("date", "document", "debit", "credit", "balance", "counterparty"):
        c1, c2 = cols1.get(kind), cols2.get(kind)
        if c1 and c2:
            pairs.append((kind, c1, c2))

    differences, only1, only2, matches = [], [], [], []
    for key in dict.fromkeys(list(idx1) + list(idx2)):
        if key not in idx2:
            only1.append(rows1[idx1[key]].copy())
            continue
        if key not in idx1:
            only2.append(rows2[idx2[key]].copy())
            continue
        r1, r2 = rows1[idx1[key]], rows2[idx2[key]]
        changed = []
        for kind, c1, c2 in pairs:
            a, b = r1.get(c1), r2.get(c2)
            if not equal(a, b, tolerance):
                na, nb = number(a), number(b)
                delta = nb - na if na is not None and nb is not None else ""
                changed.append((kind, c1, c2, a, b, delta))
        if changed:
            for kind, c1, c2, a, b, delta in changed:
                differences.append([key, kind.upper(), c1, c2, a, b, delta, "РАЗЛИЧИЕ"])
        else:
            matches.append([key, "Совпадает"])
    return differences, only1, only2, matches


def totals(rows, cols):
    out = {}
    for kind in ("debit", "credit", "balance"):
        col = cols.get(kind)
        if not col:
            out[kind] = None
            continue
        values = [number(r.get(col)) for r in rows]
        values = [x for x in values if x is not None]
        out[kind] = sum(values) if values else 0.0
    return out


def money(value):
    if value is None:
        return "—"
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def autosize(ws):
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        max_len = max((len(str(cell.value or "")) for cell in col), default=0)
        ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 42)


def create_report(output, rows1, rows2, cols1, cols2, differences, only1, only2, matches, name1, name2):
    t1, t2 = totals(rows1, cols1), totals(rows2, cols2)

    def diff(kind):
        return t2[kind] - t1[kind] if t1[kind] is not None and t2[kind] is not None else None

    wb = Workbook()
    ws = wb.active
    ws.title = "ИТОГ"
    summary = [
        ["СВЕРКА PRO — ИТОГ", ""], ["Акт 1", name1], ["Акт 2", name2],
        ["Строк в акте 1", len(rows1)], ["Строк в акте 2", len(rows2)],
        ["Строк с расхождениями", len(set(x[0] for x in differences))],
        ["Всего отдельных расхождений", len(differences)], ["Только в акте 1", len(only1)],
        ["Только в акте 2", len(only2)], ["Совпадения", len(matches)],
        ["ИТОГО ДЕБЕТ — акт 1", t1["debit"]], ["ИТОГО ДЕБЕТ — акт 2", t2["debit"]],
        ["РАЗНИЦА ДЕБЕТ", diff("debit")], ["ИТОГО КРЕДИТ — акт 1", t1["credit"]],
        ["ИТОГО КРЕДИТ — акт 2", t2["credit"]], ["РАЗНИЦА КРЕДИТ", diff("credit")],
        ["САЛЬДО — акт 1", t1["balance"]], ["САЛЬДО — акт 2", t2["balance"]],
        ["РАЗНИЦА САЛЬДО", diff("balance")],
    ]
    for row in summary:
        ws.append(row)

    wsd = wb.create_sheet("РАЗЛИЧИЯ")
    wsd.append(["Ключ", "Поле", "Колонка акта 1", "Колонка акта 2", "Акт 1", "Акт 2", "Разница", "Статус"])
    for row in differences:
        wsd.append(row)

    def write_rows(title, data):
        sheet = wb.create_sheet(title)
        if not data:
            sheet.append(["Нет данных"])
            return
        headers = list(data[0].keys())
        sheet.append(headers)
        for row in data:
            sheet.append([row.get(h, "") for h in headers])

    write_rows("ТОЛЬКО АКТ 1", only1)
    write_rows("ТОЛЬКО АКТ 2", only2)
    wsm = wb.create_sheet("СОВПАДЕНИЯ")
    wsm.append(["Ключ", "Статус"])
    for row in matches:
        wsm.append(row)

    for sheet in wb.worksheets:
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            cell.fill = PatternFill("solid", fgColor="17365D")
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        autosize(sheet)
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, float):
                    cell.number_format = "#,##0.00"

    for row in range(2, wsd.max_row + 1):
        wsd.cell(row, 5).fill = PatternFill("solid", fgColor="FECACA")
        wsd.cell(row, 6).fill = PatternFill("solid", fgColor="DCFCE7")
        wsd.cell(row, 7).fill = PatternFill("solid", fgColor="FEF3C7")
    wb.save(output)


def get_android_activity():
    return autoclass("org.kivy.android.PythonActivity").mActivity


def open_document(callback):
    Intent = autoclass("android.content.Intent")
    intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
    intent.addCategory(Intent.CATEGORY_OPENABLE)
    intent.setType("*/*")
    intent.putExtra(Intent.EXTRA_MIME_TYPES, [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
        "text/comma-separated-values",
    ])
    get_android_activity().startActivityForResult(intent, 7001)
    App.get_running_app().pending_open_callback = callback


def create_document(callback):
    Intent = autoclass("android.content.Intent")
    intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
    intent.addCategory(Intent.CATEGORY_OPENABLE)
    intent.setType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    intent.putExtra(Intent.EXTRA_TITLE, "Отчет_сравнения_актов.xlsx")
    get_android_activity().startActivityForResult(intent, 7002)
    App.get_running_app().pending_save_callback = callback


def uri_suffix(uri):
    resolver = get_android_activity().getContentResolver()
    mime = str(resolver.getType(uri) or "").lower()
    if "spreadsheetml" in mime or "xlsx" in mime:
        return ".xlsx"
    if "csv" in mime:
        return ".csv"
    try:
        OpenableColumns = autoclass("android.provider.OpenableColumns")
        cursor = resolver.query(uri, None, None, None, None)
        if cursor and cursor.moveToFirst():
            idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if idx >= 0:
                ext = Path(str(cursor.getString(idx))).suffix.lower()
                if ext in (".xlsx", ".csv"):
                    return ext
        if cursor:
            cursor.close()
    except Exception:
        pass
    return ".xlsx"


def uri_to_tempfile(uri):
    resolver = get_android_activity().getContentResolver()
    stream = resolver.openInputStream(uri)
    fd, path = tempfile.mkstemp(suffix=uri_suffix(uri))
    os.close(fd)
    try:
        with open(path, "wb") as out:
            buf = bytearray(64 * 1024)
            while True:
                count = stream.read(buf)
                if count <= 0:
                    break
                out.write(bytes(buf[:count]))
    finally:
        stream.close()
    return path


def copy_to_uri(local_path, uri):
    resolver = get_android_activity().getContentResolver()
    stream = resolver.openOutputStream(uri)
    try:
        with open(local_path, "rb") as src:
            while True:
                chunk = src.read(64 * 1024)
                if not chunk:
                    break
                stream.write(chunk)
        stream.flush()
    finally:
        stream.close()


class MainScreen(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(10), padding=dp(14), **kwargs)
        self.rows1 = self.rows2 = None
        self.headers1, self.headers2 = [], []
        self.cols1, self.cols2 = {}, {}
        self.last_result = None
        self.build_ui()

    def title(self, text, size=22):
        label = Label(text=text, color=TEXT, font_size=sp(size), bold=True, size_hint_y=None, height=dp(42), halign="left", valign="middle")
        label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        return label

    def make_button(self, text, callback, color=BLUE):
        button = Button(text=text, size_hint_y=None, height=dp(48), background_normal="", background_color=color, color=WHITE, bold=True)
        button.bind(on_release=callback)
        return button

    def build_ui(self):
        scroll = ScrollView(do_scroll_x=False)
        root = BoxLayout(orientation="vertical", spacing=dp(12), size_hint_y=None)
        root.bind(minimum_height=root.setter("height"))
        root.add_widget(self.title(APP_NAME))
        root.add_widget(Label(text="Сравнение актов сверки прямо на Android", color=MUTED, font_size=sp(13), size_hint_y=None, height=dp(30)))
        root.add_widget(self.make_button("📄  Выбрать АКТ 1", self.choose1))
        self.file1_label = Label(text="Файл 1 не выбран", color=MUTED, size_hint_y=None, height=dp(28))
        root.add_widget(self.file1_label)
        root.add_widget(self.make_button("📄  Выбрать АКТ 2", self.choose2))
        self.file2_label = Label(text="Файл 2 не выбран", color=MUTED, size_hint_y=None, height=dp(28))
        root.add_widget(self.file2_label)
        root.add_widget(self.title("Распознанные поля", 17))
        self.fields_grid = GridLayout(cols=2, spacing=dp(6), size_hint_y=None)
        self.fields_grid.bind(minimum_height=self.fields_grid.setter("height"))
        root.add_widget(self.fields_grid)
        tol_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        tol_row.add_widget(Label(text="Допуск, руб.:", color=TEXT, size_hint_x=0.55))
        self.tolerance = TextInput(text="0.01", multiline=False, input_filter="float", size_hint_x=0.45)
        tol_row.add_widget(self.tolerance)
        root.add_widget(tol_row)
        root.add_widget(self.title("Результат", 17))
        self.result_label = Label(text="Выберите два акта и нажмите «Сравнить».", color=MUTED, font_size=sp(13), size_hint_y=None, height=dp(125), halign="left", valign="top")
        self.result_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        root.add_widget(self.result_label)
        root.add_widget(self.make_button("🔍  СРАВНИТЬ АКТЫ", self.run_compare, GREEN))
        self.save_button = self.make_button("💾  СОХРАНИТЬ EXCEL-ОТЧЕТ", self.save_report)
        self.save_button.disabled = True
        root.add_widget(self.save_button)
        root.add_widget(Label(text="Поддерживаются XLSX и CSV.", color=MUTED, font_size=sp(11), size_hint_y=None, height=dp(40)))
        scroll.add_widget(root)
        self.add_widget(scroll)

    def choose1(self, *_):
        open_document(self.open1)

    def choose2(self, *_):
        open_document(self.open2)

    def load_file(self, uri, target):
        try:
            path = uri_to_tempfile(uri)
            headers, rows, _ = read_table(path)
            cols = {k: detect_column(headers, k) for k in ALIASES}
            if target == 1:
                self.rows1, self.headers1, self.cols1 = rows, headers, cols
                self.file1_label.text = f"✓ АКТ 1: {len(rows)} строк"
            else:
                self.rows2, self.headers2, self.cols2 = rows, headers, cols
                self.file2_label.text = f"✓ АКТ 2: {len(rows)} строк"
            self.update_fields()
        except Exception as exc:
            self.error(str(exc))

    def open1(self, uri):
        self.load_file(uri, 1)

    def open2(self, uri):
        self.load_file(uri, 2)

    def update_fields(self):
        self.fields_grid.clear_widgets()
        if self.rows1 is None and self.rows2 is None:
            return
        for kind, title in (("date", "Дата"), ("document", "Документ"), ("debit", "Дебет"), ("credit", "Кредит"), ("balance", "Сальдо"), ("counterparty", "Контрагент")):
            c1, c2 = self.cols1.get(kind) or "—", self.cols2.get(kind) or "—"
            self.fields_grid.add_widget(Label(text=f"{title}\n[Акт 1] {c1}", color=TEXT, size_hint_y=None, height=dp(52), halign="left", valign="middle"))
            self.fields_grid.add_widget(Label(text=f"[Акт 2] {c2}", color=MUTED, size_hint_y=None, height=dp(52), halign="left", valign="middle"))

    def run_compare(self, *_):
        if self.rows1 is None or self.rows2 is None:
            self.error("Сначала выберите оба акта сверки.")
            return
        if not self.cols1.get("document") and not self.cols1.get("date"):
            self.error("В акте 1 не найдено поле Документ или Дата.")
            return
        if not self.cols2.get("document") and not self.cols2.get("date"):
            self.error("В акте 2 не найдено поле Документ или Дата.")
            return
        try:
            tolerance = float(self.tolerance.text.replace(",", "."))
            result = compare(self.rows1, self.rows2, self.cols1, self.cols2, tolerance)
            self.last_result = result
            self.save_button.disabled = False
            differences, only1, only2, matches = result
            t1, t2 = totals(self.rows1, self.cols1), totals(self.rows2, self.cols2)
            debit = t2["debit"] - t1["debit"] if t1["debit"] is not None and t2["debit"] is not None else None
            credit = t2["credit"] - t1["credit"] if t1["credit"] is not None and t2["credit"] is not None else None
            self.result_label.text = (
                f"[b]РАСХОЖДЕНИЯ:[/b] {len(set(x[0] for x in differences))}\n"
                f"Отдельных отличий: {len(differences)}\nТолько в акте 1: {len(only1)}\n"
                f"Только в акте 2: {len(only2)}\nСовпадений: {len(matches)}\n\n"
                f"Разница ДЕБЕТ: {money(debit)} руб.\nРазница КРЕДИТ: {money(credit)} руб."
            )
            self.result_label.markup = True
        except Exception as exc:
            self.error(str(exc))

    def save_report(self, *_):
        if not self.last_result:
            self.error("Сначала выполните сравнение.")
            return
        create_document(self.on_save_uri)

    def on_save_uri(self, uri):
        try:
            differences, only1, only2, matches = self.last_result
            fd, path = tempfile.mkstemp(suffix=".xlsx")
            os.close(fd)
            try:
                create_report(path, self.rows1, self.rows2, self.cols1, self.cols2, differences, only1, only2, matches, "Акт 1", "Акт 2")
                copy_to_uri(path, uri)
            finally:
                if os.path.exists(path):
                    os.unlink(path)
            self.popup("Готово", "Excel-отчет сохранен в выбранное вами место.")
        except Exception as exc:
            self.error(str(exc))

    def error(self, text):
        self.popup("Ошибка", text)

    def popup(self, title, message):
        box = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        label = Label(text=message, color=TEXT, halign="left", valign="top")
        label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        box.add_widget(label)
        btn = Button(text="OK", size_hint_y=None, height=dp(44))
        box.add_widget(btn)
        pop = Popup(title=title, content=box, size_hint=(0.88, 0.42), auto_dismiss=False)
        btn.bind(on_release=pop.dismiss)
        pop.open()


class AndroidApp(App):
    def build(self):
        Window.clearcolor = BG
        self.pending_open_callback = None
        self.pending_save_callback = None
        from android import activity
        self.android_activity = activity
        activity.bind(on_activity_result=self.on_activity_result)
        return MainScreen()

    def on_stop(self):
        try:
            self.android_activity.unbind(on_activity_result=self.on_activity_result)
        except Exception:
            pass

    def on_activity_result(self, request_code, result_code, intent):
        if result_code != -1 or intent is None:
            return
        uri = intent.getData()
        if uri is None:
            return
        if request_code == 7001 and self.pending_open_callback:
            cb = self.pending_open_callback
            self.pending_open_callback = None
            Clock.schedule_once(lambda dt: cb(uri), 0)
        elif request_code == 7002 and self.pending_save_callback:
            cb = self.pending_save_callback
            self.pending_save_callback = None
            Clock.schedule_once(lambda dt: cb(uri), 0)


if __name__ == "__main__":
    AndroidApp().run()
