# SDK3 component review — 2026-10-31

Scope: the SDK3 binary/source hashes recorded in [the matrix](sdk-licenses.en.md).
This is a limited evidence review, not approval of the whole SDK. Archives were
read without extracting or executing upstream code. The generated artifacts and
their original notices were not modified.

## Results and remaining conditions

| Check | Evidence/result | What remains open |
| --- | --- | --- |
| ACL library version-label ambiguity | The library source headers and `doc/COPYING.LGPL` support LGPL-2.1-or-later, consistent with the retained notice's prose rather than its abbreviated `LGPL-2+` label. | Complete file/build scope and LGPL distribution conditions; no blanket approval of the package. |
| attr library version-label ambiguity | The same LGPL-2.1-or-later wording is present in library headers and relevant added source files in the Ubuntu patch series. | File scope, header-only helpers and distribution conditions. |
| DB_File actually uses Berkeley DB | `readelf -d` on the shipped `DB_File.so` records `libdb-5.3.so` as NEEDED. | Source-access instructions and applicable combined-distribution conditions. |
| DB and direct Perl consumer sources | The companion includes exact `db5.3` and `perl` archives; Perl's archive contains `cpan/DB_File/DB_File.xs`, with its original copyright and Perl-license grant. | Completeness/rebuildability review beyond this module, permitted route selection and durable publication. |
| Notice/license retention | Selected binary notices are retained; `LGPL-2.1`, `GPL-1` and `Artistic` texts exist in the SDK's common-license directory. | End-to-end delivery to recipients and all other component/resource notices. |

Only the narrow ACL/attr **version-wording clarification** is resolved here.
P1–P8 remain open at SDK level. No upstream license notice is rewritten and no
license alternative is silently elected for Perl or Berkeley DB.

## ACL and attr source evidence

Exact source versions: `acl 2.3.2-1build1.1` and `attr 1:2.5.2-1ubuntu0.1`.
Relevant files inside their original archives include:

- `acl-2.3.2/libacl/acl_get_file.c`, `libacl/acl_init.c`,
  `libacl/perm_copy_fd.c`, `libacl/perm_copy_file.c` and `doc/COPYING.LGPL`.
- `attr-2.5.2/libattr/attr_copy_fd.c`, `libattr/attr_copy_file.c`,
  `include/attributes.h` and `doc/COPYING.LGPL`.

The `libacl`, `libattr`, `include` and `libmisc` source groups were inspected for
license headings. ACL also has short internal headers without independent
license prose; attr has configuration/translation helper headers of that kind.
Do not infer an independent license grant for those just from nearby files.

The Debian/Ubuntu archives contain the applied patch lists and patches. ACL's
series changes `tools/getfacl.c`, not these library license headings. attr's
series also adds headers and `libmisc` implementations: the reviewed new C
sources for xattrat/compatibility, walk-tree and openat2 carry LGPL-2.1-or-later
wording, as does its `compat-xattr-header.patch`. This is why an upstream-only
review is insufficient. The patch series and all sources remain in the companion.

For distributed library source and linked consumers, review the appropriate
LGPL conditions separately; the version clarification alone does not establish
source completeness or replacement/relink compliance.

## Berkeley DB / Perl evidence

Exact source versions: `db5.3 5.3.28+dfsg2-7` and `perl 5.38.2-3.2ubuntu0.6`.
The actual source `db-5.3.28/LICENSE` and binary `libdb5.3t64/copyright` retain
Sleepycat terms. The checked Perl `DB_File.xs` delegates to Perl's terms; the
retained Perl copyright specifically lists `cpan/DB_File/*` as GPL-1+ or Artistic.
Its source archive also contains `Copying` and `Artistic`.

