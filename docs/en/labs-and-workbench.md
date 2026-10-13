# Labs and workbench

A **Lab** is a reusable peripheral arrangement independent from an Icestudio project. It stores its board, components, pin assignments, properties, positions, zoom, and camera state. The virtual clock normally uses the selected board's `clock_hz`. In Simulation settings, enable **Use a custom clock for this Lab** to override it for one Lab; restoring defaults returns to the board clock. Interface refresh and temporal sampling remain user-wide settings. The effective temporal sampling rate is shown in the dialog and cannot exceed the virtual clock.

On first launch after this change, a previously saved global virtual clock is assigned to the active Lab. Other Labs continue to use their own board clock unless configured separately. The `--clock-hz` command-line option overrides the clock for the current launch without changing a Lab.

## Dot grid

The workbench toolbar's dot-grid button shows or hides a visual grid. Visibility
is remembered per user across Labs, not stored in the Lab. The grid shows fewer
dots at distant zoom levels. The separate magnet button enables movement
snapping; the adjacent field sets spacing from 4 to 200 scene units. These
editing options are saved per Lab and work even when the grid is hidden.
Enabling snapping does not move existing items. When dragging peripherals or
annotations, the grabbed element is aligned to the grid and the group keeps
its relative positions. A completed drag remains one undoable operation;
annotation resizing is not snapped. At distant zoom levels, snapping still
uses the configured spacing, even if only some grid points are displayed.

## Connections

The Connections window identifies the active board and shows board endpoints,
physical FPGA pins, direction, constrained HDL nets and connected peripheral
terminals together in one table.

## Manage Labs

Open the Lab manager from the selector in the top bar. You can create, duplicate, rename, delete, import, and export Labs. Exported `.lab` files are portable JSON documents and can be shared with the corresponding `.ice` design.

Existing `.lab.json` files remain supported. Import validates and copies a Lab
into the local workspace without overwriting another Lab. The most recently
selected Lab is remembered in the user's FPGALab settings and restored at
startup. Lab files do not contain machine-specific project paths.

Default locations:

- Linux and macOS: `~/FPGALab/labs`
- Windows: `Documents/FPGALab/labs`

Set `FPGALAB_WORKSPACE` to choose another workspace root.

## Workbench controls

- Open the floating catalog button to add a peripheral.
- Drag a component to move it.
- Drag empty space to select several components.
- Use `Shift`+click to change the selection.
- Use `Ctrl+D` to duplicate and `Delete` to remove the selection.
- Use `Ctrl+C` / `Ctrl+V`, or the workbench context menu, to copy and paste peripherals and annotations, including between Labs. Pasting keeps properties and relative positions, places the group in the current view, and leaves electrical connections unassigned to avoid conflicts. Each paste is one undoable operation.
- Use `Ctrl+Z` and `Ctrl+Y` to undo and redo.
- Use the mouse wheel to zoom.
- Use `Ctrl`+drag or middle-button drag to pan.
- Use the toolbar for 100% zoom and fit-to-content.

Peripheral terminals may remain unconnected while arranging a Lab. Required missing connections are reported when the simulation starts.

## Annotation editor

Right-click the workbench and choose **Add annotation** to insert Markdown
text, a line, rectangle or ellipse at the clicked position. Shapes appear
directly, selected for moving or resizing; text opens a multiline editor first.
Drag the selected shape's resize handle or a line endpoint to adjust geometry;
hold Shift on a line for horizontal/vertical orientation, or on an ellipse for
a circle. Double-click text to edit Markdown. There are no numeric size fields.
The empty workbench shows a right-click hint; the toolbar has no annotation
button. Cancel leaves the Lab unchanged; creation and editing support undo/redo.
Older annotations and their additional saved properties remain preserved.

## Peripheral catalog

Open the floating catalog to search by category or name and add a peripheral.
The built-in catalog includes buttons, switches, LEDs, sensors, traffic lights,
seven-segment and BCD displays, and VGA monitors. You can also install a
declarative package from a folder or ZIP file using the catalog's install
action; installed packages can be removed from the catalog. An unavailable
package does not erase its saved Lab instances. For the package format and
validation rules, see the [external peripheral API](peripheral-api.md).

## Virtual time and visual updates

The native model batches FPGA cycles while the interface refreshes at a lower,
human-friendly rate. Simulation settings control the per-Lab virtual clock,
the user-wide interface refresh rate (60 Hz by default), and the temporal
sampling rate (1 MHz by default) used for effects such as PWM brightness and
multiplexed displays. A display common can be tied to `GND` or `VCC`, or driven
from an FPGA pin for multiplexing. Lower sampling rates
reduce measurement cost; use a rate at least as fast as the behavior you need
to observe. The host may not sustain a high requested clock, especially with
complex designs or Labs; the status bar shows the achieved rate.

VGA 640×480 designs typically need a virtual clock near 25 MHz. FPGALab warns
when a VGA monitor is used with the 12 MHz Alhambra II default; it does not
change the clock automatically. The catalog includes 1-bit, 6-bit, and 12-bit
VGA monitors.
