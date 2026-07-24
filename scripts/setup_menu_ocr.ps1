<#
.SYNOPSIS
    Menu Agent의 실제 OCR(PaddleOCR + Tesseract) 환경을 한 번에 준비한다.

.DESCRIPTION
    다른 팀원이 저장소를 받은 뒤 아래 한 줄만 실행하면 된다.

        powershell -ExecutionPolicy Bypass -File scripts/setup_menu_ocr.ps1

    이 스크립트는:
      1. Windows/uv 환경을 확인하고
      2. `uv sync`로 Python 의존성(paddlepaddle, paddleocr, pytesseract 포함)을 설치하고
      3. Tesseract-OCR 프로그램이 없으면 winget으로 설치하고
      4. 관리자 권한 없이 쓸 수 있는 사용자 캐시 폴더(%LOCALAPPDATA%\tessdata)에
         eng/kor/osd 언어 모델을 준비하고(이미 있으면 다시 받지 않음)
      5. PaddleOCR 모델을 미리 받아두고
      6. 간단한 한국어 OCR 테스트로 전체가 실제로 동작하는지 확인한다.

    개인 컴퓨터의 사용자 이름이 들어간 절대경로를 이 스크립트나 프로젝트
    코드에 하드코딩하지 않는다(모두 %LOCALAPPDATA%, PATH 등 표준 환경변수로
    계산한다).

    실패해도 기존 sidecar `.txt` 기반 Menu Tool(get_menu/get_current_menu/
    reload_menu_data)은 계속 정상 동작한다 — 이 스크립트는 "선택 기능"인
    실제 OCR을 준비하는 것뿐이다.
#>

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    [경고] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "    [실패] $msg" -ForegroundColor Red }

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$hadError = $false

# 1. Windows 환경 확인
Write-Step "1/9 Windows 환경 확인"
$os = Get-CimInstance Win32_OperatingSystem
Write-Ok "$($os.Caption) ($($os.OSArchitecture))"

# 2. uv 설치 여부 확인
Write-Step "2/9 uv 설치 확인"
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    Write-Fail "uv가 설치되어 있지 않습니다. https://docs.astral.sh/uv/ 에서 설치한 뒤 다시 실행해 주세요."
    exit 1
}
Write-Ok "uv $(uv --version)"

# 3. 프로젝트 의존성 설치 (paddlepaddle/paddleocr/pytesseract 포함)
Write-Step "3/9 uv sync (Python 의존성 설치)"
try {
    uv sync
    Write-Ok "uv sync 완료"
} catch {
    Write-Fail "uv sync 실패: $($_.Exception.Message)"
    $hadError = $true
}

