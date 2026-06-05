$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bin = Join-Path $root "bin"
New-Item -ItemType Directory -Force -Path $bin | Out-Null

$cl = Get-Command cl.exe -ErrorAction SilentlyContinue
$gpp = Get-Command g++.exe -ErrorAction SilentlyContinue
$clang = Get-Command clang++.exe -ErrorAction SilentlyContinue

function Build-Helper {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Source
    )

    $sourcePath = Join-Path $root $Source
    $outputPath = Join-Path $bin "$Name.exe"
    if ($cl) {
        Push-Location $root
        try {
            & $cl.Source /nologo /O2 /EHsc /std:c++17 $sourcePath /Fe:$outputPath
        } finally {
            Pop-Location
        }
    } elseif ($gpp) {
        & $gpp.Source -O3 -std=c++17 $sourcePath -o $outputPath
    } elseif ($clang) {
        & $clang.Source -O3 -std=c++17 $sourcePath -o $outputPath
    } else {
        throw "No C++ compiler found. Install Visual Studio Build Tools, MinGW g++, or LLVM clang++."
    }
    if (-not (Test-Path $outputPath)) {
        throw "Build did not produce $outputPath"
    }
    Write-Host "Built $outputPath"
}

Build-Helper -Name "audio_rms" -Source "audio_rms.cpp"
Build-Helper -Name "media_analyzer" -Source "media_analyzer.cpp"
Build-Helper -Name "cover_pick" -Source "cover_pick.cpp"

$faceTrack = $false
if ($env:CHERRYX_BUILD_FACE_TRACK -eq "1") {
    Build-Helper -Name "face_track" -Source "face_track.cpp"
    $faceTrack = $true
} else {
    Write-Host "Skipping native face_track: OpenCV C++ build is optional. Set CHERRYX_BUILD_FACE_TRACK=1 to build placeholder/helper."
}

$capabilities = [ordered]@{
    audio_rms = $true
    media_analyzer = $true
    cover_pick = $true
    face_track = $faceTrack
    built_at = (Get-Date).ToString("o")
}
$manifestPath = Join-Path $root "capabilities.json"
($capabilities | ConvertTo-Json -Depth 3) | Set-Content -Path $manifestPath -Encoding UTF8
Write-Host "Wrote $manifestPath"
