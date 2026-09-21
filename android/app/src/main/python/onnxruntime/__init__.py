# -*- coding: utf-8 -*-
"""شیم onnxruntime برای اندروید — پایتون چاکوپی، بک‌اند ONNX Runtime جاوا.

چون ویل اندرویدی onnxruntime در PyPI/چاکوپی وجود ندارد، این ماژول همان
API حداقلی (InferenceSession و SessionOptions) را روی کتابخانه جاوا
com.microsoft.onnxruntime:onnxruntime-android پیاده می‌کند تا manga.py و
rapidocr بدون تغییر کد کار کنند.
"""
import numpy as np

__version__ = "1.20.0-android-shim"

try:
    from java import jclass, jarray
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
    def __init__(self, name, shape, dtype="tensor(float)"):
        self.name = name
        self.shape = shape
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
    """numpy → OnnxTensor جاوا."""
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
    ja = jarray.zeros(flat.size, code)
    ja[:] = flat.tolist()
    shape = jarray.zeros(x.ndim, "j")
    for i in range(x.ndim):
        shape[i] = int(x.shape[i])
    return _OnnxTensor.createTensor(_ENV, _buf_of(ja, code), shape)


def _to_numpy(value):
    """آرایه جاوای چندبعدی → numpy (نوع از خود داده)."""
    def conv(v):
        try:
            it = iter(v)
        except TypeError:
            return v
        return [conv(x) for x in it]
    return np.asarray(conv(value))


class _ModelMeta:
    producer_name = ""
    graph_name = ""
    description = ""
    custom_metadata_map = {}


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
        infos = self._sess.getInputInfo()
        out = []
        for name in self._in_names:
            shape = []
            try:
                info = infos.get(name)
                if info is not None:
                    js = info.getShape()
                    if js is not None:
                        shape = [int(s) if s is not None else -1
                                 for s in list(js.getShape())]
            except Exception:
                pass
            out.append(NodeArg(name, shape))
        return out

    def get_outputs(self):
        return [NodeArg(n) for n in self._out_names]

    def get_modelmeta(self):
        return _ModelMeta()

    def run(self, output_names, input_feed, run_options=None, **kw):
        feed = _HashMap()
        for name, x in input_feed.items():
            feed.put(str(name), _tensor_create(x))
        result = self._sess.run(feed)
        names = [str(n) for n in output_names] if output_names else self._out_names
        outs = []
        for name in names:
            t = result.get(name)
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
