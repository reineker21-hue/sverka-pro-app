from pathlib import Path

path = Path("main.py")
text = path.read_text(encoding="utf-8")


def once(old, new, label, required=True):
    global text
    if old not in text:
        if required:
            raise RuntimeError(f"Не найден участок: {label}")
        return False
    text = text.replace(old, new, 1)
    return True


once('__version__ = "1.6.0"', '__version__ = "1.7.0"', "версия")
once(
    "from datetime import datetime, timedelta\nfrom difflib import SequenceMatcher",
    "from datetime import datetime, timedelta\nfrom difflib import SequenceMatcher\nfrom threading import Thread\nimport traceback",
    "Thread + traceback",
)

# Excel / Microsoft 365 inspired light palette.
once(
    '''BG = (0.955, 0.965, 0.985, 1)\nSURFACE = (1, 1, 1, 1)\nSURFACE_SOFT = (0.965, 0.975, 0.995, 1)\nTEXT = (0.075, 0.095, 0.14, 1)\nMUTED = (0.39, 0.43, 0.51, 1)\nBORDER = (0.865, 0.89, 0.94, 1)\nPRIMARY = (0.16, 0.38, 0.90, 1)\nPRIMARY_PRESSED = (0.11, 0.29, 0.72, 1)\nSUCCESS = (0.07, 0.62, 0.34, 1)\nSUCCESS_PRESSED = (0.05, 0.48, 0.27, 1)\nDANGER = (0.91, 0.28, 0.25, 1)''',
    '''BG = (0.965, 0.965, 0.965, 1)\nSURFACE = (1, 1, 1, 1)\nSURFACE_SOFT = (0.975, 0.975, 0.975, 1)\nTEXT = (0.125, 0.125, 0.125, 1)\nMUTED = (0.38, 0.38, 0.38, 1)\nBORDER = (0.82, 0.82, 0.82, 1)\nPRIMARY = (0.063, 0.486, 0.255, 1)\nPRIMARY_PRESSED = (0.047, 0.376, 0.196, 1)\nSUCCESS = (0.063, 0.486, 0.255, 1)\nSUCCESS_PRESSED = (0.047, 0.376, 0.196, 1)\nDANGER = (0.78, 0.16, 0.16, 1)''',
    "Excel palette",
)

once('def __init__(self, radius=18, **kwargs):', 'def __init__(self, radius=10, **kwargs):', "card radius", required=False)
once('self._radius = dp(15)', 'self._radius = dp(6)', "button radius", required=False)
once('height=dp(52),', 'height=dp(48),', "button height", required=False)
once('header = Card(radius=22)', 'header = Card(radius=10)', "header radius", required=False)
once('spacing=dp(14), padding=[dp(14), dp(14), dp(14), dp(24)]', 'spacing=dp(10), padding=[dp(12), dp(12), dp(12), dp(22)]', "layout spacing", required=False)
once('ModernButton("СРАВНИТЬ АКТЫ", tone="success")', 'ModernButton("Сравнить акты", tone="success")', "compare caption", required=False)
once('ModernButton("СОХРАНИТЬ EXCEL-ОТЧЕТ", tone="neutral")', 'ModernButton("Сохранить Excel-отчёт", tone="neutral")', "save caption", required=False)
once('ModernButton("ПРОТОКОЛ РАСХОЖДЕНИЙ • ФНС", tone="primary")', 'ModernButton("Протокол расхождений • ФНС", tone="primary")', "FNS caption", required=False)
once('self.file1_button = ModernButton("Выбрать АКТ 1")', 'self.file1_button = ModernButton("Выбрать акт 1")', "file1 caption", required=False)
once('self.file2_button = ModernButton("Выбрать АКТ 2")', 'self.file2_button = ModernButton("Выбрать акт 2")', "file2 caption", required=False)
once('self.file1_label = text_label("Файл 1 не выбран", size=12, color=MUTED, height=26)', 'self.file1_label = text_label("Акт 1: файл не выбран", size=12, color=MUTED, height=32)', "file1 label", required=False)
once('self.file2_label = text_label("Файл 2 не выбран", size=12, color=MUTED, height=26)', 'self.file2_label = text_label("Акт 2: файл не выбран", size=12, color=MUTED, height=32)', "file2 label", required=False)
once('text_label("Распознанные поля", size=17, bold=True, height=30)', 'text_label("Распознанные данные", size=17, bold=True, height=30)', "fields title", required=False)

