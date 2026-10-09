$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force .tools,.deps | Out-Null
# Fetch just the Arduino LVGL8 files using HTTP ranges; the full vendor archive
# is 215 MB and contains unrelated IDF projects and firmware.
py -3.12 scripts\fetch_vendor.py
if ($LASTEXITCODE -ne 0) { throw 'Vendor dependency download failed.' }
Copy-Item '.tools\vendor-extracted\ESP32-S3-LCD-3.16-Demo\Arduino\libraries\lvgl8\*' '.deps' -Recurse -Force
Copy-Item 'firmware\VibeHUD\lv_conf.h' '.deps\lv_conf.h' -Force
Write-Host 'Vendor LVGL 8.4.0 installed locally. Use Espressif Arduino core 3.3.11.'
