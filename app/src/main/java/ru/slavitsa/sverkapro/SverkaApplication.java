package ru.slavitsa.sverkapro;

import android.app.Application;

public final class SverkaApplication extends Application {
    @Override public void onCreate() {
        super.onCreate();
        CrashLogger.install(this);
    }
}
