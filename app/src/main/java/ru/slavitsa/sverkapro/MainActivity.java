package ru.slavitsa.sverkapro;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import ru.slavitsa.sverkapro.core.ReconciliationEngine;
import ru.slavitsa.sverkapro.core.TableData;
import ru.slavitsa.sverkapro.core.XlsxReportWriter;

import java.io.InputStream;
import java.io.OutputStream;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int OPEN_FIRST = 1001;
    private static final int OPEN_SECOND = 1002;
    private static final int SAVE_REPORT = 1003;
    private static final int STORAGE_PERMISSION = 1010;

    private static final int GREEN = Color.rgb(16, 124, 65);
    private static final int GREEN_DARK = Color.rgb(11, 94, 50);
    private static final int TEXT = Color.rgb(32, 36, 34);
    private static final int MUTED = Color.rgb(92, 101, 96);
    private static final int BORDER = Color.rgb(218, 224, 220);
    private static final int SURFACE = Color.WHITE;
    private static final int BACKGROUND = Color.rgb(244, 246, 244);
    private static final int DANGER = Color.rgb(180, 35, 35);

    private final ExecutorService worker = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, "sverka-worker");
        thread.setPriority(Thread.NORM_PRIORITY - 1);
        return thread;
    });

    private TableData first;
    private TableData second;
    private ReconciliationEngine.Result lastResult;

    private Button firstButton;
    private Button secondButton;
    private Button compareButton;
    private Button saveButton;
    private Button logButton;
    private TextView firstStatus;
    private TextView secondStatus;
    private TextView fieldsStatus;
    private TextView resultStatus;
    private EditText tolerance;
    private ProgressBar progress;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        CrashLogger.install(this);
        CrashLogger.breadcrumb("activity:create");
        getWindow().setStatusBarColor(GREEN_DARK);
        getWindow().setNavigationBarColor(BACKGROUND);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        }
        setContentView(buildInterface());
        requestLegacyStoragePermission();
        if (BuildConfig.DEBUG && getIntent().getBooleanExtra("sverka_selftest", false)) {
            new Handler(Looper.getMainLooper()).postDelayed(this::runNativeSelfTest, 700);
        }
    }

    private View buildInterface() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BACKGROUND);

        LinearLayout root = vertical();
        root.setPadding(dp(14), dp(16), dp(14), dp(28));
        scroll.addView(root, new ScrollView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        root.addView(buildHeader(), fullWidth());
        root.addView(space(12));
        root.addView(buildFilesCard(), fullWidth());
        root.addView(space(12));
        root.addView(buildRecognitionCard(), fullWidth());
        root.addView(space(12));
        root.addView(buildCompareCard(), fullWidth());
        root.addView(space(12));
        root.addView(buildResultCard(), fullWidth());
        root.addView(space(12));
        root.addView(buildActionsCard(), fullWidth());
        return scroll;
    }

    private View buildHeader() {
        LinearLayout card = card();
        LinearLayout line = new LinearLayout(this);
        line.setOrientation(LinearLayout.HORIZONTAL);
        line.setGravity(Gravity.CENTER_VERTICAL);
        ImageView icon = new ImageView(this);
        icon.setImageResource(R.drawable.ic_app);
        line.addView(icon, new LinearLayout.LayoutParams(dp(58), dp(58)));

        LinearLayout titles = vertical();
        titles.setPadding(dp(12), 0, 0, 0);
        TextView title = text("Сверка ПРО", 23, TEXT, true);
        TextView subtitle = text("Нативный Android · стабильная сверка актов", 13, MUTED, false);
        titles.addView(title);
        titles.addView(subtitle);
        line.addView(titles, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        card.addView(line);

        TextView version = text("Версия 2.0.3 · исправлена кириллица XLS", 12, GREEN, true);
        version.setPadding(0, dp(10), 0, 0);
        card.addView(version);
        return card;
    }

    private View buildFilesCard() {
        LinearLayout card = card();
        card.addView(sectionTitle("Исходные акты"));
        card.addView(helper("Поддерживаются XLS, XLSX и CSV. Файлы обрабатываются только на устройстве."));

        firstButton = button("Выбрать акт 1", GREEN, Color.WHITE);
        firstButton.setOnClickListener(view -> openDocument(OPEN_FIRST));
        card.addView(firstButton, buttonParams());
        firstStatus = helper("Акт 1: файл не выбран");
        firstStatus.setPadding(0, dp(7), 0, dp(12));
        card.addView(firstStatus);

        secondButton = button("Выбрать акт 2", GREEN, Color.WHITE);
        secondButton.setOnClickListener(view -> openDocument(OPEN_SECOND));
        card.addView(secondButton, buttonParams());
        secondStatus = helper("Акт 2: файл не выбран");
        secondStatus.setPadding(0, dp(7), 0, 0);
        card.addView(secondStatus);
        return card;
    }

    private View buildRecognitionCard() {
        LinearLayout card = card();
        card.addView(sectionTitle("Распознанные данные"));
        fieldsStatus = helper("Поля появятся после загрузки актов.");
        fieldsStatus.setLineSpacing(0, 1.18f);
        fieldsStatus.setTextIsSelectable(true);
        card.addView(fieldsStatus);
        return card;
    }

    private View buildCompareCard() {
        LinearLayout card = card();
        card.addView(sectionTitle("Настройки сверки"));
        LinearLayout line = new LinearLayout(this);
        line.setOrientation(LinearLayout.HORIZONTAL);
        line.setGravity(Gravity.CENTER_VERTICAL);
        TextView label = text("Допуск, руб.", 15, TEXT, false);
        line.addView(label, new LinearLayout.LayoutParams(0, dp(52), 1));

        tolerance = new EditText(this);
        tolerance.setText("0.01");
        tolerance.setSingleLine(true);
        tolerance.setTextSize(15);
        tolerance.setTextColor(TEXT);
        tolerance.setInputType(android.text.InputType.TYPE_CLASS_NUMBER | android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        tolerance.setPadding(dp(12), 0, dp(12), 0);
        tolerance.setBackground(roundRect(Color.rgb(248, 250, 248), BORDER, 9));
        line.addView(tolerance, new LinearLayout.LayoutParams(dp(132), dp(48)));
        card.addView(line);

        compareButton = button("Сравнить акты", GREEN, Color.WHITE);
        compareButton.setOnClickListener(view -> compareActs());
        card.addView(compareButton, buttonParams());

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(true);
        progress.setIndeterminateTintList(ColorStateList.valueOf(GREEN));
        progress.setVisibility(View.GONE);
        LinearLayout.LayoutParams progressParams = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(4));
        progressParams.topMargin = dp(8);
        card.addView(progress, progressParams);
        return card;
    }

    private View buildResultCard() {
        LinearLayout card = card();
        card.addView(sectionTitle("Результат"));
        resultStatus = text("Выберите оба акта и нажмите «Сравнить акты».", 14, MUTED, false);
        resultStatus.setLineSpacing(dp(3), 1.08f);
        resultStatus.setTextIsSelectable(true);
        resultStatus.setMinHeight(dp(120));
        card.addView(resultStatus, fullWidth());
        return card;
    }

    private View buildActionsCard() {
        LinearLayout card = card();
        card.addView(sectionTitle("Выгрузка"));
        saveButton = button("Сохранить Excel-отчёт", Color.rgb(48, 78, 63), Color.WHITE);
        saveButton.setEnabled(false);
        saveButton.setOnClickListener(view -> createReportDocument());
        card.addView(saveButton, buttonParams());

        logButton = button("Выгрузить технический лог", Color.rgb(231, 238, 234), TEXT);
        logButton.setOnClickListener(view -> exportLog());
        LinearLayout.LayoutParams logParams = buttonParams();
        logParams.topMargin = dp(10);
        card.addView(logButton, logParams);

        TextView note = helper("При аварийном закрытии журнал автоматически сохраняется в «Загрузки/Сверка_PRO». Содержимое актов в журнал не записывается.");
        note.setPadding(0, dp(10), 0, 0);
        card.addView(note);
        return card;
    }

    private void openDocument(int requestCode) {
        CrashLogger.breadcrumb(requestCode == OPEN_FIRST ? "picker:first" : "picker:second");
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel", "text/csv", "text/comma-separated-values", "text/plain"});
        startActivityForResult(intent, requestCode);
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        if (requestCode == OPEN_FIRST || requestCode == OPEN_SECOND) {
            try {
                getContentResolver().takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION);
            } catch (Exception ignored) {}
            loadAct(uri, requestCode == OPEN_FIRST ? 1 : 2);
        } else if (requestCode == SAVE_REPORT) {
            saveReport(uri);
        }
    }

    private void loadAct(Uri uri, int target) {
        String name = displayName(uri);
        setBusy(true, "Чтение акта " + target + "...");
        CrashLogger.breadcrumb("load:start target=" + target);
        worker.execute(() -> {
            try (InputStream input = getContentResolver().openInputStream(uri)) {
                if (input == null) throw new IllegalArgumentException("Android не смог открыть выбранный файл.");
                TableData table = AndroidSpreadsheetReader.read(input, name);
                CrashLogger.breadcrumb("load:ok target=" + target + " rows=" + table.rows.size());
                runOnUiThread(() -> applyLoadedAct(table, target));
            } catch (Exception error) {
                CrashLogger.breadcrumb("load:error target=" + target + " type=" + error.getClass().getSimpleName());
                runOnUiThread(() -> showError("Не удалось прочитать акт", error));
            }
        });
    }

    private void applyLoadedAct(TableData table, int target) {
        if (target == 1) {
            first = table;
            firstStatus.setText("Акт 1: " + table.sourceName + " · " + table.rows.size() + " строк");
            firstStatus.setTextColor(GREEN);
        } else {
            second = table;
            secondStatus.setText("Акт 2: " + table.sourceName + " · " + table.rows.size() + " строк");
            secondStatus.setTextColor(GREEN);
        }
        lastResult = null;
        saveButton.setEnabled(false);
        updateRecognizedFields();
        setBusy(false, null);
    }

    private void updateRecognizedFields() {
        if (first == null && second == null) return;
        StringBuilder status = new StringBuilder();
        for (Map.Entry<String, String> field : Map.of(
                "Дата", "date", "Документ", "document", "Дебет", "debit", "Кредит", "credit").entrySet()) {
            if (status.length() > 0) status.append('\n');
            status.append(field.getKey()).append(":  Акт 1 — ")
                    .append(columnName(first, field.getValue())).append("   ·   Акт 2 — ")
                    .append(columnName(second, field.getValue()));
        }
        fieldsStatus.setText(status.toString());
        fieldsStatus.setTextColor(TEXT);
    }

    private String columnName(TableData table, String kind) {
        if (table == null) return "—";
        String value = table.columns.get(kind);
        if (value != null) return value;
        return "date".equals(kind) || "document".equals(kind) ? "из содержимого" : "—";
    }

    private void compareActs() {
        hideKeyboard();
        if (first == null || second == null) {
            message("Сначала выберите оба акта сверки.");
            return;
        }
        double allowed;
        try {
            allowed = Double.parseDouble(tolerance.getText().toString().replace(',', '.'));
        } catch (Exception error) {
            message("Укажите корректный допуск в рублях.");
            return;
        }
        TableData firstSnapshot = first;
        TableData secondSnapshot = second;
        setBusy(true, "Выполняется сравнение...");
        resultStatus.setTextColor(MUTED);
        resultStatus.setText("Выполняется сравнение...");
        CrashLogger.breadcrumb("compare:start rows=" + firstSnapshot.rows.size() + "+" + secondSnapshot.rows.size());
        worker.execute(() -> {
            long started = System.nanoTime();
            try {
                ReconciliationEngine.Result result = ReconciliationEngine.compare(firstSnapshot, secondSnapshot, allowed);
                long elapsed = (System.nanoTime() - started) / 1_000_000;
                CrashLogger.breadcrumb("compare:ok ms=" + elapsed + " match=" + result.matches().size()
                        + " only=" + result.onlyFirst().size() + "+" + result.onlySecond().size());
                runOnUiThread(() -> showResult(result, elapsed));
            } catch (Exception error) {
                CrashLogger.breadcrumb("compare:error type=" + error.getClass().getSimpleName());
                runOnUiThread(() -> showError("Сравнение не выполнено", error));
            }
        });
    }

    private void showResult(ReconciliationEngine.Result result, long elapsedMs) {
        lastResult = result;
        resultStatus.setTextColor(TEXT);
        resultStatus.setText("Сверка завершена\n\n"
                + "Документов требуют проверки: " + result.documentsToCheck() + "\n"
                + "Только в акте 1: " + result.onlyFirst().size() + "\n"
                + "Только в акте 2: " + result.onlySecond().size() + "\n"
                + "Совпадений: " + result.matches().size() + "\n\n"
                + "Начальное сальдо, разница: " + money(result.openingDifference()) + " руб.\n"
                + "Начисления, разница: " + money(result.accrualDifference()) + " руб.\n"
                + "Оплаты, разница: " + money(result.settlementDifference()) + " руб.\n"
                + "Конечное сальдо, разница: " + money(result.endingDifference()) + " руб.\n\n"
                + "Время расчёта: " + elapsedMs + " мс");
        saveButton.setEnabled(true);
        setBusy(false, null);
    }

    private void createReportDocument() {
        if (lastResult == null) {
            message("Сначала выполните сравнение актов.");
            return;
        }
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        String date = new SimpleDateFormat("yyyy-MM-dd_HH-mm", Locale.US).format(new Date());
        intent.putExtra(Intent.EXTRA_TITLE, "Отчет_сверки_" + date + ".xlsx");
        startActivityForResult(intent, SAVE_REPORT);
    }

    private void saveReport(Uri uri) {
        ReconciliationEngine.Result snapshot = lastResult;
        if (snapshot == null) return;
        setBusy(true, "Сохранение Excel-отчёта...");
        CrashLogger.breadcrumb("report:start");
        worker.execute(() -> {
            try (OutputStream output = getContentResolver().openOutputStream(uri, "w")) {
                if (output == null) throw new IllegalArgumentException("Android не смог создать Excel-отчёт.");
                XlsxReportWriter.write(snapshot, output);
                CrashLogger.breadcrumb("report:ok");
                runOnUiThread(() -> {
                    setBusy(false, null);
                    message("Excel-отчёт успешно сохранён.");
                });
            } catch (Exception error) {
                CrashLogger.breadcrumb("report:error type=" + error.getClass().getSimpleName());
                runOnUiThread(() -> showError("Не удалось сохранить отчёт", error));
            }
        });
    }

    private void exportLog() {
        setBusy(true, "Выгрузка технического лога...");
        worker.execute(() -> {
            try {
                String location = CrashLogger.exportDiagnosticLog();
                runOnUiThread(() -> {
                    setBusy(false, null);
                    message("Технический лог сохранён:\n" + location);
                });
            } catch (Exception error) {
                runOnUiThread(() -> showError("Не удалось выгрузить лог", error));
            }
        });
    }

    private void runNativeSelfTest() {
        CrashLogger.breadcrumb("selftest:start");
        try {
            TableData xlsFixture = AndroidSpreadsheetReader.createAndReadSelfTestXls();
            if (xlsFixture.rows.size() != 2
                    || !(xlsFixture.rows.get(0).get("Дебет") instanceof Number)
                    || !(xlsFixture.rows.get(1).get("Кредит") instanceof Number)
                    || !String.valueOf(xlsFixture.rows.get(0).get("Документ")).contains("Поступление")) {
                throw new IllegalStateException("XLS self-test failed");
            }
            List<List<Object>> firstRows = new ArrayList<>();
            List<List<Object>> secondRows = new ArrayList<>();
            firstRows.add(List.of("Дата", "Документ", "Дебет", "Кредит"));
            secondRows.add(List.of("Дата", "Документ", "Дебет", "Кредит"));
            for (int index = 1; index <= 80; index++) {
                double amount = 100 + index / 10.0;
                firstRows.add(List.of("01.07.26", "Поступление № УТ-" + index + " от 01.07.2026", "", amount));
                secondRows.add(List.of("01.07.26", "Отгрузка 01.07.26 ( №УТ-" + index + ")", amount, ""));
            }
            first = TableData.fromMatrix("selftest-1.xlsx", "Лист1", firstRows);
            second = TableData.fromMatrix("selftest-2.xls", "Лист1", secondRows);
            firstStatus.setText("Акт 1: selftest-1.xlsx · 80 строк");
            secondStatus.setText("Акт 2: selftest-2.xls · 80 строк");
            updateRecognizedFields();
            compareActs();
            new Handler(Looper.getMainLooper()).postDelayed(() -> {
                if (lastResult != null && lastResult.matches().size() == 80
                        && resultStatus.getText().toString().startsWith("Сверка завершена")) {
                    Log.i("SverkaPRO", "NATIVE_SELFTEST_OK");
                } else {
                    Log.e("SverkaPRO", "NATIVE_SELFTEST_FAIL: result not rendered");
                }
            }, 4000);
        } catch (Throwable error) {
            Log.e("SverkaPRO", "NATIVE_SELFTEST_FAIL", error);
            throw new RuntimeException(error);
        }
    }

    private void setBusy(boolean busy, String stage) {
        progress.setVisibility(busy ? View.VISIBLE : View.GONE);
        firstButton.setEnabled(!busy);
        secondButton.setEnabled(!busy);
        compareButton.setEnabled(!busy);
        saveButton.setEnabled(!busy && lastResult != null);
        logButton.setEnabled(!busy);
        if (busy && stage != null) Toast.makeText(this, stage, Toast.LENGTH_SHORT).show();
    }

    private void showError(String title, Exception error) {
        setBusy(false, null);
        String details = error.getMessage();
        if (details == null || details.isBlank()) details = error.getClass().getSimpleName();
        resultStatus.setTextColor(DANGER);
        resultStatus.setText(title + ".\n" + details);
        new AlertDialog.Builder(this).setTitle(title).setMessage(details).setPositiveButton("OK", null).show();
    }

    private String displayName(Uri uri) {
        try (android.database.Cursor cursor = getContentResolver().query(uri,
                new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (index >= 0) {
                    String name = cursor.getString(index);
                    if (name != null && !name.isBlank()) return name;
                }
            }
        } catch (Exception ignored) {}
        String segment = uri.getLastPathSegment();
        return segment == null ? "выбранный файл" : segment;
    }

    private void requestLegacyStoragePermission() {
        if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.P
                && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, STORAGE_PERMISSION);
        }
    }

    private void hideKeyboard() {
        View focused = getCurrentFocus();
        if (focused == null) return;
        InputMethodManager keyboard = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
        if (keyboard != null) keyboard.hideSoftInputFromWindow(focused.getWindowToken(), 0);
        focused.clearFocus();
    }

    private void message(String text) { Toast.makeText(this, text, Toast.LENGTH_LONG).show(); }

    private String money(double value) {
        if (Double.isNaN(value)) return "—";
        DecimalFormatSymbols symbols = new DecimalFormatSymbols(new Locale("ru", "RU"));
        DecimalFormat format = new DecimalFormat("#,##0.00", symbols);
        return format.format(value);
    }

    private LinearLayout vertical() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    private LinearLayout card() {
        LinearLayout card = vertical();
        card.setPadding(dp(16), dp(16), dp(16), dp(16));
        card.setBackground(roundRect(SURFACE, BORDER, 14));
        card.setElevation(dp(1));
        return card;
    }

    private TextView sectionTitle(String value) {
        TextView title = text(value, 18, TEXT, true);
        title.setPadding(0, 0, 0, dp(9));
        return title;
    }

    private TextView helper(String value) {
        TextView text = text(value, 12, MUTED, false);
        text.setLineSpacing(0, 1.12f);
        return text;
    }

    private TextView text(String value, float size, int color, boolean bold) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(color);
        text.setTypeface(Typeface.create("sans", bold ? Typeface.BOLD : Typeface.NORMAL));
        text.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        return text;
    }

    private Button button(String value, int background, int foreground) {
        Button button = new Button(this);
        button.setText(value);
        button.setTextSize(15);
        button.setTextColor(foreground);
        button.setAllCaps(false);
        button.setTypeface(Typeface.create("sans", Typeface.BOLD));
        button.setGravity(Gravity.CENTER);
        button.setPadding(dp(12), 0, dp(12), 0);
        button.setBackgroundTintList(ColorStateList.valueOf(background));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) button.setStateListAnimator(null);
        return button;
    }

    private GradientDrawable roundRect(int fill, int stroke, int radius) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(dp(radius));
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private LinearLayout.LayoutParams fullWidth() {
        return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams buttonParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(50));
        params.topMargin = dp(12);
        return params;
    }

    private View space(int height) {
        View view = new View(this);
        view.setLayoutParams(new LinearLayout.LayoutParams(1, dp(height)));
        return view;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override protected void onDestroy() {
        CrashLogger.breadcrumb("activity:destroy finishing=" + isFinishing());
        worker.shutdownNow();
        super.onDestroy();
    }
}
