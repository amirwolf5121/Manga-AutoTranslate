#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""نقطه ورود اپ اندروید.

موتور (manga.py / manga_app.py / …) فقط از داخل APK می‌آید: Kotlin فایل‌های
assets/engine را روی دیسک کپی می‌کند و همین‌جا روی sys.path می‌رود.

آپدیت آنلاین از release «files» (apply_updates قدیمی) کلاً حذف شده — اپ دیگر
هیچ فایلی را از گیت‌هاب دانلود/جایگزین نمی‌کند؛ نسخه موتور همیشه همان است که
با APK نصب شده (قابل پیش‌بینی و تست‌شده).
"""
import os
import re
import shutil
import sys
import traceback

# ---------- لاگ راه‌اندازی برای نمایش در UI ----------
LOGS = []


def _log(msg):
    LOGS.append(str(msg))
    del LOGS[:-40]
    print("[launcher] %s" % msg, flush=True)


def status():
    """وضعیت فایل‌ها برای نمایش در کادر لاگ اپ — کاربر ببیند فایل هست یا نه."""
    try:
        files_dir = os.environ.get("MANGA_FILES_DIR") or os.getcwd()
        upd = os.path.join(files_dir, "updates")
        out = list(LOGS)
        for n in ("manga.py", "manga_app.py"):
            p = os.path.join(upd, n)
            if os.path.isfile(p):
                out.append("%s: هست (%d بایت)" % (n, os.path.getsize(p)))
            else:
                out.append("%s: نیست!" % n)
        return "\n".join(out)
    except Exception as e:
        return "status error: %s" % e


def _read_ver_from_str(src):
    m = re.search(r'APP_VER\s*=\s*"([^"]+)"', src or "")
    return m.group(1) if m else "0"


def _cmp_ver(a, b):
    try:
        pa = [int(x) for x in a.split(".")]
        pb = [int(x) for x in b.split(".")]
    except Exception:
        return 0
    while len(pa) < len(pb):
        pa.append(0)
    while len(pb) < len(pa):
        pb.append(0)
    return (pa > pb) - (pa < pb)


def _file_ver(upd_dir, name):
    try:
        with open(os.path.join(upd_dir, ".ver_" + name), encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "0"


def _stamp(upd_dir, name, ver):
    try:
        with open(os.path.join(upd_dir, ".ver_" + name), "w", encoding="utf-8") as f:
            f.write(ver)
    except Exception:
        pass


def _pyfile_ver(path):
    """APP_VER داخل یک فایل py روی دیسک."""
    try:
        with open(path, encoding="utf-8") as f:
            return _read_ver_from_str(f.read(8192))
    except Exception:
        return "0"


def check_bundled(files_dir):
    """سلامت فایل‌های روی دیسک را چک می‌کند (Kotlin از assets کپی کرده).

    اگر فایل خالی/خراب باشد (مثل فایل‌های ۰ بایت نسخه‌های قبلی) حذف می‌شود
    تا Kotlin دفعه بعد دوباره کپی کند؛ آپدیت سالم ریپو دست‌نخورده می‌ماند.
    """
    upd = os.path.join(files_dir, "updates")
    os.makedirs(upd, exist_ok=True)
    for n in ("manga.py", "manga_app.py"):
        p = os.path.join(upd, n)
        if os.path.isfile(p) and os.path.getsize(p) < 1000:
            try:
                os.remove(p)
                _log("فایل خراب/خالی حذف شد: %s" % n)
            except Exception:
                pass


def apply_updates(files_dir):
    """آپدیت آنلاین حذف شده — فقط نسخه داخل APK.

    قبلاً این تابع manga.py / manga_app.py / bridge.py و … را از release
    «files» گیت‌هاب دانلود و روی دیسک می‌نوشت؛ طبق درخواست صاحب اپ این مسیر
    کلاً بسته شد: هیچ درخواست شبکه‌ای زده نمی‌شود و فایل‌های روی دیسک همان
    کپی Kotlin از assets/engine می‌مانند (نسخه‌ای که با APK تست شده).
    """
    upd_dir = os.path.join(files_dir, "updates")
    os.makedirs(upd_dir, exist_ok=True)
    check_bundled(files_dir)
    _log("آپدیت آنلاین غیرفعال — نسخه موتور از داخل APK استفاده می‌شود.")
    return upd_dir


def _pip_runtime(files_dir):
    """نصب SDKهای واقعی در اجرای اول — فقط پکیج‌های pure-python.

    openai نسخه‌ای انتخاب شده که pydantic v1 (خالص) می‌پذیرد؛ نسخه‌های
    جدید openai و همه نسخه‌های google-genai به pydantic-core (native)
    نیاز دارند که روی اندروید wheel ندارد و pip گوشی هم کامپایلر ندارد.
    برای Gemini از provider «gemini-openai» (endpoint سازگار openai)
    استفاده کن.
    """
    site = os.path.join(files_dir, "site_pkgs")
    os.makedirs(site, exist_ok=True)
    if site not in sys.path:
        sys.path.append(site)
    if os.path.isfile(os.path.join(site, ".pip_done")):
        return
    try:
        from pip._internal.cli.main import main as _pipmain
    except Exception:
        try:
            import pip as _p
            _pipmain = getattr(_p, "main", None)
        except Exception:
            _pipmain = None
    if _pipmain is None:
        _log("pip runtime در دسترس نیست — SDKها با MangaTranslator نصب می‌شوند.")
        return
    groups = [
        ["pydantic==1.10.17"],
        ["typing-extensions", "sniffio", "certifi", "idna", "h11", "httpcore",
         "anyio", "httpx", "distro"],
        ["openai==1.35.13"],
    ]
    for args in groups:
        try:
            _log("pip install: " + " ".join(args))
            rc = _pipmain(["install", "--no-cache-dir", "--no-deps",
                           "--target", site, "--quiet"] + args)
            _log(("✔ " if rc == 0 else "✘ نشد: ") + " ".join(args))
        except SystemExit as e:
            _log("pip exit: %s" % e)
        except Exception as e:
            _log("pip خطا: %s" % e)
    try:
        open(os.path.join(site, ".pip_done"), "w").write("ok")
    except Exception:
        pass


def main(files_dir=None):
    files_dir = files_dir or os.environ.get("MANGA_FILES_DIR") or os.getcwd()
    os.environ["MANGA_FILES_DIR"] = files_dir
    os.chdir(files_dir)
    os.environ.setdefault("HOME", files_dir)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        _pip_runtime(files_dir)
    except Exception:
        traceback.print_exc()
    try:
        upd_dir = apply_updates(files_dir)
        # updates باید «قبل از» dir داخلی باشد تا manga.py / manga_app.py
        # آپدیت‌شده از ریپو واقعاً در اجرا استفاده شوند
        if os.path.isdir(upd_dir):
            sys.path.insert(0, upd_dir)
    except Exception:
        traceback.print_exc()

    # دانلود خودکار فونت‌ها (بار اول یا اگر فایل گم شده باشد).
    # FONT_DIR عمداً بیرون updates/ است — چون apply_updates پوشه updates
    # را از نو می‌سازد و فونت‌ها نباید هر بار دانلود شوند.
    try:
        import manga_app
        fonts_dir = os.path.join(files_dir, "fonts")
        os.makedirs(fonts_dir, exist_ok=True)
        old_fonts = os.path.join(files_dir, "updates", "fonts")
        if os.path.isdir(old_fonts):  # یک‌بار مهاجرت از نسخه‌های قبلی
            for f in os.listdir(old_fonts):
                dst = os.path.join(fonts_dir, f)
                if not os.path.isfile(dst):
                    try:
                        os.rename(os.path.join(old_fonts, f), dst)
                    except Exception:
                        pass
            shutil.rmtree(old_fonts, ignore_errors=True)
        manga_app.FONT_DIR = fonts_dir
        n = manga_app.download_fonts(log=_log)
        if n:
            _log("%d فونت دانلود شد." % n)
        else:
            _log("فونت‌ها آماده‌اند.")
    except Exception:
        traceback.print_exc()
        _log("دانلود فونت ناموفق بود — دفعه بعد دوباره تلاش می‌شود.")

    # UI بومی (MainActivity) مستقیماً ماژول bridge را صدا می‌زند.


if __name__ == "__main__":
    main()
