from pathlib import Path

path = Path("main.py")
text = path.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    if old not in text:
        raise RuntimeError(f"Не найден участок для патча: {label}")
    text = text.replace(old, new, 1)


replace_once('__version__ = "1.1.0"', '__version__ = "1.2.0"', "версия")

old_read_table = '''def read_table(path):
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        return read_csv(path)
    if ext == ".xlsx":
        return read_xlsx(path)
    raise ValueError("Поддерживаются XLSX и CSV. Файл XLS сначала сохраните как XLSX.")
'''

new_read_table = '''def read_xls(path):
    """Read classic Excel 97-2003 .xls files, including common 1C exports."""
    import xlrd

    book = xlrd.open_workbook(path, on_demand=True)
    try:
        for sheet in book.sheets():
            matrix = []
            for row_idx in range(sheet.nrows):
                row = []
                for col_idx in range(sheet.ncols):
                    cell = sheet.cell(row_idx, col_idx)
                    value = cell.value
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        try:
                            dt = xlrd.xldate.xldate_as_datetime(value, book.datemode)
                            value = dt.date() if (dt.hour, dt.minute, dt.second, dt.microsecond) == (0, 0, 0, 0) else dt
                        except Exception:
                            pass
                    elif cell.ctype == xlrd.XL_CELL_NUMBER:
                        try:
                            num = float(value)
                            value = int(num) if num.is_integer() else num
                        except Exception:
                            pass
                    row.append(value)
                matrix.append(row)

            if matrix and any(any(x is not None and str(x).strip() for x in row) for row in matrix):
                return matrix_to_table(matrix, sheet.name)
    finally:
        try:
            book.release_resources()
        except Exception:
            pass
    raise ValueError("В XLS не найден непустой лист с таблицей.")


def read_table(path):
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        return read_csv(path)
    if ext == ".xls":
        return read_xls(path)
    if ext == ".xlsx":
        return read_xlsx(path)
    raise ValueError("Поддерживаются XLSX, XLS и CSV.")
'''
replace_once(old_read_table, new_read_table, "поддержка XLS")

replace_once(
'''        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",''',
'''        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "text/csv",''',
"XLS MIME",
)

replace_once(
'''    if "spreadsheetml" in mime or "xlsx" in mime:
        return ".xlsx"
    if "csv" in mime:
        return ".csv"''',
'''    if "spreadsheetml" in mime or "xlsx" in mime:
        return ".xlsx"
    if "ms-excel" in mime:
        return ".xls"
    if "csv" in mime:
        return ".csv"''',
"определение MIME XLS",
)

replace_once(
'''                if ext in (".xlsx", ".csv"):
                    return ext''',
'''                if ext in (".xlsx", ".xls", ".csv"):
                    return ext''',
"расширение XLS",
)

replace_once(
'files.add_widget(text_label("Выберите два акта в XLSX или CSV", size=12, color=MUTED, height=24))',
'files.add_widget(text_label("Выберите два акта в XLSX, XLS или CSV", size=12, color=MUTED, height=24))',
"подпись форматов",
)

replace_once(
'actions.add_widget(text_label("Поддерживаются XLSX и CSV. Нестандартные XLSX из 1С читаются в резервном режиме.", size=11, color=MUTED, height=38, valign="top"))',
'actions.add_widget(text_label("Поддерживаются XLSX, XLS и CSV. Выгрузки из 1С обрабатываются автоматически.", size=11, color=MUTED, height=38, valign="top"))',
"нижняя подпись форматов",
)

path.write_text(text, encoding="utf-8")
print("Prebuild patch applied: XLS support + UI labels + version 1.2.0")
