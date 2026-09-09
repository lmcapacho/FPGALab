"""Semantic visual theme shared by every FPGALab window and renderer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QPushButton


@dataclass(frozen=True)
class ThemePalette:
    canvas: str
    surface: str
    surface_raised: str
    surface_hover: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    success_hover: str
    success_surface: str
    danger: str
    danger_hover: str
    danger_surface: str
    warning: str
    board_surface: str
    board_border: str
    board_title: str
    workbench: str
    segment_off: str


DARK = ThemePalette(
    canvas="#0b1220", surface="#111a2b", surface_raised="#172238", surface_hover="#22304a",
    border="#27364f", border_strong="#41536f", text="#e6edf7", text_muted="#91a2bb",
    accent="#38bdf8", accent_hover="#7dd3fc", accent_text="#071521",
    success="#22c55e", success_hover="#4ade80", success_surface="#14532d",
    danger="#ef4444", danger_hover="#f87171", danger_surface="#7f1d1d", warning="#fbbf24",
    board_surface="#102820", board_border="#34d67b", board_title="#bbf7d0",
    workbench="#0d1628", segment_off="#334155",
)

LIGHT = ThemePalette(
    canvas="#eef3f8", surface="#ffffff", surface_raised="#f7f9fc", surface_hover="#e8eef6",
    border="#d4dde9", border_strong="#9aabc0", text="#172033", text_muted="#5f7088",
    accent="#0284c7", accent_hover="#0369a1", accent_text="#ffffff",
    success="#15803d", success_hover="#166534", success_surface="#dcfce7",
    danger="#dc2626", danger_hover="#b91c1c", danger_surface="#fee2e2", warning="#b45309",
    board_surface="#e8f5ee", board_border="#16a34a", board_title="#14532d",
    workbench="#f4f7fb", segment_off="#cbd5e1",
)


class Metrics:
    SPACE_XS = 4
    SPACE_SM = 6
    SPACE_MD = 8
    SPACE_LG = 12
    RADIUS_SM = 5
    RADIUS_MD = 8
    RADIUS_LG = 12
    CONTROL_HEIGHT = 28
    ICON_BUTTON_WIDTH = 32
    FONT_SIZE = 13
    FONT_SMALL = 11
    FONT_TITLE = 18


_palette = DARK
_ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons" / "ui"


def palette() -> ThemePalette:
    """Return the active semantic palette."""
    return _palette


def set_palette(mode: str) -> ThemePalette:
    """Select a prepared palette before rebuilding the application stylesheet."""
    global _palette
    _palette = LIGHT if mode.casefold() == "light" else DARK
    return _palette


def color(role: str) -> QColor:
    """Resolve a semantic color for custom-painted widgets."""
    return QColor(getattr(_palette, role))


def icon(name: str) -> QIcon:
    """Load one consistent interface SVG icon."""
    return QIcon(str(_ICON_DIR / f"{name}.svg"))


def style_button(button: QPushButton, role: str = "secondary", icon_name: str | None = None) -> None:
    """Apply a semantic role and optional SVG icon to a button."""
    button.setProperty("role", role)
    if icon_name:
        button.setIcon(icon(icon_name))
    if role in {"icon", "icon-danger"}:
        button.setFixedSize(Metrics.ICON_BUTTON_WIDTH, Metrics.CONTROL_HEIGHT)


def application_stylesheet(mode: str = "dark") -> str:
    """Build the application-wide QSS from one semantic palette."""
    p = set_palette(mode)
    combo_arrow = (_ICON_DIR / "chevron-down.svg").as_posix()
    return f"""
    QMainWindow, QDialog {{ background: {p.canvas}; }}
    QWidget {{ color: {p.text}; font-family: Inter, "Segoe UI", Arial, sans-serif; font-size: {Metrics.FONT_SIZE}px; }}
    QFrame#panel, QFrame#toolbarPanel {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: {Metrics.RADIUS_MD}px; }}
    QFrame#boardPanel {{ background: {p.board_surface}; border: 1px solid {p.board_border}; border-radius: {Metrics.RADIUS_LG}px; }}
    QLabel#boardTitle {{ color: {p.board_title}; font-size: {Metrics.FONT_TITLE}px; font-weight: 700; }}
    QLabel#caption, QLabel#infoText, QLabel#clockStatus {{ color: {p.text_muted}; font-size: {Metrics.FONT_SMALL}px; }}
    QLabel#errorText {{ color: {p.danger_hover}; font-size: {Metrics.FONT_SMALL}px; }}
    QLabel#emptyState {{ color: {p.text_muted}; font-size: 15px; padding: 28px; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {{
        min-height: {Metrics.CONTROL_HEIGHT}px; padding: 0 8px; background: {p.surface_raised};
        border: 1px solid {p.border}; border-radius: {Metrics.RADIUS_SM}px; selection-background-color: {p.accent};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus {{ border-color: {p.accent}; }}
    QComboBox {{ padding-right: 30px; }}
    QComboBox::drop-down {{ border: 0; width: 28px; }}
    QComboBox::down-arrow {{ image: url("{combo_arrow}"); width: 12px; height: 12px; }}
    QComboBox#languageSelector {{ padding: 0 14px 0 5px; }}
    QComboBox#languageSelector::drop-down {{ width: 14px; }}
    QComboBox#languageSelector::down-arrow {{ width: 8px; height: 8px; }}
    QSpinBox {{ padding-right: 24px; }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 20px; border: 0; background: {p.surface_hover}; }}
    QListWidget, QTableWidget, QGraphicsView {{ background: {p.workbench}; border: 1px solid {p.border}; border-radius: {Metrics.RADIUS_SM}px; }}
    QListWidget::item {{ padding: 5px 7px; border-radius: 4px; }}
    QListWidget::item:selected {{ background: {p.accent}; color: {p.accent_text}; }}
    QPushButton {{ min-height: {Metrics.CONTROL_HEIGHT}px; padding: 0 10px; background: {p.surface_raised}; border: 1px solid {p.border_strong}; border-radius: {Metrics.RADIUS_SM}px; }}
    QPushButton:hover {{ background: {p.surface_hover}; border-color: {p.accent}; }}
    QPushButton:pressed {{ background: {p.canvas}; }}
    QPushButton:disabled {{ color: {p.text_muted}; background: {p.surface}; border-color: {p.border}; }}
    QPushButton[role="primary"] {{ background: {p.accent}; border-color: {p.accent}; color: {p.accent_text}; font-weight: 650; }}
    QPushButton[role="primary"]:hover {{ background: {p.accent_hover}; }}
    QPushButton[role="success"] {{ background: {p.success}; border-color: {p.success_hover}; color: #ffffff; }}
    QPushButton[role="success"]:hover {{ background: {p.success_hover}; }}
    QPushButton[role="danger"] {{ background: {p.danger_surface}; border-color: {p.danger}; color: #ffffff; }}
    QPushButton[role="danger"]:hover {{ background: {p.danger}; }}
    QPushButton[role="selector"] {{ background: {p.surface_hover}; border-color: {p.border_strong}; font-weight: 600; }}
    QPushButton[role="selector"]:hover {{ border-color: {p.accent}; }}
    QPushButton[role="icon"] {{ padding: 0; background: transparent; border-color: {p.border}; }}
    QPushButton[role="icon"]:hover {{ background: {p.surface_hover}; border-color: {p.accent}; }}
    QPushButton[role="icon-danger"] {{ padding: 0; background: transparent; border-color: {p.border}; }}
    QPushButton[role="icon-danger"]:hover {{ background: {p.danger_surface}; border-color: {p.danger}; }}
    QPushButton[role="success"]:disabled, QPushButton[role="danger"]:disabled {{
        background: {p.surface}; border-color: {p.border}; color: {p.text_muted};
    }}
    QPushButton#switch {{ background: {p.surface_raised}; border: 1px solid {p.border_strong}; border-radius: {Metrics.RADIUS_MD}px; padding: 10px; font-weight: 700; }}
    QPushButton#switch:pressed {{ background: {p.success}; color: {p.accent_text}; }}
    QStatusBar {{ background: {p.surface}; color: {p.warning}; border-top: 1px solid {p.border}; font-weight: 600; }}
    QProgressBar {{ background: {p.surface_raised}; border: 1px solid {p.border}; border-radius: 4px; text-align: center; }}
    QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}
    QToolTip {{ background: {p.surface_raised}; color: {p.text}; border: 1px solid {p.border_strong}; padding: 4px; }}
    """
