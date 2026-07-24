<#
.SYNOPSIS
    Menu Agent의 OCR 환경이 준비되어 있는지 한 번에 점검한다(설치/변경 없음, 읽기 전용).

.DESCRIPTION
        powershell -ExecutionPolicy Bypass -File scripts/check_menu_ocr.ps1

    문제가 있는 항목에는 해결 방법(대부분 scripts/setup_menu_ocr.ps1 재실행)을 안내한다.
#>

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Write-Item($label, $ok, $detail = "") {
    $mark = if ($ok) { "[OK]" } else { "[X]" }
    $color = if ($ok) { "Green" } else { "Red" }
    Write-Host ("  {0,-6} {1}  {2}" -f $mark, $label, $detail) -ForegroundColor $color
}

Write-Host "=== Menu Agent OCR 환경 점검 ===" -ForegroundColor Cyan

# Python / uv
$uv = Get-Command uv -ErrorAction SilentlyContinue
Write-Item "uv" ([bool]$uv) $(if ($uv) { uv --version } else { "설치 필요: https://docs.astral.sh/uv/" })

$pyVersion = uv run python --version 2>$null
Write-Item "Python(가상환경)" ([bool]$pyVersion) $pyVersion

# check_ocr_status() 결과를 그대로 받아온다 (중복 구현 방지 — 코드와 동일한 판단 로직 사용).
$statusJson = uv run python -c "
import json
from app.menu_agent_tool import check_ocr_status
print(json.dumps(check_ocr_status(), ensure_ascii=False))
" 2>$null

if (-not $statusJson) {
    Write-Host "`ncheck_ocr_status() 호출에 실패했습니다. 'uv sync'를 먼저 실행해 주세요." -ForegroundColor Red
    exit 1
}

$status = $statusJson | ConvertFrom-Json

Write-Item "PaddlePaddle" $status.paddlepaddle_available $(if (-not $status.paddlepaddle_available) { "uv add paddlepaddle" })
Write-Item "PaddleOCR" $status.paddleocr_available $(if (-not $status.paddleocr_available) { "uv add paddleocr" })
Write-Item "pytesseract" $status.pytesseract_available $(if (-not $status.pytesseract_available) { "uv add pytesseract" })
Write-Item "Tesseract 실행 파일" $status.tesseract_available $status.tesseract_executable_path
Write-Item "Tesseract 버전" ([bool]$status.tesseract_version) $status.tesseract_version
Write-Item "언어: eng" $status.languages.eng
Write-Item "언어: kor" $status.languages.kor $(if (-not $status.languages.kor) { "scripts/setup_menu_ocr.ps1 실행 (kor.traineddata 자동 준비)" })
Write-Item "언어: osd" $status.languages.osd
Write-Item "Pillow" $status.pillow_available $status.pillow_version
Write-Item "OpenCV" $status.opencv_available $status.opencv_version
Write-Item "PaddleOCR 모델 캐시" ([bool]$status.paddleocr_model_cache_dir) $status.paddleocr_model_cache_dir

Write-Host "`n--- 한국어 OCR 실행 테스트 ---" -ForegroundColor Cyan
$ocrTest = uv run python -c "
import json, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

with tempfile.TemporaryDirectory() as tmp:
    img_path = Path(tmp) / 'test.png'
    img = Image.new('RGB', (300, 80), color=(255, 255, 255))
    try:
        font = ImageFont.truetype('malgun.ttf', 28)
    except Exception:
        font = ImageFont.load_default()
    ImageDraw.Draw(img).text((10, 20), '테스트', fill=(0, 0, 0), font=font)
    img.save(img_path)

    from app.menu_agent_tool import preview_menu_ocr
    result = preview_menu_ocr(img_path)
    print(json.dumps({'success': result['success'], 'tesseract_text': result['tesseract_text'], 'paddle_text': result['paddle_text'], 'warnings': result['warnings'], 'error': result['error']}, ensure_ascii=False))
" 2>$null

if ($ocrTest) {
    $ocrResult = $ocrTest | ConvertFrom-Json
    Write-Item "OCR 실행(미리보기)" $ocrResult.success
    if ($ocrResult.tesseract_text) { Write-Host "    Tesseract 인식 결과: $($ocrResult.tesseract_text)" }
    if ($ocrResult.paddle_text) { Write-Host "    PaddleOCR 인식 결과: $($ocrResult.paddle_text)" }
    foreach ($w in $ocrResult.warnings) { Write-Host "    참고: $w" -ForegroundColor Yellow }
} else {
    Write-Item "OCR 실행(미리보기)" $false "테스트 스크립트 실행 실패"
}

Write-Host "`n--- 최종 사용 가능 여부 ---" -ForegroundColor Cyan
Write-Item "PaddleOCR 사용 가능" $status.paddle_ready
Write-Item "Tesseract 사용 가능" $status.tesseract_ready
Write-Item "최소 한 엔진 사용 가능" $status.any_engine_ready

if ($status.resolutions.Count -gt 0) {
    Write-Host "`n--- 해결 방법 ---" -ForegroundColor Yellow
    foreach ($r in $status.resolutions) { Write-Host "  - $r" }
}

Write-Host "`n참고: OCR이 준비되지 않았어도 get_menu()/get_current_menu()/reload_menu_data()는" -ForegroundColor Gray
Write-Host "      sidecar TXT 기반으로 항상 정상 동작합니다." -ForegroundColor Gray

if (-not $status.any_engine_ready) { exit 1 } else { exit 0 }
