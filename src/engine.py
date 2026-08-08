"""
محرك العزل — SoundIsolator engine.

المسار الكامل:
    ملف صوت/فيديو  →  ffmpeg (فك ترميز إلى WAV float32)  →  النموذج  →
    اختيار الأجزاء  →  معالجة نهائية (طرح طيفي / تسوية)  →  ترميز الإخراج.

كل شيء هنا مستقل عن الواجهة، فتستطيع استدعاؤه من GUI أو CLI أو سكربت.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from models import BY_KEY, OUTPUT_FORMATS, REGISTRY, ModelSpec  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
CACHE_DIR = ROOT / "cache"

# ضع كل الكاشات على قرص المشروع حتى لا يمتلئ قرص النظام
os.environ.setdefault("TORCH_HOME", str(CACHE_DIR / "torch"))
os.environ.setdefault("HF_HOME", str(CACHE_DIR / "hf"))
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_DIR))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")


def _enable_onnx_cuda() -> None:
    """
    onnxruntime-gpu يحتاج cuDNN/cuBLAS، وهي محزومة داخل torch/lib على ويندوز
    لكنها ليست في PATH. نضيفها لمسار البحث عن DLL قبل تحميل onnxruntime،
    وإلا سقطت نماذج ONNX إلى المعالج بصمت.
    """
    try:
        import torch
        lib = Path(torch.__file__).parent / "lib"
        if lib.is_dir():
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(lib))
            os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass  # بلا CUDA سيعمل كل شيء على المعالج


_enable_onnx_cuda()

AUDIO_EXTS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus",
              ".wma", ".aiff", ".aif", ".alac", ".ape", ".mka"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg"}
MEDIA_EXTS = AUDIO_EXTS | VIDEO_EXTS

ProgressFn = Callable[[float, str], None]


def _noop(frac: float, msg: str) -> None:
    pass


# ════════════════════════════════════════════════════════════════════
#  أدوات ffmpeg
# ════════════════════════════════════════════════════════════════════

def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(
            f"لم يتم العثور على {name}. ثبّته عبر:  winget install Gyan.FFmpeg"
        )
    return path


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def probe(path: str | Path) -> dict:
    """يقرأ بيانات الملف: المدة، معدل العينات، عدد القنوات، هل فيه فيديو."""
    res = _run([
        _tool("ffprobe"), "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    if res.returncode != 0:
        raise RuntimeError(f"تعذّر قراءة الملف:\n{res.stderr[-800:]}")
    data = json.loads(res.stdout or "{}")
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    video = next((s for s in data.get("streams", [])
                  if s.get("codec_type") == "video"
                  and s.get("disposition", {}).get("attached_pic", 0) == 0), None)
    if audio is None:
        raise RuntimeError("الملف لا يحتوي على مسار صوتي.")
    return {
        "duration": float(data.get("format", {}).get("duration") or 0.0),
        "sample_rate": int(audio.get("sample_rate") or 44100),
        "channels": int(audio.get("channels") or 2),
        "codec": audio.get("codec_name", "?"),
        "has_video": video is not None,
        "size_mb": round(int(data.get("format", {}).get("size") or 0) / 1048576, 2),
    }


def decode_to_wav(src: str | Path, dst: str | Path, sample_rate: int, mono: bool = False) -> None:
    """يفكّ ترميز أي وسيط (صوت أو فيديو) إلى WAV float32 — بلا فقد في هذه المرحلة."""
    cmd = [
        _tool("ffmpeg"), "-y", "-vn", "-sn", "-dn", "-i", str(src),
        "-acodec", "pcm_f32le", "-ar", str(sample_rate),
        "-ac", "1" if mono else "2", str(dst),
    ]
    res = _run(cmd)
    if res.returncode != 0:
        raise RuntimeError(f"فشل فك الترميز:\n{res.stderr[-800:]}")


def read_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """يقرأ WAV ويعيد (قنوات × عينات) float32."""
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return np.ascontiguousarray(data.T), sr


def write_audio(audio: np.ndarray, sr: int, out_path: Path, fmt_key: str) -> Path:
    """يكتب مصفوفة (قنوات × عينات) بالصيغة المطلوبة."""
    ext, method, param = OUTPUT_FORMATS[fmt_key]
    out_path = out_path.with_suffix(ext)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    interleaved = np.ascontiguousarray(audio.T)

    if method == "sf":
        sf.write(str(out_path), interleaved, sr, subtype=param)
        return out_path

    # الصيغ المضغوطة: نكتب WAV مؤقتًا ثم نُرمّزه بـ ffmpeg
    with tempfile.TemporaryDirectory(dir=CACHE_DIR) as td:
        tmp = Path(td) / "raw.wav"
        sf.write(str(tmp), interleaved, sr, subtype="FLOAT")
        res = _run([_tool("ffmpeg"), "-y", "-i", str(tmp), *param, str(out_path)])
        if res.returncode != 0:
            raise RuntimeError(f"فشل الترميز إلى {ext}:\n{res.stderr[-800:]}")
    return out_path


def mux_into_video(video_src: Path, audio_src: Path, out_path: Path) -> Path:
    """يعيد تركيب الصوت المعزول داخل الفيديو الأصلي بلا إعادة ترميز للصورة."""
    out_path = out_path.with_suffix(".mp4")
    res = _run([
        _tool("ffmpeg"), "-y", "-i", str(video_src), "-i", str(audio_src),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "320k", "-shortest", str(out_path),
    ])
    if res.returncode != 0:
        raise RuntimeError(f"فشل دمج الفيديو:\n{res.stderr[-800:]}")
    return out_path


# ════════════════════════════════════════════════════════════════════
#  الإعدادات
# ════════════════════════════════════════════════════════════════════

@dataclass
class Settings:
    """كل مقابض التحكم التي يعرضها البرنامج."""
    model: str = "mdx23c"
    stem_mode: str = "both"            # vocals | instrumental | both | all
    output_format: str = "wav24"
    sample_rate: int = 44100           # 44100 | 48000 | 0 = مثل المصدر

    # الجهاز والأداء
    device: str = "auto"               # auto | cuda | cpu
    segment: float = 7.0               # طول المقطع بالثواني (يقلّل الذاكرة)
    overlap: float = 0.25              # تداخل المقاطع 0.0–0.75 (أعلى = أنعم وأبطأ)
    shifts: int = 1                    # shift-trick لـ Demucs: 1..10 (أعلى = أدق وأبطأ)
    jobs: int = 0                      # عمليات متوازية على المعالج (0 = تلقائي)
    batch_size: int = 1                # حجم الدفعة لنماذج UVR

    # جودة/معالجة نهائية
    residual_instrumental: bool = True  # استخراج "العكس" بطرح الغناء من الأصل
    normalize: bool = False             # تسوية الذروة
    peak_dbfs: float = -0.3             # ذروة الهدف عند التسوية
    denoise_threshold: float = 0.9      # عتبة التسوية الداخلية لنماذج UVR (0.1–1.0)

    # الفيديو
    remux_video: bool = False           # أعد تركيب الناتج داخل الفيديو الأصلي

    def spec(self) -> ModelSpec:
        return BY_KEY[self.model]


@dataclass
class Result:
    input_path: str
    output_dir: str
    files: dict = field(default_factory=dict)   # stem -> path
    seconds: float = 0.0
    device_used: str = ""
    model_label: str = ""
    log: list = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════
#  اختيار الجهاز
# ════════════════════════════════════════════════════════════════════

def resolve_device(pref: str = "auto") -> str:
    if pref == "cpu":
        return "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    if pref == "cuda":
        raise RuntimeError("طُلب CUDA لكن PyTorch لا يرى كرت الشاشة. شغّل على cpu أو أعد تثبيت torch بنسخة CUDA.")
    return "cpu"


def vram_gb() -> float:
    """ذاكرة الكرت بالجيجابايت، أو 0 إن لم يوجد كرت مدعوم."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_properties(0).total_memory / 1024**3
    except Exception:
        pass
    return 0.0


