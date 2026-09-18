# Changelog

All notable changes to FPGALab are documented in this file.

## Unreleased

### Added

- Light and dark interface themes with an accessible sun/moon selector and per-user persistence.

## 0.1.0rc3 — 2026-09-16

### Added

- Bilingual English and Spanish documentation site with GitHub Pages deployment.
- Searchable peripheral catalog with compact visual previews.
- BCD display, four-position DIP switch, and single toggle-switch peripherals.
- Portable Lab import and export using the `.lab` extension, while retaining compatibility with existing `.lab.json` files.
- Multi-selection, group movement and deletion, duplication, undo and redo in the virtual workbench.
- Infinite-style workbench canvas with cursor-centered zoom, panning, 100% zoom, and fit-to-content controls.
- Adjustable board/workbench divider with its proportion remembered per user.
- Simulation settings for virtual FPGA frequency, interface refresh rate, temporal sampling rate, and Verilator optimization mode.
- Configurable Verilator compatibility mode for designs that cannot use the recommended optimization path.
- Self-managed incremental compilation cache with automatic size and age limits.
- Toolchain diagnostics that report the resolved Verilator, Make, compiler, Python, and shell paths.
- Project attribution, citation metadata, AI-assisted development disclosure, and an About dialog.

### Changed

- Split the workbench canvas and peripheral graphics item out of the main peripheral panel module.
- Refined the BCD display with compact visuals and an optional active-high `enable` input for display selection.
- Refreshed the visual design system, controls, icons, dialogs, workbench hierarchy, and peripheral renderers.
- Made peripheral terminals optionally unconnected so partially wired components can be placed and configured incrementally.
- Optimized declarative temporal observation to reduce simulation overhead for LEDs and displays.
- Preserved workbench edit history when starting and stopping a simulation.
- Locked project, Lab, peripheral, and simulation settings controls while a simulation is running.
- Adopted a risk-based testing policy focused on behavior and regressions instead of one test per UI change.

### Fixed

- Fully stop combinational output updates after the simulation is stopped.
- Terminate active simulation and build processes when FPGALab closes.
- Hide Make and compiler console windows during builds on Windows.
- Keep momentary buttons active for the complete duration of keyboard shortcut presses.
- Preserve peripheral configuration when validation detects a conflicting input pin.

## 0.1.0rc2 — 2026-09-04

### Added

- Manifest-driven peripheral catalog and renderer registry, allowing new workbench parts to be added without central `if kind ==` branches.
- Cycle-accurate VGA capture through the native streaming-sink interface, with 1-bit, 6-bit, and 12-bit 640×480 monitors.
- macOS application packaging for Intel and Apple Silicon in the release workflow.
- Declarative temporal sampling for LEDs, traffic lights, and seven-segment displays.
- Interactive workbench buttons with keyboard shortcuts and press-and-release behavior.
- Lab management with search, create, duplicate, rename, delete, and last-selected Lab restoration.
- Per-Lab workbench zoom persistence.
- CI validation on Python 3.13 and 3.14 in addition to the previously supported versions.
- Automated tests for the peripheral catalog, wiring, native simulation binding, and VGA decoder.

### Changed

- Reworked the simulation ABI around `SimulationFrame`, batched GPIO state, temporal observations, and VGA snapshots.
- Restored and adapted the original LED, traffic-light, seven-segment, button, and sensor peripherals to the declarative catalog architecture.
- Kept existing Alhambra II Lab files compatible with the new catalog format.
- Sanitized release artifact names so pull-request builds work consistently across Linux, Windows, and macOS.

### Fixed

- Refresh combinational outputs while a simulation is running, including designs without a clock input.
- Preserve entered peripheral settings when a pin conflict or another validation error prevents saving.
- Correct native shared-library linker handling across Linux, Windows, and macOS.

## 0.1.0rc1 — 2026-08-23

### Added

- Icestudio project discovery, PCF-aware board mapping, and cached Verilator builds.
- Interactive Alhambra II board view with integrated LEDs, switches, reset, and editable layout assets.
- Reusable virtual laboratories with configurable external LEDs, buttons, sensors, traffic lights, and seven-segment displays.
- Virtual clock execution with independent human-visible signal sampling.
- English and Spanish interface support.
- GitHub Releases update checks and Linux/Windows release packaging workflows, including a self-contained Windows executable.

### Known limitations

- The first release candidate targets the Alhambra II board.
- Release packages are portable archives; installer-based updates are not yet provided.
