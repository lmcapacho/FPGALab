# Primeros pasos

## Instalar FPGALab

Descarga el paquete para Linux, Windows o macOS desde [GitHub Releases](https://github.com/lmcapacho/FPGALab/releases). Descomprime completamente los paquetes portables antes de abrir la aplicación.

- **Linux:** extrae `linux-x86_64.tar.gz` y ejecuta `FPGALab` desde la carpeta resultante.
- **Windows:** usa el archivo autocontenido `windows-x64.exe`, o extrae completamente `windows-x64-portable.zip` antes de ejecutar `FPGALab.exe`.
- **macOS Intel:** extrae `macos-x86_64.zip`.
- **macOS Apple Silicon:** extrae `macos-arm64.zip`.

La aplicación de macOS tiene firma ad hoc, pero todavía no está notarizada por Apple. En la primera ejecución puede ser necesario usar **Control-clic → Abrir** sobre `FPGALab.app`.

Para ejecutar desde el código fuente:

```bash
git clone https://github.com/lmcapacho/FPGALab.git
cd FPGALab
python -m venv .venv
source .venv/bin/activate
pip install -e .
fpga-lab
```

El comando de activación anterior se usa en Linux y macOS. En Windows PowerShell usa `.venv\Scripts\Activate.ps1`.

## Ejecutar un diseño

1. Abre el diseño en Icestudio.
2. Genera su salida Verilog. El proyecto debe contener `ice-build/<design>/main.v` y un archivo de restricciones de pines PCF o XDC.
3. Abre el archivo `.ice` con el botón **Browse** de FPGALab.
4. Selecciona o crea un Lab. Su tarjeta guardada aparece en el selector de la barra superior y determina qué definición se usa para asignar pines y simular. Si cambias el selector, se actualiza el Lab actual. Por ahora, Alhambra II es la única tarjeta incluida.
5. Presiona **Run**. La primera ejecución puede compilar el modelo nativo; las siguientes reutilizan la caché incremental cuando sea posible.
6. Interactúa con los controles de la tarjeta y los periféricos externos.
7. Presiona **Stop** antes de cambiar el proyecto, la tarjeta, el Lab o la configuración de simulación.

FPGALab almacena los modelos nativos en la caché del usuario, no dentro del proyecto de Icestudio.

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

FPGALab consulta GitHub Releases al iniciar y desde el botón de actualización
de la barra de estado. Las versiones estables consultan versiones estables;
las candidatas también consideran otras candidatas. La actualización abre la
página de descarga, sin reemplazar automáticamente la aplicación en uso.
