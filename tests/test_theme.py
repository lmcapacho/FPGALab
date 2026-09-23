from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication

from fpga_lab.board_editor import BoardLayoutEditor
from fpga_lab.board_layout import BoardLayout, bundled_layout
from fpga_lab.lab_workspace import LabWorkspace
from fpga_lab.main_window import FPGALabMainWindow
from fpga_lab.theme import (
    DARK,
    LIGHT,
    Metrics,
    application_palette,
    application_stylesheet,
    icon,
    load_theme_mode,
    palette,
    save_theme_mode,
)


def test_dark_and_light_styles_share_semantic_structure():
    assert DARK.__dataclass_fields__.keys() == LIGHT.__dataclass_fields__.keys()
    for mode, expected in (("dark", DARK), ("light", LIGHT)):
        stylesheet = application_stylesheet(mode)
        assert palette() == expected
        assert expected.canvas in stylesheet
        assert expected.accent in stylesheet
        native_palette = application_palette(mode)
        assert native_palette.color(QPalette.ColorRole.Highlight).name() == expected.accent
        assert native_palette.color(QPalette.ColorRole.HighlightedText).name() == expected.accent_text
    application_stylesheet("dark")


def test_ui_icons_are_packaged_svg_assets():
    icon_dir = Path(__file__).parents[1] / "fpga_lab" / "assets" / "icons" / "ui"
    names = {path.stem for path in icon_dir.glob("*.svg")}
    assert {"play", "stop", "refresh", "tools", "settings", "connections", "edit", "zoom-in", "zoom-out", "chevron-down", "chevron-up", "chevron-down-light", "chevron-up-light", "sun", "moon"} <= names
    assert Metrics.ICON_BUTTON_WIDTH >= Metrics.CONTROL_HEIGHT
    assert not icon("play").isNull()


def test_board_editor_uses_the_shared_theme_without_name_collisions():
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(application_stylesheet("dark"))
    editor = BoardLayoutEditor(BoardLayout.load(bundled_layout()))
    assert editor._canvas.backgroundBrush().color().name() == DARK.canvas
    editor.close()


def test_theme_preference_is_validated_and_persisted(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)

    assert load_theme_mode(settings) == "dark"
    assert save_theme_mode("LIGHT", settings) == "light"
    assert load_theme_mode(settings) == "light"
    settings.setValue("ui/theme", "unknown")
    assert load_theme_mode(settings) == "dark"


def test_theme_button_switches_palette_and_user_preference(tmp_path):
    application = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = LabWorkspace(tmp_path / "labs", settings)
    window = FPGALabMainWindow(workspace, settings=settings)

    window._toggle_theme()

    assert load_theme_mode(settings) == "light"
    assert palette() == LIGHT
    assert not window._theme_button.icon().isNull()
    window.close()
    application.setStyleSheet(application_stylesheet("dark"))