# ميزانية الانتظار للوضع التلقائي: السرعة أولوية — لا نُجبر المستخدم على
# انتظار أطول من هذا. عمليًا يعني هذا اختيار أسرع نموذج متاح في أغلب الحالات.
AUTO_TIME_BUDGET_S = 30.0


def estimate_seconds(model_key: str, duration_s: float, device: str | None = None) -> float:
    """تقدير زمن المعالجة اعتمادًا على معاملات مُعايَرة بالقياس الفعلي."""
    spec = BY_KEY[model_key]
    dev = device or resolve_device("auto")
    factor = spec.rt_cuda if dev == "cuda" else spec.rt_cpu
    return duration_s * factor + 6.0          # + زمن تحميل النموذج وفك الترميز


def _fmt_duration(seconds: float) -> str:
    """
    ~{mins:.0f} دقيقة كانت تعرض «~0 دقيقة» لأي تقدير دون 90 ثانية (0.5
    دقيقة تُقرَّب لأقرب زوجي = صفر) — مربك وغير صحيح. نعرض ثوانٍ تحت الدقيقة.
    """
    if seconds < 60:
        return f"~{max(round(seconds), 5)} ثانية"
    return f"~{seconds / 60:.0f} دقيقة"


def autopick_model(duration_s: float, budget_s: float = AUTO_TIME_BUDGET_S) -> tuple[str, str]:
    """
    يختار أفضل نموذج **يليق بعتاد هذا الجهاز**، ويعيد (المفتاح، سبب الاختيار).

    القاعدة: أعلى درجة SDR ينهي الملف داخل ميزانية الوقت وتكفيه ذاكرة الكرت.
    فمقطع قصير يحصل على أدقّ نموذج، وملف طويل يحصل على نموذج يُنهيه في وقت معقول
    بدل أن يعلّق المستخدم ساعة بلا تفسير.
    """
    dev = resolve_device("auto")
    mem = vram_gb()

    fits = [m for m in REGISTRY
            if m.backend != "demucs" or m.stems[0] == "vocals"]           # كلها تعطي غناء
    fits = [m for m in fits if "vocals" in m.stems and "reverb" not in m.stems[0]]
    if dev == "cuda":
        fits = [m for m in fits if m.vram_gb <= mem - 0.4]                # هامش أمان
    fits.sort(key=lambda m: m.sdr, reverse=True)

    # قيم rt_cpu تقديرية بلا أي قياس فعلي (لا كرت GPU لدينا للمقارنة محليًا).
    # قِيست لاحقًا على Render فعليًا: نموذج قُدِّر له ~3 دقائق (rt_cpu=8) وصل
    # 486 ثانية وهو عند 25% فقط — أي ~32 دقيقة حقيقية، أبطأ بـ13× من التقدير.
    # المعالجات المُستضافة غالبًا حصّة صغيرة من نواة مشتركة، لا نواة كاملة.
    # بلا بيانات موثوقة لأي نموذج، الاختيار الآمن الوحيد هو الأسرع دائمًا —
    # نتجاوز حلقة الميزانية كليًا على المعالج بدل الوثوق بأرقام مضلِّلة.
    if dev == "cpu":
        fastest = min(fits, key=lambda m: m.rt_cpu)
        secs = estimate_seconds(fastest.key, duration_s, dev)
        return fastest.key, (f"معالجة على المعالج (لا كرت شاشة هنا) — أبطأ بكثير من "
                             f"المتوقّع أحيانًا، فاخترت الأسرع. تقدير {_fmt_duration(secs)} "
                             f"غير مضمون؛ قد يطول أكثر")

    for m in fits:
        secs = estimate_seconds(m.key, duration_s, dev)
        if secs <= budget_s:
            return m.key, f"أعلى دقة متاحة تنتهي خلال {_fmt_duration(secs)} على جهازك"

    fastest = min(fits, key=lambda m: m.rt_cuda)
    secs = estimate_seconds(fastest.key, duration_s, dev)
    return fastest.key, f"الملف طويل — اخترت الأسرع لينتهي خلال {_fmt_duration(secs)}"


