"""
سطر الأوامر — SoundIsolator CLI.

أمثلة:
    python src/cli.py "D:/Music/song.mp3"
    python src/cli.py song.mp3 --model roformer_bs --stems vocals --format flac24
    python src/cli.py clip.mp4 --stems instrumental --remux
    python src/cli.py --folder "D:/Album" --model mdx23c --format mp3_320
    python src/cli.py --list-models
    python src/cli.py --demo
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import (ROOT, Settings, collect_media, gpu_info, separate_batch,  # noqa: E402
                    separate_file)
from models import BY_KEY, FORMAT_LABELS, REGISTRY, STEM_MODES  # noqa: E402


def bar(frac: float, msg: str) -> None:
    width = 34
    filled = int(width * min(max(frac, 0.0), 1.0))
    sys.stdout.write(f"\r[{'█' * filled}{'░' * (width - filled)}] {frac*100:5.1f}%  {msg[:52]:<52}")
    sys.stdout.flush()
    if frac >= 1.0:
        sys.stdout.write("\n")


def list_models() -> None:
    print("\n  المفتاح              المحرك    الأجزاء                        الجودة  السرعة  VRAM")
    print("  " + "─" * 92)
    for m in REGISTRY:
        print(f"  {m.key:<20} {m.backend:<8}  {'+'.join(m.stems)[:28]:<28}  "
              f"{'★'*m.quality:<6}  {'★'*m.speed:<6}  {m.vram_gb}GB")
        print(f"  {'':<20} {m.label}")
    print("\n  أوضاع العزل:", ", ".join(f"{k} ({v})" for k, v in STEM_MODES.items()))
    print("  الصيغ:", ", ".join(FORMAT_LABELS))
    print(f"\n  الجهاز: {gpu_info()}\n")


def main() -> int:
    p = argparse.ArgumentParser(
        prog="SoundIsolator",
        description="عزل الصوت عن الأغاني والفيديوهات باستخدام نماذج التعلّم العميق.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)

    p.add_argument("input", nargs="?", help="ملف صوت أو فيديو")
    p.add_argument("--folder", help="عالج كل ملفات مجلد")
    p.add_argument("-r", "--recursive", action="store_true", help="اشمل المجلدات الفرعية")
    p.add_argument("-o", "--out", default=str(ROOT / "outputs"), help="مجلد الإخراج")

    p.add_argument("-m", "--model", default="mdx23c", choices=list(BY_KEY), help="النموذج")
    p.add_argument("-s", "--stems", default="both", choices=list(STEM_MODES), help="ماذا تستخرج")
    p.add_argument("-f", "--format", dest="fmt", default="wav24",
                   choices=list(FORMAT_LABELS), help="صيغة الإخراج")
    p.add_argument("--sr", type=int, default=44100, choices=[0, 44100, 48000],
                   help="معدل العينات (0 = مثل المصدر)")

    p.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    p.add_argument("--segment", type=float, default=7.0, help="طول المقطع بالثواني")
    p.add_argument("--overlap", type=float, default=0.25, help="تداخل المقاطع 0.05–0.75")
    p.add_argument("--shifts", type=int, default=1, help="مستوى الدقة 1–10")
    p.add_argument("--batch", type=int, default=1, help="حجم الدفعة لنماذج UVR")
    p.add_argument("--jobs", type=int, default=0, help="خيوط المعالج")
    p.add_argument("--threshold", type=float, default=0.9, help="عتبة التسوية الداخلية")

    p.add_argument("--no-residual", action="store_true", help="لا تستخرج العكس بالطرح الطوري")
    p.add_argument("--normalize", action="store_true", help="سوِّ الذروة")
    p.add_argument("--peak", type=float, default=-0.3, help="ذروة الهدف dBFS")
    p.add_argument("--remux", action="store_true", help="أعد تركيب الناتج داخل الفيديو")

    p.add_argument("--list-models", action="store_true", help="اعرض النماذج المتاحة")
    p.add_argument("--demo", action="store_true", help="ولّد عينة تجريبية واعزلها")

    a = p.parse_args()

    if a.list_models:
        list_models()
        return 0

    st = Settings(
        model=a.model, stem_mode=a.stems, output_format=a.fmt, sample_rate=a.sr,
        device=a.device, segment=a.segment, overlap=a.overlap, shifts=a.shifts,
        jobs=a.jobs, batch_size=a.batch, residual_instrumental=not a.no_residual,
        normalize=a.normalize, peak_dbfs=a.peak, denoise_threshold=a.threshold,
        remux_video=a.remux,
    )

    target = a.input
    if a.demo:
        sys.path.insert(0, str(ROOT / "demo"))
        from make_demo import build_demo
        target = str(build_demo(ROOT / "demo"))
        print(f"عينة تجريبية: {target}")

    print(f"الجهاز: {gpu_info()}")
    print(f"النموذج: {BY_KEY[a.model].label}\n")

    if a.folder:
        files = collect_media(a.folder, a.recursive)
        if not files:
            print("لم يُعثر على ملفات وسائط."); return 1
        print(f"عدد الملفات: {len(files)}\n")
        results = separate_batch(files, st, a.out, bar)
        ok = sum(1 for r in results if r.files)
        print(f"\nانتهى: {ok}/{len(results)} ناجحة → {a.out}")
        for r in results:
            if not r.files:
                print(f"  ❌ {Path(r.input_path).name}: {r.log[-1] if r.log else ''}")
        return 0 if ok else 1

    if not target:
        p.print_help(); return 1

    try:
        res = separate_file(target, st, a.out, bar)
    except Exception as exc:
        print(f"\n❌ {exc}"); return 1

    print()
    for line in res.log:
        print(f"  · {line}")
    print(f"\n  المجلد: {res.output_dir}")
    for k, v in res.files.items():
        print(f"    {k:<14} → {Path(v).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
