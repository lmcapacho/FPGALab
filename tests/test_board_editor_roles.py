"""The layout editor persists board-specific control roles."""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest

from fpga_lab.board_editor import BoardLayoutEditor
from fpga_lab.board_layout import BoardLayout


_APPLICATION = QApplication.instance() or QApplication([])


def test_editor_assigns_and_persists_signals_and_roles(tmp_path, monkeypatch):
    (tmp_path / "board.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="60"/>',
        encoding="utf-8",
    )
    source = tmp_path / "layout.json"
    source.write_text(json.dumps({
        "board_id": "sample", "svg": "board.svg", "viewBox": [0, 0, 100, 60],
        "components": [
            {"id": "status", "type": "led", "signal": "status_light", "x": 1, "y": 1, "width": 5, "height": 5},
            {"id": "restart", "type": "button", "signal": "restart_signal", "x": 10, "y": 1, "width": 5, "height": 5},
        ],
    }), encoding="utf-8")
    (tmp_path / "board.json").write_text(json.dumps({
        "id": "sample", "label": "Sample", "clock_hz": 12_000_000,
        "controls": {"clock": "CLK"},
        "pins": [
            {"id": "CLK", "fpga_pin": "1", "direction": "input", "location": "board.clock"},
            {"id": "LED_A", "fpga_pin": "2", "direction": "output", "location": "board.led"},
            {"id": "BTN_A", "fpga_pin": "3", "direction": "input", "location": "board.button"},
            {"id": "GPIO", "fpga_pin": "4", "direction": "inout", "location": "header"},
        ],
    }), encoding="utf-8")
    editor = BoardLayoutEditor(BoardLayout.load(source))
    assert not editor._signal.isEnabled()
    editor._items["status"].setSelected(True)
    assert editor._signal.currentData() == "status_light"
    assert not editor._signal.isEditable()
    assert editor._signal.findData("BTN_A") == -1
    assert editor._signal.findData("CLK") == -1
    assert editor._signal.findData("GPIO") >= 0
    assert editor._elements["status"].signal == "status_light"
    editor._signal.setCurrentIndex(editor._signal.findData("LED_A"))
    editor._role.setCurrentIndex(editor._role.findData("power"))
    editor._items["status"].setSelected(False)
    editor._items["restart"].setSelected(True)
    assert editor._signal.currentData() == "restart_signal"
    assert editor._signal.findData("LED_A") == -1
    assert editor._signal.findData("CLK") == -1
    editor._role.setCurrentIndex(editor._role.findData("reset"))
    assert editor._signal.isEditable()
    editor._signal.lineEdit().selectAll()
    QTest.keyClicks(editor._signal.lineEdit(), " ")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    original = source.read_text(encoding="utf-8")
    editor.save()
    assert warnings and source.read_text(encoding="utf-8") == original
    assert not source.with_suffix(".json.bak").exists()
    editor._signal.lineEdit().selectAll()
    QTest.keyClicks(editor._signal.lineEdit(), "BTN_A")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Save)

    editor.save()

    saved = BoardLayout.load(source)
    assert saved.signal_for_role("power") == "LED_A"
    assert saved.signal_for_role("reset") == "BTN_A"
    assert source.with_suffix(".json.bak").is_file()
    editor.deleteLater()
