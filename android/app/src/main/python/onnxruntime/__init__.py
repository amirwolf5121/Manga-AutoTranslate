# -*- coding: utf-8 -*-
"""شیم onnxruntime برای اندروید — پایتون چاکوپی، بک‌اند ONNX Runtime جاوا.

چون ویل اندرویدی onnxruntime در PyPI/چاکوپی وجود ندارد، این ماژول همان
API حداقلی (InferenceSession و SessionOptions) را روی کتابخانه جاوا
com.microsoft.onnxruntime:onnxruntime-android پیاده می‌کند تا manga.py و
rapidocr بدون تغییر کد کار کنند.
"""
import numpy as np

__version__ = "1.20.0-android-shim"


def preload_dlls(*a, **k):
    """سازگاری API — اندروید نیازی به preload ندارد."""
    pass

try:
    from java import jclass, jarray
    # نشان‌گرهای نوع اولیه — برای API فراخوانی‌پذیر jarray(jtype)(seq)
    try:
        from java import (jfloat as _JF, jdouble as _JD, jlong as _JL,
                          jint as _JI, jbyte as _JB)
    except Exception:
        _JF = _JD = _JL = _JI = _JB = None
    _FloatBuffer = jclass("java.nio.FloatBuffer")
    _LongBuffer = jclass("java.nio.LongBuffer")
    _IntBuffer = jclass("java.nio.IntBuffer")
    _ByteBuffer = jclass("java.nio.ByteBuffer")
    _DoubleBuffer = jclass("java.nio.DoubleBuffer")
    _HashMap = jclass("java.util.HashMap")
    _OrtEnvironment = jclass("ai.onnxruntime.OrtEnvironment")
    _OrtSession_cls = jclass("ai.onnxruntime.OrtSession$SessionOptions")
    _OnnxTensor = jclass("ai.onnxruntime.OnnxTensor")
    _ENV = _OrtEnvironment.getEnvironment()
    _OK = True
    _IMPORT_ERR = None
except Exception as _e:
    _OK = False
    _IMPORT_ERR = _e

# ---------------------------------------------------------------- ساخت آرایه جاوا
# نکته مهم: در چاکوپی ۱۵/۱۶، «jarray» یک تابع فراخوانی‌پذیر (Cython) است و
# ویژگی zeros ندارد → «jarray.zeros(n, code)» با ارور
# «'_cython_…cython_function_or_method' object has no attribute 'zeros'»
# می‌شکند (ارور واقعی دستگاه کاربر). پس هر سه سازوکار را به‌ترتیب امتحان
# می‌کنیم و موفق‌بار اول را کش می‌کنیم:
#   ۱) jarray(jtype)(seq) — هم‌زمان می‌سازد و پر می‌کند (پایدارترین)
#   ۲) jarray.zeros(n, code) — API قدیمی
#   ۳) java.lang.reflect.Array.newInstance(Float.TYPE, n)
_JCODE_TYPE = {"f": ("JF", "float"), "d": ("JD", "double"),
               "j": ("JL", "long"), "i": ("JI", "int"), "b": ("JB", "byte")}
_JSTRAT = {"n": 0}   # 0=نمی‌دانیم، ۱/۲/۳ استراتژی موفق


def _prim_cls(name):
    """کلاس نوع اولیه جاوا (float و …) بدون نیاز به jfloat و …"""
    box = {"float": "Float", "double": "Double", "long": "Long",
           "int": "Integer", "byte": "Byte"}[name]
    return jclass("java.lang." + box).TYPE


