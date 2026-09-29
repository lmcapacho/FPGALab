# Working on FPGALab

FPGALab is a PyQt6 desktop application that compiles Icestudio-generated Verilog with Verilator and runs the model through a native C ABI. The GUI, virtual clock, board mapping, and peripheral catalog are separate layers. Keep that separation when changing behavior.

## Where to work

- `fpga_lab/app.py`, `compiler.py`, and `build_cache.py`: project discovery, toolchain use, and incremental builds.
- `fpga_lab/cpp_wrapper.py`, `fpga_lab/native/`, and `simulation.py`: generated native ABI and Python binding. Changes here require native-path tests.
- `fpga_lab/simulation_worker.py` and `virtual_lab.py`: virtual-time execution, Qt thread boundary, and board/workbench coordination. Do not put per-cycle Python work or blocking compilation on the GUI thread.
- `fpga_lab/peripherals/`: manifests, catalog, installation, validation, and stock renderers. `fpga_lab/workbench/` owns canvas interaction and peripheral graphics items.
- `fpga_lab/assets/`: board definitions and artwork. `examples/peripherals/`: installable example packages.
- `docs/en/` and `docs/es/`: user and contributor documentation. `tests/`: behavioral and regression tests.

Read the relevant [architecture guide](docs/en/development.md) and [peripheral API reference](docs/en/peripheral-api.md) before changing those contracts.

## Important contracts

- Virtual FPGA cycles and wall-clock GUI refresh are different clocks. Preserve cycle timestamps and ordering across worker frames, Stop/Run, and Reset. Handle bounded queues and report lost data rather than decoding incomplete serial frames as valid data.
- Qt widgets stay on the GUI thread; the simulation model belongs to `SimulationWorker`. Communicate across that boundary with signals and slots.
- Resolve peripheral terminals through the board definition and project PCF; do not assume a particular HDL net name or hardcode a new peripheral into the simulation loop when a manifest or reusable renderer suffices.
- User-installed peripherals are declarative manifests and packaged resources, not executable Python. Validate versions, terminal directions, resource paths, and replacements before installation.
- Keep existing Labs usable when a newer peripheral or property is unavailable. Do not silently discard unknown instances, connections, or user settings.
- Keep user-visible strings translatable through `fpga_lab/i18n.py` and `fpga_lab/locales/es.json`. Check both light and dark themes for UI changes.
- Keep generated Verilator models and caches out of the repository and Icestudio's `ice-build`; use the existing managed cache behavior.

## Verification

- Run focused tests for changed behavior, then the full suite for changes spanning native code, workers, manifests, or UI routing: `QT_QPA_PLATFORM=offscreen python -m pytest -q`.
- For a new or changed external package, run `python -m fpga_lab.peripherals.validate examples/peripherals/<id>`.
- Use synthetic fixtures and `tmp_path` in tests. Never depend on a developer's local `.ice`, Lab, toolchain installation, or cached model. Native harness tests may skip when a C++ compiler is unavailable.
- Prefer a few tests for contracts and regressions over one test per cosmetic adjustment. Verify a GUI fix visually when automated assertions cannot establish its appearance.
- Update both language versions of the documentation when changing a public workflow or peripheral API, and note user-visible changes under `Unreleased` in `CHANGELOG.md`.

## Change hygiene

Inspect `git status` before editing. Preserve unrelated work and stage only files belonging to the task. Do not create commits, tags, releases, or pushes unless the user asks for them. Keep source identifiers and developer comments in English.
