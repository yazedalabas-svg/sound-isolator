# نشر SoundIsolator على Render

## قبل أن تبدأ — اقرأ هذا

هذا البرنامج يشغّل نماذج تعلّم عميق ثقيلة (Demucs، UVR، Roformer). محليًا
على جهازك يستخدم كرت شاشة (GTX 1650). **Render القياسي لا يوفّر GPU**،
فكل شيء سيعمل على المعالج فقط. هذا يعني:

| الأمر | محليًا (GPU) | على Render (CPU) |
|---|---|---|
| أسرع نموذج (`kim_vocal_2`) لأغنية ٤ دقائق | ~8 ثوانٍ | **~10 دقائق** |
| الذاكرة اللازمة | 4 GB VRAM | **≥ 2GB RAM عادية** (خطة starter بـ 512MB قد لا تكفي) |
| تنزيل النموذج عند أول استخدام | مرة واحدة، يبقى على القرص | **يتكرر بعد كل نشر جديد** ما لم تُفعّل قرصًا دائمًا |

البرنامج **يختار تلقائيًا أسرع نموذج متاح** لأي ملف أطول من دقيقة تقريبًا
(انظر `AUTO_TIME_BUDGET_S` في [src/engine.py](src/engine.py)) — هذا يخفّف
المشكلة لكن لا يلغيها. لم أختبر هذا فعليًا على Render (لا حساب ولا Docker
لديّ في بيئة البناء) — اختبرته محليًا فقط عبر محاكاة `PORT`/`0.0.0.0`.

---

## الخطوات

### ١. ارفع المستودع إلى GitHub

```bash
cd D:\SoundIsolator
git init
git add .
git commit -m "SoundIsolator"
git branch -M main
git remote add origin https://github.com/<اسمك>/sound-isolator.git
git push -u origin main
```

`.gitignore` يستثني `.venv/` و`cache/` و`outputs/` و`models/` تلقائيًا —
لن تُرفع بيئتك المحلية الثقيلة، فقط الكود.

### ٢. أنشئ خدمة على Render

**عبر Blueprint (الأسهل):** من لوحة Render اختر **New → Blueprint**، اختر
مستودعك. Render يقرأ [render.yaml](render.yaml) ويهيّئ الخدمة تلقائيًا
(Docker، منفذ، قرص دائم لكاش النماذج).

**يدويًا إن فضّلت:** New → Web Service → اختر المستودع →
- **Runtime:** Docker
- **Plan:** starter كحد أدنى (فكّر بـ standard إن ظهر خطأ ذاكرة)
- لا حاجة لضبط Start Command — `Dockerfile` يحدّده

### ٣. (اختياري لكن مهم) اربط قرصًا دائمًا

بدون قرص دائم، كل نشر جديد يمسح النماذج المُنزَّلة فيُعيد Render تنزيلها
من الصفر (بطيء وقد يستهلك حصة الشبكة). Blueprint يفعل هذا تلقائيًا
(`/app/cache`، 5GB). يدويًا: **Disks → Add Disk** بنفس المسار.

### ٤. افتح الرابط

Render يعطيك رابطًا مثل `https://sound-isolator.onrender.com`. أول طلب
بعد كل نشر بطيء (تنزيل النموذج) — طبيعي.

---

## الترقية إلى GPU (اختياري)

Render يوفّر خططًا بكرت شاشة على بعض المناطق (أغلى بكثير). لو رقّيت:
1. غيّر `requirements.txt` ليستخدم عجلات CUDA:
   ```
   --index-url https://download.pytorch.org/whl/cu124
   torch==2.5.1+cu124
   torchvision==0.20.1+cu124
   torchaudio==2.5.1+cu124
   ```
   واستبدل `audio-separator[cpu]` بـ `audio-separator[gpu]`
   و`onnxruntime==1.20.2` بـ `onnxruntime-gpu==1.20.2`.
2. في `Dockerfile` استخدم صورة أساس تدعم CUDA (`nvidia/cuda:12.4.1-runtime-ubuntu22.04`)
   بدل `python:3.11-slim`، وثبّت Python عليها يدويًا.

لم أبنِ هذا المسار افتراضيًا لأن أغلب حسابات Render التجريبية بلا GPU.

---

## استكشاف الأخطاء

| العرض | السبب المرجّح | الحل |
|---|---|---|
| الخدمة تتوقف بلا رسالة واضحة (Exit code 137) | نفاد الذاكرة | ارفع الخطة إلى standard (2GB+) |
| كل طلب بطيء جدًا حتى لو الملف قصير | لا قرص دائم، كل مرة تنزيل من جديد | فعّل القرص الدائم (الخطوة ٣) |
| `ffmpeg not found` | فشل بناء الصورة قبل نسخ الملفات | تحقّق من سجلّ البناء في Render |
| زر "افتح مجلد النتائج" مفقود | متعمَّد | لا معنى لفتح مستكشف ملفات على خادم سحابي |
