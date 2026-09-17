# Toolchain y solución de problemas

FPGALab necesita Verilator 5 o posterior, herramientas de compilación compatibles con GNU Make, Python y un compilador C++17. Usa el icono de terminal con verificación en la barra de estado para consultar las rutas exactas encontradas.

## Orden de búsqueda

FPGALab busca:

1. OSS CAD Suite instalado por Apio o Icestudio.
2. Una instalación configurada mediante `FPGALAB_OSS_CAD_SUITE`.
3. Verilator disponible en el `PATH` del sistema.

Usa `FPGALAB_VERILATOR` para seleccionar un ejecutable y `MSYS2_ROOT` si MSYS2 está instalado en otra ubicación.

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

## macOS

Instala Xcode Command Line Tools y Verilator. Homebrew es una opción:

```bash
xcode-select --install
brew install verilator
```

FPGALab ofrece aplicaciones separadas para equipos Intel (`x86_64`) y Apple Silicon (`arm64`). Ambas requieren estas herramientas externas de compilación para ejecutar un diseño de Icestudio.

## Una compilación parece bloqueada

Algunos diseños Verilog válidos exponen limitaciones del optimizador en determinadas versiones de Verilator. Activa la optimización de compatibilidad en Simulation Settings y vuelve a ejecutar.
