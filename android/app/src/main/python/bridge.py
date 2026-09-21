# -*- coding: utf-8 -*-
"""پل بومی اپ اندروید — UI بومی Kotlin از این می‌خواند.

- manifest(): تعریف UI از manga_app.py آپدیت‌شده (extract_ui) + بخش فونت‌های
  لحن (runtime از FONT_BUNDLES) + دیفالت instruction از manga.py
- start_job(params): اجرای موتور manga.py در پس‌زمینه
- poll(): وضعیت + لاگ + خروجی‌ها

بدون HTTP — Kotlin مستقیم این توابع را صدا می‌زند.
"""
import contextlib
import io
import json
import os
import threading
import traceback

import manga
from extract_ui import extract

import manga_app  # نسخه آپدیت‌شده از پوشه updates (sys.path اول)

STATE = {"job": None, "lock": threading.Lock()}
_MF_CACHE = {"mf": None}


def _bundles():
    """(slot, fname, desc, urls) از manga_app.py فعلی (runtime)."""
    try:
        b = list(manga_app.FONT_BUNDLES)
        if b:
            return b
    except Exception:
        pass
    return []


def _font_dir():
    try:
        return manga_app.FONT_DIR
    except Exception:
        return os.path.join(os.getcwd(), "fonts")


def _tone_ready(fname):
    p = os.path.join(_font_dir(), fname)
    try:
        return os.path.isfile(p) and os.path.getsize(p) > 20_000
    except Exception:
        return False


def _slot_fields(mf):
    """فیلدهای لحن از خود manifest: هر فیلدی که idاش با «_<slot>» تمام شود.

    file → فونت آپلودی آن لحن، bool → فعال/غیرفعال آن لحن. هیچ هاردکدی —
    اگر اسلاتی به manga_app.py اضافه/کم شود، اینجا هم خودکار عوض می‌شود.
    """
    slots = [b[0] for b in _bundles()]
    if not slots:
        return {}
    mapping = {}  # slot → {"file": fid, "en": fid}
    for sec in mf.get("sections", []):
        for f in sec.get("fields", []):
            fid = f.get("id") or ""
            for slot in slots:
                if fid.endswith("_" + slot):
                    m = mapping.setdefault(slot, {})
                    if f.get("type") == "file":
                        m["file"] = fid
                    elif f.get("type") == "bool":
                        m["en"] = fid
    return mapping


def _defaults(mf):
    """دیفالت‌های runtime: instruction از manga.py، readord از manga_app."""
    try:
        dflt_instr = manga.DEFAULT_SYSTEM_INSTRUCTION_STYLE.strip()
    except Exception:
        dflt_instr = ""
    for sec in mf.get("sections", []):
        for f in sec.get("fields", []):
            if not isinstance(f, dict):
                continue
            if f.get("id") == "instruction_text":
                cur = f.get("default")
                cur = cur.get("default") if isinstance(cur, dict) else cur
                if not (isinstance(cur, str) and cur.strip()):
                    f["default"] = dflt_instr or "خالی = متن پیش‌فرض داخل کد"
            elif f.get("id") == "readord":
                cur = f.get("default")
                if isinstance(cur, dict):
                    cur.setdefault("default", "rtl")
                elif cur not in ("rtl", "ltr"):
                    f["default"] = "rtl"


def _bundled_source(name):
    """سورس واقعی ماژول داخل APK — Chaquopy مسیر asset نمی‌دهد ولی
    loader.get_source سورس را کامل برمی‌گرداند (بدون نیاز به اینترنت)."""
    import importlib
    mod = importlib.import_module(name)
    loader = getattr(mod, "__loader__", None)
    if loader is None:
        raise RuntimeError("no loader for " + name)
    return loader.get_source(name)


def manifest():
    """تعریف UI بومی از manga_app.py فعلی (آپدیت‌شده از ریپو).

    ترتیب: فایل روی دیسک (updates — ریپو یا کپی bundled در اجرای اول) →
    سورس داخلی با loader.get_source → inspect. هیچ مسیری به AssetFinder
    باز نمی‌شود (FileNotFoundError نمی‌دهد).
    """
    files_dir = os.environ.get("MANGA_FILES_DIR") or os.getcwd()
    upd = os.path.join(files_dir, "updates", "manga_app.py")
    mf = None
    err = None
    for get_src in (
        lambda: (open(upd, encoding="utf-8").read(), "file")
        if os.path.isfile(upd) else (_ for _ in ()).throw(IOError(upd)),
        lambda: (_bundled_source("manga_app"), "loader"),
    ):
        try:
            src, _how = get_src()
            mf = extract(src, is_source=True)
            break
        except Exception as e:
            err = e
    if mf is None:
        try:
            mf = extract(manga_app.__file__)
        except Exception as e2:
            return json.dumps({"error": str(err or e2)}, ensure_ascii=False)
    try:
        provs = [str(x) for x in manga_app.PROVIDERS]
    except Exception:
        provs = ["gemini", "openai", "chatgpt", "deepseek", "groq"]
    for sec in mf.get("sections", []):
        for f in sec.get("fields", []):
            if f.get("choices_from") == "PROVIDERS" or f.get("id") == "provider":
                f["choices"] = [[p, p] for p in provs]
                f.pop("choices_from", None)
    try:
        _defaults(mf)
    except Exception:
        traceback.print_exc()
    _MF_CACHE["mf"] = mf
    return json.dumps(mf, ensure_ascii=False)


