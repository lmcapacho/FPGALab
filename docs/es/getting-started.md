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
2. Genera su salida Verilog. El proyecto debe contener `ice-build/<design>/main.v` y su archivo PCF.
3. Abre el archivo `.ice` con el botón **Browse** de FPGALab.
4. Selecciona o crea un Lab.
5. Presiona **Run**. La primera ejecución puede compilar el modelo nativo; las siguientes reutilizan la caché incremental cuando sea posible.
6. Interactúa con los controles de la tarjeta y los periféricos externos.
7. Presiona **Stop** antes de cambiar el proyecto, Lab o configuración de simulación.

FPGALab almacena los modelos nativos en la caché del usuario, no dentro del proyecto de Icestudio.
