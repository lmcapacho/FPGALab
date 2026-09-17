# Labs and workbench

A **Lab** is a reusable peripheral arrangement independent from an Icestudio project. It stores components, pin assignments, properties, positions, zoom, and camera state.

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
