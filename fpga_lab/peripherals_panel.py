"""Panel for registering peripherals and GPIO without visible wiring."""
from __future__ import annotations
import copy
import json
from pathlib import Path
from PyQt6.QtCore import QPointF, QSize, QTimer, Qt, pyqtSignal
import re
from PyQt6.QtGui import QColor, QCursor, QFont, QKeySequence, QPalette
from PyQt6.QtWidgets import QComboBox, QColorDialog, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGraphicsScene, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QKeySequenceEdit, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QMenu, QInputDialog
from .board import BoardDefinition
from .constraints import PcfParser
from .i18n import language_manager, t
from .peripheral_catalog_panel import PeripheralCatalogPanel
from .peripherals.catalog import load_catalog, spec_for
from .peripherals.install import install_package, uninstall_package
from .peripherals.manifest import RESERVED_PROPERTIES
from .peripherals.renderers.vga_monitor import VgaMonitorRenderer
from .temporal import LedModel, SignalWindow
from .wiring import SUPPLY_ENDPOINTS, PeripheralInstance, VirtualLabProject
from .theme import color, style_button
from .workbench import WorkbenchPeripheralItem, WorkbenchView
from .workbench.annotation import WorkbenchAnnotationItem


_EXTERNAL_LIGHT_PERSISTENCE_SECONDS = 0.030
_VISUAL_FUSION_EDGE_RATE_HZ = 60.0

class SegmentDisplay(QFrame):
    """Compact representation of an external seven-segment display."""

    _POSITIONS = {"a": (0, 1), "b": (1, 2), "c": (3, 2), "d": (4, 1), "e": (3, 0), "f": (1, 0), "g": (2, 1)}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setSpacing(1)
        for name, (row, column) in self._POSITIONS.items():
            segment = QLabel("━" if name in {"a", "d", "g"} else "┃")
            segment.setAlignment(Qt.AlignmentFlag.AlignCenter)
            font = QFont("monospace", 12, QFont.Weight.Bold)
            segment.setFont(font)
            self._set_color(segment, color("segment_off"))
            grid.addWidget(segment, row, column)
            self._segments[name] = segment

    def set_segment(self, name, active):
        segment = self._segments.get(name)
        if segment is not None:
            self._set_color(segment, QColor("#ff9d26") if active else color("segment_off"))

    @staticmethod
    def _set_color(label: QLabel, value: QColor) -> None:
        label_palette = label.palette()
        label_palette.setColor(QPalette.ColorRole.WindowText, value)
        label.setPalette(label_palette)


