# SoundIsolator — صورة الاستضافة (Render وما شابه)، نسخة CPU فقط.
FROM python:3.11-slim

# ffmpeg لفكّ/ترميز الوسائط، git لتثبيت Demucs من مستودعه مباشرة.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# طبقة المتطلبات منفصلة عن الكود حتى يُعاد استخدام كاش pip بين عمليات النشر.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY src/ src/
COPY demo/ demo/

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
