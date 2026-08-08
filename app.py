"""
نقطة الدخول للاستضافة السحابية (Render وغيرها).

Render وأغلب المنصّات تبحث عن `app.py` في جذر المستودع وتشغّله بأمر
مثل `python app.py`. المنطق الفعلي كله في src/simple.py — وهو نفسه
يكتشف متغيّر البيئة PORT ويتصرّف تلقائيًا (استضافة أو تشغيل محلي)،
فهذا الملف مجرّد جسر رفيع.

محليًا استخدم run.bat بدلًا من هذا الملف.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import simple  # noqa: E402

if __name__ == "__main__":
    simple.main()
