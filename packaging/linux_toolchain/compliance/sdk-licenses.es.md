# Matriz de licencias del SDK y pendientes

Estado: **revisión inicial de avisos; sin aprobación para redistribución pública**.
Snapshot revisado: **2026-10-25**, `ubuntu24.04-x86_64-sdk2`, snapshot Ubuntu
`20261001T000000Z`. Es un documento de evidencias y seguimiento para mantenedores,
no asesoría jurídica ni certificado de cumplimiento. No cambia ninguna licencia.

## Seguimiento técnico de SDK3 — 2026-10-31

La construcción reducida SDK3 pasó reubicación, prueba ABI nativa en Ubuntu
limpio sin red, compilaciones Make repetidas y verificación de fuentes/procedencia.
La comprobación independiente de los acompañantes también confirmó los SHA-256
de comprimidos y manifiesto. Sus 100 paquetes binarios coinciden con los 54 grupos
fuente/versión y conteos de la matriz. Conserva **28 entradas locales de
construcción**, más el registro de procedencia, sin gráficos del escritorio ni
paquetes de tarjetas/periféricos.

```text
SDK: ubuntu24.04-x86_64-sdk3
fpgalab-linux-sdk.tar.gz
56ca256eaf1cfa01aae30b6d10aff8372b06afd1d488bd93c4cc3f71bea9e6a0
fpgalab-linux-sdk-sources.tar.gz
2f61a7a20bd00858e860b82ab18f8d3a44a14bb4499a9b3528206a54bba106cb
source-manifest.json
5f39f9da39c43ea13eae82d42f336e2ba6e19b0a4732b33e22f956d7020758c9
Git: e8dce338f7fe2b05af4858f177b34a858b85a448; dirty: true
```

Esto cierra solo la comprobación técnica de selección de fuentes para estos
artefactos SDK3, no P1–P8 ni la aprobación legal. Falta la prueba gráfica de SDK3
en un escritorio limpio. Los archivos originales SDK2 ya no están disponibles
localmente para comparar sus avisos byte a byte; coincidir en identidad de
paquetes no cierra esa revisión. La matriz conserva la evaluación inicial con
las evidencias SDK2 siguientes; SDK3 requiere decisiones por archivo y controles
de publicación propios. Las licencias de gráficos siguen aplicando al acompañante
SDK2 y a la aplicación de escritorio, pero esos recursos no están en este
acompañante SDK3. Se conservan los hashes y hallazgos SDK2 sin cambiar
retroactivamente su alcance registrado.

## Alcance y evidencias de SDK2

El SDK observado registra **100 paquetes binarios de 54 pares fuente/versión**.
Su acompañante conserva archivos fuente originales Ubuntu, empaquetado/parches,
avisos y **171 archivos de entrada locales de FPGALab**. Se verificaron la
recolección y los checksums; esto **no** determina la licencia aplicable a cada
archivo distribuido ni el cumplimiento completo de todas sus condiciones.

Los archivos revisados se identifican por SHA-256, no solo por el ID del SDK:

```text
fpgalab-linux-sdk.tar.gz
3e0408750d0ec0f8b580eabf6eb1de5e12aba69dee1e23be885bb9ab05fce709
fpgalab-linux-sdk-sources.tar.gz
a4d90262b3c7dea35fef1e9330446189df9e4ff0155e27c03e24d0fe2fc0308a
source-manifest.json
9698844b59443e487f342339b80ad6186c2a44494cba70510bab8a4af3dada75
```

Ubicaciones de evidencia dentro de esos archivos:

| Evidencia | Ubicación y significado |
| --- | --- |
| Relación binario/fuente | `source-packages.json` del SDK: paquete fuente/versión exactos y ruta de copyright de cada paquete binario. |
| Avisos de terceros | SDK: `rootfs/usr/share/doc/<binario>/copyright`; acompañante: `notices/<binario>/copyright`. Revisar cada aviso binario, sin suponer una ruta por nombre del paquete fuente. |
| Textos comunes de licencias | SDK: `rootfs/usr/share/common-licenses/`; acompañante: `common-licenses/`. Otros términos pueden estar en los copyrights o fuentes originales. |
| Fuentes y checksums | `source-manifest.json`, `packages/<fuente>/<versión>/apt-source-record.txt` y `.dsc`/archivos originales del acompañante. El epoch usa `_` solo en nombres de carpetas. |
| Adaptaciones FPGALab | `fpgalab/` del acompañante, con scripts de construcción/reubicación, receta, `LICENSE`, `NOTICE` y `provenance.json`; SDK: `FPGALAB-LICENSE.txt` y `FPGALAB-NOTICE.txt`. |
| Relación entre comprimidos | `source-bundle.json` de la construcción; `toolchain.json` del SDK enlaza el acompañante mediante digest. |

