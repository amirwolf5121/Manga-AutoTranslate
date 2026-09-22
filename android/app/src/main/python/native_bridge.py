# -*- coding: utf-8 -*-
"""لایه پایدار پل اندروید — MainActivity به این وصل است، نه مستقیم به bridge.

چرا این فایل وجود دارد؟
  اپ در هر اجرا manga.py / manga_app.py / bridge.py / extract_ui.py را از ریپو
  آپدیت می‌کند (UPDATE_FILES). یعنی هر فیکسی داخل bridge.py بنویسیم، با اولین
  آپدیت ریپو پاک می‌شود. این ماژول در آن لیست نیست → پایدار است و:

  ۱) health(): اگر manga.py یا manga_app.py خراب باشد، کامل می‌گوید «کدام فایل»
     خرابه + traceback کامل + وضعیت فایل‌ها (درخواست کاربر).
  ۲) Ollama لوکال: بدون توکن کار می‌کند، فقط روی همین دستگاه (آدرس پیش‌فرض localhost:11434) —
     مدل به‌صورت خودکار از خود Ollama کشف می‌شود و قطع‌بودن اتصال پیام واضح
     فارسی می‌دهد — بدون هیچ تغییر در manga.py.
  ۳) manifest(): منیفست UI را از manga_app.py برمی‌گرداند (فیلد آدرس Ollama در v1.22 حذف شد).
  ۴) start_job(): فایل ورودی بی‌پسوند (pick گالری) را قبل از موتور اصلاح می‌کند.

همه توابع bridge (manifest/start_job/poll/cancel) از اینجا delegate می‌شوند.
"""
import json
import os
import shutil
import traceback

# ---------------------------------------------------------------- فیکس پسوند
_IMG_MAGICS = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"BM", ".bmp"),
    (b"PK\x03\x04", ".zip"),
    (b"PK\x05\x06", ".zip"),
    (b"%PDF", ".pdf"),
)
_ACCEPTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".zip", ".pdf"}


def _fix_input_ext(path):
    """پسوند فایل ورودی بی‌پسوند (pick گالری اندروید) را درست می‌کند."""
    try:
        if not path or "://" in path or not os.path.isfile(path):
            return path
        ext = os.path.splitext(path)[1].lower()
        if ext in _ACCEPTED_EXTS:
            return path
        with open(path, "rb") as f:
            head = f.read(16)
        fixed = ""
        for magic, e in _IMG_MAGICS:
            if head.startswith(magic):
                fixed = e
                break
        if not fixed and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            fixed = ".webp"
        if not fixed:
            try:
                from PIL import Image
                with Image.open(path) as im:
                    fmt = (im.format or "").lower()
                if fmt == "jpeg":
                    fmt = "jpg"
                if fmt in ("png", "jpg", "webp", "bmp", "gif"):
                    fixed = "." + fmt
            except Exception:
                return path
        if not fixed:
            return path
        base = os.path.basename(path).replace(":", "_")
        new_path = os.path.join(os.path.dirname(path), base + fixed)
        if os.path.abspath(new_path) == os.path.abspath(path):
            return path
        shutil.copyfile(path, new_path)
        return new_path
    except Exception:
        return path


# ---------------------------------------------------------------- health
_ENGINE_FILES = ("manga.py", "manga_app.py", "bridge.py", "extract_ui.py",
                 "app_server.py")


def _files_dir():
    return os.environ.get("MANGA_FILES_DIR") or os.getcwd()


def _syntax_check(path):
    """None = سالم؛ str = پیام خطای سینتکس."""
    try:
        with open(path, "rb") as f:
            src = f.read()
        try:
            compile(src, path, "exec")
        except SyntaxError as e:
            return "خطای سینتکس خط %s: %s" % (e.lineno, e.msg)
        except Exception as e:
            return "%s: %s" % (type(e).__name__, e)
    except Exception as e:
        return "خواندن ناموفق: %s" % e
    return None