The [Sleepycat license](https://opensource.org/license/sleepycat) requires
directions to the complete DB sources and accompanying software using it.
The [Perl licensing page](https://dev.perl.org/licenses/) describes the main
Perl license alternatives; the exact archived per-file notices control this
version and are retained. Availability of those archives is evidence of source
coverage, not a complete legal decision about every consumer or component.

Before publication, provide recipient-facing instructions pointing to the exact
DB and Perl source versions in the matching companion, plus its checksum and
durable download location. Do not substitute a generic upstream homepage or
state that sources are available at a URL that has not been published. No source
URL exists in the artifact evidence reviewed here; that part of P6 stays open.

## Reproducible evidence identities

Paths below are relative to `sdk-sources/packages/` or the binary SDK as labeled.
Original source archive SHA-256 values:

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

The SDK binary `rootfs/usr/lib/x86_64-linux-gnu/perl/5.38.2/auto/DB_File/DB_File.so`
has SHA-256 `f39e25fdff4d3956fec2be4f2d70bdcca52306bb4e328406d356ed506f330ee3`.
Use `readelf -d` on that file, not `ldd` on untrusted executables, to inspect the
recorded dependencies. Source-manifest checks cover the original/packaging
archives and the retained notice copies; they are separate from legal review.

## Verilator 5.020-1: source, relocation and license scope

The retained binary copyright and the checked source files `bin/verilator`,
`src/V3Ast.h`, `include/verilated.h` and `include/verilated.cpp` offer
`LGPL-3.0-only OR Artistic-2.0`. The original archive includes `LICENSE` (LGPL3)
and `Artistic` (Artistic2). The binary copyright contains the full Artistic2 text;
the SDK also retains common `LGPL-3` and `GPL-3` texts. Perl's older Artistic
license is not a substitute for Verilator's Artistic2.

The LGPL3 route requires reading GPL3 together with its LGPL3 permissions. The
alternative [Artistic2 terms](https://opensource.org/license/Artistic-2.0) distinguish
standard and modified distributions, source access and documentation of changes.
No final route is elected here. In particular, do not assume every modification
requires renaming: section 4 offers alternatives, while section 9 distinguishes
works that merely use or extend the package. Assess actual changes rather than
automatically treating all FPGALab launcher code as a Verilator derivative.

### Observed differences in this artifact

| Path in binary SDK | Observed content/change |
| --- | --- |
| `rootfs/usr/bin/verilator` | Matches upstream `bin/verilator` except its first-line interpreter (`#!/usr/bin/env perl` versus `#! /usr/bin/perl`). No other text difference. |
| `bin/verilator` | FPGALab shell launcher selects private Perl, PATH and `VERILATOR_ROOT`. |
| `rootfs/usr/bin/verilator_bin` | FPGALab loader wrapper dispatches to `verilator_bin.fpgalab-elf` with private library paths. |
| `rootfs/usr/bin/verilator_bin.fpgalab-elf` | Retained executable renamed by the assembler, not rebuilt from Verilator source during SDK assembly. No independent original `.deb` binary comparison was performed. |
| `rootfs/usr/share/verilator/bin/verilator_bin` | FPGALab forwarding script resolves the packaged executable path. |
| `rootfs/usr/share/verilator/include/` | All 52 installed files with a same-path upstream counterpart match byte for byte. Installed generated files need their own provenance; this is not a comparison of every packaged resource. |

Debian's source companion contains `debian/rules` and the single listed patch,
`pkgconfig.diff`, which removes a pkgconfig `libdir` field. Those are distribution
changes, distinct from FPGALab wrappers. Source and packaging inputs are present;
this does not establish reproducible compilation of the original executable.

### Embedded material is not uniformly dual-licensed

The installed include tree has 42 files declaring the dual SPDX expression,
six GTKWave files declaring MIT and two LZ4 files declaring BSD-2-Clause. Four
files have no SPDX line: generated `gtkwave/fst_config.h` and the three headers
`vltstd/svdpi.h`, `vltstd/vpi_user.h`, `vltstd/sv_vpi_user.h`. The latter refer to
IEEE/SystemVerilog interfaces. Missing SPDX does not prove absence of permission,
but the package-level wildcard notice alone is not a file-specific resolution.
Record the applicable upstream/standard header permission before closing P1/P2/P5;
do not strip headers or assign Artistic2/LGPL3 to them without that evidence.
Retain the MIT/BSD notices even if the current simulation does not enable tracing.

### Remaining publication work for Verilator

- Record the chosen permitted route for the relevant Verilator files, separately
  from embedded MIT/BSD/standard headers and independent FPGALab code.
- Deliver clear adaptation/change attribution for the paths above; preserve
  upstream notices and identify FPGALab packaging, not an upstream-endorsed build.
  The review record is not yet an artifact-delivered change notice.
- Publish exact original sources, packaging patch/rules and corresponding
  FPGALab adaptation inputs with functional recipient-facing download directions.
- Complete embedded-file scope and rebuild/source checks; retain P1/P2/P3/P5/P7
  open for this component rather than approving it from a passing ABI probe.

Source archive SHA-256:

```text
verilator_5.020.orig.tar.gz
3efb3a7c50c0bc0ea3989bf9219785b718cf9d056c643a9cef45570fbe46dafb
verilator_5.020-1.debian.tar.xz
e31f96dcff0bf32c90fd5f5d31e779be6a1a51c159e97f0d0443ae922537eaa1
```

The SDK's renamed executable has SHA-256
`25f33046f0055a6982c67cdc55081685a844abb50d044cfda087bd418db9be6c`.
Recording this review does not modify or require rebuilding the SDK; adding
recipient-facing notices later changes the artifact and requires new checksums.
