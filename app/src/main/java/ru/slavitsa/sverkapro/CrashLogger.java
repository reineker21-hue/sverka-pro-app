package ru.slavitsa.sverkapro;

import android.Manifest;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.Deque;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

public final class CrashLogger {
    private static final String TAG = "SverkaPRO";
    private static final String FOLDER = "Сверка_PRO";
    private static final int MAX_EVENTS = 120;
    private static final Deque<String> EVENTS = new ArrayDeque<>();
    private static final AtomicBoolean INSTALLED = new AtomicBoolean();
    private static final AtomicBoolean HANDLING = new AtomicBoolean();
    private static Context applicationContext;

    private CrashLogger() {}

    public static void install(Context context) {
        applicationContext = context.getApplicationContext();
        if (!INSTALLED.compareAndSet(false, true)) return;
        breadcrumb("application:start");
        Thread.UncaughtExceptionHandler previous = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread, throwable) -> {
            if (HANDLING.compareAndSet(false, true)) {
                try {
                    String report = buildReport("АВАРИЙНОЕ ЗАКРЫТИЕ", thread, throwable);
                    saveInternal(report);
                    saveToDownloads(report, crashFileName());
                } catch (Throwable loggingFailure) {
                    Log.e(TAG, "Не удалось сохранить аварийный отчёт", loggingFailure);
                }
            }
            if (previous != null) previous.uncaughtException(thread, throwable);
            else {
                android.os.Process.killProcess(android.os.Process.myPid());
                System.exit(10);
            }
        });
    }

    public static synchronized void breadcrumb(String stage) {
        String clean = stage == null ? "" : stage.replace('\n', ' ').replace('\r', ' ').trim();
        if (clean.length() > 180) clean = clean.substring(0, 180);
        String time = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(new Date());
        EVENTS.addLast(time + " | " + clean);
        while (EVENTS.size() > MAX_EVENTS) EVENTS.removeFirst();
        Log.i(TAG, clean);
    }

    public static String exportDiagnosticLog() throws IOException {
        String report = buildReport("РУЧНАЯ ВЫГРУЗКА ТЕХНИЧЕСКОГО ЖУРНАЛА", Thread.currentThread(), null);
        saveInternal(report);
        return saveToDownloads(report, diagnosticFileName());
    }

    public static File lastInternalReport(Context context) {
        return new File(context.getFilesDir(), "last_crash.txt");
    }

    private static synchronized String buildReport(String title, Thread thread, Throwable throwable) {
        Context context = applicationContext;
        StringBuilder report = new StringBuilder(16_384);
        report.append(title).append('\n')
                .append("Дата: ").append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS Z", Locale.US).format(new Date())).append('\n')
                .append("Приложение: Сверка ПРО ").append(appVersion(context)).append('\n')
                .append("Пакет: ").append(context == null ? "ru.slavitsa.sverkapro" : context.getPackageName()).append('\n')
                .append("Android: ").append(Build.VERSION.RELEASE).append(" (SDK ").append(Build.VERSION.SDK_INT).append(")\n")
                .append("Устройство: ").append(Build.MANUFACTURER).append(' ').append(Build.MODEL).append('\n')
                .append("ABI: ").append(String.join(", ", Build.SUPPORTED_ABIS)).append('\n')
                .append("Поток: ").append(thread == null ? "неизвестно" : thread.getName()).append('\n');
        Runtime runtime = Runtime.getRuntime();
        report.append("Память: используется ").append((runtime.totalMemory() - runtime.freeMemory()) / 1024 / 1024)
                .append(" МБ из ").append(runtime.maxMemory() / 1024 / 1024).append(" МБ\n\n")
                .append("ТЕХНИЧЕСКИЕ ЭТАПЫ (без содержимого актов)\n");
        for (String event : EVENTS) report.append(event).append('\n');
        if (throwable != null) {
            StringWriter stack = new StringWriter();
            throwable.printStackTrace(new PrintWriter(stack));
            report.append("\nИСКЛЮЧЕНИЕ\n").append(stack);
        }
        return report.toString();
    }

    private static String appVersion(Context context) {
        if (context == null) return "2.0.1";
        try {
            PackageInfo info = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
            return info.versionName == null ? "2.0.1" : info.versionName;
        } catch (Exception ignored) {
            return "2.0.1";
        }
    }

    private static void saveInternal(String report) {
        Context context = applicationContext;
        if (context == null) return;
        File target = lastInternalReport(context);
        try (FileOutputStream output = new FileOutputStream(target, false)) {
            output.write(report.getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
        } catch (IOException error) {
            Log.e(TAG, "Не удалось сохранить внутренний аварийный отчёт", error);
        }
    }

    private static String saveToDownloads(String report, String fileName) throws IOException {
        Context context = applicationContext;
        if (context == null) throw new IOException("Контекст приложения недоступен.");
        byte[] bytes = report.getBytes(StandardCharsets.UTF_8);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ContentResolver resolver = context.getContentResolver();
            ContentValues values = new ContentValues();
            values.put(MediaStore.MediaColumns.DISPLAY_NAME, fileName);
            values.put(MediaStore.MediaColumns.MIME_TYPE, "text/plain");
            values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/" + FOLDER);
            values.put(MediaStore.MediaColumns.IS_PENDING, 1);
            Uri uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (uri == null) throw new IOException("Android не создал файл в папке загрузок.");
            try (OutputStream output = resolver.openOutputStream(uri, "w")) {
                if (output == null) throw new IOException("Android не открыл файл журнала.");
                output.write(bytes);
                output.flush();
            } catch (IOException error) {
                resolver.delete(uri, null, null);
                throw error;
            }
            ContentValues ready = new ContentValues();
            ready.put(MediaStore.MediaColumns.IS_PENDING, 0);
            resolver.update(uri, ready, null, null);
            return "Загрузки/" + FOLDER + "/" + fileName;
        }

        boolean allowed = context.checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                == PackageManager.PERMISSION_GRANTED;
        File directory = allowed
                ? new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), FOLDER)
                : new File(context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), FOLDER);
        if (!directory.exists() && !directory.mkdirs()) throw new IOException("Не удалось создать папку журнала.");
        File target = new File(directory, fileName);
        try (FileOutputStream output = new FileOutputStream(target, false)) {
            output.write(bytes);
            output.getFD().sync();
        }
        return target.getAbsolutePath();
    }

    private static String crashFileName() {
        return "SverkaPRO_crash_" + new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(new Date()) + ".txt";
    }

    private static String diagnosticFileName() {
        return "SverkaPRO_log_" + new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(new Date()) + ".txt";
    }
}
