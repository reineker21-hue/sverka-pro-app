#!/usr/bin/env bash
set -euo pipefail

apk_path="Sverka-PRO-2.0.2-column-fix.apk"
test -f "$apk_path"
adb install -r "$apk_path"
adb logcat -c
adb shell am force-stop ru.slavitsa.sverkapro || true
adb shell am start -W -n ru.slavitsa.sverkapro/.MainActivity --ez sverka_selftest true

logcat_path="/tmp/sverka-native-logcat.txt"
for _ in $(seq 1 35); do
  adb logcat -d > "$logcat_path"
  if grep -q 'NATIVE_SELFTEST_OK' "$logcat_path"; then
    break
  fi
  if grep -E 'NATIVE_SELFTEST_FAIL|FATAL EXCEPTION|ANR in ru.slavitsa.sverkapro' "$logcat_path"; then
    cat "$logcat_path"
    exit 1
  fi
  sleep 1
done

grep -q 'NATIVE_SELFTEST_OK' "$logcat_path" || { cat "$logcat_path"; exit 1; }
pid="$(adb shell pidof ru.slavitsa.sverkapro | tr -d '\r')"
test -n "$pid"
echo "NATIVE_ANDROID_SELFTEST_OK pid=$pid"
