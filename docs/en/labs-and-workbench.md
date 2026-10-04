# Labs and workbench

A **Lab** is a reusable peripheral arrangement independent from an Icestudio project. It stores its board, components, pin assignments, properties, positions, zoom, and camera state. The virtual clock normally uses the selected board's `clock_hz`. In Simulation settings, enable **Use a custom clock for this Lab** to override it for one Lab; restoring defaults returns to the board clock. Interface refresh and temporal sampling remain user-wide settings. The effective temporal sampling rate is shown in the dialog and cannot exceed the virtual clock.

On first launch after this change, a previously saved global virtual clock is assigned to the active Lab. Other Labs continue to use their own board clock unless configured separately. The `--clock-hz` command-line option overrides the clock for the current launch without changing a Lab.

## Manage Labs

Open the Lab manager from the selector in the top bar. You can create, duplicate, rename, delete, import, and export Labs. Exported `.lab` files are portable JSON documents and can be shared with the corresponding `.ice` design.

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
- Use `Ctrl+Z` and `Ctrl+Y` to undo and redo.
- Use the mouse wheel to zoom.
- Use `Ctrl`+drag or middle-button drag to pan.
- Use the toolbar for 100% zoom and fit-to-content.

Peripheral terminals may remain unconnected while arranging a Lab. Required missing connections are reported when the simulation starts.
