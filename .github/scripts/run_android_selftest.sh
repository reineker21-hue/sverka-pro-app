#!/usr/bin/env bash
set -euo pipefail

apk_path="$(find bin -maxdepth 1 -name '*.apk' -print -quit)"
test -n "$apk_path"
adb install -r "$apk_path"
adb logcat -c
adb shell am force-stop ru.slavitsa.sverkapro || true
adb shell am start -W -n ru.slavitsa.sverkapro/org.kivy.android.PythonActivity --es sverka_selftest 1

logcat_path="/tmp/sverka-logcat.txt"
for _ in $(seq 1 30); do
  adb logcat -d > "$logcat_path"
  if grep -q 'SVERKA_SELFTEST_OK' "$logcat_path"; then
    break
  fi
  if grep -E 'SVERKA_SELFTEST_FAIL|FATAL EXCEPTION|Fatal Python error|SIGSEGV|ANR in ru.slavitsa.sverkapro' "$logcat_path"; then
    cat "$logcat_path"
    exit 1
  fi
  sleep 1
done

if ! grep -q 'SVERKA_SELFTEST_OK' "$logcat_path"; then
  cat "$logcat_path"
  exit 1
fi

pid="$(adb shell pidof ru.slavitsa.sverkapro | tr -d '\r')"
test -n "$pid"
if grep -E 'SVERKA_SELFTEST_FAIL|FATAL EXCEPTION|Fatal Python error|SIGSEGV|ANR in ru.slavitsa.sverkapro' "$logcat_path"; then
  cat "$logcat_path"
  exit 1
fi
echo "ANDROID_COMPARE_SELFTEST_OK pid=$pid"
