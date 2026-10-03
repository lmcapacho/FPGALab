"""The layout editor persists board-specific control roles."""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from fpga_lab.board_editor import BoardLayoutEditor
from fpga_lab.board_layout import BoardLayout


_APPLICATION = QApplication.instance() or QApplication([])


def test_editor_assigns_and_persists_roles(tmp_path, monkeypatch):
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
    editor = BoardLayoutEditor(BoardLayout.load(source))
    editor._items["status"].setSelected(True)
    editor._role.setCurrentIndex(editor._role.findData("power"))
    editor._items["status"].setSelected(False)
    editor._items["restart"].setSelected(True)
    editor._role.setCurrentIndex(editor._role.findData("reset"))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Save)

    editor.save()

    saved = BoardLayout.load(source)
    assert saved.signal_for_role("power") == "status_light"
    assert saved.signal_for_role("reset") == "restart_signal"
    assert source.with_suffix(".json.bak").is_file()
    editor.deleteLater()
