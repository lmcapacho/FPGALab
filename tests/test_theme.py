from pathlib import Path

from PyQt6.QtWidgets import QApplication

from fpga_lab.board_editor import BoardLayoutEditor
from fpga_lab.board_layout import BoardLayout, bundled_layout
from fpga_lab.theme import DARK, LIGHT, Metrics, application_stylesheet, icon, palette


def test_dark_and_light_styles_share_semantic_structure():
    assert DARK.__dataclass_fields__.keys() == LIGHT.__dataclass_fields__.keys()
    for mode, expected in (("dark", DARK), ("light", LIGHT)):
        stylesheet = application_stylesheet(mode)
        assert palette() == expected
        assert expected.canvas in stylesheet
        assert expected.accent in stylesheet
        assert 'QPushButton[role="primary"]' in stylesheet
        assert 'QPushButton[role="danger"]' in stylesheet
        assert 'QPushButton[role="icon"]' in stylesheet
    application_stylesheet("dark")


def test_ui_icons_are_packaged_svg_assets():
    icon_dir = Path(__file__).parents[1] / "fpga_lab" / "assets" / "icons" / "ui"
    names = {path.stem for path in icon_dir.glob("*.svg")}
    assert {"play", "stop", "refresh", "tools", "settings", "connections", "edit", "zoom-in", "zoom-out", "chevron-down"} <= names
    assert Metrics.ICON_BUTTON_WIDTH >= Metrics.CONTROL_HEIGHT
    assert not icon("play").isNull()


def test_board_editor_uses_the_shared_theme_without_name_collisions():
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(application_stylesheet("dark"))
    editor = BoardLayoutEditor(BoardLayout.load(bundled_layout()))
    assert editor._canvas.backgroundBrush().color().name() == DARK.canvas
    editor.close()