def health():
    """گزارش کامل سلامت موتور — Kotlin در شروع اپ صدا می‌زند.

    خروجی: {"ok": bool, "report": str}
    اگر manga.py / manga_app.py / bridge.py خراب باشد، «کدام فایل» خرابه +
    traceback کامل + وضعیت همه فایل‌های موتور را می‌گوید.
    """
    files_dir = _files_dir()
    upd = os.path.join(files_dir, "updates")
    lines = []
    ok = True

    # ۱) وضعیت فایل‌ها: موجود بودن، اندازه، سینتکس
    lines.append("📋 وضعیت فایل‌های موتور (updates):")
    for n in _ENGINE_FILES:
        p = os.path.join(upd, n)
        if not os.path.isfile(p):
            lines.append("  • %s — نیست (از داخل APK استفاده می‌شود)" % n)
            continue
        size = os.path.getsize(p)
        if size < 1000:
            ok = False
            lines.append("  • %s — ❌ خراب (فقط %d بایت)" % (n, size))
            continue
        err = _syntax_check(p)
        if err:
            ok = False
            lines.append("  • %s — ❌ %s" % (n, err))
        else:
            lines.append("  • %s — ✔ سالم (%.1f KB)" % (n, size / 1024.0))

    # ۲) تست import واقعی — مقصر را دقیق نام می‌برد
    culprit = None
    tb_full = ""
    try:
        import manga  # noqa: F401  (همان import که bridge هم انجام می‌دهد)
        lines.append("📥 import manga.py — ✔ موفق")
    except Exception:
        ok = False
        tb_full = traceback.format_exc()
        culprit = _find_culprit(tb_full)
        lines.append("📥 import manga.py — ❌ خطا:")
        lines.append("```")
        lines.append(tb_full.strip()[-2500:])
        lines.append("```")
        lines.append("👉 فایل مقصر: %s" % (culprit or "نامشخص — traceback بالا را ببین"))
    try:
        import manga_app  # noqa: F401
        lines.append("📥 import manga_app.py — ✔ موفق")
    except Exception:
        ok = False
        tb_full = traceback.format_exc()
        culprit2 = _find_culprit(tb_full) or culprit
        lines.append("📥 import manga_app.py — ❌ خطا:")
        lines.append("```")
        lines.append(tb_full.strip()[-2500:])
        lines.append("```")
        lines.append("👉 فایل مقصر: %s" % (culprit2 or "نامشخص"))

    if ok:
        lines.insert(0, "✅ موتور سالم است.")
        lines.append("💡 اگر باز هم خطا گرفتی، متن کامل خطای زمان اجرا در همین "
                     "کادر لاگ، موقع شروع ترجمه نمایش داده می‌شود.")
    else:
        lines.insert(0, "❌ موتور خرابه — دقیقاً این‌جا:")
        lines.append("🔧 راه‌حل سریع: تنظیمات اپ → پاک‌کردن داده اپ (Clear Data) "
                     "→ باز کردن دوباره؛ یا نسخه جدید اپ را نصب کن.")
    return json.dumps({"ok": ok, "report": "\n".join(lines)}, ensure_ascii=False)


def _find_culprit(tb_text):
    """از داخل traceback نام فایل مقصر (manga.py / manga_app.py / …) را درمی‌آورد."""
    import re
    for n in _ENGINE_FILES:
        if re.search(r'File "[^"]*%s"' % re.escape(n), tb_text):
            return n
    return None


# ---------------------------------------------------------------- manifest
# ⚠ v1.22 — فیلد «آدرس سرور Ollama» (api_base) به‌خواست کاربر کلاً حذف شد.
# Ollama اگر انتخاب شود با آدرس پیش‌فرض http://localhost:11434/v1 کار می‌کند
# (اجرا روی خود گوشی/Termux). هیچ فیلدی به منیفست تزریق نمی‌شود.