def _cfg(key, dflt=None):
    try:
        return manga_app.load_config().get(key, dflt)
    except Exception:
        return dflt


def _resolve_main_font(job):
    """فونت اصلی: آپلود کاربر → find_font → دانلود خودکار → دوباره find_font."""
    custom = job["params"].get("font_upload_file") or job["params"].get("font_file")
    if custom and os.path.isfile(custom):
        _log(job, "🔤 فونت اصلی (آپلودی): %s" % os.path.basename(custom))
        return custom
    fp = ""
    try:
        fp = manga_app.find_font() or ""
    except Exception:
        pass
    if fp:
        return fp
    _log(job, "⬇ فونت روی دستگاه نیست — دانلود خودکار…")
    try:
        manga_app.download_fonts(log=lambda m: _log(job, str(m)))
    except Exception as e:
        _log(job, "⚠ دانلود فونت ناموفق: %s" % e)
    try:
        fp = manga_app.find_font() or ""
    except Exception:
        fp = ""
    return fp


def _resolve_tones(job, mf):
    """لحن‌های فعال → (font_by_style, active_tones).

    فیلدها از manifest (یعنی خود manga_app.py) با پسوند «_<slot>» پیدا
    می‌شوند: آپلود کاربر مقدم است؛ فونت دانلودشدهٔ FONT_BUNDLES هم قابل
    استفاده است. سوییچ خاموش = لحن حذف.
    """
    slot_map = _slot_fields(mf)
    p = job["params"]
    font_by_style, active = {}, []
    for slot, fname, _desc, _u in _bundles():
        ids = slot_map.get(slot, {})
        en_fid = ids.get("en")
        on = True if en_fid is None else bool(p.get(en_fid, True))
        file_fid = ids.get("file")
        custom = p.get(file_fid + "_file") if file_fid else None
        path = custom if (custom and os.path.isfile(custom)) \
            else os.path.join(_font_dir(), fname)
        lbl = slot
        if not on:
            _log(job, "🔇 لحن خاموش: %s" % lbl)
            continue
        if path and os.path.isfile(path) and os.path.getsize(path) > 20_000:
            font_by_style[slot] = path
            active.append(slot)
        else:
            _log(job, "⚠ فونت لحن «%s» پیدا نشد — با فونت اصلی رندر می‌شود" % lbl)
    return font_by_style, active


def start_job(params_json, files_dir):
    """params: {src, file, provider, keys, model, ocr_lang, fmt, quality,
    debug, fake, clean_only, use_lama, force_cpu, two_pass, readord,
    glossary, instruction, story_brief, font_upload_file,
    tone_on_<slot>, tone_font_<slot>_file, workers, bubbles, batchw,
    timeout, maxre, reqdelay, temp}"""
    with STATE["lock"]:
        if STATE["job"] and not STATE["job"].get("done"):
            return json.dumps({"error": "یک کار در حال اجراست"}, ensure_ascii=False)
        p = json.loads(params_json)
        work = os.path.join(files_dir, "work")
        os.makedirs(work, exist_ok=True)
        out = os.path.join(work, "out")
        out_file = os.path.join(out, "output." + str(p.get("fmt", "PDF")).lower())
        if str(p.get("fmt", "PDF")).upper() == "PDF":
            out_file = os.path.join(out, "output.pdf")
        job = {
            "done": False, "log": "⏳ آماده‌سازی…", "error": None,
            "out_file": None, "images": [], "debug_images": [],
            "params": p, "out": out, "out_file_path": out_file,
        }
        STATE["job"] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return json.dumps({"ok": True}, ensure_ascii=False)


def _log(job, msg):
    with STATE["lock"]:
        txt = str(job.get("log") or "")
        job["log"] = (txt + "\n" + str(msg))[-12000:]