def _jarr_fill(seq, code):
    """آرایه جاوا از یک دنباله پایتون — با پرچم استراتژی کش‌شده."""
    seq = list(seq)
    s = _JSTRAT["n"]
    if s == 0 or s == 1:
        try:
            tname, prim = _JCODE_TYPE[code]
            jt = {"JF": _JF, "JD": _JD, "JL": _JL, "JI": _JI,
                  "JB": _JB}.get(tname)
            if jt is None:
                jt = _prim_cls(prim)
            arr = jarray(jt)(seq)
            _JSTRAT["n"] = 1
            return arr
        except Exception:
            if s == 1:
                raise
            _JSTRAT["n"] = 2
    if s == 0 or s == 2:
        try:
            arr = jarray.zeros(len(seq), code)
            for i, v in enumerate(seq):
                arr[i] = v
            _JSTRAT["n"] = 2
            return arr
        except Exception:
            if s == 2:
                raise
            _JSTRAT["n"] = 3
    # استراتژی ۳ — reflect
    prim = _JCODE_TYPE[code][1]
    _Arr = jclass("java.lang.reflect.Array")
    arr = _Arr.newInstance(_prim_cls(prim), len(seq))
    for i, v in enumerate(seq):
        arr[i] = v
    return arr


class ExecutionMode:
    """سازگاری API — اندروید always sequential."""

    ORT_SEQUENTIAL = 0
    ORT_PARALLEL = 1


class GraphOptimizationLevel:
    """سازگاری API — سطح بهینه‌سازی؛ اندروید no-op."""

    ORT_DISABLE_ALL = 0
    ORT_ENABLE_BASIC = 1
    ORT_ENABLE_EXTENDED = 2
    ORT_ENABLE_ALL = 99


class SessionOptions:
    """سازگاری API — اندروید همیشه CPU است؛ تنظیمات no-op."""

    def __init__(self):
        self.intra_op_num_threads = 3
        self.inter_op_num_threads = 1
        self.optimized_model_filepath = ""

    def __setattr__(self, k, v):
        self.__dict__[k] = v  # هر attribute اضافی را بپذیر (سازگاری rapidocr)

    def add_session_config_entry(self, *a, **k):
        pass


def get_available_providers():
    return ["CPUExecutionProvider"]


def get_device():
    return "CPU"


def _jmap_to_dict(m):
    """java.util.Map → dict — با iterator خود جاوا (Set قابل iter مستقیم نیست)."""
    out = {}
    try:
        it = m.entrySet().iterator()
        while it.hasNext():
            e = it.next()
            out[str(e.getKey())] = str(e.getValue())
    except Exception:
        pass
    return out


def _jset_to_list(js):
    """java.util.Set → list — چاکوپی روی Set مستقیم iter نمی‌دهد."""
    out = []
    try:
        it = js.iterator()
        while it.hasNext():
            out.append(str(it.next()))
    except Exception:
        try:
            out = [str(x) for x in js.toArray()]
        except Exception:
            pass
    return out


class NodeArg:
    def __init__(self, name, shape=None, dtype="tensor(float)"):
        # ⚠ shape باید اختیاری باشد — باگ واقعی دستگاه (v1.18):
        # «NodeArg.__init__() missing 1 required positional argument: 'shape'»
        # چون get_outputs فقط name می‌داد. حالا اگر shape نیاید [] می‌گیریم.
        self.name = name
        self.shape = list(shape) if shape else []
        self.type = dtype

    def __repr__(self):
        return "NodeArg(%r, %r, %r)" % (self.name, self.shape, self.type)


def _buf_of(ja, code):
    if code == "f":
        return _FloatBuffer.wrap(ja)
    if code == "j":
        return _LongBuffer.wrap(ja)
    if code == "i":
        return _IntBuffer.wrap(ja)
    if code == "d":
        return _DoubleBuffer.wrap(ja)
    return _ByteBuffer.wrap(ja)