def manifest():
    """منیفست اصلی bridge — بدون تزریق فیلد آدرس Ollama (حذف‌شده در v1.22)."""
    import bridge
    return bridge.manifest()


# ---------------------------------------------------------------- ollama
def _ollama_base(p):
    # v1.22: فیلد آدرس از UI حذف شد — فقط آدرس پیش‌فرض لوکال.
    # (اگر پارامتر قدیمی api_base در params باشد، همچنان احترام می‌گذرد.)
    b = str(p.get("api_base") or "").strip().rstrip("/")
    if b and not b.endswith("/v1"):
        b += "/v1"
    return b or "http://localhost:11434/v1"


def _ollama_check(p):
    """پیش‌چک Ollama: اتصال + کشف خودکار مدل.

    خروجی: (error_str یا None، پیام وضعیت)
    """
    import requests

    base = _ollama_base(p)
    headers = {}
    key0 = str(p.get("keys") or "").split(",")[0].strip()
    if key0:
        headers["Authorization"] = "Bearer " + key0
    try:
        r = requests.get(base + "/models", timeout=(4, 10), headers=headers)
        r.raise_for_status()
        data = r.json().get("data") or []
        models = [str(m.get("id") or "").strip() for m in data if m.get("id")]
    except Exception as e:
        host = base.replace("/v1", "")
        return (
            "اتصال به Ollama برقرار نشد (%s)\n"
            "│  خطا: %s\n"
            "├─ آدرس استفاده‌شده: %s (پیش‌فرض لوکال)\n"
            "├─ اگه Ollama روی خود گوشی (Termux) است: مطمئن شو «ollama serve» در حال اجراست\n"
            "└─ نکته: از v1.22 فیلد آدرس از تنظیمات حذف شده؛ Ollama فقط روی همین دستگاه پشتیبانی می‌شود."
            % (host, type(e).__name__, host)
        ), base

    if not str(p.get("model") or "").strip() and models:
        p["model"] = models[0]
    return None, base + ("  |  مدل‌ها: " + "، ".join(models[:8]) if models else "")


def start_job(params_json, files_dir):
    """پیش‌پردازش پارام‌ها و delegate به bridge.start_job."""
    p = json.loads(params_json)

    # ۱) پسوند ورودی (pick گالری) — قبل از هر چیز
    src0 = str(p.get("src") or "")
    src1 = _fix_input_ext(src0)
    if src1 != src0:
        p["src"] = src1

    # ۲) Ollama لوکال — بدون توکن، آدرس دلخواه، کشف مدل
    prov = str(p.get("provider") or "gemini").strip().lower()
    if prov == "ollama":
        # بدون کلید هم باید کار کند (bridge حداقل یک کلید می‌خواهد)
        if not str(p.get("keys") or "").strip():
            p["keys"] = "ollama"
        # استخراج محلی می‌کند — تایم‌اوت کوتاه پیش‌فرض نمی‌گذاریم
        if not p.get("timeout"):
            p["timeout"] = 180
        err, info = _ollama_check(p)
        if err:
            return json.dumps(
                {"ok": False, "error": "❌ " + err + "\n\n🔎 " + info},
                ensure_ascii=False)
        # base_url را برای MangaTranslator اعمال کن (بدون تغییر manga.py)
        try:
            import manga
            manga.PROVIDER_PRESETS["ollama"]["base_url"] = _ollama_base(p)
        except Exception:
            pass

    return _delegate_start(json.dumps(p, ensure_ascii=False), files_dir)


def _delegate_start(params_json, files_dir):
    import bridge
    return bridge.start_job(params_json, files_dir)


# ---------------------------------------------------------------- delegate
def poll():
    import bridge
    return bridge.poll()


def cancel():
    import bridge
    return bridge.cancel()


def status():
    try:
        import launcher
        return launcher.status()
    except Exception:
        return "status error"


def check_engine_files():
    """مثل status ولی کامل‌تر — برای نمایش اختیاری."""
    return health()
