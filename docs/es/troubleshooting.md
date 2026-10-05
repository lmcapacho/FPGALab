# Toolchain y solución de problemas

FPGALab necesita Verilator 5 o posterior, herramientas compatibles con GNU Make y un compilador C++17. Python 3.10 o posterior y PyQt6 también son necesarios al ejecutar desde el código fuente; los paquetes de aplicación incluyen su propio entorno Python. Usa el icono de terminal con verificación en la barra de estado para consultar las rutas exactas encontradas.

## Orden de búsqueda

FPGALab busca:

1. OSS CAD Suite instalado por Apio o Icestudio.
2. Una instalación configurada mediante `FPGALAB_OSS_CAD_SUITE`.
3. Verilator disponible en el `PATH` del sistema.

Usa `FPGALAB_VERILATOR` para seleccionar un ejecutable y `MSYS2_ROOT` si MSYS2 está instalado en otra ubicación.

También se reconoce el nombre anterior `tools-oss-cad-suite`. Entre las rutas
habituales de OSS CAD Suite están `~/.apio/packages/oss-cad-suite` en Linux y
macOS y `%USERPROFILE%\.icestudio\apio\packages\oss-cad-suite` en Windows.
Algunas instalaciones de Icestudio usan `AppData` u otra ubicación: define
`FPGALAB_OSS_CAD_SUITE` con la carpeta que contiene `bin` y `share`. Una ruta
explícita en `FPGALAB_VERILATOR` tiene prioridad.

Por ejemplo, para una instalación independiente en Linux o macOS, define
`FPGALAB_OSS_CAD_SUITE=/ruta/a/oss-cad-suite` antes de ejecutar `fpga-lab`.
OSS CAD Suite proporciona Verilator, pero no sustituye Make ni un compilador
C++17. En Windows, FPGALab detecta la instalación habitual `C:\msys64`; usa
`MSYS2_ROOT` si MSYS2 está en otra carpeta.

## Linux

Instala Verilator, Make y un compilador C++ mediante el administrador de paquetes de la distribución, o utiliza OSS CAD Suite instalado por Apio. En sistemas basados en Debian o Ubuntu, una instalación típica es:

```bash
sudo apt install verilator make g++
```

## Windows

Icestudio puede proporcionar Verilator sin incluir todo el entorno de compilación nativa. Instala MSYS2 y ejecuta en su terminal UCRT64:

```bash
pacman -S --needed make python mingw-w64-ucrt-x86_64-gcc
```

No ejecutes la aplicación directamente desde un ZIP: extrae todo el paquete para conservar `_internal` junto al ejecutable.

El archivo independiente `windows-x64.exe` es la descarga más sencilla. El
paquete alternativo `windows-x64-portable.zip` debe extraerse por completo.
Hasta que la aplicación tenga firma Authenticode y reputación, Windows
SmartScreen puede advertir que el editor es desconocido.

## macOS

Instala Xcode Command Line Tools y Verilator. Homebrew es una opción:

```bash
xcode-select --install
brew install verilator
```

FPGALab ofrece aplicaciones separadas para equipos Intel (`x86_64`) y Apple Silicon (`arm64`). Ambas requieren estas herramientas externas de compilación para ejecutar un diseño de Icestudio.

Los paquetes tienen firma ad hoc para integridad, pero no están notarizados
por Apple. Si macOS bloquea la primera ejecución, usa **Control-clic → Abrir**
sobre `FPGALab.app`.

## Una compilación parece bloqueada

Algunos diseños Verilog válidos exponen limitaciones del optimizador en determinadas versiones de Verilator. Activa la optimización de compatibilidad en Simulation Settings y vuelve a ejecutar.
