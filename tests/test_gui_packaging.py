"""Portable GUI dependency contracts without host library requirements."""

import importlib.util
from pathlib import Path

import pytest


def test_linux_packaging_requires_xcb_libraries_and_leaves_other_platforms_alone():
    path = Path(__file__).parents[1] / "packaging/pyinstaller/linux_runtime.py"
    spec = importlib.util.spec_from_file_location("linux_qt_runtime", path)
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    resolve = lambda name: f"/synthetic/lib/{name}"
    binaries = runtime.collect_linux_qt_runtime(resolve, platform_name="linux")
    assert ("/synthetic/lib/libxcb-cursor.so.0", ".") in binaries
    assert len(binaries) == len(runtime.XCB_LIBRARIES)
    with pytest.raises(RuntimeError, match="libxcb-cursor.so.0"):
        runtime.collect_linux_qt_runtime(
            lambda name: None if name == "libxcb-cursor.so.0" else resolve(name), platform_name="linux")
    for platform_name in ("win32", "darwin"):
        assert runtime.collect_linux_qt_runtime(lambda _: pytest.fail("No Linux lookup"),
                                               platform_name=platform_name) == []