Esta construcción de prueba registra la revisión Git
`cf790d51154143da03d34a5d49e396d00054342e` con `dirty: true`. Los hashes conservados
identifican sus entradas reales; esa revisión por sí sola **no** identifica todas
sus fuentes. Un archivo o entradas diferentes requieren revisar las evidencias
de nuevo, aunque coincida la etiqueta de versión. No se sustituye silenciosamente
un SDK publicado bajo el mismo ID.

## Cómo leer la matriz

La receta posterior SDK3 limita el contexto de construcción y las fuentes locales
a dependencias del compilador/prueba, fuentes nativas, scripts de empaquetado y
avisos; excluye gráficos del escritorio. Es un cambio de selección de fuentes,
no una revisión ni sustitución de los archivos SDK2 identificados arriba. SDK3
ya tiene construcción y validación técnica registradas arriba, pero aún requiere
revisión de licencias del artefacto.
El hallazgo de los SVG sigue aplicando al acompañante SDK2 archivado y al paquete
de escritorio; excluirlos de SDK3 no resuelve su licencia.

Cada fila agrupa **fuente/versión**, no un único ejecutable; el conteo indica
paquetes binarios del inventario. No significa que se hayan copiado todos los
archivos upstream al SDK. Los resúmenes son una lectura inicial de los avisos
conservados, **no expresiones SPDX para paquetes completos ni elecciones finales
de licencia**. Por ejemplo, GPL en empaquetado/pruebas no describe automáticamente
una biblioteca de ese paquete. El [formato de copyright de Debian](https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/)
relaciona términos de licencia con grupos de archivos.

`+` significa «o posterior» donde el aviso lo permite. Las alternativas y
excepciones solo aplican a los archivos cuyos avisos las ofrecen. **Todas las
filas siguen abiertas** para los pendientes transversales de abajo; la última
columna señala una revisión específica, no autorización para redistribuir ni
una enumeración exhaustiva de obligaciones.

