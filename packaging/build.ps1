<#
.SYNOPSIS
  퀵 임포징 Windows 배포 폴더를 빌드하고 zip으로 묶는다.

.DESCRIPTION
  저장소 어디에서 실행해도 된다. 하는 일:
    1. qpdf, Poppler가 bin\ 에 없으면 GitHub Releases에서 내려받는다
    2. Python 패키지와 PyInstaller를 설치한다 (.venv가 있으면 그것을 쓴다)
    3. dist\QuickImposing\ 을 새로 빌드한다
    4. bin\ 과 사용설명서를 배포 폴더에 넣는다
    5. 두 프로그램이 뜨는지 시작 점검을 한다
    6. dist\QuickImposing-<버전>.zip 을 만든다

.EXAMPLE
  .\packaging\build.ps1
  .\packaging\build.ps1 -Test       # 빌드 전에 pytest도 돌린다 (Noto Sans CJK KR 글꼴 필요)
  .\packaging\build.ps1 -NoZip      # zip은 만들지 않는다
  .\packaging\build.ps1 -ToolsOnly  # qpdf, Poppler만 준비한다
#>
param(
    [switch]$Test,
    [switch]$NoZip,
    [switch]$ToolsOnly
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "실패: $text" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- 1. 도구
function Get-ReleaseZip($repo, $pattern) {
    $headers = @{ "User-Agent" = "quick-imposing-build" }
    if ($env:GH_TOKEN) { $headers["Authorization"] = "Bearer $env:GH_TOKEN" }
    $release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest" -Headers $headers
    $asset = $release.assets | Where-Object { $_.name -like $pattern } | Select-Object -First 1
    if (-not $asset) { Fail "$repo 최신 배포본에서 $pattern 파일을 찾지 못했습니다." }
    $zip = Join-Path "tools" $asset.name
    Invoke-WebRequest $asset.browser_download_url -OutFile $zip -UseBasicParsing
    $target = Join-Path "tools" ($asset.name -replace "\.zip$", "")
    Expand-Archive $zip -DestinationPath $target -Force
    Write-Host "  받음: $($asset.name)"
    return $target
}

function Install-Tool($name, $exe, $repo, $pattern) {
    $folder = Join-Path "bin" $name
    if (Test-Path (Join-Path $folder $exe)) {
        Write-Host "  $name 있음 ($folder)"
        return
    }
    New-Item -ItemType Directory -Force tools, $folder | Out-Null
    $extracted = Get-ReleaseZip $repo $pattern
    $found = Get-ChildItem $extracted -Recurse -Filter $exe | Select-Object -First 1
    if (-not $found) { Fail "$exe 를 내려받은 파일에서 찾지 못했습니다." }
    Copy-Item (Join-Path $found.Directory.FullName "*") $folder -Recurse -Force
}

Step "qpdf, Poppler 준비"
Install-Tool "qpdf" "qpdf.exe" "qpdf/qpdf" "*-msvc64.zip"
Install-Tool "poppler" "pdftoppm.exe" "oschwartz10612/poppler-windows" "Release-*.zip"
if ($ToolsOnly) { Write-Host ""; Write-Host "도구 준비 완료." -ForegroundColor Green; exit 0 }

# ---------------------------------------------------------------- 2. Python
Step "Python 패키지 설치"
if (Test-Path ".venv\Scripts\python.exe") {
    $python = (Resolve-Path ".venv\Scripts\python.exe").Path
} else {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) { Fail "python을 찾을 수 없습니다. Python 3.12 이상을 설치하거나 .venv를 만드세요." }
    $python = $command.Source
}
Write-Host "  $python"
& $python -m pip install -q -e ".[test,gui]" pyinstaller
if ($LASTEXITCODE -ne 0) { Fail "패키지 설치" }

$version = (Select-String -Path pyproject.toml -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1).Matches[0].Groups[1].Value
if (-not $version) { Fail "pyproject.toml에서 버전을 읽지 못했습니다." }
Write-Host "  버전 $version"

