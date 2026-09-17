# Labs y mesa de trabajo

Un **Lab** es una configuración reutilizable de periféricos, independiente del proyecto de Icestudio. Almacena componentes, asignaciones de pines, propiedades, posiciones, zoom y posición de la cámara.

## Administrar Labs

Abre el administrador desde el selector de la barra superior. Puedes crear, duplicar, renombrar, eliminar, importar y exportar Labs. Los archivos `.lab` exportados son documentos JSON portables que se pueden compartir junto con el diseño `.ice` correspondiente.

Ubicaciones predeterminadas:

- Linux y macOS: `~/FPGALab/labs`
- Windows: `Documents/FPGALab/labs`

Configura `FPGALAB_WORKSPACE` para elegir otra carpeta raíz.

## Controles de la mesa

- Abre el catálogo con el botón flotante para agregar un periférico.
- Arrastra un componente para moverlo.
- Arrastra sobre un espacio vacío para seleccionar varios componentes.
- Usa `Shift`+clic para modificar la selección.
- Usa `Ctrl+D` para duplicar y `Supr` para eliminar.
- Usa `Ctrl+Z` y `Ctrl+Y` para deshacer y rehacer.
- Usa la rueda del mouse para controlar el zoom.
- Usa `Ctrl`+arrastrar o el botón central para desplazar la mesa.
- Usa la barra para volver a 100 % o encuadrar todos los elementos.

Los terminales pueden quedar sin conexión mientras se organiza el Lab. Al iniciar la simulación se informan las conexiones obligatorias faltantes.
