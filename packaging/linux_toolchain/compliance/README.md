# SDK maintenance and compliance records

This directory contains maintainer evidence, artifact-specific validation results
and unresolved publication checks. It is not the development guide, a release
announcement or legal redistribution approval. These records are excluded from
the controlled Docker context and source companion: they are not build inputs.

- [License matrix and SDK2/SDK3 evidence — English](sdk-licenses.en.md)
- [Matriz de licencias y evidencias SDK2/SDK3 — español](sdk-licenses.es.md)
- [SDK3 component review — English](sdk3-review.en.md)
- [Revisión de componentes SDK3 — español](sdk3-review.es.md)
- [Build and test procedure — English](../../../docs/en/packaging.md#experimental-self-contained-linux-toolchain)
- [Procedimiento de construcción y pruebas — español](../../../docs/es/packaging.md#toolchain-linux-autocontenido-experimental)

## Earlier desktop observations

The following reports preceded SDK3; they are retained from the development guide
as historical observations, not qualification of a new artifact. Exact artifact
hashes were not attached to these desktop reports.

- Default startup on a clean Ubuntu 24.04 desktop worked without forcing X11.
- A controlled SDK completed a loopback download into isolated temporary user
  data, automatic discovery and the relocated native ABI probe without host build
  tools. This does not establish downloaded-SDK desktop compatibility.
- The complete offline bundle was tested on a clean Ubuntu 24.04 VM: direct
  startup, bundled-tool discovery, Lab/design loading, compilation, simulation
  and reopening without manual toolchain paths. This is not qualification of
  SDK3, other distributions or network isolation.

## Observaciones de escritorio anteriores

Estos informes preceden a SDK3 y se conservan como observaciones históricas,
no como validación de un artefacto nuevo. No se asociaron hashes exactos a esos
informes de escritorio.

- El arranque predeterminado funcionó en Ubuntu 24.04 limpio sin forzar X11.
- Un SDK controlado completó descarga por loopback a datos de usuario temporales,
  detección automática y prueba ABI nativa reubicada sin herramientas del sistema.
  Esto no valida el SDK descargado en un escritorio limpio.
- El paquete offline completo se probó en una VM Ubuntu 24.04 limpia: apertura,
  detección de herramientas incluidas, carga de Lab/diseño, compilación, simulación
  y reapertura sin rutas manuales. No valida SDK3, otras distribuciones ni
  aislamiento de red.

Record new results against exact artifact identities, including limitations and
remaining checks. Keep developer instructions in the guides and release outcomes
in the changelog; do not turn either into a running test diary.

Registra resultados nuevos contra artefactos identificados, con sus límites y
pendientes. Las instrucciones van en las guías y los resultados relevantes para
versiones en el changelog; ninguno debe convertirse en diario de pruebas.