# ميزانية وضع «الجودة العالية». قِسْت أن roformer_v1 (أعلى SDR) يحتاج
# ~18× طول الملف — أغنية ٤ دقائق ≈ ٧٢ دقيقة معالجة، وهذا يخالف «ما تطول
# مرّة» مهما بلغت الدقة. فبدل تثبيت نموذج واحد، نطبّق نفس منطق autopick
# بسقف أعلى معقول: أفضل دقة تُنجَز خلال ٣ دقائق — على مقاطع قصيرة جدًا فقط
# يحصل المستخدم على roformer_v1 نفسه (يفي بالسقف الضيق)، وأغلب الملفات
# تنزلق تلقائيًا لنموذج أسرع بوضوح (mdxnet_inst_hq3/kim_vocal_2 عادة) —
# لا يزال أدقّ من وضع السرعة، لكن الوقت مضمون ألا يتجاوز ٣ دقائق أبدًا.
QUALITY_TIME_BUDGET_S = 180.0


def pick_for_mode(duration_s: float, mode: str) -> tuple[str, str]:
    """
    اختيار صريح بين وضعين يراهما المستخدم بوضوح قبل أن يضغط:
      speed   → ميزانية AUTO_TIME_BUDGET_S (٣٠ث) — أسرع نموذج يليق بالوقت
      quality → ميزانية QUALITY_TIME_BUDGET_S (٣د) — أعلى دقة ضمن حدّ معقول
    """
    budget = QUALITY_TIME_BUDGET_S if mode == "quality" else AUTO_TIME_BUDGET_S
    return autopick_model(duration_s, budget_s=budget)


