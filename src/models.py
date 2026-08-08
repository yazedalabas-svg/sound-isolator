"""
سجل النماذج — Model registry.

محركان:
  * demucs  : Hybrid Transformer Demucs v4 (Meta / adefossez) — فصل متعدد الأجزاء.
  * uvr     : python-audio-separator — يشغّل نماذج UVR5 / MDX-Net / MDX23C / BS-Roformer.

كل مدخل يصف: المفتاح، الاسم المعروض، المحرك، معرّف النموذج، الأجزاء الناتجة،
وتقدير استهلاك الذاكرة حتى تستطيع الواجهة تحذير صاحب كرت 4GB.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSpec:
    key: str
    label: str          # الاسم المعروض في الواجهة (عربي)
    backend: str        # "demucs" أو "uvr"
    model_id: str       # اسم النموذج كما يفهمه المحرك
    stems: tuple        # الأجزاء التي ينتجها
    quality: int        # 1..5 تقدير الجودة
    speed: int          # 1..5 (5 = الأسرع)
    vram_gb: float      # تقدير ذاكرة الكرت المطلوبة على الإعدادات الافتراضية
    note: str = ""
    sdr: float = 0.0    # درجة SDR المنشورة للغناء (أعلى = أدق)
    # معامل الزمن: ثوانٍ من الحوسبة لكل ثانية صوت.
    # مُعايَر على GTX 1650 4GB — تقديري على عتاد آخر.
    rt_cuda: float = 3.0
    rt_cpu: float = 20.0


# ملاحظة: نماذج uvr تُنزَّل تلقائيًا عند أول استخدام من مستودعات UVR على GitHub.
REGISTRY: list[ModelSpec] = [
    # ---------- الأفضل لعزل الغناء (نماذج Roformer / MDX23C) ----------
    ModelSpec(
        key="roformer_v1",
        label="Mel-Band Roformer v1 ★★ الأعلى دقة على الإطلاق (SDR 12.60)",
        backend="uvr",
        model_id="vocals_mel_band_roformer.ckpt",
        stems=("vocals", "instrumental"),
        quality=5, speed=1, vram_gb=3.5, sdr=12.60,
        note="أعلى درجة SDR متاحة. الخيار الأول للإخراج النهائي إن توفّر الوقت.",
        rt_cuda=18.0, rt_cpu=120.0,
    ),
    ModelSpec(
        key="roformer_melband",
        label="Mel-Band Roformer big beta4 ★ (SDR 12.52)",
        backend="uvr",
        model_id="melband_roformer_big_beta4.ckpt",
        stems=("vocals", "instrumental"),
        quality=5, speed=1, vram_gb=3.5, sdr=12.52,
        note="منافس مباشر، أحيانًا أنظف في الترددات العالية.",
        rt_cuda=18.0, rt_cpu=120.0,
    ),
    ModelSpec(
        key="roformer_bs",
        label="BS-Roformer ★ (SDR 11.77)",
        backend="uvr",
        model_id="model_bs_roformer_ep_317_sdr_12.9755.ckpt",
        stems=("vocals", "instrumental"),
        quality=5, speed=2, vram_gb=3.5, sdr=11.77,
        note="بنية مختلفة عن Mel-Band؛ جرّبها إن لم يعجبك ناتج الأولى.",
        rt_cuda=16.0, rt_cpu=110.0,
    ),
    ModelSpec(
        key="mdx23c",
        label="MDX23C-InstVoc HQ — متوازن (SDR 10.56)",
        backend="uvr",
        model_id="MDX23C-8KFFT-InstVoc_HQ.ckpt",
        stems=("vocals", "instrumental"),
        quality=4, speed=3, vram_gb=2.5, sdr=10.56,
        note="جودة عالية وسرعة أفضل من Roformer.",
        rt_cuda=3.1, rt_cpu=20.0,
    ),
    ModelSpec(
        key="mdxnet_inst_hq3",
        label="UVR-MDX-NET Inst HQ 3 — الأفضل للموسيقى فقط (Karaoke)",
        backend="uvr",
        model_id="UVR-MDX-NET-Inst_HQ_3.onnx",
        stems=("vocals", "instrumental"),
        quality=4, speed=4, vram_gb=2.0, sdr=9.5,
        note="مضبوط لاستخراج الموسيقى بأقل بقايا غناء. سريع.",
        rt_cuda=0.45, rt_cpu=3.0,
    ),
    ModelSpec(
        key="kim_vocal_2",
        label="Kim Vocal 2 — سريع جدًا وجودة جيدة",
        backend="uvr",
        model_id="Kim_Vocal_2.onnx",
        stems=("vocals", "instrumental"),
        quality=4, speed=5, vram_gb=2.0, sdr=9.3,
        note="أسرع خيار بفارق كبير — ممتاز للملفات الطويلة والمعالجة بالجملة.",
        rt_cuda=0.38, rt_cpu=2.5,
    ),

    # ---------- Demucs: فصل متعدد الأجزاء ----------
    ModelSpec(
        key="htdemucs_ft",
        label="Demucs v4 htdemucs_ft ★ أدق نسخة (4 أجزاء)",
        backend="demucs",
        model_id="htdemucs_ft",
        stems=("vocals", "drums", "bass", "other"),
        quality=5, speed=1, vram_gb=3.0, sdr=10.79,
        note="نسخة مُحسَّنة (fine-tuned) — أبطأ ٤ مرات لكنها أدق نسخة Demucs.",
        rt_cuda=4.8, rt_cpu=32.0,
    ),
    ModelSpec(
        key="htdemucs",
        label="Demucs v4 htdemucs — قياسي (4 أجزاء)",
        backend="demucs",
        model_id="htdemucs",
        stems=("vocals", "drums", "bass", "other"),
        quality=4, speed=3, vram_gb=2.5, sdr=9.87,
        note="التوازن الافتراضي بين السرعة والدقة.",
        rt_cuda=1.2, rt_cpu=8.0,
    ),
    ModelSpec(
        key="htdemucs_6s",
        label="Demucs v4 htdemucs_6s — ٦ أجزاء (+بيانو +جيتار)",
        backend="demucs",
        model_id="htdemucs_6s",
        stems=("vocals", "drums", "bass", "guitar", "piano", "other"),
        quality=4, speed=2, vram_gb=3.0, sdr=9.5,
        note="يضيف الجيتار والبيانو. جزء البيانو تجريبي وأقل دقة.",
        rt_cuda=1.8, rt_cpu=12.0,
    ),
    ModelSpec(
        key="mdx_extra",
        label="Demucs mdx_extra — قوي على الباص والإيقاع",
        backend="demucs",
        model_id="mdx_extra",
        stems=("vocals", "drums", "bass", "other"),
        quality=4, speed=3, vram_gb=2.5,
        note="فائز مسابقة MDX 2021 (فرع B). ممتاز للطبول والباص.",
    ),

    # ---------- معالجات مساعدة ----------
    ModelSpec(
        key="dereverb",
        label="DeEcho-DeReverb — إزالة الصدى والريفيرب",
        backend="uvr",
        model_id="UVR-DeEcho-DeReverb.pth",
        stems=("no_reverb", "reverb"),
        quality=4, speed=4, vram_gb=1.5,
        note="مرّره على الغناء المعزول لإزالة الصدى — يعطي صوتًا جافًا نظيفًا.",
    ),
    ModelSpec(
        key="karaoke",
        label="Karaoke 6_HP — فصل الغناء الرئيسي عن الكورال",
        backend="uvr",
        model_id="6_HP-Karaoke-UVR.pth",
        stems=("lead_vocals", "back_vocals"),
        quality=3, speed=4, vram_gb=1.5,
        note="يفصل الصوت الرئيسي عن الأصوات الخلفية/الدوبلات.",
    ),
]

BY_KEY = {m.key: m for m in REGISTRY}

DEFAULT_MODEL = "mdx23c"

# أوضاع الإخراج التي يختارها المستخدم
STEM_MODES = {
    "vocals":       "الصوت البشري فقط",
    "instrumental": "الموسيقى فقط (بدون غناء)",
    "both":         "الاثنان معًا (غناء + موسيقى)",
    "all":          "كل الأجزاء التي يدعمها النموذج",
}

# صيغ الإخراج: المفتاح -> (الامتداد, طريقة الكتابة, المعامل)
OUTPUT_FORMATS = {
    "wav24":    (".wav",  "sf",     "PCM_24"),
    "wav16":    (".wav",  "sf",     "PCM_16"),
    "wav32f":   (".wav",  "sf",     "FLOAT"),
    "flac24":   (".flac", "sf",     "PCM_24"),
    "flac16":   (".flac", "sf",     "PCM_16"),
    "mp3_320":  (".mp3",  "ffmpeg", ["-c:a", "libmp3lame", "-b:a", "320k"]),
    "mp3_v0":   (".mp3",  "ffmpeg", ["-c:a", "libmp3lame", "-q:a", "0"]),
    "m4a_256":  (".m4a",  "ffmpeg", ["-c:a", "aac", "-b:a", "256k"]),
    "opus_192": (".opus", "ffmpeg", ["-c:a", "libopus", "-b:a", "192k"]),
}

FORMAT_LABELS = {
    "wav24":    "WAV 24-bit — بلا فقد (موصى به للمونتاج)",
    "wav16":    "WAV 16-bit — جودة قرص مدمج",
    "wav32f":   "WAV 32-bit float — أقصى مدى ديناميكي",
    "flac24":   "FLAC 24-bit — بلا فقد ومضغوط",
    "flac16":   "FLAC 16-bit — بلا فقد ومضغوط",
    "mp3_320":  "MP3 320 kbps",
    "mp3_v0":   "MP3 VBR V0",
    "m4a_256":  "M4A / AAC 256 kbps",
    "opus_192": "Opus 192 kbps",
}
