"""
الواجهة الرسومية — SoundIsolator GUI (Gradio).

تشغيل:  run.bat    أو    .venv\\Scripts\\python src\\gui.py
تفتح على http://127.0.0.1:7860 محليًا بالكامل — لا يُرفع أي ملف إلى الإنترنت.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).resolve().parent))

import engine
from engine import ROOT, Settings, collect_media, gpu_info, probe, separate_batch, separate_file
from models import BY_KEY, FORMAT_LABELS, REGISTRY, STEM_MODES

MODEL_CHOICES = [(m.label, m.key) for m in REGISTRY]
STEM_CHOICES = [(v, k) for k, v in STEM_MODES.items()]
FORMAT_CHOICES = [(v, k) for k, v in FORMAT_LABELS.items()]

CSS = """
.gradio-container {direction: rtl; font-family: 'Segoe UI', Tahoma, sans-serif;}
footer {display: none !important;}
#title {text-align: center;}
.log-box textarea {direction: ltr; text-align: left; font-family: Consolas, monospace; font-size: 12px;}
"""


def _settings(model, stem_mode, out_fmt, sr, device, segment, overlap,
              shifts, jobs, batch, residual, normalize, peak, thresh, remux) -> Settings:
    return Settings(
        model=model, stem_mode=stem_mode, output_format=out_fmt,
        sample_rate=int(sr), device=device, segment=float(segment),
        overlap=float(overlap), shifts=int(shifts), jobs=int(jobs),
        batch_size=int(batch), residual_instrumental=bool(residual),
        normalize=bool(normalize), peak_dbfs=float(peak),
        denoise_threshold=float(thresh), remux_video=bool(remux),
    )


def on_model_change(key: str):
    m = BY_KEY[key]
    stars = lambda n: "★" * n + "☆" * (5 - n)
    md = (
        f"**{m.label}**\n\n"
        f"- المحرك: `{m.backend}` · الملف: `{m.model_id}`\n"
        f"- الأجزاء: {' ، '.join(m.stems)}\n"
        f"- الجودة: {stars(m.quality)} · السرعة: {stars(m.speed)} · "
        f"ذاكرة الكرت المتوقعة: ~{m.vram_gb} GB\n\n"
        f"{m.note}"
    )
    if m.vram_gb > 3.2:
        md += "\n\n⚠️ كرتك 4 GB — إن ظهر خطأ ذاكرة، قلّل «طول المقطع» أو حوّل الجهاز إلى CPU."
    return md


def on_file(path):
    if not path:
        return "لم يُختَر ملف."
    try:
        info = probe(path)
        kind = "فيديو 🎬" if info["has_video"] else "صوت 🎵"
        return (f"**{Path(path).name}** — {kind}\n\n"
                f"المدة {info['duration']:.1f}s · {info['sample_rate']} Hz · "
                f"{info['channels']} قناة · {info['codec']} · {info['size_mb']} MB")
    except Exception as exc:
        return f"❌ {exc}"


def run_single(file_path, *cfg, progress=gr.Progress()):
    if not file_path:
        raise gr.Error("اختر ملفًا أولًا.")
    st = _settings(*cfg)

    def cb(frac, msg):
        progress(min(max(frac, 0.0), 1.0), desc=msg)

    try:
        res = separate_file(file_path, st, progress=cb)
    except Exception as exc:
        raise gr.Error(f"{exc}") from exc

    audios = [gr.update(value=p, label=f"🔊 {k}", visible=True)
              for k, p in list(res.files.items())[:6] if not p.endswith(".mp4")]
    audios += [gr.update(visible=False)] * (6 - len(audios))

    report = ["✅ **تم العزل بنجاح**", "", *[f"- {l}" for l in res.log], "",
              f"- الجهاز: `{res.device_used}`", f"- المجلد: `{res.output_dir}`", "",
              "**الملفات:**", *[f"  - `{k}` → {Path(v).name}" for k, v in res.files.items()]]
    return (*audios, "\n".join(report), list(res.files.values()))


def run_batch(folder, recursive, *cfg, progress=gr.Progress()):
    if not folder or not Path(folder).is_dir():
        raise gr.Error("أدخل مسار مجلد صحيح.")
    files = collect_media(folder, recursive)
    if not files:
        raise gr.Error("لم يُعثر على ملفات وسائط في المجلد.")

    def cb(frac, msg):
        progress(min(max(frac, 0.0), 1.0), desc=msg)

    results = separate_batch(files, _settings(*cfg), progress=cb)
    ok = sum(1 for r in results if r.files)
    lines = [f"### انتهت المعالجة: {ok}/{len(results)} ناجحة", ""]
    for r in results:
        mark = "✅" if r.files else "❌"
        lines.append(f"{mark} **{Path(r.input_path).name}** — {r.log[-1] if r.log else ''}")
    return "\n".join(lines)


def make_demo():
    """يولّد مقطعًا تجريبيًا مركّبًا (غناء صناعي + موسيقى) لاختبار البرنامج فورًا."""
    sys.path.insert(0, str(ROOT / "demo"))
    from make_demo import build_demo
    path = build_demo(ROOT / "demo")
    return str(path), f"✅ أُنشئت العينة: `{path}`\n\nاضغط **ابدأ العزل** لتجربتها."


with gr.Blocks(title="SoundIsolator — عازل الصوت الاحترافي", css=CSS,
               theme=gr.themes.Soft(primary_hue="indigo")) as demo:

    gr.Markdown("# 🎚️ SoundIsolator — عزل الصوت عن الأغاني", elem_id="title")
    gr.Markdown(f"**كرت الشاشة:** {gpu_info()}  |  المعالجة محلية بالكامل، لا يخرج أي ملف من جهازك.")

    with gr.Row():
        # ─────────── العمود الأيمن: الإعدادات ───────────
        with gr.Column(scale=1):
            gr.Markdown("### ١) النموذج ووضع العزل")
            model = gr.Dropdown(MODEL_CHOICES, value="mdx23c", label="تقنية العزل")
            model_info = gr.Markdown(on_model_change("mdx23c"))
            stem_mode = gr.Radio(STEM_CHOICES, value="both", label="ماذا تريد أن تستخرج؟")

            gr.Markdown("### ٢) الإخراج")
            out_fmt = gr.Dropdown(FORMAT_CHOICES, value="wav24", label="صيغة الملف الناتج")
            sr = gr.Dropdown([("مثل المصدر", 0), ("44100 Hz", 44100), ("48000 Hz", 48000)],
                             value=44100, label="معدل العينات")
            remux = gr.Checkbox(False, label="أعد تركيب الناتج داخل الفيديو الأصلي (للفيديوهات)")

            with gr.Accordion("### ٣) تحكم متقدّم", open=False):
                device = gr.Radio([("تلقائي", "auto"), ("كرت الشاشة CUDA", "cuda"), ("المعالج CPU", "cpu")],
                                  value="auto", label="جهاز المعالجة")
                segment = gr.Slider(2, 20, value=7, step=0.5,
                                    label="طول المقطع (ثانية) — أصغر = ذاكرة أقل")
                overlap = gr.Slider(0.05, 0.75, value=0.25, step=0.05,
                                    label="تداخل المقاطع — أعلى = انتقالات أنعم وأبطأ")
                shifts = gr.Slider(1, 10, value=1, step=1,
                                   label="مستوى الدقة (shifts / TTA) — كل زيادة تضاعف الوقت وتحسّن الدقة")
                batch = gr.Slider(1, 8, value=1, step=1, label="حجم الدفعة (UVR) — ارفعه لو الذاكرة تسمح")
                jobs = gr.Slider(0, 16, value=0, step=1, label="خيوط المعالج (0 = تلقائي)")
                thresh = gr.Slider(0.1, 1.0, value=0.9, step=0.05,
                                   label="عتبة التسوية الداخلية (UVR) — خفّضها لو ظهر تشويه")
                residual = gr.Checkbox(True, label="استخراج «العكس» بالطرح الطوري (موسيقى = الأصل − الغناء)")
                normalize = gr.Checkbox(False, label="تسوية الذروة")
                peak = gr.Slider(-6, 0, value=-0.3, step=0.1, label="ذروة الهدف (dBFS)")

        # ─────────── العمود الأيسر: التشغيل ───────────
        with gr.Column(scale=1):
            with gr.Tab("ملف واحد"):
                inp = gr.Audio(label="أفلت ملفًا صوتيًا هنا", type="filepath", sources=["upload"])
                gr.Markdown("للفيديو (MP4/MOV/MKV) استخدم الحقل التالي:")
                vid = gr.File(label="أو ارفع ملف فيديو / أي صيغة",
                              file_types=[f".{e}" for e in
                                          ["mp4", "mov", "mkv", "avi", "webm", "flac", "m4a", "opus", "wma", "aiff"]],
                              type="filepath")
                meta = gr.Markdown("لم يُختَر ملف.")
                with gr.Row():
                    demo_btn = gr.Button("🎼 أنشئ عينة تجريبية")
                    run_btn = gr.Button("▶️ ابدأ العزل", variant="primary", scale=2)

                players = [gr.Audio(label=f"مخرج {i+1}", visible=False, interactive=False)
                           for i in range(6)]
                report = gr.Markdown()
                downloads = gr.File(label="⬇️ تنزيل النتائج", file_count="multiple", visible=True)

            with gr.Tab("معالجة مجلد كامل"):
                folder = gr.Textbox(label="مسار المجلد", placeholder=r"D:\Music\Album")
                recursive = gr.Checkbox(True, label="اشمل المجلدات الفرعية")
                batch_btn = gr.Button("▶️ عالج كل الملفات", variant="primary")
                batch_report = gr.Markdown()

            with gr.Tab("شرح سريع"):
                gr.Markdown(r"""
