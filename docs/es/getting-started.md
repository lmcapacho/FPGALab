# Primeros pasos

Para ejecutar tu primer diseño necesitas **FPGALab**, un **diseño de Icestudio
con Verilog generado** y las **herramientas de simulación**. No necesitas una
tarjeta FPGA física. Sigue estos tres pasos en orden.

## 1. Instalar FPGALab

Descarga el paquete para Linux, Windows o macOS desde [GitHub Releases](https://github.com/lmcapacho/FPGALab/releases). Descomprime completamente los paquetes portables antes de abrir la aplicación.

- **Linux:** extrae `linux-x86_64.tar.gz` y ejecuta `FPGALab` desde la carpeta resultante.
- **Windows:** usa el archivo autocontenido `windows-x64.exe`, o extrae completamente `windows-x64-portable.zip` antes de ejecutar `FPGALab.exe`.
- **macOS Intel:** extrae `macos-x86_64.zip`.
- **macOS Apple Silicon:** extrae `macos-arm64.zip`.

La aplicación de macOS tiene firma ad hoc, pero todavía no está notarizada por Apple. En la primera ejecución puede ser necesario usar **Control-clic → Abrir** sobre `FPGALab.app`.

Los paquetes incluyen Python y PyQt, **no el toolchain completo de simulación**.
Esto también aplica al `.exe` independiente de Windows: continúa con el paso 2
antes de intentar ejecutar un diseño.

## 2. Preparar y comprobar las herramientas de simulación

FPGALab compila cada diseño con **Verilator 5+, GNU Make y un compilador
C++17**. Instálalos por separado si aún no están disponibles; las versiones
actuales no los descargan ni configuran automáticamente.

| Sistema | Qué preparar | Instrucciones de instalación |
| --- | --- | --- |
| Linux | Verilator, Make y G++; Verilator también puede provenir de Icestudio/Apio. | [Toolchain para Linux](troubleshooting.md#linux) |
| Windows | Verilator de Icestudio/Apio u OSS CAD Suite, más MSYS2 con Make, Python y un compilador C++ MinGW-w64. | [Toolchain para Windows](troubleshooting.md#windows) |
| macOS | Verilator y Xcode Command Line Tools para Make y el compilador C++. | [Toolchain para macOS](troubleshooting.md#macos) |

Tener Icestudio instalado no garantiza que estén todas las herramientas.
Después de instalarlas, abre FPGALab y usa el **icono de terminal con
verificación en la barra de estado**. Comprueba que Verilator, Make y el
compilador tengan rutas disponibles antes de continuar. Si falta alguno,
sigue la guía de tu sistema; las ubicaciones no habituales se explican en
[Orden de búsqueda](troubleshooting.md#orden-de-busqueda).

## 3. Ejecutar tu primer diseño

1. Abre el diseño en Icestudio.
2. Genera su salida Verilog. El proyecto debe contener `ice-build/<design>/main.v` y un archivo de restricciones de pines PCF o XDC.
3. Abre el archivo `.ice` con el botón **Browse** de FPGALab.
4. Selecciona o crea un **Lab**, que guarda la tarjeta virtual y la distribución de periféricos. Comprueba que la tarjeta del selector superior coincida con la de tu diseño de Icestudio.
5. Presiona **Run**. La primera ejecución puede compilar el modelo nativo; las siguientes reutilizan la caché incremental cuando sea posible.
6. Interactúa con los controles de la tarjeta y los periféricos externos.
7. Presiona **Stop** antes de cambiar el proyecto, la tarjeta, el Lab o la configuración de simulación.

FPGALab almacena los modelos nativos en la caché del usuario, no dentro del proyecto de Icestudio.

Para agregar periféricos, asignar pines y compartir Labs, continúa con
[Labs y mesa de trabajo](labs-and-workbench.md). Los detalles de integración
y límites de Bitsy están en la [guía de desarrollo](development.md#integracion-de-tarjetas-icebreaker-bitsy).

## Cómo se asignan los pines

FPGALab lee el PCF o XDC del diseño en `ice-build` para relacionar las redes
HDL generadas con los pines físicos y endpoints de la tarjeta. Por eso un LED
o interruptor integrado funciona aunque su red HDL no se llame `LED0` o `SW1`.
En la configuración de un periférico de la mesa, conecta su terminal a un
endpoint de la tarjeta; FPGALab busca la red HDL correspondiente con las mismas
restricciones. Un periférico puede seguir conectado en el Lab cuando el diseño
actual no usa ese pin, pero no intercambiará una señal con el HDL.

Usa **Conexiones** para inspeccionar estas asignaciones. El soporte XDC cubre
asignaciones literales `PACKAGE_PIN`, no expresiones Tcl arbitrarias; consulta
[Arquitectura y contribución](development.md) para conocer las formas admitidas.

## Abrir desde la línea de comandos

Inicia la aplicación con `fpga-lab` o abre directamente un diseño con
`fpga-lab --ice /ruta/al/diseno.ice`. Entre las opciones avanzadas están
`--library` y `--profile` para un modelo ya compilado, `--cache-dir` para
otra caché y `--clock-hz`, `--ui-refresh-hz` y `--observation-hz` para ajustes
de simulación válidos solo durante esta ejecución. Usa `fpga-lab --help` para
ver todas las opciones.

## Opcional: ejecutar desde el código fuente

Esta alternativa requiere Python 3.10+, además del toolchain del paso 2:

```bash
git clone https://github.com/lmcapacho/FPGALab.git
cd FPGALab
python -m venv .venv
source .venv/bin/activate
pip install -e .
fpga-lab
```

La activación anterior se usa en Linux y macOS. En Windows PowerShell usa
`.venv\Scripts\Activate.ps1`.
