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

## Install an external peripheral

FPGALab discovers no-code peripheral folders at startup from:

- Linux: `~/.local/share/FPGALab/peripherals/`
- Windows: `%APPDATA%\FPGALab\peripherals\`
- macOS: `~/Library/Application Support/FPGALab/peripherals/`

Copy a complete peripheral directory into that location and restart FPGALab. For example, copy `examples/peripherals/led_bar` so the resulting path ends in `peripherals/led_bar/manifest.json`. The 8-LED bar then appears in the catalog without modifying or rebuilding FPGALab.

External peripherals are currently declarative: they may use supported manifest properties, simulation classes, and generic renderers, but FPGALab does not execute Python code from these folders. Set `FPGALAB_PERIPHERALS_DIR` to use a different catalog folder while developing or testing a peripheral.

## Add a bundled peripheral

Create `fpga_lab/peripherals/<id>/manifest.json` and its licensed SVG resources. Define terminal direction, required connections, properties, visual renderer, size, and simulation mode. Reuse a generic renderer when possible; add a renderer class only when the behavior cannot be described by existing primitives.

The generic `led_array` renderer accepts `visual.terminals`, `visual.orientation`, and `visual.color_property`. See `examples/peripherals/led_bar` for a complete API version 1 manifest.

Run the tests before opening a pull request:

```bash
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen pytest -q
```

Keep source code, identifiers, and developer comments in English. User-visible text must pass through the translation layer.
