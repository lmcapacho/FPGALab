# Architecture and contribution

## Simulation path

```text
Icestudio .ice project
  -> generated main.v and PCF
  -> Verilog interface and board profile
  -> cached Verilator native model
  -> ctypes simulation binding
  -> SimulationWorker
  -> board view and peripheral workbench
```

The native wrapper batches virtual FPGA cycles and publishes `SimulationFrame` objects. GPIO inputs, sampled outputs, temporal observations, and streaming sinks such as VGA remain separate data paths.

## Main modules

- `app.py`: application orchestration and build lifecycle.
- `compiler.py` and `build_cache.py`: Verilator generation and incremental native builds.
- `simulation.py` and `simulation_worker.py`: native binding and background execution.
- `virtual_lab.py`: board/workbench composition.
- `peripherals/catalog.py` and `peripherals/manifest.py`: declarative catalog.
- `workbench/view.py` and `workbench/item.py`: canvas interaction and rendered instances.
- `wiring.py`: Lab terminal-to-board-to-HDL resolution.

Board assets live together in `fpga_lab/assets/boards/<board-id>/`. Each board
directory keeps its definition, pin constraints, profile, layout, and SVG in
one place. The Alhambra II directory is the reference layout for future boards.
FPGALab consumes the project-specific PCF generated in the Icestudio project's
`ice-build` directory; the packaged `pinout.pcf` is the board pinout reference.
`BoardCatalog` discovers these directories and validates their required files,
definition, layout, profile, and PCF. Invalid packages are skipped with a
diagnostic. Its `board_id` is the directory name (for example, `alhambra_ii`);
the `id` in `board.json` remains the board's public identifier.
In `layout.json`, a board LED may declare `"role": "power"` and a board button
may declare `"role": "reset"`. These optional roles control the simulation
indicator and reset action without depending on the elements' signal names.
Select the element in Edit layout to assign its role; each role can belong to
only one element.
The `controls.leds` order in `board.json` determines the order of LED samples
published by the worker. Each endpoint name selects the corresponding visual
LED in `layout.json`; a board may declare any number of LEDs, including none.

## External peripherals

The [external peripheral API v1](peripheral-api.md) documents the manifest fields, reusable renderers, package metadata, examples, validation, and installation. Use it when creating a shareable package. FPGALab does not load Python code from user peripheral folders.

## Add a bundled peripheral

Create `fpga_lab/peripherals/<id>/manifest.json` and its licensed SVG resources. Define terminal direction, required connections, properties, visual renderer, size, and simulation mode. Reuse a generic renderer when possible; add a renderer class only when the behavior cannot be described by existing primitives.

See the [API reference](peripheral-api.md#visual-reusable-renderers) for the available renderers and their manifest fields.

Run the tests before opening a pull request:

```bash
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen pytest -q
```

Keep source code, identifiers, and developer comments in English. User-visible text must pass through the translation layer.