| Fuente | Versión fuente exacta | Binarios | Lectura inicial de licencias | Revisión específica pendiente |
| --- | --- | ---: | --- | --- |
| `acl` | `2.3.2-1build1.1` | 1 | GPL-2+; biblioteca con etiqueta LGPL-2+ y texto LGPL-2.1+ | Resolver discrepancia de versión con cabeceras originales de la biblioteca (P1/P4). |
| `attr` | `1:2.5.2-1ubuntu0.1` | 1 | GPL-2+; biblioteca con etiqueta LGPL-2+ y texto LGPL-2.1+ | Misma discrepancia; separar biblioteca y utilidades (P1/P4). |
| `base-files` | `13ubuntu10.5` | 1 | Material del paquete GPL-2+; documentos de licencia con sus propios términos | Separar scripts, licencias e identidad/marcas de la distribución (P1/P5). |
| `bash` | `5.2.21-2ubuntu4` | 1 | GPL-3+; otros términos por archivo y documentación GFDL | Identificar auxiliares/documentación incluidos y conservar avisos aplicables (P1/P3/P5). |
| `binutils` | `2.42-4ubuntu2.10` | 8 | GPL-3+ y términos/excepciones específicos de bibliotecas | Revisar ensamblador/enlazador, bibliotecas y plugins por separado (P1/P4). |
| `bzip2` | `1.0.8-5.1ubuntu0.1` | 1 | Variante BSD de bzip2; empaquetado GPL-2 | Conservar sus condiciones reales; no etiquetar la biblioteca por el empaquetado (P1/P5). |
| `coreutils` | `9.4-3ubuntu6.3` | 1 | GPL-3+; aportes ISC/BSD y documentación GFDL | Mapear aportes auxiliares y documentación conservada (P1/P3/P5). |
| `dash` | `0.5.12-6ubuntu5` | 1 | BSD-3-Clause; auxiliares de dominio público/GPL-2+ | Separar shell instalado y auxiliares solo de construcción (P1/P5). |
| `db5.3` | `5.3.28+dfsg2-7` | 1 | Sleepycat y BSD-3-Clause; otros bindings con términos distintos | Prioridad alta: acceso a fuentes del software acompañante, incluido DB_File de Perl (P2/P6). |
| `debconf` | `1.5.86ubuntu1` | 1 | BSD-2-Clause | Conservar copyright, condiciones y descargo de scripts/módulos incluidos (P1/P5). |
| `debianutils` | `5.17build1` | 1 | GPL-2+; SMAIL-GPL y archivos de dominio público | Revisar términos particulares de savelog y utilidades distribuidas (P1/P2). |
| `dpkg` | `1.22.6ubuntu6.6` | 1 | GPL-2+; componentes de dominio público | Relacionar herramientas y auxiliares con fuentes/avisos correspondientes (P1/P3). |
| `expat` | `2.6.1-2ubuntu0.6` | 1 | MIT | Comprobar entrega del copyright, licencia y descargo de la biblioteca (P5). |
| `findutils` | `4.9.0-5build1` | 1 | Herramientas GPL-3+; auxiliares LGPL/BSD/ISC, excepciones y documentación GFDL | No confundir el bloque predeterminado de documentación con los ejecutables (P1/P3). |
| `fonts-font-awesome` | `5.0.10+really4.7.0~dfsg-4.1` | 1 | Fuentes OFL-1.1; CSS Expat; empaquetado GPL-3+ | Revisar nombres/entrega de licencias de fuentes, separados de CSS/empaquetado (P2/P5). |
| `fonts-lato` | `2.015-1` | 1 | Fuentes OFL-1.1; empaquetado GPL-2+ | Revisar nombres reservados si se modifican; conservar copyright/OFL (P2/P5). |
| `gcc-13` | `13.3.0-6ubuntu2~24.04.1` | 9 | Compilador GPL-3+; ciertos runtimes con GCC Runtime Library Exception 3.1 | Separar compilador, cabeceras, plugins y excepciones aplicables a runtimes (P1/P3/P4). |
| `gcc-14` | `14.2.0-4ubuntu2~24.04.1` | 13 | Familia GPL-3+; excepciones de runtimes y términos por componente | El grupo aporta runtimes, no prueba un segundo compilador instalado; revisar cada biblioteca (P1/P4). |
| `gcc-defaults` | `1.214ubuntu1` | 6 | Scripts GPL-2+; otros términos de páginas de manual | Separar selectores/enlaces de las licencias de compiladores/runtimes GCC (P1/P5). |
| `gdbm` | `1.23-5.1build1` | 2 | Biblioteca GPL-3+; pruebas GPL-2+ y documentación GFDL | Revisar consumidores y alcance de biblioteca/fuentes incluidos (P1/P4). |
| `glibc` | `2.39-0ubuntu8.9` | 3 | Principalmente LGPL-2.1+; utilidades GPL-2+ y otros aportes | Prioridad alta: cargador, bibliotecas, cabeceras y condiciones de reemplazo/reconstrucción (P1/P3/P4). |
| `gmp` | `2:6.3.0+dfsg-2ubuntu6.1` | 1 | GPL-2+ O LGPL-3+ para archivos principales; otros términos en demos | Registrar elección permitida para archivos aplicables de la biblioteca (P1/P2/P4). |
| `isl` | `0.26-3build1.1` | 1 | Principalmente MIT; archivos BSD y LGPL-2.1+ | Identificar aportes qsort/imath compilados, no solo licencia principal (P1/P4). |
| `jansson` | `2.14-2build2` | 1 | Expat/estilo MIT | Conservar el copyright y permiso concretos (P5). |
| `libffi` | `3.4.6-1build1` | 1 | Biblioteca Expat; auxiliares GPL/alternativas MPL y dominio público | Separar biblioteca y auxiliares de pruebas/plataforma/construcción (P1/P5). |
| `libmd` | `1.1.0-2build1.1` | 1 | Variantes BSD, ISC, Beerware y aportes de dominio público | Conservar avisos por algoritmo; no reemplazarlos por un BSD genérico (P1/P2/P5). |
| `libselinux` | `3.5-2ubuntu2.1` | 1 | Biblioteca declarada de dominio público; utilidades/empaquetado GPL-2 | No clasificar libselinux1 como GPL solo por avisos de utilidades (P1/P5). |
| `libxcrypt` | `1:4.4.36-4build1` | 2 | LGPL-2.1+ general; licencias particulares por archivo | Revisar aportes de implementaciones criptográficas, cabeceras y alcance de biblioteca (P1/P4). |
| `libzstd` | `1.5.5+dfsg2-2build1.1` | 1 | BSD-3-Clause O GPL-2 para archivos principales; otros aportes | Registrar elección aplicable y separar contribuciones incorporadas (P1/P2/P5). |
| `linux` | `6.8.0-146.146` | 1 | Aviso GPL-2 del kernel; cabeceras UAPI con Linux-syscall-note/otros términos | Solo se registra linux-libc-dev; revisar SPDX de cada cabecera exportada (P1/P4). |
| `make-dfsg` | `4.3-4.1build2` | 1 | GPL-3+ | Instrucciones de reconstrucción/fuentes y adaptaciones del lanzador make del SDK (P3/P6/P7). |
| `mawk` | `1.3.4.20240123-1build1` | 1 | GPL-2.0-only; auxiliar X11 e icono CC-BY-3.0 | Conservar versión GPL exacta; comprobar si se distribuye el icono (P1/P5). |
| `media-types` | `10.1.0` | 1 | Información pública/declaración de dominio público; aviso ad-hoc | Conservar la declaración real, sin inventar una concesión SPDX (P2/P5). |
| `mpclib3` | `1.3.1-1build1.1` | 1 | Biblioteca LGPL-3+; empaquetado de dominio público | Condiciones de fuentes/reemplazo de la biblioteca (P3/P4). |
| `mpfr4` | `4.2.1-1build1.1` | 1 | Biblioteca LGPL-3+; documentación GFDL-1.2+ | Separar términos de biblioteca y documentación (P1/P4/P5). |
| `ncurses` | `6.4+20240113-1ubuntu2.2` | 2 | Estilo MIT/X11; archivos BSD-3-Clause | Conservar copyright/descargos específicos (P1/P5). |
| `netbase` | `6.4` | 1 | Aviso GPL-2 | Determinar datos/documentos copiados; el constructor excluye /etc (P1). |
| `node-jquery` | `3.6.1+dfsg+~3.5.14-1` | 1 | Expat | Conservar avisos JS y comprobar cobertura de fuentes originales/minificadas (P1/P5). |
| `openssl` | `3.0.13-0ubuntu3.16` | 1 | Archivos principales Apache-2.0; auxiliares Perl con otros términos | Comprobar material NOTICE aplicable y alcance real de la biblioteca (P1/P5). |
| `pcre2` | `10.42-4ubuntu2.1` | 1 | Variante BSD-3-clause Cambridge con excepción binary-library-like; otros términos | Leer excepción concreta; conservar avisos no implica exención general (P1/P2/P5). |
| `perl` | `5.38.2-3.2ubuntu0.6` | 4 | GPL-1+ O Perl Artistic para código principal; muchas licencias por módulo | Prioridad alta: elecciones, módulos, DB_File y lanzador modificado (P1/P2/P4/P7). |
| `python3-defaults` | `3.12.3-0ubuntu2.1` | 3 | Historial de licencias Python/aviso de empaquetado | Revisar selectores/lanzadores por separado de módulos CPython (P1/P5). |
| `python3.12` | `3.12.3-1ubuntu0.17` | 4 | Cadena histórica PSF/Python y software incorporado | Revisar enlaces de extensiones, avisos y lanzador privado (P1/P4/P7). |
| `readline` | `8.2-4build1` | 2 | GPL-3+; documentación GFDL y otros aportes | La extensión readline de CPython enlaza esta biblioteca; revisar distribución combinada (P1/P4). |
| `rpcsvc-proto` | `1.4.2-0ubuntu7` | 1 | Material BSD-3-Clause/permisivo; excepciones de auxiliares | Identificar entradas/salidas de rpcgen y archivos solo de construcción (P1/P5). |
| `sphinx` | `7.2.6-6` | 1 | BSD-2-Clause; recursos de búsqueda BSD-3-Clause | Solo se registra libjs-sphinxdoc; revisar avisos/fuentes JS (P1/P5). |
| `sphinx-rtd-theme` | `2.0.0+dfsg-1` | 1 | Expat; plantilla de búsqueda BSD-2-Clause | Relacionar recursos del tema y avisos frontend incorporados (P1/P5). |
| `sqlite3` | `3.45.1-1ubuntu2.8` | 1 | SQLite de dominio público; empaquetado GPL-2+ | No trasladar la licencia del empaquetado a libsqlite3-0; conservar procedencia (P1/P5). |
| `tar` | `1.35+dfsg-3ubuntu0.4` | 1 | GPL-3+; auxiliares LGPL y excepciones de parsers | Mapear herramientas, auxiliares y documentación conservada (P1/P3). |
| `tzdata` | `2026c-0ubuntu0.24.04.1` | 1 | Principalmente datos de dominio público; material ICU | El constructor excluye zoneinfo; identificar archivos restantes distribuidos (P1/P5). |
| `underscore` | `1.13.4~dfsg+~1.11.4-3` | 1 | JS Expat; documentación BSD; empaquetado GPL-3+ | Separar JS instalado y empaquetado; revisar fuentes de recursos (P1/P5). |
| `verilator` | `5.020-1` | 1 | Artistic-2.0 O LGPL-3 | Prioridad alta: elegir ruta permitida y documentar lanzador/recursos modificados (P1/P2/P7). |
| `xz-utils` | `5.6.1+really5.4.5-1ubuntu0.3` | 1 | liblzma principalmente de dominio público; herramientas/auxiliares GPL/LGPL y otros términos | Revisar liblzma de esta versión exacta; no etiquetarla por todas las herramientas xz (P1/P2). |
| `zlib` | `1:1.3.dfsg-3.1ubuntu2.2` | 1 | Licencia zlib | Conservar avisos e identificar con precisión fuentes modificadas (P5/P7). |