def gpu_info() -> str:
    try:
        import torch
        if not torch.cuda.is_available():
            return "لا يوجد كرت مدعوم — سيُستخدم المعالج (CPU)."
        name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        return f"{name} — {vram:.1f} GB VRAM (CUDA {torch.version.cuda})"
    except Exception as exc:
        return f"تعذّر فحص الكرت: {exc}"


# ════════════════════════════════════════════════════════════════════
#  محرك 1: Demucs v4
# ════════════════════════════════════════════════════════════════════

_demucs_cache: dict = {}


def _separate_demucs(wav: np.ndarray, sr: int, st: Settings,
                     progress: ProgressFn) -> tuple[dict[str, np.ndarray], int]:
    import torch
    from demucs.api import Separator

    device = resolve_device(st.device)
    spec = st.spec()
    cache_key = (spec.model_id, device, st.segment, st.overlap, st.shifts, st.jobs)

    def build(dev: str, segment: float):
        return Separator(
            model=spec.model_id,
            device=dev,
            shifts=max(0, int(st.shifts) - 1),   # 1 في الواجهة = بلا shift إضافي
            overlap=float(st.overlap),
            split=True,
            segment=float(segment) if segment else None,
            jobs=int(st.jobs),
            progress=False,
        )

    progress(0.15, f"تحميل نموذج {spec.model_id} على {device.upper()} …")
    if cache_key in _demucs_cache:
        separator = _demucs_cache[cache_key]
    else:
        separator = build(device, st.segment)
        _demucs_cache[cache_key] = separator

    tensor = torch.from_numpy(wav)
    if tensor.shape[0] == 1:                     # Demucs يتوقع ستيريو
        tensor = tensor.repeat(2, 1)

    progress(0.25, "جارٍ الفصل … (هذه أطول مرحلة)")
    attempts = [(device, st.segment)]
    if device == "cuda":
        attempts += [("cuda", max(3.0, st.segment / 2)), ("cpu", st.segment)]

    last_exc = None
    for dev, seg in attempts:
        try:
            if (dev, seg) != (device, st.segment):
                progress(0.25, f"ذاكرة غير كافية — إعادة المحاولة على {dev.upper()} بمقطع {seg:.0f}s …")
                separator = build(dev, seg)
            _, stems = separator.separate_tensor(tensor, sr)
            out = {k: v.cpu().numpy().astype(np.float32) for k, v in stems.items()}
            return out, separator.samplerate
        except (torch.cuda.OutOfMemoryError, RuntimeError) as exc:
            if "out of memory" not in str(exc).lower():
                raise
            last_exc = exc
            torch.cuda.empty_cache()
    raise RuntimeError(f"نفدت الذاكرة على كل المحاولات: {last_exc}")


# ════════════════════════════════════════════════════════════════════
#  محرك 2: python-audio-separator (UVR / MDX / MDX23C / Roformer)
# ════════════════════════════════════════════════════════════════════