def _tensor_create(x):
    """numpy → OnnxTensor جاوا.

    نکته: ساخت آرایه جاوا با _jarr_fill انجام می‌شود، نه jarray.zeros —
    چون در چاکوپی‌های جدید jarray.zeros وجود ندارد (بمب ارور cython/zeros).
    """
    if not isinstance(x, np.ndarray):
        x = np.asarray(x)
    if x.dtype == np.float64:
        x = x.astype(np.float32)
    if x.dtype in (np.int16, np.uint16, np.uint32, np.uint64, np.bool_):
        x = x.astype(np.int64) if x.dtype == np.bool_ else x.astype(np.float32)
    x = np.ascontiguousarray(x)
    flat = x.ravel()
    if x.dtype == np.float32:
        code = "f"
    elif x.dtype == np.int64:
        code = "j"
    elif x.dtype == np.int32:
        code = "i"
    elif x.dtype in (np.uint8, np.int8):
        code = "b"
    else:
        flat = flat.astype(np.float32)
        code = "f"
    ja = _jarr_fill(flat.tolist(), code)
    shape = _jarr_fill([int(v) for v in x.shape], "j")
    return _OnnxTensor.createTensor(_ENV, _buf_of(ja, code), shape)


def _to_numpy(value):
    """آرایه جاوای چندبعدی → numpy.

    نکته: OnnxTensor.getValue() آرایه‌ی جاوا float می‌دهد که چاکوپی به float
    پایتون (دوبل) تبدیل می‌کند → numpy float64 می‌سازد؛ در حالی که ORT واقعی
    float32 برمی‌گرداند. پس float64 → float32 (مثل ORT واقعی).
    """
    def conv(v):
        try:
            it = iter(v)
        except TypeError:
            return v
        return [conv(x) for x in it]
    arr = np.asarray(conv(value))
    if arr.dtype == np.float64:
        arr = arr.astype(np.float32)
    return arr


def _result_value(result, name):
    """استخراج OnnxValue از OrtSession.Result جاوا — سازگار با همه حالت‌ها.

    باگ واقعی دستگاه (v1.17): OrtSession.Result.get(String) در کتابخانه جاوا
    java.util.Optional برمی‌گرداند، نه خود OnnxValue → فراخوانی
    t.getValue() روی Optional ارور
    «'Optional' object has no attribute 'getValue'» می‌داد و کل فاز ۱ (تشخیص
    حباب + OCR) می‌شکست. سه مسیر به‌ترتیب امتحان می‌شود:
      ۱) iterator — Result از Iterable<Map.Entry<String,OnnxValue>> ارث می‌برد
         → بدون Optional اصلاً (پایدارترین مسیر)
      ۲) get(String) → Optional → unwrap دستی با isPresent/get
      ۳) اگر هم None بود یا OnnxValue مستقیم بود، همان برگردانده می‌شود.
    """
    # مسیر ۱ — iterator (بدون Optional)
    try:
        it = result.iterator()
        while it.hasNext():
            e = it.next()
            if str(e.getKey()) == str(name):
                return e.getValue()
    except Exception:
        pass
    # مسیر ۲ — get(String) → Optional
    try:
        t = result.get(name)
    except Exception:
        t = None
    if t is None:
        return None
    # unwrap Optional جاوا (java.util.Optional از API 24 موجود است)
    try:
        if hasattr(t, "isPresent"):
            return t.get() if t.isPresent() else None
    except Exception:
        pass
    # مسیر ۳ — خود OnnxValue برگشته
    return t


class _ModelMeta:
    def __init__(self, sess=None):
        self.producer_name = ""
        self.graph_name = ""
        self.description = ""
        self.custom_metadata_map = {}
        if sess is None:
            return
        try:
            md = sess.getMetadata()
            self.custom_metadata_map = _jmap_to_dict(md.getCustomMetadata())
            self.producer_name = str(md.getProducerName() or "")
            self.graph_name = str(md.getGraphName() or "")
            self.description = str(md.getDescription() or "")
        except Exception:
            pass


_JTYPE2ORT = {
    "FLOAT": "tensor(float)", "DOUBLE": "tensor(double)",
    "INT8": "tensor(int8)", "INT16": "tensor(int16)",
    "INT32": "tensor(int32)", "INT64": "tensor(int64)",
    "UINT8": "tensor(uint8)", "BOOL": "tensor(bool)",
    "STRING": "tensor(string)", "BFLOAT16": "tensor(bfloat16)",
}


