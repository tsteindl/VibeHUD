param([switch]$Flash, [switch]$Demo, [string]$Port = 'COM7')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$cli = Get-Command arduino-cli -ErrorAction SilentlyContinue
$cliPath = if ($cli) { $cli.Source } else { "$env:LOCALAPPDATA\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" }
if (!(Test-Path -LiteralPath $cliPath)) { throw 'Install Arduino IDE or put arduino-cli on PATH.' }
if (!(Test-Path '.deps\lvgl\library.properties')) { throw 'Run scripts/setup.ps1 first.' }
$fqbn = 'esp32:esp32:esp32s3:CDCOnBoot=cdc,PSRAM=opi,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB'
$sketch = 'firmware\VibeHUD'
$build = 'build\device'
if ($Demo) {
    $sketch = '.tools\07_LVGL_V8_Test'
    New-Item -ItemType Directory -Force $sketch | Out-Null
    Copy-Item 'vendor\lcd-demo\*' $sketch -Recurse -Force
}
& $cliPath compile --fqbn $fqbn --libraries .deps --build-path $build $sketch
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
if ($Flash) {
    & $cliPath upload --fqbn $fqbn --port $Port --input-dir $build $sketch
    if ($LASTEXITCODE -ne 0) { throw 'Upload failed.' }
}