def _run(job):
    p = job["params"]
    try:
        os.makedirs(job["out"], exist_ok=True)
        for old in os.listdir(job["out"]):
            try:
                os.remove(os.path.join(job["out"], old))
            except Exception:
                pass
        langs = [x for x in str(p.get("ocr_lang") or "en").split() if x.strip()]
        keys = [k.strip() for k in str(p.get("keys") or "").split(",") if k.strip()]
        if not keys and not (bool(p.get("fake")) or bool(p.get("clean_only"))):
            _log(job, "❌ حداقل یک کلید API لازم است — کلید بده یا "
                      "«حالت تست» / «فقط پاکسازی» را در تنظیمات پیشرفته فعال کن.")
            with STATE["lock"]:
                job["done"] = True
                job["error"] = True
            return
        glossary_path = None
        if p.get("glossary"):
            glossary_path = os.path.join(job["out"], "glossary.txt")
            with open(glossary_path, "w", encoding="utf-8") as f:
                f.write(str(p["glossary"]))

        fp = _resolve_main_font(job)
        if not fp:
            _log(job, "❌ فونت اصلی پیدا نشد — اینترنت را چک کن یا فونت .ttf آپلود کن.")
            with STATE["lock"]:
                job["done"] = True
                job["error"] = True
            return

        def _f(key, dflt):
            try:
                return float(p.get(key) or dflt)
            except Exception:
                return dflt

        def _i(key, dflt):
            try:
                return int(float(p.get(key) or dflt))
            except Exception:
                return dflt

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            mf = _MF_CACHE["mf"]
            if mf is None:
                try:
                    mf = json.loads(manifest())
                except Exception:
                    mf = {}
            font_by_style, active = _resolve_tones(job, mf)
            tr = manga.MangaTranslator(
                api_key=keys or ["placeholder"],
                provider=str(p.get("provider") or "gemini"),
                model_name=(str(p.get("model")) or None) if p.get("model") else None,
                ocr_langs=langs,
                font_path=fp,
                reading_order=str(p.get("readord") or "rtl"),
                gpu=False if p.get("force_cpu") else None,
                two_pass_ocr=bool(p.get("two_pass", True)),
                debug=bool(p.get("debug")),
                glossary_path=glossary_path,
                story_brief=bool(p.get("story_brief", True)),
                fake_translate=bool(p.get("fake")),
                clean_only=bool(p.get("clean_only")),
                max_workers=_i("workers", 2),
                bubbles_per_request=_i("bubbles", 6),
                api_timeout=_f("timeout", 40.0),
                max_retries=_i("maxre", 8),
                request_delay=_f("reqdelay", 0.0),
                translation_temperature=_f("temp", 0.85),
                img_quality=_i("quality", 92),
                style_fonts=bool(active),
                active_tones=active or None,
                instruction_text=(str(p["instruction"]).strip() or None)
                if p.get("instruction") else None,
            )
            tr.batch_workers = _i("batchw", 3)  # مثل CLI: بعد از ساخت
            if font_by_style:
                tr.font_by_style = font_by_style
                tr.style_fonts = True
                _log(job, "🎨 لحن‌های فعال: %s" % "، ".join(active))
            tr.run(str(p.get("src")), job["out_file_path"], resume=False)
        txt = buf.getvalue()
        if txt:
            _log(job, txt[-8000:])

        # خروجی‌ها: فایل نهایی + صفحات (از cache خروجی برای نمایش)
        imgs, dbg = [], []
        cache = job["out_file_path"] + ".cache"
        for root, _d, files in os.walk(cache):
            for f in sorted(files):
                lp = os.path.join(root, f)
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    if "debug" in f.lower() or "debug" in root.lower():
                        dbg.append(lp)
                    else:
                        imgs.append(lp)
        if not imgs:
            for root, _d, files in os.walk(job["out"]):
                for f in sorted(files):
                    lp = os.path.join(root, f)
                    if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        (dbg if "debug" in f.lower() else imgs).append(lp)
        dl = job["out_file_path"] if os.path.isfile(job["out_file_path"]) else None
        with STATE["lock"]:
            job["images"] = imgs
            job["debug_images"] = dbg
            job["out_file"] = dl
            job["done"] = True
        _log(job, "✅ تمام شد — %d صفحه، خروجی: %s" % (len(imgs), dl or "-"))
    except Exception:
        _log(job, "❌ خطا:\n" + traceback.format_exc()[-2500:])
        with STATE["lock"]:
            job["done"] = True
            job["error"] = True


def poll():
    with STATE["lock"]:
        job = STATE["job"]
        if not job:
            return json.dumps({"idle": True}, ensure_ascii=False)
        return json.dumps({
            "idle": False,
            "done": bool(job.get("done")),
            "error": bool(job.get("error")),
            "log": job.get("log", ""),
            "images": job.get("images", []),
            "debug_images": job.get("debug_images", []),
            "out_file": job.get("out_file"),
        }, ensure_ascii=False)


def cancel():
    with STATE["lock"]:
        job = STATE["job"]
    if job and not job.get("done"):
        _log(job, "⏹ درخواست توقف ثبت شد (پایان مرحله فعلی)")
    return json.dumps({"ok": True}, ensure_ascii=False)
