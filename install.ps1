# ═══════════════════════════════════════════════════════════════════
#  SoundIsolator — مثبّت البيئة
#  ينشئ بيئة بايثون معزولة على قرص المشروع ويثبّت كل المتطلبات.
#  شغّله مرة واحدة فقط:   powershell -ExecutionPolicy Bypass -File install.ps1
# ═══════════════════════════════════════════════════════════════════

$ErrorActionPreference = 'Stop'
$Root  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv  = Join-Path $Root '.venv'
$Py    = Join-Path $Venv 'Scripts\python.exe'

# كل الكاشات على قرص المشروع حتى لا يمتلئ قرص النظام
$env:PIP_CACHE_DIR = Join-Path $Root 'cache\pip'
$env:TORCH_HOME    = Join-Path $Root 'cache\torch'
$env:HF_HOME       = Join-Path $Root 'cache\hf'
New-Item -ItemType Directory -Force -Path $env:PIP_CACHE_DIR, $env:TORCH_HOME, $env:HF_HOME | Out-Null

function Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Ok($msg)        { Write-Host "    OK  $msg" -ForegroundColor Green }

Write-Host "=== SoundIsolator — تثبيت البيئة ===" -ForegroundColor Yellow
Write-Host "المجلد: $Root"

# ── 1) بايثون 3.11 ──────────────────────────────────────────────────
Step 1 'التحقق من بايثون 3.11'
$base = $null
try { $base = (& py -3.11 -c "import sys; print(sys.executable)" 2>$null) } catch {}
if (-not $base) {
    $cand = "$env:LOCALAPPDATA\PDFSmartTranslatorOneClick\Python311\python.exe"
    if (Test-Path $cand) { $base = $cand }
}
if (-not $base) { throw "لم يُعثر على Python 3.11. ثبّته من python.org ثم أعد التشغيل." }
Ok $base

# ── 2) البيئة المعزولة ──────────────────────────────────────────────
Step 2 'إنشاء البيئة المعزولة (.venv)'
if (-not (Test-Path $Py)) { & $base -m venv $Venv }
if (-not (Test-Path $Py)) { throw "فشل إنشاء .venv" }
& $Py -m pip install --upgrade pip wheel setuptools --quiet
Ok (& $Py --version)

# ── 3) محرك UVR / MDX / Roformer ────────────────────────────────────
# يُثبَّت أولًا لأنه يسحب torch من PyPI (نسخة معالج فقط)؛ الخطوة التالية
# تستبدلها بنسخة CUDA. العكس يؤدي إلى فقد تسريع الكرت بصمت.
Step 3 'تثبيت python-audio-separator (نماذج UVR / MDX23C / BS-Roformer)'
& $Py -m pip install "audio-separator[gpu]"
if ($LASTEXITCODE -ne 0) {
    Write-Host '    نسخة GPU فشلت - التحويل إلى نسخة المعالج.' -ForegroundColor Yellow
    & $Py -m pip install "audio-separator[cpu]"
}
Ok 'audio-separator'

# ── 4) PyTorch بدعم CUDA ────────────────────────────────────────────
# الثلاثة معًا وبنسخ متطابقة، وإلا رفض pip أو سقط التسريع.
Step 4 'تثبيت PyTorch + CUDA 12.4  (~2.5 GB - الأطول)'
& $Py -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
if ($LASTEXITCODE -ne 0) {
    Write-Host '    تعذّر تنزيل نسخة CUDA - التحويل إلى نسخة المعالج.' -ForegroundColor Yellow
    & $Py -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1
}
Ok 'PyTorch'

# ── 5) onnxruntime متطابق مع CUDA 12.4 ──────────────────────────────
# الإصدارات الأحدث مبنية على CUDA أعلى فتسقط نماذج ONNX إلى المعالج بصمت.
Step 5 'ضبط onnxruntime على نسخة CUDA 12.4'
& $Py -m pip install "onnxruntime-gpu==1.20.2"
Ok 'onnxruntime-gpu'

# ── 6) Demucs v4 من GitHub ──────────────────────────────────────────
Step 6 'تثبيت Demucs v4 من GitHub (adefossez/demucs)'
& $Py -m pip install dora-search einops julius lameenc openunmix pyyaml tqdm submitit treetable huggingface-hub safetensors sphn
& $Py -m pip install --no-deps "git+https://github.com/adefossez/demucs.git"
Ok 'Demucs'

# ── 7) الواجهة والأدوات ─────────────────────────────────────────────
Step 7 'تثبيت الواجهة الرسومية والأدوات'
& $Py -m pip install "gradio>=4.44,<6" soundfile
Ok 'Gradio + soundfile'

# ── 8) التحقق ───────────────────────────────────────────────────────
Step 8 'التحقق من التثبيت'
& $Py (Join-Path $Root 'src\selftest.py')
if ($LASTEXITCODE -ne 0) { throw 'فشل التحقق — راجع الرسائل أعلاه.' }

Write-Host "`n=== تم التثبيت بنجاح ===" -ForegroundColor Green
Write-Host "شغّل الواجهة بـ:  run.bat"
Write-Host "أو سطر الأوامر بـ:  run-cli.bat --list-models`n"
