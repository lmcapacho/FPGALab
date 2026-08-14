# FPGALab

Laboratorio virtual interactivo para diseños Verilog y perfiles de placas FPGA.
El diseño se compila con Verilator a una biblioteca compartida y la GUI PyQt6
interactúa con ella por medio de una ABI C y `ctypes`; no se generan ni se
consumen archivos VCD durante la simulación interactiva.

## Arquitectura

```text
main.v + board_profile.json
        │
        ▼
VerilatorCompiler ──► sim_main.cpp (ABI C + run_cycles) ──► libVtop_shared.{so,dylib,dll}
                                                     │ ctypes
                                                     ▼
                                            VerilatorSimulation
                                                     │ QThread + QTimer
                                                     ▼
                                            FPGAVirtualLab
```

El perfil de placa describe los puertos reales del módulo superior. La plantilla
C++ se genera desde él, por lo que los nombres de señales se validan en la
compilación de C++ y no quedan escondidos en el código Python.

## Requisitos

* Python 3.10+ y PyQt6.
* Verilator 5.x, GNU Make y un compilador C++17 (GCC/Clang o MSVC+make
  compatible). En Windows es recomendable usar MSYS2/MinGW64 para la primera
  iteración.

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\\Scripts\\activate
pip install -e .
verilator --version
```

## Inicio rápido

El ejemplo incluido usa los puertos declarados en `examples/main.v`.

```bash
python -m fpga_lab.compiler examples/main.v \
  --profile examples/board_profile.json --top top
python -m fpga_lab.app --library build/verilator/obj_dir/libVtop_shared.so \
  --profile examples/board_profile.json --clock-hz 12000000 --ui-refresh-hz 60
```

En Windows, cambie la última extensión por `.dll`; en macOS por `.dylib`.
La misma lista de argumentos puede entregarse a `QProcess` desde una UI sin usar una shell.

## Reloj virtual y refresco visual

El modelo avanza según el tiempo real y `--clock-hz` (12 MHz por defecto).
Cada frame llama una sola vez a `run_cycles()` dentro de C++, evitando miles
de cruces `ctypes`. La interfaz recibe el estado a `--ui-refresh-hz` (60 Hz
por defecto), suficiente para el ojo humano sin alterar la relación temporal
de contadores, divisores y prescaladores.

Si un diseño no alcanza 12 MHz en el anfitrión, mantener tiempo real requiere
el núcleo disponible; se puede bajar `--clock-hz` para un modo didáctico.

## Contrato HDL

Los nombres y anchos se declaran en `board_profile.json`. El perfil de ejemplo
expone `clk`, `SW1`, `SW2`, `LED0`…`LED7`, un bus de entrada/salida GPIO de 8
bits y 14 bits para dos displays de siete segmentos. Puede adaptarlo a la
exportación de Icestudio sin editar Python:

```json
{
  "inputs": {"clk": 1, "SW1": 1, "SW2": 1, "gpio_in": 8},
  "outputs": {"LED0": 1, "LED1": 1, "segments": 14, "gpio_out": 8}
}
```

`clk` debe ser una entrada escalar. Los puertos son nombres Verilog válidos y
deben existir como puertos públicos de `--top-module`.

## Git

```bash
git init
git add .
git commit -m "feat: base del laboratorio virtual FPGA"
```

Los directorios de construcción y las bibliotecas producidas se ignoran. No
versione artefactos generados: versiona HDL, perfiles y código fuente.