def _node_info(info):
    """(shape, dtype) از NodeInfo جاوا — چند استراتژی محافظت‌شده.

    API جاوا: NodeInfo.getInfo() → TensorInfo؛ TensorInfo.getShape() → long[]
    و TensorInfo.getType() → OnnxJavaType. بعضی نسخه‌ها getShape را روی خود
    NodeInfo هم دارند — هر دو مسیر امتحان می‌شود.
    """
    shape, dtype = [], "tensor(float)"
    js = None
    try:
        js = info.getShape()
    except Exception:
        pass
    if js is None:
        try:
            js = info.getInfo().getShape()
        except Exception:
            pass
    try:
        shape = [int(s) if s is not None else -1 for s in list(js)]
    except Exception:
        pass
    try:
        dtype = _JTYPE2ORT.get(str(info.getInfo().getType()), "tensor(float)")
    except Exception:
        pass
    return shape, dtype


class InferenceSession:
    def __init__(self, path_or_bytes, sess_options=None, providers=None, **kw):
        if not _OK:
            raise ImportError("شیم ORT اندروید لود نشد: %s" % (_IMPORT_ERR,))
        if isinstance(path_or_bytes, (bytes, bytearray)):
            import os
            import tempfile
            fd, tmp = tempfile.mkstemp(suffix=".onnx")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(path_or_bytes)
                self._sess = _ENV.createSession(tmp)
            finally:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
        else:
            self._sess = _ENV.createSession(str(path_or_bytes))
        self._in_names = _jset_to_list(self._sess.getInputNames())
        self._out_names = _jset_to_list(self._sess.getOutputNames())

    def get_inputs(self):
        infos = None
        try:
            infos = self._sess.getInputInfo()
        except Exception:
            pass
        out = []
        for name in self._in_names:
            shape, dtype = [], "tensor(float)"
            if infos is not None:
                try:
                    info = infos.get(name)
                except Exception:
                    info = None
                if info is not None:
                    shape, dtype = _node_info(info)
            out.append(NodeArg(name, shape, dtype))
        return out

    def get_outputs(self):
        # ⚠ باگ دستگاه v1.18: «[NodeArg(n) for n in self._out_names]» بدون shape
        # بود → rapidocr در get_output_names کرش می‌کرد → فاز ۱ صفر خروجی می‌داد.
        infos = None
        try:
            infos = self._sess.getOutputInfo()
        except Exception:
            pass
        out = []
        for name in self._out_names:
            shape, dtype = [], "tensor(float)"
            if infos is not None:
                try:
                    info = infos.get(name)
                except Exception:
                    info = None
                if info is not None:
                    shape, dtype = _node_info(info)
            out.append(NodeArg(name, shape, dtype))
        return out

    def get_modelmeta(self):
        return _ModelMeta(self._sess)

    def get_providers(self):
        return ["CPUExecutionProvider"]

    def get_provider_options(self):
        return {"CPUExecutionProvider": {}}

    def run(self, output_names, input_feed, run_options=None, **kw):
        feed = _HashMap()
        for name, x in input_feed.items():
            feed.put(str(name), _tensor_create(x))
        result = self._sess.run(feed)
        names = [str(n) for n in output_names] if output_names else self._out_names
        outs = []
        for name in names:
            # ⚠ Result.get(String) در جاوا Optional برمی‌گرداند نه OnnxValue —
            # پس unwrap باید دستی انجام شود (باگ واقعی دستگاه در v1.17)
            t = _result_value(result, name)
            if t is None:
                outs.append(None)
                continue
            try:
                outs.append(_to_numpy(t.getValue()))
            finally:
                try:
                    t.close()
                except Exception:
                    pass
        return outs