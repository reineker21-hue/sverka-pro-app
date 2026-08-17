from pathlib import Path

path = Path('main.py')
text = path.read_text(encoding='utf-8')

if '__version__ = "1.5.0"' not in text:
    raise RuntimeError('Stable runtime должен применяться непосредственно к проверенной версии 1.5.0')
text = text.replace('__version__ = "1.5.0"', '__version__ = "1.12.0"', 1)

# Keep the Excel/Microsoft 365 visual refresh, but do not bring back any of the
# post-1.5 threading / crash-diagnostic overrides.
text = text.replace(
    '''BG = (0.955, 0.965, 0.985, 1)\nSURFACE = (1, 1, 1, 1)\nSURFACE_SOFT = (0.965, 0.975, 0.995, 1)\nTEXT = (0.075, 0.095, 0.14, 1)\nMUTED = (0.39, 0.43, 0.51, 1)\nBORDER = (0.865, 0.89, 0.94, 1)\nPRIMARY = (0.16, 0.38, 0.90, 1)\nPRIMARY_PRESSED = (0.11, 0.29, 0.72, 1)\nSUCCESS = (0.07, 0.62, 0.34, 1)\nSUCCESS_PRESSED = (0.05, 0.48, 0.27, 1)\nDANGER = (0.91, 0.28, 0.25, 1)''',
    '''BG = (0.965, 0.965, 0.965, 1)\nSURFACE = (1, 1, 1, 1)\nSURFACE_SOFT = (0.975, 0.975, 0.975, 1)\nTEXT = (0.125, 0.125, 0.125, 1)\nMUTED = (0.38, 0.38, 0.38, 1)\nBORDER = (0.82, 0.82, 0.82, 1)\nPRIMARY = (0.063, 0.486, 0.255, 1)\nPRIMARY_PRESSED = (0.047, 0.376, 0.196, 1)\nSUCCESS = (0.063, 0.486, 0.255, 1)\nSUCCESS_PRESSED = (0.047, 0.376, 0.196, 1)\nDANGER = (0.78, 0.16, 0.16, 1)''',
    1,
)
for old, new in (
    ('def __init__(self, radius=18, **kwargs):', 'def __init__(self, radius=10, **kwargs):'),
    ('self._radius = dp(15)', 'self._radius = dp(6)'),
    ('height=dp(52),', 'height=dp(48),'),
    ('header = Card(radius=22)', 'header = Card(radius=10)'),
    ('spacing=dp(14), padding=[dp(14), dp(14), dp(14), dp(24)]', 'spacing=dp(10), padding=[dp(12), dp(12), dp(12), dp(22)]'),
    ('ModernButton("СРАВНИТЬ АКТЫ", tone="success")', 'ModernButton("Сравнить акты", tone="success")'),
    ('ModernButton("СОХРАНИТЬ EXCEL-ОТЧЕТ", tone="neutral")', 'ModernButton("Сохранить Excel-отчёт", tone="neutral")'),
    ('ModernButton("ПРОТОКОЛ РАСХОЖДЕНИЙ • ФНС", tone="primary")', 'ModernButton("Протокол расхождений • ФНС", tone="primary")'),
    ('self.file1_button = ModernButton("Выбрать АКТ 1")', 'self.file1_button = ModernButton("Выбрать акт 1")'),
    ('self.file2_button = ModernButton("Выбрать АКТ 2")', 'self.file2_button = ModernButton("Выбрать акт 2")'),
    ('self.file1_label = text_label("Файл 1 не выбран", size=12, color=MUTED, height=26)', 'self.file1_label = text_label("Акт 1: файл не выбран", size=12, color=MUTED, height=32)'),
    ('self.file2_label = text_label("Файл 2 не выбран", size=12, color=MUTED, height=26)', 'self.file2_label = text_label("Акт 2: файл не выбран", size=12, color=MUTED, height=32)'),
    ('text_label("Распознанные поля", size=17, bold=True, height=30)', 'text_label("Распознанные данные", size=17, bold=True, height=30)'),
):
    text = text.replace(old, new, 1)