## Hallazgos concretos y prioridad

Seguimiento SDK3: [la revisión de componentes](sdk3-review.es.md) aclara la versión
ACL/attr contra cabeceras y parches, y confirma cobertura fuente de DB_File. Es
avance limitado; también registra reubicación Verilator y alcance MIT/BSD y de
cabeceras estándar. No cierra esos puntos para todo el SDK. Se
conservan los hallazgos históricos SDK2 siguientes.

1. **Berkeley DB se usa, no solo aparece en una lista.** `readelf -d` sobre
   `rootfs/usr/lib/x86_64-linux-gnu/perl/5.38.2/auto/DB_File/DB_File.so` del SDK
   registra `libdb-5.3.so` como NEEDED. Sleepycat incluye condiciones de acceso
   a fuentes de DB y del software acompañante que lo usa. Revisar explícitamente
   el consumidor Perl y las instrucciones de fuentes; disponer solo del archivo
   DB no cierra el punto. [Licencia Sleepycat](https://opensource.org/license/sleepycat).
2. **Las excepciones de runtime GCC son específicas por archivo.** No eliminan
   obligaciones de fuentes al distribuir la propia biblioteca. Hay que separar
   ese caso de compilar el diseño de un estudiante.
   [FAQ oficial de GNU](https://www.gnu.org/licenses/gcc-exception-3.1-faq.html.en).
3. **ACL/attr tienen una discrepancia en sus avisos.** La etiqueta dice
   `LGPL-2+`, pero el texto especifica versión 2.1 o posterior. Contrastar con
   las cabeceras fuente correspondientes; esta matriz no elige silenciosamente.
4. **Los enlaces de bibliotecas requieren revisar alcance.** La extensión
   `readline` de CPython registra `libreadline.so.8` como NEEDED. Comprobar que
   existen todas las fuentes de paquetes no resuelve por sí solo las condiciones
   de una distribución combinada.
5. **Fuentes tipográficas y UAPI requieren controles propios.** OFL contempla
   avisos/nombres de las fuentes; las excepciones UAPI se evalúan por cabecera,
   no cambian la licencia de todo el kernel. `rootfs/usr/include/linux/types.h`
   del SDK declara expresamente `GPL-2.0 WITH Linux-syscall-note`.
   [Guía OFL](https://openfontlicense.org/ofl-faq/),
   [reglas de licencia del kernel](https://www.kernel.org/doc/html/latest/process/license-rules.html).
6. **El acompañante también incluye gráficos.** Su carpeta
   `fpgalab/fpga_lab/assets/` conserva recursos de tarjetas, aunque el SDK en
   ejecución no tiene GUI Qt. `icebreaker_bitsy_v1/ATTRIBUTION.md` todavía indica
   que deben confirmarse los términos específicos del SVG. La atribución de
   `alhambra_ii` registra CC BY-SA 4.0 en el README y otra licencia en el LICENSE
   upstream. Confirmar alcance/términos o reducir deliberadamente entradas no
   necesarias y reconstruir con nueva procedencia/identidad. Ni atribuir ni
   incluir la licencia AGPL raíz resuelve automáticamente esa incertidumbre.
   Es un **bloqueo de publicación**.

## Registro de pendientes

Todos están abiertos para revisión del mantenedor: ninguno se cierra solo por
una construcción exitosa o por esta matriz. Al cerrar un punto se registra
evidencia, fecha y condiciones restantes; los términos ambiguos pueden requerir
asesoría especializada.

| ID | Resultado requerido antes de distribuir públicamente | Evidencia para cerrarlo |
| --- | --- | --- |
| P1 | Relacionar archivos reales del SDK y acompañante con sus términos; separar bibliotecas, herramientas, cabeceras, documentación y auxiliares solo fuente. | Evaluación de alcance con avisos/cabeceras; resolver discrepancia acl/attr y evitar licencias genéricas por paquete fuente. |
| P2 | Registrar alternativas permitidas, excepciones y condiciones no estándar relevantes. | Decisiones para Verilator/Perl/GMP/zstd y revisión de Sleepycat, OFL, PCRE2, Beerware/avisos ad-hoc; conservar licencias sin cambiarlas. |
| P3 | Revisar integridad y utilidad del código fuente correspondiente, no solo hashes. | Cobertura de fuentes/parches/reglas y comprobaciones documentadas de reconstrucción. Reensamblar binarios Ubuntu no equivale a reconstruir GCC/glibc/Verilator desde fuentes. |
| P4 | Revisar condiciones de bibliotecas/consumidores y rutas de reemplazo/reenlace donde sean necesarias. | Alcance de dependencias DB_File, readline, glibc/cargador y runtimes; condiciones LGPL aplicables, sin asumir exención System Library al redistribuir las propias bibliotecas. |
| P5 | Entregar avisos y condiciones de recursos en los paquetes finales. | Inspección de binarios/fuentes descargables: copyrights, licencias/NOTICE, fuentes tipográficas y atribuciones; no insinuar respaldo upstream. |
| P6 | Ofrecer acceso claro y duradero a las fuentes exactas junto al SDK descargable. | URLs publicadas de binarios/fuentes, checksums e instrucciones; responsable de disponibilidad/retención. Artefactos Actions de siete días y enlaces upstream genéricos no son la solución final. |
| P7 | Resolver licencias de adaptaciones/recursos FPGALab e identificar cambios donde corresponda. | Cambios de construcción/reubicación y fechas/avisos relevantes; licencia del proyecto conservada; resolver los SVG anteriores. |
| P8 | Elegir y congelar el artefacto publicable y registrar las decisiones de revisión. | Hashes exactos de binarios/fuentes, procedencia y checklist final del artefacto. Reconstruir/revisar si cambia el contenido; IDs inmutables. |

Para descargas por red hay que elegir la vía de entrega de fuentes aplicable,
sin agregar una «oferta escrita» genérica sin examinarla. La disponibilidad debe
seguir siendo adecuada para esa distribución.
[GPL, sección 6](https://www.gnu.org/licenses/gpl.en.html#section6),
[FAQ GNU sobre disponibilidad](https://www.gnu.org/licenses/gpl-faq.en.html#SourceAndBinaryOnDifferentSites).

## Límites y mantenimiento

El código de construcción/reubicación propio de FPGALab está cubierto por la
declaración AGPL-3.0-or-later del proyecto; los terceros conservan sus términos.
La matriz no asigna AGPL a componentes Ubuntu ni a todos los recursos del árbol.
No revisa las obligaciones de Python, PyQt/Qt, plugins y gráficos del ejecutable
PyInstaller: eso requiere revisar por separado ese paquete. Los Labs y diseños
HDL de estudiantes no se incluyen en el acompañante de fuentes.

Si cambian receta, versiones, entradas o artefactos elegidos, compara los nuevos
`source-packages.json` y `source-manifest.json`, actualiza filas/conteos/hashes
afectados y reabre los puntos aplicables. Este snapshot SDK2 no aprueba otras
construcciones. La [recolección de fuentes](../../../docs/es/development.md#fuentes-del-sdk-y-revision-de-redistribucion)
y el alojamiento del release no sustituyen las decisiones de revisión de licencias.