_STEM_ALIASES = {
    "vocals": "vocals", "vocal": "vocals",
    "instrumental": "instrumental", "instrument": "instrumental",
    "no reverb": "no_reverb", "noreverb": "no_reverb", "dry": "no_reverb",
    "reverb": "reverb", "echo": "reverb",
    "lead vocals": "lead_vocals", "back vocals": "back_vocals",
    "drums": "drums", "bass": "bass", "other": "other",
    "guitar": "guitar", "piano": "piano",
}


def _normalize_stem_name(raw: str) -> str:
    raw = raw.strip().lower().replace("-", " ").replace("_", " ")
    return _STEM_ALIASES.get(raw, raw.replace(" ", "_"))


def _separate_uvr(src_wav: Path, st: Settings,
                  progress: ProgressFn) -> tuple[dict[str, np.ndarray], int]:
    import logging

    from audio_separator.separator import Separator

    device = resolve_device(st.device)
    spec = st.spec()
    workdir = Path(tempfile.mkdtemp(dir=CACHE_DIR, prefix="uvr_"))

    progress(0.12, f"تجهيز {spec.model_id} … (يُنزَّل تلقائيًا عند أول استخدام)")

    common = dict(
        output_dir=str(workdir),
        output_format="WAV",
        model_file_dir=str(MODELS_DIR),
        log_level=logging.WARNING,      # سجلّ INFO يغرق شريط التقدّم
        normalization_threshold=float(st.denoise_threshold),
        use_soundfile=True,
        mdx_params={"hop_length": 1024, "segment_size": 256,
                    "overlap": max(0.001, float(st.overlap)),
                    "batch_size": int(st.batch_size), "enable_denoise": False},
        vr_params={"batch_size": int(st.batch_size), "window_size": 512,
                   "aggression": 5, "enable_tta": st.shifts > 1,
                   "enable_post_process": False, "post_process_threshold": 0.2,
                   "high_end_process": False},
        mdxc_params={"segment_size": 256, "override_model_segment_size": False,
                     "batch_size": int(st.batch_size),
                     "overlap": max(2, int(round(st.overlap * 16))),
                     "pitch_shift": 0},
    )
    if device == "cpu":
        common["use_autocast"] = False

    try:
        separator = Separator(**common)
    except TypeError:
        # توافق مع إصدارات أقدم لا تعرف بعض المعاملات
        for k in ("use_soundfile", "mdxc_params", "use_autocast", "log_level"):
            common.pop(k, None)
        separator = Separator(**common)

    progress(0.2, "تحميل أوزان النموذج …")
    separator.load_model(model_filename=spec.model_id)

    progress(0.3, "جارٍ الفصل … (هذه أطول مرحلة)")
    produced = separator.separate(str(src_wav))

    stems: dict[str, np.ndarray] = {}
    out_sr = 44100
    for name in produced:
        p = Path(name)
        if not p.is_absolute():
            p = workdir / p
        if not p.exists():
            continue
        # الاسم بالشكل:  base_(Vocals)_model.wav  →  نستخرج ما بين القوسين
        m = re.search(r"\(([^)]+)\)", p.stem)
        stem_name = _normalize_stem_name(m.group(1)) if m else p.stem.split("_")[-1].lower()
        audio, out_sr = read_audio(p)
        stems[stem_name] = audio

    shutil.rmtree(workdir, ignore_errors=True)
    if not stems:
        raise RuntimeError("لم ينتج النموذج أي ملفات — تحقّق من الاتصال بالإنترنت لتنزيل النموذج.")
    return stems, out_sr


# ════════════════════════════════════════════════════════════════════
#  معالجة نهائية
# ════════════════════════════════════════════════════════════════════

