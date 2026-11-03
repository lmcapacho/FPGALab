# Revisión de componentes SDK3 — 2026-10-31

Alcance: los hashes binarios/fuentes SDK3 registrados en [la matriz](sdk-licenses.es.md).
Es una revisión limitada de evidencias, no aprobación del SDK completo. Se leyeron
los comprimidos sin extraer ni ejecutar código upstream. No se modificaron los
artefactos generados ni sus avisos originales.

## Resultados y condiciones pendientes

| Comprobación | Evidencia/resultado | Qué sigue abierto |
| --- | --- | --- |
| Ambigüedad de versión en ACL | Las cabeceras de la biblioteca y `doc/COPYING.LGPL` respaldan LGPL-2.1-or-later, coherente con el texto del aviso conservado, no con su etiqueta abreviada `LGPL-2+`. | Alcance completo de archivos/construcción y condiciones LGPL; no aprobación global del paquete. |
| Ambigüedad de versión en attr | Las cabeceras de biblioteca y fuentes añadidas relevantes de los parches Ubuntu contienen la misma declaración LGPL-2.1-or-later. | Alcance de archivos, auxiliares de cabecera y condiciones de distribución. |
| Uso efectivo de Berkeley DB | `readelf -d` sobre `DB_File.so` distribuido registra `libdb-5.3.so` como NEEDED. | Instrucciones de acceso a fuentes y condiciones de distribución combinada aplicables. |
| Fuentes DB y consumidor Perl directo | El acompañante incluye archivos exactos `db5.3` y `perl`; el de Perl contiene `cpan/DB_File/DB_File.xs`, con copyright y declaración de licencia Perl originales. | Integridad/reconstrucción más allá del módulo, elección de vía permitida y publicación duradera. |
| Conservación de avisos/licencias | Se conservan los avisos binarios seleccionados; existen los textos `LGPL-2.1`, `GPL-1` y `Artistic` en las licencias comunes del SDK. | Entrega efectiva a destinatarios y avisos de los demás componentes/recursos. |

Solo se resuelve la **aclaración de versión** concreta de ACL/attr. P1–P8 siguen
abiertos para el SDK completo. No se reescriben avisos upstream ni se elige
silenciosamente una alternativa de licencia de Perl o Berkeley DB.

## Evidencias fuente ACL y attr

Versiones exactas: `acl 2.3.2-1build1.1` y `attr 1:2.5.2-1ubuntu0.1`.
Archivos relevantes en los comprimidos originales:

- `acl-2.3.2/libacl/acl_get_file.c`, `libacl/acl_init.c`,
  `libacl/perm_copy_fd.c`, `libacl/perm_copy_file.c` y `doc/COPYING.LGPL`.
- `attr-2.5.2/libattr/attr_copy_fd.c`, `libattr/attr_copy_file.c`,
  `include/attributes.h` y `doc/COPYING.LGPL`.

Se inspeccionaron declaraciones de licencia en los grupos fuente `libacl`,
`libattr`, `include` y `libmisc`. ACL también tiene pequeñas cabeceras internas
sin texto de licencia independiente; attr tiene auxiliares de configuración y
traducción similares. No se deduce una licencia independiente para esos archivos
solo por proximidad a los demás.

Los comprimidos Debian/Ubuntu conservan las listas y los parches aplicados.
La serie ACL modifica `tools/getfacl.c`, no estas declaraciones de biblioteca.
attr también añade cabeceras e implementaciones `libmisc`: las nuevas fuentes C
revisadas de xattrat/compatibilidad, walk-tree y openat2 declaran LGPL-2.1-or-later,
igual que `compat-xattr-header.patch`. Por eso no basta revisar solo upstream.
La serie y todas las fuentes permanecen en el acompañante.

Las condiciones LGPL para bibliotecas y consumidores enlazados se revisan aparte;
aclarar la versión no demuestra integridad de fuentes ni cumplimiento de las
condiciones de reemplazo/reenlace.

## Evidencias Berkeley DB / Perl

