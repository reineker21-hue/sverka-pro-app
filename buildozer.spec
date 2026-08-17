[app]
title = Сверка PRO
package.name = sverkapro
package.domain = ru.slavitsa
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0.1
requirements = python3,kivy,openpyxl,pyjnius
orientation = portrait
fullscreen = 0

android.api = 35
android.minapi = 23
android.ndk = 25b
android.ndk_api = 23
android.accept_sdk_license = True
android.archs = arm64-v8a
android.debug_artifact = apk
p4a.bootstrap = sdl2
p4a.branch = v2023.09.16

[buildozer]
log_level = 2
warn_on_root = 1