def _align(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """يوحّد عدد القنوات والطول قبل الطرح."""
    if a.shape[0] != b.shape[0]:
        target = max(a.shape[0], b.shape[0])
        a = np.repeat(a, target // a.shape[0], axis=0) if a.shape[0] < target else a[:target]
        b = np.repeat(b, target // b.shape[0], axis=0) if b.shape[0] < target else b[:target]
    n = min(a.shape[1], b.shape[1])
    return a[:, :n], b[:, :n]


def subtract(original: np.ndarray, part: np.ndarray) -> np.ndarray:
    """
    «العكس»: يطرح جزءًا من الخليط الأصلي فينتج كل ما تبقى.
    هذا طرح في نطاق الزمن (طرح الطور) — يحافظ على كامل الطيف بلا تلوين.
    """
    o, p = _align(original, part)
    return (o - p).astype(np.float32)


def peak_normalize(audio: np.ndarray, target_dbfs: float = -0.3) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) or 1.0
    return (audio * ((10 ** (target_dbfs / 20)) / peak)).astype(np.float32)


def safe_clip(audio: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(audio)))
    if peak > 1.0:                       # تخفيض هادئ بدل القص المشوِّه
        audio = audio / peak * 0.999
    return audio.astype(np.float32)


def mix_stems(parts: dict[str, float], out_path: Path,
              fmt_key: str = "wav24") -> tuple[Path, dict]:
    """
    يمزج أجزاءً بمستويات يختارها المستخدم ويكتب الناتج.

    parts: مسار الملف -> معامل الكسب (0.0 = مكتوم، 1.0 = المستوى الأصلي).
    يعيد (مسار الملف الناتج، تقرير مختصر).

    المزج جمع خطّي في نطاق الزمن — نفس ما تسمعه في المعاينة تمامًا،
    لأن المتصفّح يطبّق الكسب نفسه على العيّنات.
    """
    layers: list[np.ndarray] = []
    sr = 44100
    for path, gain in parts.items():
        if gain <= 0.0001:                 # مكتوم — لا داعي لقراءته
            continue
        audio, sr = read_audio(path)
        layers.append(audio * float(gain))

    if not layers:                         # كل شيء مكتوم: أخرج صمتًا بطول المرجع
        ref, sr = read_audio(next(iter(parts)))
        mixed = np.zeros_like(ref)
    else:
        channels = max(l.shape[0] for l in layers)
        length = max(l.shape[1] for l in layers)
        mixed = np.zeros((channels, length), dtype=np.float32)
        for layer in layers:
            if layer.shape[0] < channels:  # مونو داخل ستيريو
                layer = np.repeat(layer, channels // layer.shape[0], axis=0)
            mixed[:, :layer.shape[1]] += layer

    peak = float(np.max(np.abs(mixed)))
    mixed = safe_clip(mixed)
    written = write_audio(mixed, sr, out_path, fmt_key)
    return written, {"peak": peak, "clipped": peak > 1.0, "sr": sr}


def _pick_stems(stems: dict[str, np.ndarray], original: np.ndarray,
                st: Settings) -> dict[str, np.ndarray]:
    """يطبّق وضع الإخراج الذي اختاره المستخدم على الأجزاء الخام."""
    out: dict[str, np.ndarray] = {}
    has_vocals = "vocals" in stems

    # بناء «الموسيقى» إن لم يعطها النموذج مباشرة (حالة Demucs متعدد الأجزاء)
    if "instrumental" not in stems and has_vocals:
        if st.residual_instrumental:
            stems["instrumental"] = subtract(original, stems["vocals"])
        else:
            others = [v for k, v in stems.items() if k != "vocals"]
            if others:
                n = min(x.shape[1] for x in others)
                stems["instrumental"] = np.sum([x[:, :n] for x in others], axis=0).astype(np.float32)

    if st.stem_mode == "vocals":
        out = {k: stems[k] for k in ("vocals", "lead_vocals", "no_reverb") if k in stems}
    elif st.stem_mode == "instrumental":
        out = {k: stems[k] for k in ("instrumental", "back_vocals", "reverb") if k in stems}
    elif st.stem_mode == "both":
        out = {k: stems[k] for k in ("vocals", "instrumental", "lead_vocals",
                                     "back_vocals", "no_reverb", "reverb") if k in stems}
    else:  # all
        out = dict(stems)

    return out or dict(stems)


# ════════════════════════════════════════════════════════════════════
#  الواجهة الرئيسية
# ════════════════════════════════════════════════════════════════════

def separate_file(input_path: str | Path, settings: Settings,
                  output_root: str | Path | None = None,
                  progress: ProgressFn | None = None) -> Result:
    """يعزل ملفًا واحدًا ويعيد مسارات الأجزاء الناتجة."""
    progress = progress or _noop
    t0 = time.time()
    src = Path(input_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"الملف غير موجود: {src}")
    if src.suffix.lower() not in MEDIA_EXTS:
        raise ValueError(f"امتداد غير مدعوم: {src.suffix}")

    spec = settings.spec()
    out_root = Path(output_root or (ROOT / "outputs")).resolve()
    out_dir = out_root / _safe_name(src.stem)
    out_dir.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    progress(0.03, "قراءة الملف …")
    info = probe(src)
    sr = settings.sample_rate or info["sample_rate"]
    log = [f"المصدر: {info['codec']} · {info['sample_rate']} Hz · {info['channels']}ch · "
           f"{info['duration']:.1f}s · {info['size_mb']} MB"]

    with tempfile.TemporaryDirectory(dir=CACHE_DIR) as td:
        tmp_wav = Path(td) / "input.wav"
        progress(0.08, "فك الترميز إلى WAV غير مضغوط …")
        decode_to_wav(src, tmp_wav, sample_rate=sr)
        original, sr = read_audio(tmp_wav)

        if spec.backend == "demucs":
            stems, sr = _separate_demucs(original, sr, settings, progress)
        else:
            stems, sr = _separate_uvr(tmp_wav, settings, progress)
            if sr != info["sample_rate"] and settings.sample_rate == 0:
                log.append(f"ملاحظة: النموذج يعمل داخليًا على {sr} Hz.")

    progress(0.85, "تجهيز الأجزاء المطلوبة …")
    # أعد قراءة الأصل بمعدل النموذج إن اختلف، حتى يصحّ الطرح
    if original.shape[1] and stems:
        any_stem = next(iter(stems.values()))
        if abs(any_stem.shape[1] - original.shape[1]) > sr * 0.5:
            with tempfile.TemporaryDirectory(dir=CACHE_DIR) as td2:
                rewav = Path(td2) / "orig_rs.wav"
                decode_to_wav(src, rewav, sample_rate=sr)
                original, _ = read_audio(rewav)

    selected = _pick_stems(stems, original, settings)

    progress(0.9, "كتابة الملفات …")
    files: dict[str, str] = {}
    for name, audio in selected.items():
        audio = peak_normalize(audio, settings.peak_dbfs) if settings.normalize else safe_clip(audio)
        target = out_dir / f"{_safe_name(src.stem)}__{name}"
        written = write_audio(audio, sr, target, settings.output_format)
        files[name] = str(written)

    if settings.remux_video and info["has_video"]:
        progress(0.96, "إعادة تركيب الفيديو …")
        primary = files.get("instrumental") or files.get("vocals") or next(iter(files.values()))
        video_out = mux_into_video(src, Path(primary), out_dir / f"{_safe_name(src.stem)}__video")
        files["video"] = str(video_out)

    elapsed = time.time() - t0
    ratio = (info["duration"] / elapsed) if elapsed > 0 else 0
    log.append(f"النموذج: {spec.label}")
    log.append(f"استغرق {elapsed:.1f}s (أسرع من الزمن الحقيقي بـ {ratio:.1f}×)")
    progress(1.0, "تم ✔")

    return Result(
        input_path=str(src), output_dir=str(out_dir), files=files,
        seconds=elapsed, device_used=resolve_device(settings.device),
        model_label=spec.label, log=log,
    )


def separate_batch(paths: Iterable[str | Path], settings: Settings,
                   output_root: str | Path | None = None,
                   progress: ProgressFn | None = None) -> list[Result]:
    """يعالج قائمة ملفات — النموذج يُحمَّل مرة واحدة ويُعاد استخدامه."""
    progress = progress or _noop
    paths = [Path(p) for p in paths]
    results: list[Result] = []
    total = len(paths) or 1
    for i, p in enumerate(paths):
        def sub(frac: float, msg: str, i=i, p=p):
            progress((i + frac) / total, f"[{i+1}/{total}] {p.name} — {msg}")
        try:
            results.append(separate_file(p, settings, output_root, sub))
        except Exception as exc:
            results.append(Result(input_path=str(p), output_dir="", files={},
                                  log=[f"فشل: {exc}"]))
    return results


def collect_media(folder: str | Path, recursive: bool = True) -> list[Path]:
    folder = Path(folder)
    it = folder.rglob("*") if recursive else folder.glob("*")
    return sorted(p for p in it if p.is_file() and p.suffix.lower() in MEDIA_EXTS)


def _safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "output"
