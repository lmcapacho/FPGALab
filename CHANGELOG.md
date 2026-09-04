# Changelog

All notable changes to FPGALab are documented in this file.

## Unreleased

### Added

- Manifest-driven peripheral catalog (`fpga_lab/peripherals/*/manifest.json`) so new workbench parts do not need `if kind ==` branches.
- VGA monitor workbench peripherals: cycle-accurate 640×480 capture in C++ (`vga_decoder` + streaming sink), painted with PyQt6. Separate catalog parts for 1-bit, 6-bit (2 bits/colour), and 12-bit (4 bits/colour). No SDL2 and no extra Verilog top around Icestudio `main.v`.
- pytest suite for the catalog, wiring, and VGA decoder harness.

## 0.1.0rc1 — Release Candidate

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
