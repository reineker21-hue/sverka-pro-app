from pathlib import Path

path = Path('main.py')
text = path.read_text(encoding='utf-8')
if '__version__ = "1.10.0"' not in text:
    raise RuntimeError('Android self-test patch ожидает версию 1.10.0')

BLOCK = r'''
# ===== CI Android compare self-test =====
def _android_compare_selftest(root):
    try:
        intent = get_android_activity().getIntent()
        requested = str(intent.getStringExtra("sverka_selftest") or "") == "1"
    except Exception:
        requested = False
    if not requested:
        return
    try:
        rows1 = [
            {"Дата":"", "Документ":"Сальдо начальное", "Дебет":"", "Кредит":1000},
            {"Дата":"01.07.26", "Документ":"Поступление № УТ-100 от 01.07.2026", "Дебет":"", "Кредит":120},
            {"Дата":"01.07.26", "Документ":"Платежное поручение № BANK-77 от 01.07.2026", "Дебет":50, "Кредит":""},
            {"Дата":"", "Документ":"Обороты за период", "Дебет":50, "Кредит":120},
            {"Дата":"", "Документ":"Сальдо конечное", "Дебет":"", "Кредит":1070},
        ]
        rows2 = [
            {"Дата":"", "Документ":"Сальдо на 01.07.26", "Дебет":1000, "Кредит":""},
            {"Дата":"01.07.26", "Документ":"Отгрузка 01.07.26 ( №УТ-100)", "Дебет":120, "Кредит":""},
            {"Дата":"01.07.26", "Документ":"Оплата 01.07.26 ( №00012345)", "Дебет":"", "Кредит":50},
            {"Дата":"", "Документ":"Обороты за период", "Дебет":120, "Кредит":50},
            {"Дата":"", "Документ":"Сальдо конечное", "Дебет":1070, "Кредит":""},
        ]
        cols = {"date":"Дата", "document":"Документ", "debit":"Дебет", "credit":"Кредит", "balance":None, "counterparty":None}
        root.rows1, root.rows2 = rows1, rows2
        root.cols1, root.cols2 = dict(cols), dict(cols)
        root.headers1 = root.headers2 = ["Дата", "Документ", "Дебет", "Кредит"]
        root.file1_name, root.file2_name = "selftest-1.xlsx", "selftest-2.xlsx"
        root.tolerance.text = "0.01"
        _stable_run_compare(root)
        if root.last_result is None:
            raise RuntimeError("кнопка сравнения не создала результат")
        differences, only1, only2, matches = root.last_result
        if differences or only1 or only2 or len(matches) != 2:
            raise RuntimeError(
                f"неверный self-test: diff={len(differences)} only1={len(only1)} "
                f"only2={len(only2)} match={len(matches)}"
            )
        print("SVERKA_SELFTEST_OK", flush=True)
    except BaseException as exc:
        print(f"SVERKA_SELFTEST_FAIL: {type(exc).__name__}: {exc}", flush=True)


_SELFTEST_ORIGINAL_BUILD = AndroidApp.build
def _selftest_android_build(self):
    root = _SELFTEST_ORIGINAL_BUILD(self)
    try:
        Clock.schedule_once(lambda dt: _android_compare_selftest(root), 0.8)
    except Exception:
        pass
    return root

AndroidApp.build = _selftest_android_build
# ===== /CI Android compare self-test =====
'''

marker = 'if __name__ == "__main__":'
if marker not in text:
    raise RuntimeError('Не найден конец main.py')
text = text.replace(marker, BLOCK + '\n\n' + marker, 1)
path.write_text(text, encoding='utf-8')
print('Android compare self-test hook added')