class PeripheralConfigDialog(QDialog):
    """Modal editor for one instance; fields come from the catalog schema."""

    save_requested = pyqtSignal()

    def __init__(self, peripheral, board, assigned_endpoints=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Configure · {identifier}", identifier=peripheral.peripheral_id))
        self._board = board
        self._assigned_endpoints = assigned_endpoints
        self._kind = peripheral.kind
        self._spec = spec_for(peripheral.kind)
        self._pickers = {}
        self._properties = dict(peripheral.properties)
        self._property_widgets = {}
        self._delete_requested = False
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.identifier = QLineEdit(peripheral.peripheral_id)
        form.addRow(t("Identifier"), self.identifier)
        for terminal in self._spec.terminals:
            picker = QComboBox()
            picker.addItem(t("— not connected —"), "")
            for supply in terminal.supplies:
                picker.addItem(t(f"{supply} (fixed)"), supply)
            for pin in board.available_endpoints(terminal.direction):
                if pin.location.startswith("header") and (self._assigned_endpoints is None or pin.id in self._assigned_endpoints):
                    picker.addItem(pin.id, pin.id)
            index = picker.findData(peripheral.connections.get(terminal.name, ""))
            picker.setCurrentIndex(max(0, index))
            label = terminal.name if terminal.required else t("{terminal} (optional)", terminal=terminal.name)
            form.addRow(label, picker)
            self._pickers[terminal.name] = picker
        for name, schema in self._spec.properties.items():
            if name in RESERVED_PROPERTIES:
                continue
            form.addRow(t(str(schema.get("label", name))), self._property_widget(name, schema, peripheral.properties))
        layout.addLayout(form)
        self._error_label = QLabel()
        self._error_label.setObjectName("errorText")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(t("Save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("Cancel"))
        delete = buttons.addButton(t("Delete"), QDialogButtonBox.ButtonRole.DestructiveRole)
        style_button(delete, "danger")
        style_button(buttons.button(QDialogButtonBox.StandardButton.Save), "primary")
        delete.clicked.connect(self._request_delete)
        buttons.accepted.connect(self.save_requested.emit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _property_widget(self, name, schema, properties):
        kind = schema.get("type")
        if kind == "color":
            current = str(properties.get(name, schema.get("default", "#b6ff00")))
            button = QPushButton(current)
            button.clicked.connect(lambda _=False, key=name, widget=button: self._pick_color(key, widget, None))
            self._property_widgets[name] = ("color", button)
            return button
        if kind == "color_map":
            keys = list(schema.get("keys") or [])
            defaults = dict(schema.get("default") or {})
            current = {**defaults, **dict(properties.get(name, {}))}
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            buttons = {}
            for key in keys:
                button = QPushButton(str(current.get(key, "#ffffff")))
                button.clicked.connect(lambda _=False, map_name=name, map_key=key, widget=button: self._pick_color(map_name, widget, map_key))
                row.addWidget(QLabel(key))
                row.addWidget(button)
                buttons[key] = button
            self._property_widgets[name] = ("color_map", buttons, current)
            return box
        if kind == "enum":
            combo = QComboBox()
            for value in schema.get("values") or []:
                combo.addItem(str(value), str(value))
            current = str(properties.get(name, schema.get("default", "")))
            index = combo.findData(current)
            combo.setCurrentIndex(max(0, index))
            self._property_widgets[name] = ("enum", combo)
            return combo
        if kind == "boolean":
            from PyQt6.QtWidgets import QCheckBox
            box = QCheckBox()
            box.setChecked(bool(properties.get(name, schema.get("default", False))))
            self._property_widgets[name] = ("boolean", box)
            return box
        if kind == "key_sequence":
            editor = QKeySequenceEdit(self)
            editor.setKeySequence(QKeySequence(str(properties.get(name, schema.get("default", "")))))
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(editor, 1)
            clear = QPushButton(t("Clear"))
            clear.clicked.connect(editor.clear)
            row.addWidget(clear)
            self._property_widgets[name] = ("key_sequence", editor)
            return box
        field = QLineEdit(str(properties.get(name, schema.get("default", ""))))
        self._property_widgets[name] = ("string", field)
        return field

    def _request_delete(self):
        self._delete_requested = True
        self.done(2)

    def show_error(self, message: str, endpoint: str | None = None) -> None:
        """Keep the editor open and clear only an invalid endpoint assignment."""
        if endpoint:
            for picker in self._pickers.values():
                if picker.currentData() == endpoint:
                    picker.setCurrentIndex(0)
                    break
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def _pick_color(self, property_name, button: QPushButton, map_key: str | None):
        current = button.text()
        color = QColorDialog.getColor(QColor(current), self)
        if not color.isValid():
            return
        button.setText(color.name())
        widget = self._property_widgets[property_name]
        if map_key is not None:
            widget[2][map_key] = color.name()

    def value(self):
        connections = {name: picker.currentData() for name, picker in self._pickers.items() if picker.currentData()}
        properties = dict(self._properties)
        for name, widget in self._property_widgets.items():
            kind = widget[0]
            if kind == "color":
                properties[name] = widget[1].text()
            elif kind == "color_map":
                properties[name] = dict(widget[2])
            elif kind == "enum":
                properties[name] = widget[1].currentData()
            elif kind == "boolean":
                properties[name] = widget[1].isChecked()
            elif kind == "key_sequence":
                properties[name] = widget[1].keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            else:
                properties[name] = widget[1].text()
        return {"id": self.identifier.text().strip(), "type": self._kind, "connections": connections, "properties": properties}


class ConnectionDialog(QDialog):
    """Explain virtual physical connections without requiring visible wires."""

    def __init__(self, board: BoardDefinition, constraints, wires, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Connections"))
        self.resize(780, 460)
        layout = QVBoxLayout(self)
        description = QLabel(t("Board endpoints used by the PCF or an external peripheral."))
        description.setWordWrap(True)
        layout.addWidget(description)
        table = QTableWidget(self)
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            t("Board endpoint"),
            t("FPGA pin"),
            t("Direction"),
            t("HDL net (PCF)"),
            t("External peripheral"),
        ])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        net_by_pin = {constraint.fpga_pin: constraint.net for constraint in constraints}
        peripherals_by_endpoint: dict[str, list[str]] = {}
        for wire in wires:
            peripherals_by_endpoint.setdefault(wire.board_endpoint, []).append(f"{wire.peripheral_id}.{wire.terminal}")
        rows = [
            pin for pin in board.pins
            if pin.fpga_pin in net_by_pin or pin.id in peripherals_by_endpoint
        ]
        table.setRowCount(len(rows))
        for row, pin in enumerate(rows):
            values = (
                pin.id,
                pin.fpga_pin,
                pin.direction,
                net_by_pin.get(pin.fpga_pin, t("— not mapped —")),
                ", ".join(peripherals_by_endpoint.get(pin.id, ())) or t("— none —"),
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        close.accepted.connect(self.accept)
        layout.addWidget(close)



class PeripheralsPanel(QWidget):
    changed = pyqtSignal(str)
    input_changed = pyqtSignal(str, int)
    temporal_probes_changed = pyqtSignal(object)
    edge_channels_changed = pyqtSignal(object)

    def __init__(
        self,
        board: BoardDefinition,
        pcf: Path | None,
        lab: Path,
        input_widths: dict[str, int] | None = None,
        output_widths: dict[str, int] | None = None,
        parent=None,
    ):
        super().__init__(parent); self._board, self._pcf, self._lab = board, pcf, lab
        self._input_widths = input_widths or {}
        self._output_widths = output_widths or {}
        self._output_indexes = {name: index for index, name in enumerate(self._output_widths)}
        self._input_values = {}; self._editing_enabled = True
        self._powered = False
        self._assigned_endpoints = None  # The entire board is available; the design PCF is optional.
        self._temporal_probes: list[tuple[tuple[int, int, bool], ...]] = []
        self._temporal_bindings: list[tuple[WorkbenchPeripheralItem, str]] = []
        self._temporal_terminals: set[tuple[str, str]] = set()
        self._temporal_models: list[LedModel] = []
        self._edge_bindings: list[tuple[WorkbenchPeripheralItem, str, int, int]] = []
        self._active_shortcut_keys: dict[int, list[WorkbenchPeripheralItem]] = {}
        self._restoring_workbench_state = False
        self._history: list[tuple[dict[str, object], dict[str, object], str]] = []
        self._history_index = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 8)
        layout.setSpacing(5)
        workbench_header = QHBoxLayout(); workbench_header.setSpacing(4)
        self._workbench_hint = QLabel()
        workbench_header.addWidget(self._workbench_hint)
        self._connection_status = QLabel()
        self._connection_status.setObjectName("infoText")
        workbench_header.addWidget(self._connection_status)
        workbench_header.addStretch(1)
        self._zoom_out_button = QPushButton()
        self._zoom_reset_button = QPushButton()
        self._zoom_in_button = QPushButton()
        self._zoom_fit_button = QPushButton()
        self._undo_button = QPushButton()
        self._redo_button = QPushButton()
        self._annotation_button = QPushButton()
        self._annotation_menu = QMenu(self)
        self._annotation_actions = {}
        for kind, label in (("text", "Text"), ("rectangle", "Rectangle"), ("ellipse", "Ellipse"), ("line", "Line")):
            self._annotation_actions[label] = self._annotation_menu.addAction(
                t(label), lambda checked=False, kind=kind: self._add_annotation(kind)
            )
        self._annotation_button.setMenu(self._annotation_menu)
        style_button(self._annotation_button, "secondary")
        style_button(self._undo_button, "icon", "undo")
        style_button(self._redo_button, "icon", "redo")
        style_button(self._zoom_out_button, "icon", "zoom-out")
        style_button(self._zoom_in_button, "icon", "zoom-in")
        style_button(self._zoom_fit_button, "icon", "fit")
        for button in (self._zoom_out_button, self._zoom_reset_button, self._zoom_in_button, self._zoom_fit_button):
            button.setFixedWidth(32)
        self._zoom_reset_button.setFixedWidth(60)
        workbench_header.addWidget(self._undo_button)
        workbench_header.addWidget(self._redo_button)
        workbench_header.addWidget(self._annotation_button)
        workbench_header.addSpacing(4)
        workbench_header.addWidget(self._zoom_out_button)
        workbench_header.addWidget(self._zoom_reset_button)
        workbench_header.addWidget(self._zoom_in_button)
        workbench_header.addWidget(self._zoom_fit_button)
        layout.addLayout(workbench_header)
        self._compatibility_notice = QLabel()
        self._compatibility_notice.setObjectName("warningText")
        self._compatibility_notice.setWordWrap(True)
        self._compatibility_notice.hide()
        layout.addWidget(self._compatibility_notice)
        self._workbench_scene = QGraphicsScene(self); self.workbench = WorkbenchView(self._workbench_scene, self._delete_many, self._duplicate_many, self._save_positions, self.undo, self.redo)
        self._undo_button.clicked.connect(self.undo)
        self._redo_button.clicked.connect(self.redo)
        self._zoom_out_button.clicked.connect(self.workbench.zoom_out)
        self._zoom_reset_button.clicked.connect(self.workbench.reset_zoom)
        self._zoom_in_button.clicked.connect(self.workbench.zoom_in)
        self._zoom_fit_button.clicked.connect(self.workbench.fit_contents)
        self.workbench.zoom_changed.connect(self._update_zoom_label)
        self.workbench.zoom_changed.connect(self._persist_workbench_zoom)
        self.workbench.camera_changed.connect(self._persist_workbench_center)
        self.workbench.setMinimumHeight(330); layout.addWidget(self.workbench, 1)
        self._catalog_button = QPushButton(self)
        self._catalog_button.setObjectName("floatingCatalogButton")
        style_button(self._catalog_button, "primary", "catalog")
        self._catalog_button.setFixedSize(44, 44)
        self._catalog_button.setIconSize(QSize(22, 22))
        self._catalog_button.clicked.connect(self._toggle_catalog)
        # The workbench geometry is not final until its first layout pass.
        # Keep the overlay hidden instead of briefly painting it at (0, 0).
        self._catalog_button.hide()
        self._catalog_panel = PeripheralCatalogPanel(load_catalog(), self)
        self._catalog_panel.add_requested.connect(self._add_kind)
        self._catalog_panel.install_requested.connect(self._install_peripheral)
        self._catalog_panel.uninstall_requested.connect(self._uninstall_peripheral)
        self._workbench_bindings = {}; self._reload()
        self._update_history_actions()
        language_manager.language_changed.connect(self._retranslate_ui)
        self._retranslate_ui()
        QTimer.singleShot(0, self._position_catalog_button)
    def _retranslate_ui(self) -> None:
        self._catalog_button.setText("")
        self._catalog_button.setToolTip(t("Open peripheral catalog"))
        self._catalog_button.setAccessibleName(t("Open peripheral catalog"))
        self._catalog_panel.retranslate_ui()
        self._workbench_hint.setText(t("Virtual workbench"))
        self._annotation_button.setText(t("Annotate"))
        self._annotation_button.setToolTip(t("Add text or shapes to the Lab"))
        for label, action in self._annotation_actions.items():
            action.setText(t(label))
        self._workbench_hint.setToolTip(t("Drag empty space to select multiple parts. Shift+click changes the selection. Drag a selected part to move the group. Use the wheel to zoom. Ctrl+drag or middle-drag pans."))
        self._undo_button.setToolTip(t("Undo (Ctrl+Z)"))
        self._redo_button.setToolTip(t("Redo (Ctrl+Y or Ctrl+Shift+Z)"))
        self._zoom_out_button.setToolTip(t("Zoom out"))
        self._zoom_reset_button.setToolTip(t("Reset zoom"))
        self._zoom_in_button.setToolTip(t("Zoom in"))
        self._zoom_fit_button.setToolTip(t("Fit all parts"))
        self._update_zoom_label(self.workbench._zoom)
        self._update_connection_status()
        for item in self._workbench_scene.items():
            item.update()

    def refresh_theme(self) -> None:
        """Refresh custom-painted peripheral items after a palette change."""
        self._workbench_scene.update()
        self.workbench.viewport().update()
        self._catalog_panel.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_catalog_panel"):
            self._catalog_panel.reposition()
        QTimer.singleShot(0, self._position_catalog_button)

    def _position_catalog_button(self) -> None:
        """Anchor the catalog action over the workbench's upper-right corner."""
        if not hasattr(self, "workbench") or not hasattr(self, "_catalog_button"):
            return
        margin = 14
        workbench_rect = self.workbench.geometry()
        if workbench_rect.width() < self._catalog_button.width() + margin * 2:
            return
        x = workbench_rect.right() - self._catalog_button.width() - margin
        y = workbench_rect.top() + margin
        self._catalog_button.move(x, y)
        self._catalog_button.show()
        if not self._catalog_panel.isVisible():
            self._catalog_button.raise_()

    def _toggle_catalog(self) -> None:
        if self._editing_enabled:
            self._catalog_panel.toggle()

    def _install_peripheral(self) -> None:
        menu = QMenu(self)
        zip_action = menu.addAction(t("Shared package (.zip)…"))
        folder_action = menu.addAction(t("Local development folder…"))
        chosen = menu.exec(QCursor.pos())
        if chosen == zip_action:
            selected, _ = QFileDialog.getOpenFileName(self, t("Install peripheral"), "", "ZIP (*.zip)")
        elif chosen == folder_action:
            selected = QFileDialog.getExistingDirectory(self, t("Install peripheral"))
        else:
            return
        if not selected:
            return
        def confirm_update(identifier: str, old_version: str | None, new_version: str) -> bool:
            answer = QMessageBox.question(
                self, t("Update peripheral"),
                t("Update {identifier} from {old_version} to {new_version}? The installed package files will be replaced; Labs and their connections will be preserved.",
                  identifier=identifier, old_version=old_version or t("unversioned"), new_version=new_version),
            )
            return answer == QMessageBox.StandardButton.Yes

        try:
            result = install_package(Path(selected), confirm_update=confirm_update)
            if result.action == "cancelled":
                return
            if result.action == "unchanged":
                QMessageBox.information(self, t("Peripheral unchanged"), t("Peripheral {identifier} is already installed with identical files.", identifier=result.identifier))
                return
            self._catalog_panel.set_specs(load_catalog())
            self._reload()
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, t("Cannot install peripheral"), str(exc))
            return
        if result.action == "updated":
            QMessageBox.information(self, t("Peripheral updated"), t("Peripheral {identifier} was updated. Existing Labs and connections were preserved.", identifier=result.identifier))
        else:
            QMessageBox.information(self, t("Peripheral installed"), t("Peripheral {identifier} is ready to add.", identifier=result.identifier))

    def _uninstall_peripheral(self, identifier: str) -> None:
        answer = QMessageBox.question(
            self, t("Uninstall peripheral"),
            t("Remove {identifier} from this computer? Labs that use it will retain their data but show an unavailable peripheral until it is reinstalled.", identifier=identifier),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            uninstall_package(identifier)
            self._catalog_panel.set_specs(load_catalog())
            self._reload()
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, t("Cannot uninstall peripheral"), str(exc))

    def _constraints(self):
        """Load optional design constraints without requiring a PCF for the board UI."""
        return PcfParser.parse_file(self._pcf) if self._pcf and self._pcf.is_file() else []

    def set_lab_file(self, lab: str | Path) -> None:
        """Replace the workbench content with another saved laboratory."""
        next_lab = Path(lab)
        if next_lab == self._lab:
            return
        for port in tuple(self._input_values):
            self.input_changed.emit(port, 0)
        self._input_values.clear()
        self._active_shortcut_keys.clear()
        self._lab = next_lab
        self._history.clear()
        self._history_index = 0
        self._update_history_actions()
        self._reload()

    def _reload(self):
        project = VirtualLabProject.load(self._lab)
        wires, warnings = project.resolve_compatible(self._board, self._constraints())
        self._compatibility_warnings = warnings
        self._compatibility_notice.setVisible(bool(warnings))
        self._compatibility_notice.setText(t(
            "Compatibility notice: some Lab elements are inactive but remain preserved. {details}",
            details=" ".join(warnings),
        ) if warnings else "")
        self._resolved_wires = wires
        self._connection_counts = (len(wires), sum(wire.hdl_net is not None for wire in wires))
        self._workbench_scene.clear(); self._workbench_bindings = {}
        workbench_items: dict[str, WorkbenchPeripheralItem] = {}
        for index, peripheral in enumerate(project.peripherals):
            bench_item = WorkbenchPeripheralItem(peripheral, self._configure, self._save_position, self._drive_input)
            bench_item.set_editable(self._editing_enabled)
            if "position" not in peripheral.properties:
                bench_item.setPos(16 + (index % 3) * 160, 16 + (index // 3) * 88)
            self._workbench_scene.addItem(bench_item)
            workbench_items[peripheral.peripheral_id] = bench_item
            for wire in wires:
                if wire.peripheral_id == peripheral.peripheral_id:
                    self._workbench_bindings[(peripheral.peripheral_id, wire.terminal)] = (bench_item, wire.hdl_net)
        for annotation in json.loads(self._lab.read_text(encoding="utf-8")).get("annotations", []):
            if isinstance(annotation, dict) and annotation.get("type") in {"text", "rectangle", "ellipse", "line"}:
                item = WorkbenchAnnotationItem(annotation, self._edit_annotation)
                item.set_editable(self._editing_enabled)
                self._workbench_scene.addItem(item)
        self._rebuild_temporal_probes(project, workbench_items)
        self._rebuild_edge_channels(project, workbench_items)
        self._restore_workbench_zoom()
        self._update_connection_status()

    def _restore_workbench_zoom(self) -> None:
        """Load optional presentation state while remaining compatible with older Labs."""
        try:
            raw = json.loads(self._lab.read_text(encoding="utf-8"))
            state = raw.get("workbench", {})
            zoom = float(state.get("zoom", 1.0)) if isinstance(state, dict) else 1.0
            raw_center = state.get("center") if isinstance(state, dict) else None
            center = (
                QPointF(float(raw_center[0]), float(raw_center[1]))
                if isinstance(raw_center, list) and len(raw_center) == 2
                else None
            )
        except (OSError, ValueError, json.JSONDecodeError):
            zoom = 1.0
            center = None
        self._restoring_workbench_state = True
        try:
            self.workbench.set_zoom(zoom)
            self.workbench.restore_camera(center)
        finally:
            self._restoring_workbench_state = False

    def _persist_workbench_zoom(self, zoom: float) -> None:
        """Store visual framing alongside the Lab rather than in global user preferences."""
        if self._restoring_workbench_state:
            return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        state = raw.setdefault("workbench", {})
        if not isinstance(state, dict):
            state = raw["workbench"] = {}
        state["zoom"] = round(zoom, 4)
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    def _persist_workbench_center(self, center: QPointF) -> None:
        """Store the camera independently from peripheral coordinates."""
        if self._restoring_workbench_state:
            return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        state = raw.setdefault("workbench", {})
        if not isinstance(state, dict):
            state = raw["workbench"] = {}
        state["center"] = [round(center.x(), 2), round(center.y(), 2)]
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    def _output_condition(self, net: str | None, expected: bool) -> tuple[int, int, bool] | None:
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_$]*)(?:\[(\d+)])?", net or "")
        if match is None:
            return None
        name, raw_bit = match.groups()
        bit = int(raw_bit) if raw_bit else 0
        if name not in self._output_widths or bit >= self._output_widths[name]:
            return None
        return self._output_indexes[name], bit, expected

    def _rebuild_temporal_probes(self, project, workbench_items) -> None:
        """Create output predicates from a peripheral's manifest metadata."""
        probes: list[tuple[tuple[int, int, bool], ...]] = []
        bindings: list[tuple[WorkbenchPeripheralItem, str]] = []
        temporal_terminals: set[tuple[str, str]] = set()

        def add(peripheral_id: str, terminal: str, conditions: list[tuple[int, int, bool]]) -> None:
            if conditions:
                probes.append(tuple(conditions))
                bindings.append((workbench_items[peripheral_id], terminal))

        for peripheral in project.peripherals:
            try:
                spec = spec_for(peripheral.kind)
            except ValueError:
                continue
            temporal = spec.temporal
            if temporal is None:
                continue
            if temporal["mode"] == "per_terminal":
                for terminal in spec.terminals:
                    if terminal.direction != "output":
                        continue
                    binding = self._workbench_bindings.get((peripheral.peripheral_id, terminal.name))
                    condition = self._output_condition(binding[1] if binding else None, True)
                    if condition is not None:
                        add(peripheral.peripheral_id, terminal.name, [condition])
                continue

            common_terminal = str(temporal["common_terminal"])
            common_type = str(peripheral.properties.get(str(temporal["polarity_property"]), "cathode"))
            common_endpoint = peripheral.connections.get(
                common_terminal, "GND" if common_type == "cathode" else "VCC"
            )
            if common_endpoint in SUPPLY_ENDPOINTS:
                common_conditions = [] if common_endpoint == ("GND" if common_type == "cathode" else "VCC") else None
            else:
                binding = self._workbench_bindings.get((peripheral.peripheral_id, common_terminal))
                condition = self._output_condition(binding[1] if binding else None, common_type == "anode")
                common_conditions = [condition] if condition is not None else None
            if common_conditions is None:
                temporal_terminals.update(
                    (peripheral.peripheral_id, str(terminal))
                    for terminal in temporal.get("active_terminals", ())
                )
                continue
            for terminal in temporal.get("active_terminals", ()):
                temporal_terminals.add((peripheral.peripheral_id, str(terminal)))
                binding = self._workbench_bindings.get((peripheral.peripheral_id, str(terminal)))
                # Segment current flows low for common-anode displays and high
                # for common-cathode displays. The common enable is handled above.
                condition = self._output_condition(binding[1] if binding else None, common_type == "cathode")
                if condition is not None:
                    add(peripheral.peripheral_id, str(terminal), [*common_conditions, condition])

        self._temporal_probes = probes
        self._temporal_bindings = bindings
        self._temporal_terminals = temporal_terminals | {
            (item.peripheral.peripheral_id, terminal) for item, terminal in bindings
        }
        self._temporal_models = [LedModel(_EXTERNAL_LIGHT_PERSISTENCE_SECONDS) for _ in bindings]
        self.temporal_probes_changed.emit(self.temporal_probes())

    def temporal_probes(self) -> list[tuple[tuple[int, int, bool], ...]]:
        return list(self._temporal_probes)

    def _rebuild_edge_channels(self, project, workbench_items) -> None:
        bindings: list[tuple[WorkbenchPeripheralItem, str, int, int]] = []
        for peripheral in project.peripherals:
            try:
                spec = spec_for(peripheral.kind)
            except ValueError:
                continue
            for terminal in spec.edge_channels:
                wire = self._workbench_bindings.get((peripheral.peripheral_id, terminal))
                condition = self._output_condition(wire[1] if wire else None, True)
                if condition is not None:
                    output, bit, _ = condition
                    bindings.append((workbench_items[peripheral.peripheral_id], terminal, output, bit))
        self._edge_bindings = bindings
        self.edge_channels_changed.emit(self.edge_channels())

    def edge_channels(self) -> list[tuple[int, int]]:
        return [(output, bit) for _, _, output, bit in self._edge_bindings]

    def _update_connection_status(self) -> None:
        """Summarize physical terminals and the subset currently present in HDL."""
        total, mapped = getattr(self, "_connection_counts", (0, 0))
        if total == 0:
            self._connection_status.setText(t("PCF —"))
            self._connection_status.setToolTip(t("No peripheral terminals configured."))
            return
        unmapped = total - mapped
        self._connection_status.setText(t("PCF {mapped}/{total}", mapped=mapped, total=total))
        self._connection_status.setToolTip(t(
            "{mapped}/{total} peripheral terminal(s) are mapped by the current PCF; {unmapped} are physically connected but unused by this HDL.",
            mapped=mapped,
            total=total,
            unmapped=unmapped,
        ))

    def _update_zoom_label(self, zoom: float) -> None:
        self._zoom_reset_button.setText(f"{round(zoom * 100)}%")

    def _show_status(self, message: str, timeout_ms: int = 3500) -> None:
        """Forward concise feedback to the application's shared status bar."""
        del timeout_ms
        self.changed.emit(message)

    def set_editable(self, enabled):
        self._editing_enabled = enabled
        self._catalog_button.setEnabled(enabled)
        self._annotation_button.setEnabled(enabled)
        if not enabled:
            self._catalog_panel.close_drawer()
        self.workbench.set_editable(enabled)
        self._update_history_actions()
        for item in self._workbench_scene.items():
            if isinstance(item, (WorkbenchPeripheralItem, WorkbenchAnnotationItem)): item.set_editable(enabled)

    def set_powered(self, powered: bool) -> None:
        """Propagate simulation power state to manifest renderers."""
        self._powered = powered
        for item in self._workbench_scene.items():
            if isinstance(item, WorkbenchPeripheralItem):
                item.set_powered(powered)

    def handle_shortcut_event(self, event, pressed: bool) -> bool:
        """Route configured keyboard shortcuts as momentary external button presses."""
        key = event.key()
        if event.isAutoRepeat():
            return key in self._active_shortcut_keys
        if pressed:
            sequence = QKeySequence(event.keyCombination())
            matches: list[WorkbenchPeripheralItem] = []
            for item in self._workbench_scene.items():
                if not isinstance(item, WorkbenchPeripheralItem) or item.peripheral.kind != "button":
                    continue
                shortcut = str(item.peripheral.properties.get("shortcut", ""))
                configured = QKeySequence.fromString(shortcut, QKeySequence.SequenceFormat.PortableText)
                if shortcut and configured.matches(sequence) == QKeySequence.SequenceMatch.ExactMatch:
                    matches.append(item)
            if not matches:
                return False
            self._active_shortcut_keys[key] = matches
            for item in matches:
                item.set_button_pressed(f"key:{key}", True)
            return True
        matches = self._active_shortcut_keys.pop(key, [])
        for item in matches:
            item.set_button_pressed(f"key:{key}", False)
        return bool(matches)

    def open_connections(self) -> None:
        """Show PCF and peripheral mappings in a compact, inspectable table."""
        ConnectionDialog(self._board, self._constraints(), self._resolved_wires, self).exec()

    def _drive_input(self, peripheral_id, terminal, value):
        if not self._powered:
            return
        binding = self._workbench_bindings.get((peripheral_id, terminal))
        net = binding[1] if binding else None
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_$]*)(?:\[(\d+)\])?", net or "")
        if not match or match.group(1) not in self._input_widths:
            return
        port, raw_bit = match.groups()
        bit = int(raw_bit) if raw_bit else 0
        if bit >= self._input_widths[port]: return
        current = self._input_values.get(port, 0)
        current = current | (1 << bit) if value else current & ~(1 << bit)
        self._input_values[port] = current; self.input_changed.emit(port, current)

    def _save_position(self, peripheral_id, x, y):
        self._save_positions([(peripheral_id, x, y)])

    def _save_positions(self, updates: list[tuple[str, float, float]]) -> None:
        """Persist one completed drag as a single Lab document update."""
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        previous = json.loads(json.dumps(raw))
        positions = {update[0]: [round(update[1], 1), round(update[2], 1)] for update in updates}
        geometries = {update[0]: update[3:] for update in updates if len(update) > 3}
        for item in raw.get("peripherals", []):
            if item["id"] in positions:
                item.setdefault("properties", {})["position"] = positions[item["id"]]
        for item in raw.get("annotations", []):
            if item.get("id") in positions:
                item["position"] = positions[item["id"]]
                if item["id"] in geometries:
                    width, height, reverse, orientation = geometries[item["id"]]
                    item["width"] = round(width, 1)
                    item["height"] = round(height, 1)
                    item["reverse"] = reverse
                    item["orientation"] = orientation
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        message = t("Moved {count} peripheral(s)", count=len(updates))
        self._record_history(previous, raw, message)
        self.changed.emit(message)

    def _commit(self, raw, message):
        previous = json.loads(self._lab.read_text(encoding="utf-8"))
        try:
            VirtualLabProject.from_raw(raw).resolve_compatible(self._board, self._constraints())
        except Exception as exc:
            self._show_configuration_error(str(exc))
            return False
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        self._record_history(previous, raw, message)
        self._show_status(message)
        self._reload()
        return True

    def _record_history(self, before: dict[str, object], after: dict[str, object], message: str) -> None:
        """Record one complete Lab mutation, dropping any abandoned redo branch."""
        if before == after:
            return
        del self._history[self._history_index:]
        self._history.append((before, json.loads(json.dumps(after)), message))
        if len(self._history) > 50:
            del self._history[0]
        self._history_index = len(self._history)
        self._update_history_actions()

    def undo(self) -> None:
        if not self._editing_enabled or self._history_index == 0:
            return
        before, _, message = self._history[self._history_index - 1]
        self._history_index -= 1
        self._restore_history_document(before, t("Undid: {action}", action=message))

    def redo(self) -> None:
        if not self._editing_enabled or self._history_index >= len(self._history):
            return
        _, after, message = self._history[self._history_index]
        self._history_index += 1
        self._restore_history_document(after, t("Redid: {action}", action=message))

    def _restore_history_document(self, raw: dict[str, object], message: str) -> None:
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        self._reload()
        self._show_status(message)
        self._update_history_actions()

    def _update_history_actions(self) -> None:
        if not hasattr(self, "_undo_button"):
            return
        self._undo_button.setEnabled(self._editing_enabled and self._history_index > 0)
        self._redo_button.setEnabled(self._editing_enabled and self._history_index < len(self._history))

    def history_state(self) -> tuple[list[tuple[dict[str, object], dict[str, object], str]], int]:
        """Return a detached session history before the simulation rebuilds the Lab widget."""
        return copy.deepcopy(self._history), self._history_index

    def restore_history_state(
        self,
        state: tuple[list[tuple[dict[str, object], dict[str, object], str]], int],
    ) -> None:
        """Restore history belonging to the same Lab after a widget replacement."""
        history, index = state
        self._history = copy.deepcopy(history[-50:])
        self._history_index = max(0, min(int(index), len(self._history)))
        self._update_history_actions()

    def _show_configuration_error(self, message: str) -> None:
        """Keep validation failures visible instead of hiding them below the catalog."""
        self._show_status(message, 7000)
        QMessageBox.warning(self, t("Peripheral configuration"), message)

    def _configure(self, peripheral):
        try:
            spec_for(peripheral.kind)
        except ValueError:
            QMessageBox.information(
                self,
                t("Unsupported peripheral"),
                t(
                    "{identifier} uses the unavailable type '{kind}'. Its data will remain in the Lab. Install the matching peripheral or open the Lab with a compatible FPGALab version to configure it.",
                    identifier=peripheral.peripheral_id,
                    kind=peripheral.kind,
                ),
            )
            return
        dialog = PeripheralConfigDialog(peripheral, self._board, self._assigned_endpoints, self)
        dialog.save_requested.connect(lambda: self._save_configuration(dialog, peripheral))
        result = dialog.exec()
        if result == 2: self._delete_many([peripheral]); return
        if result != QDialog.DialogCode.Accepted: return

    def _save_configuration(self, dialog: PeripheralConfigDialog, peripheral) -> None:
        value = dialog.value()
        if not value["id"]:
            dialog.show_error(t("Complete the identifier."))
            return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        ids = [item["id"] for item in raw.get("peripherals", []) if item["id"] != peripheral.peripheral_id]
        if value["id"] in ids:
            dialog.show_error(t("A peripheral with that identifier already exists."))
            return
        for index, item in enumerate(raw.get("peripherals", [])):
            if item["id"] == peripheral.peripheral_id:
                dialog_properties = dict(value["properties"]); dialog_properties.pop("position", None)
                value["properties"] = {**item.get("properties", {}), **dialog_properties}
                raw["peripherals"][index] = value; break
        error = self._validation_error(raw)
        if error:
            dialog.show_error(error, self._conflicting_endpoint(error))
            return
        if self._commit(raw, t("{identifier} updated", identifier=value["id"])):
            dialog.accept()
            self._show_missing_connection_warning(value)

    def _validation_error(self, raw) -> str | None:
        try:
            VirtualLabProject.from_raw(raw).resolve_compatible(self._board, self._constraints())
        except Exception as exc:
            return str(exc)
        return None

    @staticmethod
    def _conflicting_endpoint(error: str) -> str | None:
        marker = t("Input conflict: more than one peripheral drives {endpoint}.", endpoint="{endpoint}")
        pattern = re.escape(marker).replace(re.escape("{endpoint}"), r"(?P<endpoint>.+)")
        match = re.fullmatch(pattern, error)
        return match.group("endpoint") if match else None

    def _delete(self, peripheral):
        self._delete_many([peripheral])

    def _delete_many(self, selected) -> None:
        annotation_ids = {item["id"] for item in selected if isinstance(item, dict)}
        peripheral_ids = {item.peripheral_id for item in selected if not isinstance(item, dict)}
        count = len(annotation_ids) + len(peripheral_ids)
        if not count:
            return
        if count == 1:
            identifier = next(iter(annotation_ids or peripheral_ids))
            title = t("Delete annotation") if annotation_ids else t("Delete peripheral")
            prompt = t("Delete {identifier}?", identifier=identifier)
            message = (
                t("Annotation {identifier} deleted", identifier=identifier)
                if annotation_ids else t("{identifier} deleted", identifier=identifier)
            )
        elif annotation_ids and peripheral_ids:
            title = t("Delete selected items")
            prompt = t("Delete {count} selected items (peripherals and annotations)?", count=count)
            message = t("{count} items deleted", count=count)
        elif annotation_ids:
            title = t("Delete annotations")
            prompt = t("Delete {count} selected annotations?", count=count)
            message = t("{count} annotations deleted", count=count)
        else:
            title = t("Delete peripherals")
            prompt = t("Delete {count} selected peripherals?", count=count)
            message = t("{count} peripherals deleted", count=count)
        answer = QMessageBox.question(self, title, prompt)
        if answer != QMessageBox.StandardButton.Yes: return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        raw["peripherals"] = [item for item in raw.get("peripherals", []) if item["id"] not in peripheral_ids]
        raw["annotations"] = [item for item in raw.get("annotations", []) if item.get("id") not in annotation_ids]
        self._commit(raw, message)

    def _duplicate(self, peripheral) -> None:
        """Duplicate a selected visual part without copying electrical connections."""
        self._duplicate_many([peripheral])

    def _duplicate_many(self, peripherals) -> None:
        """Duplicate one selection in a single undoable Lab mutation."""
        if not self._editing_enabled:
            return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        existing = {item["id"] for item in raw.get("peripherals", [])}
        duplicate_ids: list[str] = []
        for peripheral in peripherals:
            if isinstance(peripheral, dict):
                annotation = copy.deepcopy(peripheral)
                base = annotation["id"]
                index = 1
                annotation_ids = {item["id"] for item in raw.get("annotations", [])}
                while f"{base}_{index}" in annotation_ids:
                    index += 1
                annotation["id"] = f"{base}_{index}"
                annotation["position"] = [float(annotation["position"][0]) + 24, float(annotation["position"][1]) + 24]
                raw.setdefault("annotations", []).append(annotation)
                duplicate_ids.append(annotation["id"])
                continue
            index = 1
            while f"{peripheral.kind}_{index}" in existing:
                index += 1
            identifier = f"{peripheral.kind}_{index}"
            existing.add(identifier)
            properties = dict(peripheral.properties)
            position = properties.get("position", [16, 16])
            properties["position"] = [round(float(position[0]) + 24, 1), round(float(position[1]) + 24, 1)]
            raw.setdefault("peripherals", []).append({
                "id": identifier,
                "type": peripheral.kind,
                "connections": {},
                "properties": properties,
            })
            duplicate_ids.append(identifier)
        message = (
            t("{identifier} duplicated", identifier=duplicate_ids[0])
            if len(duplicate_ids) == 1
            else t("{count} peripherals duplicated", count=len(duplicate_ids))
        )
        if duplicate_ids and self._commit(raw, message):
            for item in self._workbench_scene.items():
                if isinstance(item, WorkbenchPeripheralItem) and item.peripheral.peripheral_id in duplicate_ids:
                    item.setSelected(True)
                if isinstance(item, WorkbenchAnnotationItem) and item.data["id"] in duplicate_ids:
                    item.setSelected(True)

    def _add_annotation(self, kind: str) -> None:
        if not self._editing_enabled:
            return
        value = ""
        if kind == "text":
            value, accepted = QInputDialog.getMultiLineText(self, t("Add text"), t("Markdown text"))
            if not accepted or not value.strip():
                return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        existing = {item.get("id") for item in raw.get("annotations", [])}
        index = 1
        while f"{kind}_{index}" in existing:
            index += 1
        center = self.workbench.camera_center()
        raw.setdefault("annotations", []).append({"id": f"{kind}_{index}", "type": kind, "text": value, "position": [round(center.x(), 1), round(center.y(), 1)], "width": 180 if kind == "text" else 120, "height": 68 if kind == "text" else (12 if kind == "line" else 80), **({"orientation": "horizontal"} if kind == "line" else {})})
        self._commit(raw, t("Annotation added"))

    def _edit_annotation(self, annotation: dict) -> None:
        if annotation.get("type") != "text":
            return
        value, accepted = QInputDialog.getMultiLineText(self, t("Edit text"), t("Markdown text"), annotation.get("text", ""))
        if not accepted:
            return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        for item in raw.get("annotations", []):
            if item.get("id") == annotation["id"]:
                item["text"] = value
                break
        self._commit(raw, t("Annotation updated"))

    def update_outputs(self, outputs: dict[str, int]) -> None:
        """Paint output peripherals from their actual HDL net resolved by the PCF."""
        for (peripheral_id, terminal), (item, net) in self._workbench_bindings.items():
            if (peripheral_id, terminal) in self._temporal_terminals:
                continue
            match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_$]*)(?:\[(\d+)])?", net or "")
            if match is None:
                item.set_terminal(terminal, False)
                continue
            port, raw_bit = match.groups()
            bit = int(raw_bit) if raw_bit else 0
            item.set_terminal(terminal, bool(outputs.get(port, 0) & (1 << bit)))

    def update_frame(self, frame) -> None:
        self.update_outputs(frame.outputs)
        temporal = getattr(frame, "temporal", None)
        if temporal is not None:
            self._update_temporal_outputs(temporal)
        edge_frame = getattr(frame, "edge_stream", None)
        if edge_frame is not None:
            for channel, (item, terminal, _, _) in enumerate(self._edge_bindings):
                item.feed_edge_events(
                    terminal,
                    tuple(event for event in edge_frame.events if event.channel == channel),
                    edge_frame.cycle,
                    edge_frame.clock_hz,
                    edge_frame.dropped,
                )
        for item in self._workbench_scene.items():
            if not isinstance(item, WorkbenchPeripheralItem):
                continue
            snapshot = frame.sinks.get(item.peripheral.peripheral_id) if getattr(frame, "sinks", None) else None
            if snapshot is not None or isinstance(getattr(item, "_renderer", None), VgaMonitorRenderer):
                item.set_snapshot(snapshot)

    def _update_temporal_outputs(self, temporal) -> None:
        """Apply native duty-cycle summaries using the same visual persistence as board LEDs."""
        if temporal.samples <= 0:
            for item, terminal in self._temporal_bindings:
                item.set_terminal_brightness(terminal, 0.0)
                item.set_temporal_observation(terminal, 0.0, 0.0)
            self._temporal_models = [LedModel(_EXTERNAL_LIGHT_PERSISTENCE_SECONDS) for _ in self._temporal_bindings]
            return
        for index, (item, terminal) in enumerate(self._temporal_bindings):
            model = self._temporal_models[index]
            edge_rate = temporal.edges[index] / temporal.elapsed_seconds if temporal.elapsed_seconds > 0 else 0.0
            pulse_width = temporal.pulse_high_seconds[index] if index < len(temporal.pulse_high_seconds) else None
            item.set_temporal_observation(terminal, temporal.hits[index] / temporal.samples, edge_rate, pulse_width)
            final_level = bool(temporal.ends[index])
            high_samples = temporal.hits[index]
            if edge_rate < _VISUAL_FUSION_EDGE_RATE_HZ:
                high_samples = temporal.samples if final_level else 0
            window = SignalWindow(final_level, final_level, high_samples, temporal.samples, temporal.edges[index])
            item.set_terminal_brightness(terminal, model.advance({"anode": window}, temporal.elapsed_seconds))

    def drop_vga_images(self) -> None:
        for item in self._workbench_scene.items():
            if isinstance(item, WorkbenchPeripheralItem):
                item.drop_vga_images()

    def current_wires(self):
        return getattr(self, "_resolved_wires", ())

    def missing_required_connections(self) -> tuple[str, ...]:
        """Return required terminals intentionally left electrically open."""
        missing: list[str] = []
        for peripheral in VirtualLabProject.load(self._lab).peripherals:
            try:
                required = spec_for(peripheral.kind).required_terminals(peripheral.properties)
            except ValueError:
                continue
            missing.extend(
                f"{peripheral.peripheral_id}.{terminal}"
                for terminal in required
                if not peripheral.connections.get(terminal)
            )
        return tuple(missing)

    def _show_missing_connection_warning(self, value: dict[str, object]) -> None:
        spec = spec_for(str(value["type"]))
        properties = dict(value.get("properties", {}))
        connections = dict(value.get("connections", {}))
        missing = [terminal for terminal in spec.required_terminals(properties) if not connections.get(terminal)]
        if missing:
            self._show_status(t(
                "{identifier} saved with required terminals not connected: {terminals}.",
                identifier=value["id"],
                terminals=", ".join(missing),
            ))

    def _add_kind(self, kind: str) -> None:
        if not self._editing_enabled or kind not in load_catalog():
            return
        self._catalog_panel.close_drawer()
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        existing = {item["id"] for item in raw.get("peripherals", [])}
        index = 1
        while f"{kind}_{index}" in existing: index += 1
        draft = PeripheralInstance(f"{kind}_{index}", kind, {}, {})
        dialog = PeripheralConfigDialog(draft, self._board, self._assigned_endpoints, self)
        dialog.save_requested.connect(lambda: self._save_new_peripheral(dialog, kind, existing))
        dialog.exec()

    def _save_new_peripheral(self, dialog: PeripheralConfigDialog, kind: str, existing: set[str]) -> None:
        value = dialog.value()
        if not value["id"]:
            dialog.show_error(t("Complete the identifier."))
            return
        if value["id"] in existing:
            dialog.show_error(t("A peripheral with that identifier already exists."))
            return
        camera = self.workbench.camera_center()
        preview = WorkbenchPeripheralItem(
            PeripheralInstance(value["id"], kind, value["connections"], value["properties"]),
            self._configure, self._save_position, self._drive_input,
        )
        item_center = preview.boundingRect().center()
        value["properties"]["position"] = [
            round(camera.x() - item_center.x(), 1),
            round(camera.y() - item_center.y(), 1),
        ]
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        workbench_state = raw.get("workbench")
        if not isinstance(workbench_state, dict):
            workbench_state = raw["workbench"] = {}
        workbench_state["center"] = [round(camera.x(), 2), round(camera.y(), 2)]
        raw.setdefault("peripherals", []).append(value)
        error = self._validation_error(raw)
        if error:
            dialog.show_error(error, self._conflicting_endpoint(error))
            return
        if self._commit(raw, t("{identifier} added", identifier=value["id"])):
            dialog.accept()
            self._show_missing_connection_warning(value)
