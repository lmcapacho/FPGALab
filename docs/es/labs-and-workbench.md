# Labs y mesa de trabajo

Un **Lab** es una configuración reutilizable de periféricos, independiente del proyecto de Icestudio. Almacena la tarjeta, los componentes, asignaciones de pines, propiedades, posiciones, zoom y posición de la cámara. El reloj virtual usa normalmente el `clock_hz` de la tarjeta seleccionada. En Configuración de simulación, activa **Usar otra frecuencia de reloj para este Lab** para cambiarla solo en ese Lab; restaurar los valores predeterminados vuelve al reloj de la tarjeta. El refresco de la interfaz y el muestreo temporal siguen siendo ajustes globales del usuario. El diálogo muestra la frecuencia efectiva de muestreo temporal, que no puede superar el reloj virtual.

Al iniciar por primera vez después de este cambio, el reloj virtual global guardado anteriormente se asigna al Lab activo. Los demás Labs usan el reloj de su tarjeta, salvo que se configuren por separado. La opción `--clock-hz` prevalece solo durante la ejecución actual y no modifica el Lab.

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
