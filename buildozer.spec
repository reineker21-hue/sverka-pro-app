[app]
title = Сравнение АС from NB
package.name = sverkapro
package.domain = ru.slavitsa
source.dir = .
source.include_exts = py,png
source.exclude_patterns = prebuild_patch.py,smart_patch.py,automation_patch.py,fns_protocol_patch.py,reconcile_accuracy_patch.py,stability_excel_ui_patch.py,safe_compare_patch.py,lean_runtime_patch.py,generate_assets.py
version = 1.9.0
requirements = python3,kivy,openpyxl,et_xmlfile,pyjnius,xlrd==2.0.1
orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png

android.api = 34
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