OVERRIDES = r'''
# ===== Stability + Excel UI 1.7 =====
def uri_display_name(uri):
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


def _amount_cents(item):
    value = item.get("amount")
    if value is None:
        return None
    try:
        return int(round(abs(float(value)) * 100))
    except Exception:
        return None


def _tail_key(value):
    value = norm_doc_num(value)
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[-5:] if len(digits) >= 3 else value[-5:]


def _candidate_score(a, b, stage):
    ns = num_similarity(a.get("number"), b.get("number")) if a.get("number") and b.get("number") else 0.0
    ts = type_similarity(a.get("type"), b.get("type")) if a.get("type") and b.get("type") else 0.72
    distance = _accuracy_date_distance(a, b)
    ds = 1.0 if distance == 0 else 0.92 if distance == 1 else 0.80 if distance is not None and distance <= 3 else 0.55 if distance is not None and distance <= 7 else 0.0
    am = 1.0 if _accuracy_amount_equal(a, b) else 0.0
    if stage == "exact":
        return 0.64 * ns + 0.18 * am + 0.12 * ds + 0.06 * ts
    if stage == "payment":
        return 0.66 * am + 0.26 * ds + 0.08 * ts
    if stage == "amount_date":
        return 0.58 * am + 0.28 * ds + 0.14 * ts
    return 0.50 * ns + 0.28 * am + 0.14 * ds + 0.08 * ts


def _assign_edges(edges, free1, free2, pairs):
    for score, i1, i2, reason, a, b in sorted(edges, key=lambda item: item[0], reverse=True):
        if i1 in free1 and i2 in free2:
            free1.remove(i1)
            free2.remove(i2)
            pairs.append((i1, i2, score, a, b, reason))


def pair_rows(rows1, rows2, cols1, cols2):
    # Indexed matching: avoids O(N²) scans on Android and keeps the UI responsive.
    tx1 = [i for i, row in enumerate(rows1) if is_transaction_row(row, cols1)]
    tx2 = [i for i, row in enumerate(rows2) if is_transaction_row(row, cols2)]
    id1 = {i: smart_identity(rows1[i], cols1, i) for i in tx1}
    id2 = {i: smart_identity(rows2[i], cols2, i) for i in tx2}
    free1, free2, pairs = set(tx1), set(tx2), []

    by_number, by_amount, by_tail = {}, {}, {}
    for j in tx2:
        item = id2[j]
        if item.get("number"):
            by_number.setdefault(item["number"], []).append(j)
            by_tail.setdefault(_tail_key(item["number"]), []).append(j)
        cents = _amount_cents(item)
        if cents is not None:
            by_amount.setdefault(cents, []).append(j)

    # 1) Exact document number.
    edges = []
    for i in tx1:
        a = id1[i]
        if not a.get("number"):
            continue
        for j in by_number.get(a["number"], ()): 
            b = id2[j]
            distance = _accuracy_date_distance(a, b)
            if _accuracy_type_ok(a, b) and (distance is None or distance <= 10):
                edges.append((_candidate_score(a, b, "exact"), i, j, "точный номер", a, b))
    _assign_edges(edges, free1, free2, pairs)

    # 2) Payments: exact amount + closest date. Internal payment numbers often differ.
    edges = []
    for i in tuple(free1):
        a = id1[i]
        if not _accuracy_settlement(a):
            continue
        cents = _amount_cents(a)
        if cents is None:
            continue
        candidates = by_amount.get(cents, ())
        for j in candidates[:80]:
            if j not in free2:
                continue
            b = id2[j]
            if not _accuracy_settlement(b) or not _accuracy_type_ok(a, b):
                continue
            distance = _accuracy_date_distance(a, b)
            if distance is not None and distance <= 2:
                edges.append((_candidate_score(a, b, "payment"), i, j, "платеж: сумма+дата", a, b))
    _assign_edges(edges, free1, free2, pairs)

    # 3) Non-payment documents: amount + nearby date is a safe fallback when numbering differs.
    edges = []
    for i in tuple(free1):
        a = id1[i]
        if _accuracy_settlement(a):
            continue
        cents = _amount_cents(a)
        if cents is None:
            continue
        for j in by_amount.get(cents, ())[:80]:
            if j not in free2:
                continue
            b = id2[j]
            if _accuracy_settlement(b) or not _accuracy_type_ok(a, b):
                continue
            distance = _accuracy_date_distance(a, b)
            if distance is not None and distance <= 3:
                score = _candidate_score(a, b, "amount_date")
                if score >= 0.76:
                    edges.append((score, i, j, "сумма+дата", a, b))
    _assign_edges(edges, free1, free2, pairs)

    # 4) Fuzzy document number, but only inside a small indexed candidate bucket.
    edges = []
    for i in tuple(free1):
        a = id1[i]
        if not a.get("number"):
            continue
        candidates = set(by_tail.get(_tail_key(a["number"]), ()))
        cents = _amount_cents(a)
        if cents is not None:
            candidates.update(by_amount.get(cents, ()))
        for j in list(candidates)[:100]:
            if j not in free2:
                continue
            b = id2[j]
            if not _accuracy_type_ok(a, b):
                continue
            ns = num_similarity(a.get("number"), b.get("number")) if b.get("number") else 0.0
            distance = _accuracy_date_distance(a, b)
            if ns >= 0.86 and (_accuracy_amount_equal(a, b) or (distance is not None and distance <= 4)):
                score = _candidate_score(a, b, "fuzzy")
                if score >= 0.76:
                    edges.append((score, i, j, "похожий номер", a, b))
    _assign_edges(edges, free1, free2, pairs)
    return pairs, sorted(free1), sorted(free2)


def _excel_load_file(self, uri, target):
    path = None
    try:
        filename = uri_display_name(uri)
        path = uri_to_tempfile(uri)
        headers, rows, sheet = read_table(path)
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
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except Exception:
                pass


def _compare_done(screen, payload):
    result, t1, t2 = payload
    screen.last_result = result
    screen.compare_button.disabled = False
    screen.save_button.disabled = False
    if hasattr(screen, "fns_button"):
        screen.fns_button.disabled = False
    differences, only1, only2, matches = result
    _, accrual_diff, settlement_diff = reconcile_total_diffs(t1, t2)
    opening_diff = t1["opening"] - t2["opening"] if t1.get("opening") is not None and t2.get("opening") is not None else None
    ending_diff = t1["ending"] - t2["ending"] if t1.get("ending") is not None and t2.get("ending") is not None else None
    screen.result_label.color = TEXT
    screen.result_label.height = dp(190)
    screen.result_label.text = (
        f"[b]Сверка завершена[/b]\n"
        f"Документов требуют проверки: {len(only1) + len(only2)}\n"
        f"Только в акте 1: {len(only1)} • Только в акте 2: {len(only2)}\n"
        f"Совпадений: {len(matches)}\n\n"
        f"Начальное сальдо: {money(opening_diff)} руб.\n"
        f"[b]Разница начислений:[/b] {money(accrual_diff)} руб.\n"
        f"[b]Разница оплат:[/b] {money(settlement_diff)} руб.\n"
        f"[b]Разница конечного сальдо:[/b] {money(ending_diff)} руб."
    )


def _compare_failed(screen, message):
    screen.compare_button.disabled = False
    screen.result_label.color = DANGER
    screen.result_label.text = "Сравнение не выполнено. Подробность ошибки показана ниже."
    screen.error(message)


def _excel_run_compare(self, *_):
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
    self.result_label.color = MUTED
    self.result_label.text = "Сравнение выполняется… Приложение можно не трогать несколько секунд."

    def worker():
        try:
            result = compare(self.rows1, self.rows2, self.cols1, self.cols2, tolerance)
            t1 = totals(self.rows1, self.cols1)
            t2 = totals(self.rows2, self.cols2)
            payload = (result, t1, t2)
            Clock.schedule_once(lambda dt, p=payload: _compare_done(self, p), 0)
        except BaseException as exc:
            details = f"{type(exc).__name__}: {exc}"
            trace = traceback.format_exc(limit=6)
            if trace:
                details += "\n\n" + trace[-1800:]
            Clock.schedule_once(lambda dt, m=details: _compare_failed(self, m), 0)

    Thread(target=worker, name="reconcile-worker", daemon=True).start()


def _excel_on_save_uri(self, uri):
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


MainScreen.load_file = _excel_load_file
MainScreen.run_compare = _excel_run_compare
MainScreen.on_save_uri = _excel_on_save_uri
# ===== /Stability + Excel UI 1.7 =====
'''

marker = 'if __name__ == "__main__":'
if marker not in text:
    raise RuntimeError("Не найден конец main.py")
text = text.replace(marker, OVERRIDES + "\n\n" + marker, 1)

# Update small helper captions after all previous patches.
text = text.replace(
    'XLS / XLSX / CSV • точная сверка • платежи по дате+сумме • протокол ФНС.',
    'Excel-стиль • XLS / XLSX / CSV • сверка в фоне • протокол ФНС.',
    1,
)

path.write_text(text, encoding="utf-8")
print("Stability + Excel UI patch 1.7 applied")