#### كيف يعمل؟
1. **فك الترميز** — يحوّل ffmpeg أي ملف (صوت أو فيديو) إلى WAV غير مضغوط، فلا يبدأ النموذج من مصدر متضرّر.
2. **الفصل** — الشبكة تحوّل الإشارة إلى تمثيل طيفي (Spectrogram) وتتعلّم *قناعًا* لكل جزء،
   ثم تعيد تركيب الموجة. نماذج Roformer تعمل على نطاقات ميل مع Attention، ولهذا تتفوّق على الأقنعة التقليدية.
3. **العكس (الطرح الطوري)** — الموسيقى = الخليط الأصلي − الغناء المعزول، في نطاق الزمن.
   هذا يحافظ على كامل الطيف بلا تلوين، بدل توليد الموسيقى من الصفر.
4. **الإخراج** — كتابة بلا فقد (WAV/FLAC 24-bit) أو ترميز مضغوط عبر ffmpeg.

#### أي نموذج أختار؟
| الهدف | النموذج |
|---|---|
| أنظف غناء ممكن | **BS-Roformer** |
| موسيقى بلا بقايا غناء (كاريوكي) | **UVR-MDX-NET Inst HQ 3** |
| توازن جودة/سرعة على كرت 4GB | **MDX23C** |
| فصل الطبول والباص والآلات | **Demucs htdemucs_ft** |
| إزالة صدى من غناء معزول | **DeEcho-DeReverb** |