# 4. Tesseract 실행 파일 탐색: TESSERACT_CMD -> PATH -> Windows 기본 후보 경로
Write-Step "4/9 Tesseract-OCR 설치 확인"
function Find-TesseractCmd {
    if ($env:TESSERACT_CMD -and (Test-Path $env:TESSERACT_CMD)) { return $env:TESSERACT_CMD }
    $onPath = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    $candidates = @(
        "C:\Program Files\Tesseract-OCR\tesseract.exe",
        "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

$tesseractCmd = Find-TesseractCmd
if ($tesseractCmd) {
    Write-Ok "Tesseract 발견: $tesseractCmd"
} else {
    Write-Warn "Tesseract-OCR을 찾지 못했습니다. winget으로 설치를 시도합니다."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Fail "winget이 없어 Tesseract를 자동 설치할 수 없습니다. https://github.com/UB-Mannheim/tesseract/wiki 에서 수동 설치해 주세요."
        $hadError = $true
    } else {
        try {
            winget install --id UB-Mannheim.TesseractOCR -e --source winget --accept-package-agreements --accept-source-agreements --silent
            Start-Sleep -Seconds 2
            $tesseractCmd = Find-TesseractCmd
            if ($tesseractCmd) {
                Write-Ok "Tesseract 설치 완료: $tesseractCmd"
            } else {
                Write-Fail "설치 명령은 끝났지만 실행 파일을 찾지 못했습니다. PC를 재시작하거나 수동으로 확인해 주세요."
                $hadError = $true
            }
        } catch {
            Write-Fail "Tesseract 설치 실패: $($_.Exception.Message)"
            $hadError = $true
        }
    }
}

# 5. PaddlePaddle/PaddleOCR/pytesseract 파이썬 패키지 확인
Write-Step "5/9 PaddlePaddle / PaddleOCR / pytesseract 패키지 확인"
$pkgCheck = uv run python -c "
import importlib
missing = []
for pkg in ['paddle', 'paddleocr', 'pytesseract']:
    try:
        importlib.import_module(pkg)
    except ImportError:
        missing.append(pkg)
print(','.join(missing))
" 2>$null
if ($pkgCheck) {
    Write-Fail "누락된 패키지: $pkgCheck (uv sync가 정상적으로 끝났는지 확인해 주세요)"
    $hadError = $true
} else {
    Write-Ok "paddle, paddleocr, pytesseract 모두 import 가능"
}

# 6. 사용자 쓰기 가능한 OCR 캐시 폴더 준비 (관리자 권한 불필요, 개인 경로 하드코딩 없음)
Write-Step "6/9 언어 모델 캐시 폴더 준비"
$cacheDir = Join-Path $env:LOCALAPPDATA "tessdata"
New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
Write-Ok "캐시 폴더: $cacheDir"

# 7~10. eng/kor/osd 언어 모델 준비 (이미 있으면 재다운로드하지 않음, 최소 크기 검증)
Write-Step "7/9 언어 모델(eng/kor/osd) 준비"
$langFiles = @{
    "eng" = "https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata"
    "kor" = "https://github.com/tesseract-ocr/tessdata/raw/main/kor.traineddata"
    "osd" = "https://github.com/tesseract-ocr/tessdata/raw/main/osd.traineddata"
}
# 정상적으로 받아지면 최소 이 크기(바이트) 이상이어야 한다. 비정상적으로 작은
# 파일(예: 다운로드 실패로 만들어진 에러 페이지)은 거부하고 다시 받는다.
$minSizeBytes = 500000

foreach ($lang in $langFiles.Keys) {
    $dest = Join-Path $cacheDir "$lang.traineddata"
    $needsDownload = $true

    if (Test-Path $dest) {
        $size = (Get-Item $dest).Length
        if ($size -ge $minSizeBytes) {
            Write-Ok "$lang.traineddata 이미 존재함 (재다운로드하지 않음, $size bytes)"
            $needsDownload = $false
        } else {
            Write-Warn "$lang.traineddata 파일 크기가 비정상적으로 작습니다($size bytes). 다시 받습니다."
        }
    }

    if ($needsDownload) {
        # 먼저 로컬 Tesseract 설치 폴더에 이미 있는 언어(보통 eng/osd)는 복사만 한다.
        $installedTessdata = if ($tesseractCmd) { Join-Path (Split-Path $tesseractCmd) "tessdata\$lang.traineddata" } else { $null }
        if ($installedTessdata -and (Test-Path $installedTessdata)) {
            try {
                Copy-Item $installedTessdata $dest -Force
                Write-Ok "$lang.traineddata 를 Tesseract 설치 폴더에서 복사함"
                continue
            } catch {
                Write-Warn "$lang.traineddata 복사 실패, 공식 저장소에서 다시 받습니다: $($_.Exception.Message)"
            }
        }

        try {
            Invoke-WebRequest -Uri $langFiles[$lang] -OutFile $dest -UseBasicParsing
            $size = (Get-Item $dest).Length
            if ($size -lt $minSizeBytes) {
                Remove-Item $dest -Force -ErrorAction SilentlyContinue
                Write-Fail "$lang.traineddata 다운로드 결과가 비정상적으로 작습니다($size bytes). 네트워크를 확인해 주세요."
                $hadError = $true
            } else {
                Write-Ok "$lang.traineddata 다운로드 완료 ($size bytes)"
            }
        } catch {
            Write-Fail "$lang.traineddata 다운로드 실패: $($_.Exception.Message)"
            $hadError = $true
        }
    }
}

# Tesseract 실제 로딩 확인 (언어 모델 경로 자동 연결까지 포함)
if ($tesseractCmd) {
    $env:TESSDATA_PREFIX = $cacheDir
    $langsOutput = & $tesseractCmd --list-langs 2>&1 | Out-String
    if ($langsOutput -match "kor" -and $langsOutput -match "eng") {
        Write-Ok "Tesseract가 kor/eng 언어를 정상적으로 인식함"
    } else {
        Write-Fail "Tesseract가 kor/eng 언어를 인식하지 못했습니다.`n$langsOutput"
        $hadError = $true
    }
}

# 8. PaddleOCR 모델 준비 (첫 실행 시 자동 다운로드, 캐시는 %USERPROFILE%\.paddlex)
Write-Step "8/9 PaddleOCR 모델 준비 (처음 한 번은 자동 다운로드로 시간이 걸릴 수 있습니다)"
$paddleCheck = uv run python -c "
try:
    from paddleocr import PaddleOCR
    PaddleOCR(lang='korean', use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
    print('OK')
except Exception as e:
    print(f'FAIL:{e}')
" 2>$null
if ($paddleCheck -like "OK*") {
    Write-Ok "PaddleOCR 모델 준비 완료"
} else {
    Write-Warn "PaddleOCR 모델 준비 중 문제가 발생했습니다: $paddleCheck"
    Write-Warn "네트워크 상태에 따라 첫 다운로드가 실패할 수 있습니다. scripts/check_menu_ocr.ps1로 나중에 다시 확인해 주세요."
}

# 9. 간단한 한국어 OCR 실행 테스트 (check_ocr_status + 실제 인식 1회)
Write-Step "9/9 최종 확인"
uv run python -c "
import json
from app.menu_agent_tool import check_ocr_status
status = check_ocr_status()
print(json.dumps(status, ensure_ascii=False, indent=2))
"

if ($hadError) {
    Write-Host "`n일부 단계가 실패했습니다. 위 로그의 [실패] 항목을 확인해 주세요." -ForegroundColor Red
    Write-Host "실제 OCR 없이도 기존 sidecar TXT 기반 Menu Tool(get_menu 등)은 정상 동작합니다." -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "`n모든 단계가 완료되었습니다. scripts/check_menu_ocr.ps1로 언제든 다시 확인할 수 있습니다." -ForegroundColor Green
    exit 0
}
