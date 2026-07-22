"""Business tests for archiver delete rules (import without GUI)."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "zdem_archiver_main.py"


def _load_helpers():
    for name in ("PyQt5", "PyQt5.QtWidgets", "PyQt5.QtCore", "PyQt5.QtGui"):
        sys.modules.setdefault(name, types.ModuleType(name))
    qtcore = sys.modules["PyQt5.QtCore"]
    if not hasattr(qtcore, "Qt"):
        qtcore.Qt = types.SimpleNamespace()
    if not hasattr(qtcore, "QThread"):
        class QThread:
            pass
        qtcore.QThread = QThread
    if not hasattr(qtcore, "pyqtSignal"):
        qtcore.pyqtSignal = lambda *a, **k: None
    widgets = sys.modules["PyQt5.QtWidgets"]
    for cls in (
        "QApplication", "QMainWindow", "QWidget", "QVBoxLayout", "QHBoxLayout",
        "QLabel", "QLineEdit", "QPushButton", "QTextBrowser", "QProgressBar",
        "QFileDialog", "QDialog", "QListWidget", "QListWidgetItem", "QAbstractItemView",
    ):
        if not hasattr(widgets, cls):
            setattr(widgets, cls, type(cls, (), {}))
    pyqt = sys.modules["PyQt5"]
    pyqt.QtCore = qtcore
    pyqt.QtGui = sys.modules["PyQt5.QtGui"]
    pyqt.QtWidgets = widgets
    spec = importlib.util.spec_from_file_location("zdem_archiver_main", SRC)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_mod = _load_helpers()
format_size = _mod.format_size
should_delete_file = _mod.should_delete_file


def test_format_size_units():
    assert format_size(500).endswith("B")
    assert "KB" in format_size(2048)
    assert "MB" in format_size(2 * 1024 * 1024)


def test_whitelist_ini_xyr(tmp_path):
    f = tmp_path / "ini_xyr.dat"
    f.write_text("keep", encoding="utf-8")
    assert should_delete_file(f, tmp_path) is None


def test_delete_log_and_pycache(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("x", encoding="utf-8")
    assert should_delete_file(log, tmp_path) == "日志/错误文件"
    junk = tmp_path / "__pycache__" / "x.pyc"
    junk.parent.mkdir()
    junk.write_text("x", encoding="utf-8")
    assert should_delete_file(junk, tmp_path) == "IDE/编译缓存"


def test_delete_timestep_dat_keep_static(tmp_path):
    # filename contains "result" → data/result keyword rule wins before timestep rule
    step = tmp_path / "result_10000.dat"
    step.write_text("x", encoding="utf-8")
    assert should_delete_file(step, tmp_path) == "数据/结果冗余文件"
    # pure timestep name without data/result keyword
    step2 = tmp_path / "output_10000.dat"
    step2.write_text("x", encoding="utf-8")
    assert should_delete_file(step2, tmp_path) == "时间步 .dat"
    static = tmp_path / "material.dat"
    static.write_text("x", encoding="utf-8")
    assert should_delete_file(static, tmp_path) is None


def test_delete_mohr_and_gif(tmp_path):
    mohr = tmp_path / "mohr_circle.png"
    mohr.write_bytes(b"x")
    assert should_delete_file(mohr, tmp_path) == "莫尔圆图片"
    gif = tmp_path / "anim.gif"
    gif.write_bytes(b"x")
    assert should_delete_file(gif, tmp_path) == "GIF 动画"