$toolPath = "$root\bin\qpdf;$root\bin\poppler"

# ---------------------------------------------------------------- 3. 테스트 (선택)
if ($Test) {
    Step "pytest"
    $saved = $env:PATH
    try {
        $env:PATH = "$toolPath;$saved"
        $env:QT_QPA_PLATFORM = "offscreen"
        New-Item -ItemType Directory -Force out | Out-Null
        # 임시 폴더를 저장소와 같은 드라이브에 둔다 (B는 프로젝트 기준 상대경로)
        & $python -m pytest -q --tb=short --basetemp=out/pytest-tmp
        if ($LASTEXITCODE -ne 0) { Fail "pytest. 테스트용 글꼴(Noto Sans CJK KR)이 설치되어 있는지 확인하세요." }
    } finally {
        $env:PATH = $saved
        Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------- 4. 빌드
Step "배포 폴더 빌드"
$dist = "dist\QuickImposing"
foreach ($old in "build", $dist) {
    if (Test-Path $old) { Remove-Item $old -Recurse -Force }
}
$pythonDir = Split-Path -Parent $python
$saved = $env:PATH
try {
    # PATH에 있는 다른 프로그램의 DLL이 배포본에 섞이면 실행되지 않는다.
    $env:PATH = "$pythonDir;$pythonDir\Scripts;$env:SystemRoot\System32;$env:SystemRoot"
    & $python -m PyInstaller packaging\quick-imposing.spec --noconfirm --log-level WARN
    if ($LASTEXITCODE -ne 0) { Fail "PyInstaller" }
} finally {
    $env:PATH = $saved
}
Copy-Item bin (Join-Path $dist "bin") -Recurse -Force
Copy-Item docs\USER-GUIDE.md (Join-Path $dist "사용설명서.md") -Force
if (Test-Path docs\images) { Copy-Item docs\images (Join-Path $dist "images") -Recurse -Force }
Set-Content (Join-Path $dist "VERSION.txt") $version -Encoding ascii

# ---------------------------------------------------------------- 5. 시작 점검
Step "시작 점검"
Remove-Item selftest-*.txt -ErrorAction SilentlyContinue
$failed = $false
foreach ($name in "QuickImposing", "QuickImposingEditor") {
    $exe = (Resolve-Path (Join-Path $dist "$name.exe")).Path
    $process = Start-Process $exe -ArgumentList "--selftest" -PassThru
    if (-not $process.WaitForExit(90000)) {
        $process.Kill()
        Write-Host "  $name : 90초 안에 끝나지 않음" -ForegroundColor Red
        $failed = $true
        continue
    }
    if ($process.ExitCode -eq 0) {
        Write-Host "  $name : 정상"
    } else {
        Write-Host "  $name : 종료 코드 $($process.ExitCode)" -ForegroundColor Red
        $failed = $true
    }
}
foreach ($required in "bin\qpdf\qpdf.exe", "bin\poppler\pdftoppm.exe", "_internal\imposing\gui\assets\work.ico") {
    if (-not (Test-Path (Join-Path $dist $required))) {
        Write-Host "  없음: $required" -ForegroundColor Red
        $failed = $true
    }
}
Get-ChildItem selftest-*.txt -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "--- $($_.Name)"
    Get-Content $_ -Encoding UTF8
}
if ($failed) { Fail "시작 점검. 위 내용을 확인하세요." }

# ---------------------------------------------------------------- 6. zip
if (-not $NoZip) {
    Step "zip 만들기"
    $zip = "dist\QuickImposing-$version.zip"
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path $dist -DestinationPath $zip
    $size = [math]::Round((Get-Item $zip).Length / 1MB)
    Write-Host "  $zip ($size MB)"
}

Write-Host ""
Write-Host "완료: 버전 $version" -ForegroundColor Green
Write-Host "  배포 폴더  $root\$dist"
if (-not $NoZip) { Write-Host "  배포 파일  $root\$zip" }
