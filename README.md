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

Para un diseño Icestudio, FPGALab inspecciona `main.v` y detecta el módulo
superior y sus puertos antes de generar la plantilla C++. Un perfil manual sigue
disponible para flujos avanzados, por lo que los nombres de señales se validan
en la compilación de C++ y no quedan escondidos en el código Python.

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
  --profile examples/board_profile.json --clock-hz 12000000 --ui-refresh-hz 60 --observation-hz 1000000
```

En Windows, cambie la última extensión por `.dll`; en macOS por `.dylib`.
La misma lista de argumentos puede entregarse a `QProcess` desde una UI sin usar una shell.

### Ejecutar un diseño de Icestudio

La ruta habitual no requiere buscar `main.v` ni pulsar un botón de compilación:

```bash
python -m fpga_lab.app --ice /ruta/al/diseño.ice \
  --profile examples/board_profile.json
```

Al abrir FPGALab, la barra superior integrada permite elegir la ruta `.ice`,
buscar un archivo, reutilizar proyectos recientes y pulsar **Ejecutar**. Para cada
diseño localiza
`ice-build/<nombre-del-diseño>/main.v` (o `ice-build/main.v`), compila solo si el
contenido de `main.v`, el PCF o el perfil cambió, y guarda el resultado en la
caché de usuario (`$XDG_CACHE_HOME/fpgalab/verilator`). Por tanto `ice-build` no
se llena con archivos de Verilator.

Los montajes visuales se conservan en un workspace global reutilizable, no dentro
de `ice-build` ni junto al diseño Icestudio. La barra de FPGALab permite seleccionar
o crear un laboratorio. La ruta predeterminada es `~/FPGALab/labs` en Linux y
`Documentos/FPGALab/labs` en Windows; puede cambiarse mediante la variable de
entorno `FPGALAB_WORKSPACE`. FPGALab no crea ni modifica carpetas auxiliares
junto a los proyectos de Icestudio.

El PCF del diseño se entrega al laboratorio para relacionar la red HDL con el pin
físico de la Alhambra II; los nombres HDL siguen siendo los declarados por el
perfil hasta completar la detección automática de la interfaz Verilog.

## Reloj virtual y refresco visual

El modelo avanza según el tiempo real y `--clock-hz` (12 MHz por defecto).
Cada frame llama una sola vez a `run_cycles()` dentro de C++, evitando miles
de cruces `ctypes`. La interfaz se pinta a `--ui-refresh-hz` (60 Hz por defecto). La sonda temporal
trabaja por separado a `--observation-hz` (1 MHz por defecto): entrega ciclo de
trabajo, transiciones y estado final, de modo que PWM y señales rápidas se
presentan como brillo sin depender de la fase del temporizador de Qt. Cada
periférico podrá declarar sus señales y resolución de observación.

Si un diseño no alcanza 12 MHz en el anfitrión, mantener tiempo real requiere
el núcleo disponible; se puede bajar `--clock-hz` para un modo didáctico.

## Contrato HDL

Los nombres y anchos pueden declararse en `board_profile.json`. El perfil de ejemplo
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


## Layout visual de placa

La apariencia y los controles integrados viven fuera de Python:

- `fpga_lab/assets/boards/alhambra_ii.svg`: arte vectorial escalable.
- `fpga_lab/assets/board_layouts/alhambra_ii.json`: posición, tamaño, señal y tipo de cada elemento.

Un componente `led` se enlaza a una salida HDL y un `button` a una entrada. Por
ello se pueden ajustar posiciones, añadir controles o crear un perfil para otra
placa sin tocar el motor Verilator. Los periféricos externos se añadirán como
layouts separados conectados por el esquema de cableado virtual.