Versiones exactas: `db5.3 5.3.28+dfsg2-7` y `perl 5.38.2-3.2ubuntu0.6`.
El archivo fuente `db-5.3.28/LICENSE` y el copyright binario `libdb5.3t64/copyright`
conservan Sleepycat. El `DB_File.xs` revisado remite a los términos de Perl;
su copyright conservado identifica expresamente `cpan/DB_File/*` como GPL-1+
o Artistic. Su comprimido fuente también contiene `Copying` y `Artistic`.

La [licencia Sleepycat](https://opensource.org/license/sleepycat) exige
instrucciones para obtener las fuentes completas de DB y del software acompañante
que lo usa. La [página de licencias de Perl](https://dev.perl.org/licenses/)
describe las alternativas principales; los avisos exactos por archivo del
comprimido corresponden a esta versión y se conservan. Tener esos archivos es
evidencia de cobertura, no decisión legal completa sobre todos los consumidores.

Antes de publicar, entregar instrucciones al destinatario que identifiquen las
versiones exactas DB y Perl en el acompañante correspondiente, checksum y lugar
duradero de descarga. No sustituirlas por una página upstream genérica ni afirmar
que hay fuentes en una URL aún no publicada. No hay URL de fuentes en las
evidencias revisadas; esa parte de P6 sigue abierta.

## Identidades reproducibles de evidencia

Las rutas siguientes son relativas a `sdk-sources/packages/`; el binario se indica
por separado. SHA-256 de los comprimidos fuente originales:

```text
acl/2.3.2-1build1.1/acl_2.3.2.orig.tar.xz
97203a72cae99ab89a067fe2210c1cbf052bc492b479eca7d226d9830883b0bd
attr/1_2.5.2-1ubuntu0.1/attr_2.5.2.orig.tar.xz
f2e97b0ab7ce293681ab701915766190d607a1dba7fae8a718138150b700a70b
db5.3/5.3.28+dfsg2-7/db5.3_5.3.28+dfsg2.orig.tar.xz
ad41b507415dec8316e828b2230242af2251d2c86eefa3c7aa9ef47c5239ef33
perl/5.38.2-3.2ubuntu0.6/perl_5.38.2.orig.tar.xz
d91115e90b896520e83d4de6b52f8254ef2b70a8d545ffab33200ea9f1cf29e8
```

El binario SDK `rootfs/usr/lib/x86_64-linux-gnu/perl/5.38.2/auto/DB_File/DB_File.so`
tiene SHA-256 `f39e25fdff4d3956fec2be4f2d70bdcca52306bb4e328406d356ed506f330ee3`.
Usar `readelf -d` sobre él, no `ldd` con ejecutables no confiables, para consultar
las dependencias registradas. Los controles del manifiesto cubren comprimidos
originales/de empaquetado y copias de avisos; son distintos de la revisión legal.

## Verilator 5.020-1: fuentes, reubicación y alcance de licencia

El copyright binario y los archivos fuente revisados `bin/verilator`,
`src/V3Ast.h`, `include/verilated.h` e `include/verilated.cpp` ofrecen
`LGPL-3.0-only OR Artistic-2.0`. El comprimido original incluye `LICENSE` (LGPL3)
y `Artistic` (Artistic2). El copyright binario contiene el texto completo Artistic2;
el SDK también conserva los textos comunes `LGPL-3` y `GPL-3`. La Artistic antigua
de Perl no sustituye la Artistic2 de Verilator.

La vía LGPL3 requiere leer GPL3 junto con los permisos adicionales LGPL3. La
alternativa [Artistic2](https://opensource.org/license/Artistic-2.0) distingue
distribuciones estándar/modificadas, acceso a fuentes y documentación de cambios.
Aquí no se elige la vía definitiva. En particular, no se supone que todo cambio
obligue a renombrar: la sección 4 ofrece alternativas y la 9 distingue obras que
solo usan o extienden el paquete. Se evalúan los cambios reales, sin considerar
automáticamente todo lanzador FPGALab como derivado de Verilator.

### Diferencias observadas en este artefacto

| Ruta en el SDK binario | Contenido/cambio observado |
| --- | --- |
| `rootfs/usr/bin/verilator` | Coincide con `bin/verilator` upstream salvo el intérprete de la primera línea (`#!/usr/bin/env perl` frente a `#! /usr/bin/perl`). No hay otra diferencia textual. |
| `bin/verilator` | Lanzador shell FPGALab que selecciona Perl privado, PATH y `VERILATOR_ROOT`. |
| `rootfs/usr/bin/verilator_bin` | Wrapper FPGALab del cargador que llama a `verilator_bin.fpgalab-elf` con bibliotecas privadas. |
| `rootfs/usr/bin/verilator_bin.fpgalab-elf` | Ejecutable conservado y renombrado por el ensamblador, no recompilado desde fuentes Verilator al armar el SDK. No se hizo comparación binaria independiente contra el `.deb` original. |
| `rootfs/usr/share/verilator/bin/verilator_bin` | Script FPGALab que redirige a la ubicación del ejecutable incluido. |
| `rootfs/usr/share/verilator/include/` | Los 52 archivos instalados que tienen contraparte upstream en la misma ruta coinciden byte a byte. Los generados necesitan procedencia propia; no se compararon todos los recursos empaquetados. |

El acompañante Debian conserva `debian/rules` y el único parche listado,
`pkgconfig.diff`, que elimina el campo pkgconfig `libdir`. Son cambios de la
distribución, distintos de los wrappers FPGALab. Se conservan fuentes e insumos
de empaquetado; esto no demuestra reconstrucción reproducible del ejecutable.

### El material incluido no tiene una licencia dual uniforme

El árbol include instalado contiene 42 archivos con el SPDX dual, seis GTKWave
con MIT y dos LZ4 con BSD-2-Clause. Cuatro no tienen línea SPDX: el generado
`gtkwave/fst_config.h` y las tres cabeceras `vltstd/svdpi.h`, `vltstd/vpi_user.h`,
`vltstd/sv_vpi_user.h`. Estas últimas remiten a interfaces IEEE/SystemVerilog.
No tener SPDX no demuestra ausencia de permiso, pero el aviso global del paquete
no resuelve por sí solo cada archivo. Registrar el permiso aplicable upstream/de
la norma antes de cerrar P1/P2/P5; no quitar cabeceras ni asignarles Artistic2 o
LGPL3 sin esa evidencia. Conservar avisos MIT/BSD aunque la simulación actual no
active trazas.

### Pendientes de publicación para Verilator

- Registrar la vía permitida elegida para los archivos Verilator relevantes,
  separada de MIT/BSD/cabeceras estándar y código independiente FPGALab.
- Entregar atribución clara de adaptaciones/cambios en las rutas anteriores;
  conservar avisos upstream e identificar el empaquetado FPGALab sin insinuar
  respaldo upstream. Este registro no es aún un aviso entregado con el artefacto.
- Publicar fuentes originales exactas, parches/reglas de empaquetado e insumos
  FPGALab correspondientes, con instrucciones de descarga funcionales.
- Completar alcance de archivos incluidos y comprobaciones de reconstrucción y
  fuentes; mantener P1/P2/P3/P5/P7 abiertos para este componente, sin aprobarlo
  solo porque pasó la prueba ABI.

SHA-256 de comprimidos fuente:

```text
verilator_5.020.orig.tar.gz
3efb3a7c50c0bc0ea3989bf9219785b718cf9d056c643a9cef45570fbe46dafb
verilator_5.020-1.debian.tar.xz
e31f96dcff0bf32c90fd5f5d31e779be6a1a51c159e97f0d0443ae922537eaa1
```

El ejecutable renombrado del SDK tiene SHA-256
`25f33046f0055a6982c67cdc55081685a844abb50d044cfda087bd418db9be6c`.
Registrar la revisión no modifica ni exige reconstruir el SDK; incorporar avisos
al artefacto después cambia su contenido y exige checksums nuevos.
