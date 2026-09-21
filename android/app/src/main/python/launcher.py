#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""نقطه ورود اپ اندروید.

کارها: (۱) چک نسخه داخل APK روی دیسک (Kotlin از assets/engine کپی می‌کند)،
(۲) آپدیت خودکار manga.py / manga_app.py / bridge.py / extract_ui.py از گیت‌هاب
فقط وقتی APP_VER ریپو از نسخه فعلی بالاتر باشد.

هر فایلی که در ریپو با APP_VER بالاتر پوش شود، در اجرای بعدی اپ به‌صورت
خودکار جایگزین می‌شود — بدون نصب دوباره.
"""
import os
import re
import shutil
import sys
import traceback

REPO_RAWS = [
    "https://raw.githubusercontent.com/amirwolf512k/Manga-AutoTranslate/main",
    "https://raw.githubusercontent.com/amirwolf5122/Manga-AutoTranslate/main"
]
UPDATE_FILES = ["manga.py", "manga_app.py", "app_server.py", "bridge.py",
                "extract_ui.py"]

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
    """آپدیت از ریپو فقط وقتی APP_VER ریپو بالاتر از نسخه فعلی دیسک باشد."""
    upd_dir = os.path.join(files_dir, "updates")
    os.makedirs(upd_dir, exist_ok=True)
    check_bundled(files_dir)
    cur_ver = max(_file_ver(upd_dir, "manga_app"),
                  _pyfile_ver(os.path.join(upd_dir, "manga_app.py")))

    import requests

    def _fetch(name):
        """از ریپو اصلی؛ اگر نبود از فال‌بک. None = نشد."""
        for base in REPO_RAWS:
            try:
                r = requests.get("%s/%s" % (base, name), timeout=30)
                if r.status_code == 200 and len(r.content) > 500:
                    return r.content
            except Exception:
                pass
        return None

    head = _fetch("manga_app.py")
    if head is None:
        _log("آپدیت چک نشد (شبکه در دسترس نیست) — نسخه داخل APK استفاده می‌شود.")
        return upd_dir
    new_ver = _read_ver_from_str(head.decode("utf-8", "replace"))

    if _cmp_ver(new_ver, cur_ver) <= 0:
        _log("ریپو هم‌نسخه/قدیمی‌تر است (%s ≤ %s) — آپدیت لازم نیست."
             % (new_ver or "?", cur_ver or "?"))
        return upd_dir

    tmp_dir = os.path.join(files_dir, "updates_tmp")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir, exist_ok=True)
    with open(os.path.join(tmp_dir, "manga_app.py"), "wb") as f:
        f.write(head)
    ok_any = True
    for name in UPDATE_FILES:
        if name == "manga_app.py":
            continue
        data = _fetch(name)
        if data is None:
            _log("دانلود نشد: %s" % name)
            ok_any = False
            continue
        with open(os.path.join(tmp_dir, name), "wb") as f:
            f.write(data)
    if not ok_any:
        _log("آپدیت ناقص ماند — نسخه فعلی نگه داشته شد.")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return upd_dir

    shutil.rmtree(upd_dir, ignore_errors=True)
    os.rename(tmp_dir, upd_dir)
    for name in UPDATE_FILES:
        _stamp(upd_dir, name, new_ver)
    _log("آپدیت از ریپو اعمال شد: %s → %s" % (cur_ver or "نصب اولیه", new_ver))
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
