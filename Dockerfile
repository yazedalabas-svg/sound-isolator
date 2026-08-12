# SoundIsolator — صورة الاستضافة (Render وما شابه)، نسخة CPU فقط.
FROM python:3.11-slim

# ffmpeg لفكّ/ترميز الوسائط، git لتثبيت Demucs من مستودعه مباشرة،
# build-essential (gcc) لأن audio-separator يفرض diffq العادية على أي
# نظام غير ويندوز (raw diffq>=0.2; sys_platform != "win32") — وهذه
# لا تملك عجلة جاهزة لبايثون 3.11 على لينكس فتُبنى من المصدر. رؤوس
# بايثون نفسها موجودة مسبقًا في هذه الصورة، الناقص كان المترجم فقط.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg git build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# طبقة المتطلبات منفصلة عن الكود حتى يُعاد استخدام كاش pip بين عمليات النشر.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir --no-deps "git+https://github.com/adefossez/demucs.git"

COPY app.py .
COPY src/ src/
COPY demo/ demo/

# نموذج الاستضافة الافتراضي (Kim_Vocal_2.onnx) يُنزَّل هنا وقت البناء بدل
# وقت أول طلب حقيقي. لاحظنا تعليقًا فعليًا على Render — أكثر من 150 ثانية
# بلا أي تقدّم أثناء تنزيله وقت التشغيل (على الأغلب اتصال الحاوية الحيّة
# بالإنترنت أبطأ/أقل ثباتًا من بيئة البناء). الحجم صغير (~64MB) فتضمينه في
# الصورة لا يُثقلها كثيرًا، ويُزيل هذا الاعتماد الشبكي الهش وقت التشغيل كليًا.
RUN python -c "\
import sys, logging; sys.path.insert(0, 'src'); \
from audio_separator.separator import Separator; \
s = Separator(model_file_dir='models', output_dir='/tmp', log_level=logging.WARNING); \
s.load_model(model_filename='Kim_Vocal_2.onnx'); \
print('pre-cached Kim_Vocal_2.onnx OK')"

# كل الكاشات داخل /app حتى لا تكتب خارج الحاوية.
ENV GRADIO_ANALYTICS_ENABLED=False \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    TORCH_HOME=/app/cache/torch \
    HF_HOME=/app/cache/hf \
    XDG_CACHE_HOME=/app/cache \
    PORT=7860

# قيمة افتراضية للاختبار المحلي بـ docker run — Render يضبط PORT فعليًا وقت التشغيل.
EXPOSE 7860

CMD ["python", "app.py"]
