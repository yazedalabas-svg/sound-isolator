"""
مولّد العيّنة التجريبية.

يبني «أغنية» صناعية من ١٦ ثانية: صوت غنائي مُركَّب بطريقة المصدر-المرشِّح
(Source-Filter: نبضات حنجرية + مرشِّحات فورمانت) فوق مصاحبة موسيقية
(كوردات + باص + طبول). يُحفظ الخليط مع الأجزاء المرجعية، فتستطيع مقارنة
ناتج العزل بالحقيقة المطلقة وقياس جودة النموذج فعليًا.

تشغيل مستقل:  python demo/make_demo.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
BPM = 92
BEAT = 60.0 / BPM

# فورمانتات الحروف الصوتية (Hz) — تعطي الصوت طابعًا بشريًا
VOWELS = {
    "a": (800, 1200, 2500),
    "e": (400, 2200, 2800),
    "i": (300, 2700, 3300),
    "o": (450, 800, 2600),
    "u": (325, 700, 2500),
}

NOTE = {"C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61, "G3": 196.00,
        "A3": 220.00, "B3": 246.94, "C4": 261.63, "D4": 293.66, "E4": 329.63,
        "F4": 349.23, "G4": 392.00, "A4": 440.00, "B4": 493.88, "C5": 523.25}


def _adsr(n: int, a=0.02, d=0.1, s=0.7, r=0.25) -> np.ndarray:
    """مغلّف سعة بسيط."""
    na, nd = int(a * SR), int(d * SR)
    nr = int(r * SR)
    ns = max(0, n - na - nd - nr)
    return np.concatenate([
        np.linspace(0, 1, na, endpoint=False),
        np.linspace(1, s, nd, endpoint=False),
        np.full(ns, s),
        np.linspace(s, 0, n - na - nd - ns),
    ])[:n]


def _formant_filter(sig: np.ndarray, formants: tuple, bw: float = 90.0) -> np.ndarray:
    """
    يطبّق مرشِّحات فورمانت في نطاق التردد (ضرب بمنحنى غاوسي عند كل فورمانت).
    هذا ما يحوّل نبضات الحنجرة الخام إلى ما يشبه حرفًا صوتيًا بشريًا.
    """
    n = len(sig)
    spec = np.fft.rfft(sig)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    gain = np.full_like(freqs, 0.04)
    for i, f in enumerate(formants):
        amp = 1.0 / (1 + i * 0.55)                       # الفورمانتات العليا أهدأ
        gain += amp * np.exp(-0.5 * ((freqs - f) / (bw * (1 + i * 0.6))) ** 2)
    gain *= np.exp(-freqs / 9000.0)                      # ميل طبيعي للطيف
    return np.fft.irfft(spec * gain, n)


def _glottal(f0: float, n: int, vibrato=5.2, depth=0.022) -> np.ndarray:
    """نبضات حنجرية: موجة منشارية غنية بالتوافقيات + فيبراتو."""
    t = np.arange(n) / SR
    f = f0 * (1 + depth * np.sin(2 * np.pi * vibrato * t))
    phase = 2 * np.pi * np.cumsum(f) / SR
    sig = np.zeros(n)
    for h in range(1, 40):                               # مجموع توافقيات = منشار مُلطَّف
        if f0 * h > SR / 2:
            break
        sig += np.sin(phase * h) / h
    return sig * 0.5


def build_vocal(melody: list[tuple[str, float, str]]) -> np.ndarray:
    """melody: قائمة (نغمة، مدّة بالنبضات، حرف صوتي)."""
    parts = []
    for note, beats, vowel in melody:
        n = int(beats * BEAT * SR)
        if note == "-":                                   # سكتة
            parts.append(np.zeros(n)); continue
        raw = _glottal(NOTE[note], n)
        voiced = _formant_filter(raw, VOWELS[vowel])
        breath = np.random.default_rng(0).normal(0, 0.004, n)   # همس خفيف
        parts.append((voiced + breath) * _adsr(n, 0.03, 0.12, 0.75, 0.22))
    sig = np.concatenate(parts)
    return sig / (np.max(np.abs(sig)) or 1) * 0.62


def build_chords(progression: list[tuple[list[str], float]]) -> np.ndarray:
    parts = []
    for notes, beats in progression:
        n = int(beats * BEAT * SR)
        t = np.arange(n) / SR
        chord = np.zeros(n)
        for note in notes:
            f = NOTE[note]
            for h, amp in ((1, 1.0), (2, 0.34), (3, 0.16), (4, 0.09)):
                det = 1 + (h * 0.0008)                    # detune خفيف = دفء
                chord += amp * np.sin(2 * np.pi * f * h * det * t)
        parts.append(chord / len(notes) * _adsr(n, 0.01, 0.45, 0.45, 0.5))
    sig = np.concatenate(parts)
    return sig / (np.max(np.abs(sig)) or 1) * 0.40


def build_bass(roots: list[tuple[str, float]]) -> np.ndarray:
    parts = []
    for note, beats in roots:
        n = int(beats * BEAT * SR)
        t = np.arange(n) / SR
        f = NOTE[note] / 2
        sig = (np.sin(2 * np.pi * f * t) + 0.28 * np.sin(4 * np.pi * f * t))
        parts.append(sig * _adsr(n, 0.005, 0.2, 0.6, 0.15))
    sig = np.concatenate(parts)
    return sig / (np.max(np.abs(sig)) or 1) * 0.45


def build_drums(total_beats: float) -> np.ndarray:
    n = int(total_beats * BEAT * SR)
    out = np.zeros(n)
    rng = np.random.default_rng(7)

    def place(pos_beats: float, sound: np.ndarray):
        i = int(pos_beats * BEAT * SR)
        end = min(n, i + len(sound))
        if i < n:
            out[i:end] += sound[:end - i]

    # كيك: تمشيط ترددي هابط
    kn = int(0.16 * SR); kt = np.arange(kn) / SR
    kick = np.sin(2 * np.pi * (145 * np.exp(-kt * 26) + 45) * kt) * np.exp(-kt * 17) * 0.9
    # سنير: ضجيج مُغلَّف
    sn = int(0.14 * SR); st = np.arange(sn) / SR
    snare = rng.normal(0, 1, sn) * np.exp(-st * 26) * 0.32
    # هاي هات
    hn = int(0.05 * SR); ht = np.arange(hn) / SR
    hat = rng.normal(0, 1, hn) * np.exp(-ht * 95) * 0.14

    b = 0.0
    while b < total_beats:
        place(b, kick)
        place(b + 2, snare)
        for k in range(4):
            place(b + k * 0.5, hat)
        b += 4
    return out


def _stereo(mono: np.ndarray, width: float = 0.0, length: int | None = None) -> np.ndarray:
    """يحوّل إلى ستيريو مع اتساع اختياري (تأخير بسيط)، ويضبط الطول."""
    if length is not None:
        mono = np.pad(mono, (0, max(0, length - len(mono))))[:length]
    if width <= 0:
        return np.stack([mono, mono])
    d = int(width * SR)
    left = np.pad(mono, (d, 0))[:len(mono)]
    right = np.pad(mono, (0, d))[d:len(mono) + d]
    right = np.pad(right, (0, len(mono) - len(right)))
    return np.stack([left, right])


def build_demo(out_dir: str | Path = None) -> Path:
    """يبني الخليط والأجزاء المرجعية ويعيد مسار الخليط."""
    out_dir = Path(out_dir or Path(__file__).parent)
    out_dir.mkdir(parents=True, exist_ok=True)

    # تقدّم كوردي I–V–vi–IV مكرّر مرتين (٣٢ نبضة ≈ ٢١ ثانية)
    prog = [(["C4", "E4", "G4"], 4), (["G3", "B3", "D4"], 4),
            (["A3", "C4", "E4"], 4), (["F3", "A3", "C4"], 4)] * 2
    roots = [("C4", 4), ("G3", 4), ("A3", 4), ("F3", 4)] * 2
    melody = [
        ("E4", 1, "a"), ("G4", 1, "e"), ("A4", 2, "a"),
        ("G4", 1, "o"), ("E4", 1, "a"), ("D4", 2, "i"),
        ("C4", 1, "u"), ("E4", 1, "a"), ("G4", 2, "e"),
        ("F4", 1, "o"), ("E4", 1, "a"), ("C4", 2, "a"),
        ("-", 1, "a"), ("G4", 1, "a"), ("A4", 2, "e"),
        ("G4", 2, "o"), ("E4", 2, "a"),
        ("D4", 1, "i"), ("E4", 1, "a"), ("G4", 2, "e"),
        ("E4", 2, "a"), ("C4", 2, "u"),
    ]

    total_beats = sum(b for _, b in roots)
    length = int(total_beats * BEAT * SR)

    vocal = _stereo(build_vocal(melody), width=0.0, length=length)
    chords = _stereo(build_chords(prog), width=0.012, length=length)
    bass = _stereo(build_bass(roots), width=0.0, length=length)
    drums = _stereo(build_drums(total_beats), width=0.004, length=length)

    instrumental = chords + bass + drums
    mix = vocal + instrumental
    peak = float(np.max(np.abs(mix))) or 1.0
    scale = 0.89 / peak
    mix, vocal, instrumental = mix * scale, vocal * scale, instrumental * scale

    paths = {
        "demo_mix": mix,
        "reference_vocals": vocal,
        "reference_instrumental": instrumental,
    }
    for name, audio in paths.items():
        sf.write(str(out_dir / f"{name}.wav"), audio.T.astype(np.float32), SR, subtype="PCM_24")

    return out_dir / "demo_mix.wav"


if __name__ == "__main__":
    p = build_demo()
    print(f"تم إنشاء العيّنة: {p}")
    print("الأجزاء المرجعية بجانبها: reference_vocals.wav / reference_instrumental.wav")
