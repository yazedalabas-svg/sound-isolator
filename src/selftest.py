"""
فحص ذاتي — يتأكد أن كل قطعة في السلسلة تعمل قبل أول استخدام حقيقي.
تشغيل:  .venv\\Scripts\\python src\\selftest.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

OK, FAIL = "  ✔", "  ✘"
problems: list[str] = []


def check(label: str, fn):
    try:
        detail = fn()
        print(f"{OK} {label}" + (f" — {detail}" if detail else ""))
        return True
    except Exception as exc:
        print(f"{FAIL} {label} — {type(exc).__name__}: {exc}")
        problems.append(label)
        return False


def _python():
    v = sys.version_info
    assert v >= (3, 9), "يتطلب بايثون 3.9+"
    return f"{v.major}.{v.minor}.{v.micro}"


def _ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        assert shutil.which(tool), f"{tool} غير موجود في PATH"
    return shutil.which("ffmpeg")


def _numpy():
    import numpy
    return numpy.__version__


def _soundfile():
    import soundfile
    return soundfile.__version__


def _torch():
    import torch
    if torch.cuda.is_available():
        p = torch.cuda.get_device_properties(0)
        return (f"{torch.__version__} · CUDA {torch.version.cuda} · "
                f"{p.name} {p.total_memory/1024**3:.1f}GB")
    return f"{torch.__version__} · بلا CUDA (سيعمل على المعالج)"


def _demucs():
    from demucs.api import Separator  # noqa: F401
    import demucs
    return getattr(demucs, "__version__", "git")


def _audio_separator():
    from audio_separator.separator import Separator  # noqa: F401
    try:
        from importlib.metadata import version
        return version("audio-separator")
    except Exception:
        return "installed"


def _gradio():
    import gradio
    return gradio.__version__


def _engine():
    import engine
    return f"{len(engine.MEDIA_EXTS)} صيغة مدعومة"


def _pipeline():
    """اختبار حقيقي: يولّد عيّنة، يفكّ ترميزها، ويكتب مخرجًا — بلا نموذج."""
    import numpy as np
    import engine
    sys.path.insert(0, str(engine.ROOT / "demo"))

    tmp = engine.CACHE_DIR / "selftest"
    tmp.mkdir(parents=True, exist_ok=True)
    sr = 44100
    tone = (0.3 * np.sin(2 * np.pi * 440 * np.arange(sr) / sr)).astype(np.float32)
    src = engine.write_audio(np.stack([tone, tone]), sr, tmp / "tone", "wav24")

    info = engine.probe(src)
    assert abs(info["duration"] - 1.0) < 0.05, "مدة غير متوقعة"

    wav = tmp / "decoded.wav"
    engine.decode_to_wav(src, wav, sample_rate=44100)
    audio, sr2 = engine.read_audio(wav)
    assert audio.shape[0] == 2 and sr2 == 44100

    residual = engine.subtract(audio, audio)
    assert float(np.max(np.abs(residual))) < 1e-6, "الطرح الطوري غير صحيح"

    engine.write_audio(audio, sr2, tmp / "out", "flac24")
    engine.write_audio(audio, sr2, tmp / "out", "mp3_320")
    shutil.rmtree(tmp, ignore_errors=True)
    return "فك الترميز + الطرح الطوري + WAV/FLAC/MP3"


print("\n=== SoundIsolator — الفحص الذاتي ===\n")
check("بايثون", _python)
check("ffmpeg / ffprobe", _ffmpeg)
check("numpy", _numpy)
check("soundfile", _soundfile)
check("PyTorch", _torch)
check("Demucs v4", _demucs)
check("audio-separator (UVR/MDX/Roformer)", _audio_separator)
check("Gradio", _gradio)
check("محرك البرنامج", _engine)
check("سلسلة المعالجة الكاملة", _pipeline)

print()
if problems:
    print(f"فشل {len(problems)}: {', '.join(problems)}\n")
    raise SystemExit(1)
print("كل شيء جاهز ✔  — شغّل run.bat\n")
