from pathlib import Path

path = Path("main.py")
text = path.read_text(encoding="utf-8")


def once(old, new, label):
    global text
    if old not in text:
        raise RuntimeError(f"Не найден участок: {label}")
    text = text.replace(old, new, 1)


once('__version__ = "1.7.0"', '__version__ = "1.8.0"', "версия")

OVERRIDES = r'''
# ===== Safe compare 1.8 =====
def _diag_file_path():
    try:
        app = App.get_running_app()
        if app is not None:
            return os.path.join(app.user_data_dir, "compare_diagnostic.log")
    except Exception:
        pass
    return os.path.join(tempfile.gettempdir(), "compare_diagnostic.log")


def _diag_write(message):
    try:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(_diag_file_path(), "a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {message}\n")
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except Exception:
                pass
    except Exception:
        pass


def _safe_compare_execute(screen, tolerance):
    try:
        _diag_write(
            "COMPARE START | "
            f"file1={getattr(screen, 'file1_name', 'Акт 1')} | "
            f"file2={getattr(screen, 'file2_name', 'Акт 2')} | "
            f"rows1={len(screen.rows1 or [])} | rows2={len(screen.rows2 or [])}"
        )
        _diag_write("stage=compare")
        result = compare(screen.rows1, screen.rows2, screen.cols1, screen.cols2, tolerance)
        _diag_write("stage=totals1")
        t1 = totals(screen.rows1, screen.cols1)
        _diag_write("stage=totals2")
        t2 = totals(screen.rows2, screen.cols2)
        _diag_write("stage=ui-result")
        _compare_done(screen, (result, t1, t2))
        _diag_write("COMPARE DONE")
    except BaseException as exc:
        try:
            import traceback as _tb
            details = f"{type(exc).__name__}: {exc}\n{_tb.format_exc(limit=10)}"
        except Exception:
            details = f"{type(exc).__name__}: {exc}"
        _diag_write("COMPARE ERROR | " + details.replace("\n", " | ")[:5000])
        try:
            _compare_failed(screen, details[-2600:])
        except Exception:
            try:
                screen.compare_button.disabled = False
                screen.result_label.color = DANGER
                screen.result_label.text = f"Ошибка сравнения: {type(exc).__name__}: {exc}"
            except Exception:
                pass


def _safe_run_compare(self, *_):
    try:
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
        self.result_label.text = "Сравнение выполняется…"
        _diag_write("button=compare pressed")

        # В 1.7 вычисления выполнялись в отдельном Python-потоке. На части Android-
        # устройств это приводило к аварийному завершению процесса python-for-android.
        # Для актов сверки текущего размера безопаснее выполнить чистые Python-вычисления
        # в основном цикле Kivy после короткой задержки, чтобы экран успел перерисоваться.
        Clock.schedule_once(lambda dt: _safe_compare_execute(self, tolerance), 0.08)
    except BaseException as exc:
        _diag_write(f"RUN_COMPARE ERROR | {type(exc).__name__}: {exc}")
        try:
            self.compare_button.disabled = False
            self.error(f"Не удалось запустить сравнение: {type(exc).__name__}: {exc}")
        except Exception:
            pass


def _safe_android_build(self):
    root = _SAFE_ORIGINAL_BUILD(self)
    try:
        import faulthandler
        self._compare_fault_file = open(_diag_file_path(), "a", encoding="utf-8")
        faulthandler.enable(file=self._compare_fault_file, all_threads=True)
        _diag_write("APP START | Safe compare 1.8")
    except Exception as exc:
        _diag_write(f"faulthandler unavailable: {exc}")
    return root


MainScreen.run_compare = _safe_run_compare
_SAFE_ORIGINAL_BUILD = AndroidApp.build
AndroidApp.build = _safe_android_build
# ===== /Safe compare 1.8 =====
'''

marker = 'if __name__ == "__main__":'
if marker not in text:
    raise RuntimeError("Не найден конец main.py")
text = text.replace(marker, OVERRIDES + "\n\n" + marker, 1)

text = text.replace(
    'Excel-стиль • XLS / XLSX / CSV • сверка в фоне • протокол ФНС.',
    'Excel-стиль • XLS / XLSX / CSV • безопасная сверка • протокол ФНС.',
    1,
)

path.write_text(text, encoding="utf-8")
print("Safe compare patch 1.8 applied")
