from pathlib import Path

path = Path('main.py')
text = path.read_text(encoding='utf-8')
if '__version__ = "1.12.0"' not in text:
    raise RuntimeError('Android self-test patch ожидает версию 1.12.0')

BLOCK = r'''
# ===== CI Android compare self-test =====
def _android_compare_selftest_confirm(root):
    try:
        if root.last_result is None:
            raise RuntimeError("кнопка сравнения не создала результат")
        differences, only1, only2, matches = root.last_result
        if differences or only1 or only2 or len(matches) != 80:
            raise RuntimeError(
                f"неверный self-test: diff={len(differences)} only1={len(only1)} "
                f"only2={len(only2)} match={len(matches)}"
            )
        if not root.result_label.text.startswith("Сверка завершена"):
            raise RuntimeError("итог сравнения не выведен на экран")
        if root.result_label.markup:
            raise RuntimeError("экран результата всё ещё использует markup")
        # This marker is intentionally delayed until Android has rendered
        # several frames of the final result and the process is still alive.
        print("SVERKA_SELFTEST_OK", flush=True)
    except BaseException as exc:
        print(f"SVERKA_SELFTEST_FAIL: {type(exc).__name__}: {exc}", flush=True)


def _android_compare_selftest(root):
    try:
        intent = get_android_activity().getIntent()
        requested = str(intent.getStringExtra("sverka_selftest") or "") == "1"
    except Exception:
        requested = False
    if not requested:
        return
    try:
        rows1 = []
        rows2 = []
        for index in range(1, 81):
            amount = 100 + index / 10.0
            rows1.append({
                "Дата":"01.07.26",
                "Документ":f"Поступление № УТ-{index} от 01.07.2026",
                "Дебет":"",
                "Кредит":amount,
            })
            rows2.append({
                "Дата":"01.07.26",
                "Документ":f"Отгрузка 01.07.26 ( №УТ-{index})",
                "Дебет":amount,
                "Кредит":"",
            })
        cols = {"date":"Дата", "document":"Документ", "debit":"Дебет", "credit":"Кредит", "balance":None, "counterparty":None}
        root.rows1, root.rows2 = rows1, rows2
        root.cols1, root.cols2 = dict(cols), dict(cols)
        root.headers1 = root.headers2 = ["Дата", "Документ", "Дебет", "Кредит"]
        root.file1_name, root.file2_name = "selftest-1.xlsx", "selftest-2.xlsx"
        root.tolerance.text = "0.01"
        _stable_run_compare(root)
        Clock.schedule_once(lambda dt: _android_compare_selftest_confirm(root), 4.0)
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