OVERRIDES = r'''
# ===== Stable runtime 1.12: render-safe comparison result =====
from reconcile_core import (
    compare_rows as _core_compare_rows,
    totals_rows as _core_totals_rows,
    total_diffs as _core_total_diffs,
    find_duplicates_rows as _core_find_duplicates_rows,
)


def read_xlsx(path):
    # Prefer the lightweight ZIP/XML reader. This also handles the malformed
    # sharedStrings reference seen in the real 1C test workbook.
    try:
        return read_xlsx_fallback(path)
    except Exception as xml_error:
        try:
            return read_xlsx_openpyxl(path)
        except Exception as openpyxl_error:
            raise ValueError(
                "Не удалось прочитать XLSX. "
                f"ZIP/XML: {xml_error}. Резервный режим: {openpyxl_error}"
            )


def compare(rows1, rows2, cols1, cols2, tolerance):
    return _core_compare_rows(rows1, rows2, cols1, cols2, tolerance)[0]


def totals(rows, cols):
    return _core_totals_rows(rows, cols)


def reconcile_total_diffs(t1, t2):
    return _core_total_diffs(t1, t2)


def find_duplicates(rows, cols, side):
    return _core_find_duplicates_rows(rows, cols, side)


def _stable_uri_display_name(uri):
    resolver = get_android_activity().getContentResolver()
    cursor = None
    try:
        OpenableColumns = autoclass("android.provider.OpenableColumns")
        cursor = resolver.query(uri, None, None, None, None)
        if cursor and cursor.moveToFirst():
            idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if idx >= 0:
                name = str(cursor.getString(idx) or "").strip()
                if name:
                    return Path(name).name
    except Exception:
        pass
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
    return "выбранный файл"


def _stable_load_file(self, uri, target):
    temp_path = None
    try:
        filename = _stable_uri_display_name(uri)
        temp_path = uri_to_tempfile(uri)
        headers, rows, sheet = read_table(temp_path)
        cols = {key: detect_column(headers, key) for key in ALIASES}
        if target == 1:
            self.rows1, self.headers1, self.cols1 = rows, headers, cols
            self.file1_name = filename
            self.file1_label.text = f"Акт 1: {filename}"
            self.file1_label.color = PRIMARY
        else:
            self.rows2, self.headers2, self.cols2 = rows, headers, cols
            self.file2_name = filename
            self.file2_label.text = f"Акт 2: {filename}"
            self.file2_label.color = PRIMARY
        self.last_result = None
        self.save_button.disabled = True
        if hasattr(self, "fns_button"):
            self.fns_button.disabled = True
        self.update_fields()
    except Exception as exc:
        self.error(str(exc))
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass


def _stable_run_compare(self, *_):
    # This deliberately follows the proven 1.5 execution model: one synchronous
    # Python callback, no worker Thread, no Clock trampoline and no faulthandler.
    if self.rows1 is None or self.rows2 is None:
        self.error("Сначала выберите оба акта сверки.")
        return
    if self.compare_button.disabled:
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
    # Keep this status deliberately short and without markup. On a few Android
    # GPU/font combinations the previous long marked-up result was the only
    # native operation left after the pure-Python comparison had completed.
    self.result_label.markup = False
    self.result_label.color = MUTED
    self.result_label.text = "Выполняется сравнение..."

    try:
        result, prep1, prep2 = _core_compare_rows(
            self.rows1, self.rows2, self.cols1, self.cols2, tolerance
        )
        self.last_result = result
        differences, only1, only2, matches = result
        opening_diff = (
            prep1["opening"] - prep2["opening"]
            if prep1.get("opening") is not None and prep2.get("opening") is not None
            else None
        )
        ending_diff = (
            prep1["ending"] - prep2["ending"]
            if prep1.get("ending") is not None and prep2.get("ending") is not None
            else None
        )
        accrual_diff = prep1["accrual"] - prep2["accrual"]
        settlement_diff = prep1["settlement"] - prep2["settlement"]

        # Use a fixed-size, plain Label. Avoiding markup, the bullet glyph and
        # a dynamic height prevents the result texture/layout rebuild that was
        # not covered by the old Android test and could terminate the process
        # after the comparison itself had already succeeded.
        result_text = "\n".join((
            "Сверка завершена",
            f"Требуют проверки: {len(only1) + len(only2)}",
            f"Только в акте 1: {len(only1)}; в акте 2: {len(only2)}",
            f"Совпадений: {len(matches)}",
            f"Начальное сальдо, разница: {money(opening_diff)} руб.",
            f"Начисления, разница: {money(accrual_diff)} руб.",
            f"Оплаты, разница: {money(settlement_diff)} руб.",
            f"Конечное сальдо, разница: {money(ending_diff)} руб.",
        ))
        self.result_label.markup = False
        self.result_label.color = TEXT
        self.result_label.text = result_text
        self.save_button.disabled = False
        if hasattr(self, "fns_button"):
            self.fns_button.disabled = False
    except Exception as exc:
        self.result_label.color = DANGER
        self.result_label.text = "Сравнение не выполнено."
        self.error(f"{type(exc).__name__}: {exc}")
    finally:
        self.compare_button.disabled = False


def _stable_on_save_uri(self, uri):
    try:
        differences, only1, only2, matches = self.last_result
        fd, temp_path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            create_report(
                temp_path, self.rows1, self.rows2, self.cols1, self.cols2,
                differences, only1, only2, matches,
                getattr(self, "file1_name", "Акт 1"),
                getattr(self, "file2_name", "Акт 2"),
            )
            copy_to_uri(temp_path, uri)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        self.popup("Готово", "Excel-отчёт успешно сохранён.", success=True)
    except Exception as exc:
        self.error(str(exc))


MainScreen.load_file = _stable_load_file
MainScreen.run_compare = _stable_run_compare
MainScreen.on_save_uri = _stable_on_save_uri
# ===== /Stable runtime 1.12 =====
'''

marker = 'if __name__ == "__main__":'
if marker not in text:
    raise RuntimeError('Не найден конец main.py')
text = text.replace(marker, OVERRIDES + '\n\n' + marker, 1)

text = text.replace(
    'XLS / XLSX / CSV • автосверка • протокол расхождений по структуре ФНС в Excel.',
    'Excel-стиль • XLS / XLSX / CSV • стабильная сверка • протокол ФНС.',
    1,
)

path.write_text(text, encoding='utf-8')
print('Stable runtime 1.12 applied with render-safe result')