#### نصائح لكرت 4 GB
- ابدأ بـ **MDX23C** وطول مقطع **7s**.
- لو ظهر خطأ ذاكرة: البرنامج يقلّل المقطع تلقائيًا ثم ينتقل للمعالج.
- ارفع **مستوى الدقة** إلى 2–3 فقط عند إخراج نهائي — الفرق مسموع لكن الوقت يتضاعف.

#### تسلسل احترافي للنتيجة القصوى
`BS-Roformer` لاستخراج الغناء ← ثم مرّر الغناء على `DeEcho-DeReverb` ← ثم `Karaoke 6_HP` لفصل الكورال.
""")

    # ─────────── الربط ───────────
    CFG = [model, stem_mode, out_fmt, sr, device, segment, overlap,
           shifts, jobs, batch, residual, normalize, peak, thresh, remux]

    model.change(on_model_change, model, model_info)
    inp.change(on_file, inp, meta)
    vid.change(on_file, vid, meta)

    def _pick(a, b):
        return b or a

    src_state = gr.State()
    demo_btn.click(make_demo, None, [inp, report])
    run_btn.click(_pick, [inp, vid], src_state).then(
        run_single, [src_state, *CFG], [*players, report, downloads])
    batch_btn.click(run_batch, [folder, recursive, *CFG], batch_report)


if __name__ == "__main__":
    from simple import free_port
    demo.queue(max_size=8).launch(server_name="127.0.0.1", server_port=free_port(7870),
                                  inbrowser=True, show_api=False, share=False)
