#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""وب‌سرور دسکتاپ/سرور برای موتور manga.py — همان وب‌سرور داخل اپ اندروید.

سه سکو، یک موتور (v1.21):
  • اندروید  → APK با ML Kit سبک
  • دسکتاپ  → این فایل (python run_server.py) → مرورگر
  • سرور    → python run_server.py --host 0.0.0.0 --port 8080
روی PC نیازی به ML Kit نیست — موتور خودش RapidOCR/PaddleOCR را برمی‌دارد
(تشخیص خودکار اندروید از طریق ماژول java چاکوپی).

استفاده:
    python run_server.py                       # http://127.0.0.1:8080
    python run_server.py --port 9000 --dir ./data
    python run_server.py --host 0.0.0.0        # باز روی شبکه (سرور)
"""
import argparse
import os
import sys
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))

# ۱) ریشه ریپو — manga.py / manga_app.py اینجا هستند (اولویت اول)
sys.path.insert(0, HERE)

# ۲) بسته‌های همراه اپ اندروید (openai، httpx، rapidocr و…) به‌عنوان پشتیبان
_PYDIR = os.path.join(HERE, "android", "app", "src", "main", "python")
if os.path.isdir(_PYDIR):
    sys.path.append(_PYDIR)

import app_server  # noqa: E402  — Handler و _run_job از همین‌جا


def main():
    ap = argparse.ArgumentParser(description="وب‌سرور مانگا مترجم")
    ap.add_argument("--host", default="127.0.0.1",
                    help="آدرس bind (پیش‌فرض فقط لوکال؛ برای سرور 0.0.0.0)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--dir", default=os.path.join(HERE, "data"),
                    help="پوشه کاری (ورودی/خروجی/مدل‌ها)")
    a = ap.parse_args()
    os.makedirs(a.dir, exist_ok=True)
    os.environ["MANGA_FILES_DIR"] = a.dir
    httpd = ThreadingHTTPServer((a.host, a.port), app_server.Handler)
    print("=" * 56)
    print(f"  مانگا مترجم {app_server.APP_VER} — وب‌سرور")
    print(f"  آدرس:  http://{a.host}:{a.port}"
          + ("  (فقط همین سیستم)" if a.host == "127.0.0.1" else "  (روی شبکه)"))
    print(f"  پوشه کاری: {a.dir}")
    print("  توقف: Ctrl+C")
    print("=" * 56)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nوب‌سرور بسته شد.")


if __name__ == "__main__":
    main()
