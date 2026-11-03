# SDK license matrix and open items

Status: **initial notice review; not approved for public redistribution**.
Reviewed snapshot: **2026-10-25**, `ubuntu24.04-x86_64-sdk2`, Ubuntu snapshot
`20261001T000000Z`. This is a maintainer evidence/checklist document, not legal
advice or a certificate of compliance. It does not change any component's license.

## SDK3 technical follow-up — 2026-10-31

The reduced-input SDK3 build passed relocation, the offline clean-Ubuntu native
ABI probe, repeated Make builds and source/provenance verification. Independent
verification of the generated companions also passed their archive and manifest
SHA-256 checks. Its 100 binary packages match the 54 source/version groups and
counts in the matrix below. It preserves **28 local build inputs**, plus the
provenance record, with no desktop artwork or board/peripheral packages.

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

This closes the technical source-selection check for these SDK3 artifacts only,
not P1–P8 or legal approval. A clean-desktop GUI test of SDK3 is still pending.
The original SDK2 files are no longer locally available for a byte-for-byte
notice comparison; matching package identities alone does not close that review.
The matrix remains an initial license assessment with the SDK2 evidence below;
SDK3 needs its own file-level licensing decisions and publication checks. Artwork
licensing still applies to SDK2's source companion and the desktop application,
but those graphics are absent from this SDK3 companion. Existing SDK2 hashes and
findings are retained rather than retrospectively changing its recorded scope.

## SDK2 scope and evidence

The observed SDK contains **100 inventoried binary packages from 54 source/version
pairs**. The source companion includes their original Ubuntu source archives,
packaging/patches, notices and **171 local FPGALab input files**. The collection
and checksums were verified; applicability to every shipped file and completion
of all licensing obligations are **not** established by that verification.

The reviewed archives are identified by SHA-256, not just their SDK ID:

```text
fpgalab-linux-sdk.tar.gz
3e0408750d0ec0f8b580eabf6eb1de5e12aba69dee1e23be885bb9ab05fce709
fpgalab-linux-sdk-sources.tar.gz
a4d90262b3c7dea35fef1e9330446189df9e4ff0155e27c03e24d0fe2fc0308a
source-manifest.json
9698844b59443e487f342339b80ad6186c2a44494cba70510bab8a4af3dada75
```

Evidence locations inside those archives:

| Evidence | Location and meaning |
| --- | --- |
| Binary/source relationship | SDK `source-packages.json`: each binary package's exact source/version and copyright path. |
| Third-party notices | SDK `rootfs/usr/share/doc/<binary>/copyright`; companion `notices/<binary>/copyright`. Inspect each binary's notice, not an assumed source-package path. |
| Shared license texts | SDK `rootfs/usr/share/common-licenses/`; companion `common-licenses/`. Other terms may be embedded in copyright files or upstream sources. |
| Source files and checksums | Companion `source-manifest.json`, `packages/<source>/<version>/apt-source-record.txt` and original `.dsc`/archives. Epochs use `_` in directory names only. |
| FPGALab adaptations | Companion `fpgalab/`, including build/relocation scripts, recipe, `LICENSE`, `NOTICE` and `provenance.json`; SDK `FPGALAB-LICENSE.txt` and `FPGALAB-NOTICE.txt`. |
| Archive relationship | Build output `source-bundle.json`; SDK `toolchain.json` links the source companion by digest. |

This test build records Git revision `cf790d51154143da03d34a5d49e396d00054342e`
with `dirty: true`. The preserved input hashes identify its actual contents;
the revision alone is **not** its complete source identity. A new archive or
changed inputs require a new evidence review, even if the version label matches.
Do not silently replace a published SDK under the same ID.

## How to read the matrix

The newer SDK3 recipe restricts the build context and local source companion to
compiler/probe dependencies, native sources, packaging scripts and notices;
desktop artwork is excluded. This is a source-selection change, not a review or
replacement of the SDK2 archives identified above. SDK3's technical build is
recorded above; it still needs artifact-specific license review. The SVG finding below
remains applicable to the archived SDK2 companion and the desktop package;
do not mark its licensing resolved merely because SDK3 excludes it.

Each row groups **source/version**, not a single executable; the count is the
number of binary packages in the inventory. It does not assert that all upstream
files were copied into the SDK. License summaries are an initial reading of the
retained notices, **not package-wide SPDX expressions or final license elections**.
For example, GPL terms for packaging/tests do not automatically describe a
library shipped from that package. [Debian's copyright format](https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/)
associates license terms with file groups.

`+` means “or later” where the notice grants it. Alternatives and exceptions
apply only to files whose notices offer them. **Every row remains open** for
the applicable cross-cutting items below; its last column identifies a specific
check, not permission to redistribute or a complete list of obligations.

| Source | Exact source version | Binaries | Initial license reading | Specific open check |
| --- | --- | ---: | --- | --- |
| `acl` | `2.3.2-1build1.1` | 1 | GPL-2+; library notice labeled LGPL-2+, text says LGPL-2.1+ | Resolve label/text discrepancy against original library headers (P1/P4). |
| `attr` | `1:2.5.2-1ubuntu0.1` | 1 | GPL-2+; library notice labeled LGPL-2+, text says LGPL-2.1+ | Same version discrepancy; distinguish library from utilities (P1/P4). |
| `base-files` | `13ubuntu10.5` | 1 | GPL-2+ package material; license documents retain their own terms | Separate package scripts, license texts and distribution identity/branding (P1/P5). |
| `bash` | `5.2.21-2ubuntu4` | 1 | GPL-3+; additional file terms and GFDL documentation | Identify included support files/docs; preserve applicable notices (P1/P3/P5). |
| `binutils` | `2.42-4ubuntu2.10` | 8 | GPL-3+ with component-specific library/exception terms | Review assembler/linker, libraries and plugins separately (P1/P4). |
| `bzip2` | `1.0.8-5.1ubuntu0.1` | 1 | bzip2 BSD variant; GPL-2 packaging | Preserve actual bzip2 conditions; do not label the library by packaging alone (P1/P5). |
| `coreutils` | `9.4-3ubuntu6.3` | 1 | GPL-3+; ISC/BSD contributions and GFDL docs | Map auxiliary contributions and retained documentation (P1/P3/P5). |
| `dash` | `0.5.12-6ubuntu5` | 1 | BSD-3-Clause; public-domain/GPL-2+ auxiliary files | Check installed shell versus source-only build helpers (P1/P5). |
| `db5.3` | `5.3.28+dfsg2-7` | 1 | Sleepycat and BSD-3-Clause; other bindings have separate terms | High priority: accompanying-software source directions, including Perl DB_File (P2/P6). |
| `debconf` | `1.5.86ubuntu1` | 1 | BSD-2-Clause | Preserve copyright, conditions and disclaimer for included scripts/modules (P1/P5). |
| `debianutils` | `5.17build1` | 1 | GPL-2+; SMAIL-GPL and public-domain files | Inspect savelog's distinct terms and which utilities are shipped (P1/P2). |
| `dpkg` | `1.22.6ubuntu6.6` | 1 | GPL-2+; public-domain components | Map tools and helper files to corresponding source/notice (P1/P3). |
| `expat` | `2.6.1-2ubuntu0.6` | 1 | MIT | Check copyright/license/disclaimer delivery for the library (P5). |
| `findutils` | `4.9.0-5build1` | 1 | GPL-3+ tools; LGPL/BSD/ISC helpers, exceptions, GFDL docs | Do not confuse the documentation's default stanza with the executables (P1/P3). |
| `fonts-font-awesome` | `5.0.10+really4.7.0~dfsg-4.1` | 1 | OFL-1.1 fonts; Expat CSS; GPL-3+ packaging | Review font naming and license delivery separately from CSS/packaging (P2/P5). |
| `fonts-lato` | `2.015-1` | 1 | OFL-1.1 fonts; GPL-2+ packaging | Check reserved names if modified; retain font copyright/OFL (P2/P5). |
| `gcc-13` | `13.3.0-6ubuntu2~24.04.1` | 9 | GPL-3+ compiler; selected runtimes have GCC Runtime Library Exception 3.1 | Distinguish compiler, headers, plugins and applicable runtime exceptions (P1/P3/P4). |
| `gcc-14` | `14.2.0-4ubuntu2~24.04.1` | 13 | GPL-3+ family; runtime exceptions and component-specific terms | This group supplies runtimes, not proof of a second installed compiler; inspect each library (P1/P4). |
| `gcc-defaults` | `1.214ubuntu1` | 6 | GPL-2+ scripts; additional manual-page terms | Distinguish selectors/symlinks from GCC's compiler/runtime licenses (P1/P5). |
| `gdbm` | `1.23-5.1build1` | 2 | GPL-3+ library; GPL-2+ tests, GFDL docs | Review consumers and included library/source scope (P1/P4). |
| `glibc` | `2.39-0ubuntu8.9` | 3 | Mostly LGPL-2.1+; GPL-2+ utilities and other contributions | High priority: loader, libraries, headers and replacement/rebuild conditions (P1/P3/P4). |
| `gmp` | `2:6.3.0+dfsg-2ubuntu6.1` | 1 | GPL-2+ OR LGPL-3+ for main files; other demo terms | Record a permitted license choice for applicable library files (P1/P2/P4). |
| `isl` | `0.26-3build1.1` | 1 | Mainly MIT; BSD and LGPL-2.1+ files | Identify compiled qsort/imath contributions, not just top-level license (P1/P4). |
| `jansson` | `2.14-2build2` | 1 | Expat/MIT-style | Preserve actual copyright and permission notice (P5). |
| `libffi` | `3.4.6-1build1` | 1 | Expat library; auxiliary GPL/MPL alternatives and public-domain files | Separate library code from tests/platform/build helpers (P1/P5). |
| `libmd` | `1.1.0-2build1.1` | 1 | BSD variants, ISC, Beerware and public-domain contributions | Retain algorithm-specific notices; do not replace with generic BSD text (P1/P2/P5). |
| `libselinux` | `3.5-2ubuntu2.1` | 1 | Library declared public-domain; GPL-2 utility/packaging files | Do not classify libselinux1 as GPL solely from utility notices (P1/P5). |
| `libxcrypt` | `1:4.4.36-4build1` | 2 | Overall LGPL-2.1+; multiple individual file licenses | Review crypto implementation contributions, headers and library scope (P1/P4). |
| `libzstd` | `1.5.5+dfsg2-2build1.1` | 1 | BSD-3-Clause OR GPL-2 for main files; other contributions | Record applicable choice and separate embedded contributions (P1/P2/P5). |
| `linux` | `6.8.0-146.146` | 1 | GPL-2 kernel notice; UAPI headers may carry Linux-syscall-note/other terms | Only linux-libc-dev is inventoried; inspect each exported header's SPDX notice (P1/P4). |
| `make-dfsg` | `4.3-4.1build2` | 1 | GPL-3+ | Rebuild/source directions and SDK make launcher modifications (P3/P6/P7). |
| `mawk` | `1.3.4.20240123-1build1` | 1 | GPL-2.0-only; X11 helper and CC-BY-3.0 icon | Preserve exact GPL version; check whether icon is shipped (P1/P5). |
| `media-types` | `10.1.0` | 1 | Public information/public-domain statement; ad-hoc notice | Retain the actual statement rather than inventing an SPDX grant (P2/P5). |
| `mpclib3` | `1.3.1-1build1.1` | 1 | LGPL-3+ library; public-domain packaging | Library source/replacement conditions (P3/P4). |
| `mpfr4` | `4.2.1-1build1.1` | 1 | LGPL-3+ library; GFDL-1.2+ documentation | Separate library and documentation terms (P1/P4/P5). |
| `ncurses` | `6.4+20240113-1ubuntu2.2` | 2 | MIT/X11-style; BSD-3-Clause files | Preserve component-specific copyright/disclaimer text (P1/P5). |
| `netbase` | `6.4` | 1 | GPL-2 notice | Determine which data/docs were copied; /etc is excluded by the builder (P1). |
| `node-jquery` | `3.6.1+dfsg+~3.5.14-1` | 1 | Expat | Retain JS notices and confirm original/minified source coverage (P1/P5). |
| `openssl` | `3.0.13-0ubuntu3.16` | 1 | Apache-2.0 main files; separate Perl helper terms | Check applicable upstream NOTICE material and actual library scope (P1/P5). |
| `pcre2` | `10.42-4ubuntu2.1` | 1 | Cambridge BSD-3-clause variant with binary-library-like exception; other terms | Read actual exception; retaining notices is not a blanket waiver (P1/P2/P5). |
| `perl` | `5.38.2-3.2ubuntu0.6` | 4 | GPL-1+ OR Perl Artistic for main code; many module-specific licenses | High priority: license choices, bundled modules, DB_File and modified launcher (P1/P2/P4/P7). |
| `python3-defaults` | `3.12.3-0ubuntu2.1` | 3 | Python license history/packaging notice | Inspect launcher/selector package separately from CPython modules (P1/P5). |
| `python3.12` | `3.12.3-1ubuntu0.17` | 4 | PSF/Python historical license chain plus incorporated software | Check extension-library links, bundled notices and private launcher (P1/P4/P7). |
| `readline` | `8.2-4build1` | 2 | GPL-3+; GFDL docs and other contributions | CPython readline extension links this library; review combined distribution scope (P1/P4). |
| `rpcsvc-proto` | `1.4.2-0ubuntu7` | 1 | BSD-3-Clause/permissive material; build-helper exceptions | Identify shipped rpcgen inputs/output terms and build-only files (P1/P5). |
| `sphinx` | `7.2.6-6` | 1 | BSD-2-Clause; BSD-3-Clause search assets | Only libjs-sphinxdoc is inventoried; check JS asset notices/source (P1/P5). |
| `sphinx-rtd-theme` | `2.0.0+dfsg-1` | 1 | Expat; BSD-2-Clause search template | Match theme assets and embedded frontend notices (P1/P5). |
| `sqlite3` | `3.45.1-1ubuntu2.8` | 1 | Public-domain SQLite; GPL-2+ packaging | Do not transfer packaging license to libsqlite3-0; retain source provenance (P1/P5). |
| `tar` | `1.35+dfsg-3ubuntu0.4` | 1 | GPL-3+; LGPL/helpers and parser exceptions | Map included tools, helpers and retained docs (P1/P3). |
| `tzdata` | `2026c-0ubuntu0.24.04.1` | 1 | Mostly public-domain data; ICU material | Zoneinfo is excluded by builder; identify remaining distributed files (P1/P5). |
| `underscore` | `1.13.4~dfsg+~1.11.4-3` | 1 | Expat JS; BSD docs; GPL-3+ packaging | Separate installed JS license from packaging and check source assets (P1/P5). |
| `verilator` | `5.020-1` | 1 | Artistic-2.0 OR LGPL-3 | High priority: choose permitted route and document changed launcher/resources (P1/P2/P7). |
| `xz-utils` | `5.6.1+really5.4.5-1ubuntu0.3` | 1 | liblzma mainly public-domain; GPL/LGPL tools/helpers and other terms | Inspect this exact release's liblzma files; do not label the library by all xz tools (P1/P2). |
| `zlib` | `1:1.3.dfsg-3.1ubuntu2.2` | 1 | zlib license | Retain notices and accurately identify any changed source (P5/P7). |

## Concrete findings and priority

SDK3 follow-up: [the component review](sdk3-review.en.md) clarifies the ACL/attr
version wording against source headers and patches, and confirms DB_File source
coverage. It also records Verilator's observed relocation changes and embedded
MIT/BSD/standard-header scope. This is limited progress, not closure of SDK-wide
items. Historical SDK2 observations below are retained.

1. **Berkeley DB is used, not merely listed.** `readelf -d` on the SDK's
   `rootfs/usr/lib/x86_64-linux-gnu/perl/5.38.2/auto/DB_File/DB_File.so` records
   `libdb-5.3.so` as NEEDED. Sleepycat includes source-access conditions for DB
   and accompanying software that uses it. Review the Perl consumer and source
   directions explicitly; the DB archive alone is not the whole check.
   [Sleepycat license](https://opensource.org/license/sleepycat).
2. **GCC runtime exceptions are file-specific.** They do not remove source
   obligations when distributing the library itself. Separate that case from
   merely compiling a student's design. [GNU's runtime-exception FAQ](https://www.gnu.org/licenses/gcc-exception-3.1-faq.html.en).
3. **ACL/attr notices have a version-label discrepancy.** The retained stanzas
   say `LGPL-2+`, while their prose specifies version 2.1 or later. Resolve this
   against corresponding source headers; this matrix does not silently choose.
4. **Library links need scope review.** The CPython `readline` extension records
   `libreadline.so.8` as NEEDED. Verifying that all package sources exist does not
   by itself settle the conditions for combined distributions.
5. **Fonts and UAPI headers need their own checks.** OFL conditions concern
   font notices/names; kernel UAPI exceptions are per-header, not a relicensing
   of the entire kernel. The SDK's `rootfs/usr/include/linux/types.h` explicitly
   carries `GPL-2.0 WITH Linux-syscall-note`.
   [OFL guidance](https://openfontlicense.org/ofl-faq/),
   [kernel licensing rules](https://www.kernel.org/doc/html/latest/process/license-rules.html).
6. **The source companion also contains artwork.** Its `fpgalab/fpga_lab/assets/`
   includes board resources, even though the SDK runtime has no Qt GUI.
   `icebreaker_bitsy_v1/ATTRIBUTION.md` still says the SVG's specific redistribution
   terms need confirmation. `alhambra_ii/ATTRIBUTION.md` records a CC BY-SA 4.0
   README declaration alongside a different repository LICENSE. Confirm resource
   scope/terms, or deliberately reduce unneeded companion inputs and rebuild with
   new provenance/identity. Neither attribution nor the AGPL root license resolves
   that uncertainty automatically. This is a **publication blocker**.

## Open-item register

All items below are open for maintainer review; none is closed by a passing
build or this matrix. A reviewer should record evidence, date and remaining
conditions when closing an item, and seek specialist advice for unresolved terms.

| ID | Required outcome before public distribution | Evidence needed to close |
| --- | --- | --- |
| P1 | Map actual SDK and source-companion files to applicable terms, distinguishing libraries, tools, headers, documentation and source-only helpers. | File/component scope assessment with corresponding notices/headers; resolve acl/attr discrepancy and avoid blanket source-package labels. |
| P2 | Record permitted alternatives, exceptions and nonstandard conditions where relevant. | Decisions for Verilator/Perl/GMP/zstd and review of Sleepycat, OFL, PCRE2, Beerware/ad-hoc terms; retain unchanged license texts. |
| P3 | Review completeness/usability of Corresponding Source, beyond archive hashes. | Original source/patch/build-rule coverage plus documented third-party rebuild checks. Reassembling Ubuntu binaries is not rebuilding GCC/glibc/Verilator from source. |
| P4 | Review bundled library/consumer conditions and replacement/relink paths where required. | Dependency scope for DB_File, readline, glibc/loader and runtimes; check applicable LGPL obligations rather than assuming a System Library exemption for redistributed libraries. |
| P5 | Ensure final packages deliver all required notices and resource-specific terms. | Inspect downloadable binaries and sources for retained copyrights, license/NOTICE material, font conditions and resource attribution; do not imply upstream endorsement. |
| P6 | Provide durable, clear access to matching sources alongside the downloadable SDK. | Published binary/source URLs, checksums and user-facing directions; availability/retention ownership. Seven-day Actions artifacts and generic upstream links are not the final arrangement. |
| P7 | Resolve FPGALab adaptation/resource licensing and mark modifications where required. | Explicit build/relocation changes and relevant dates/notices; project license retained; resolve the board SVG issues above. |
| P8 | Select and freeze the actual publishable artifact and record review decisions. | Exact binary/source hashes, input provenance and final checklist for that artifact. Rebuild/review if contents change; keep SDK IDs immutable. |

For network distribution, select the applicable source-delivery route rather
than adding an unexamined “written offer” boilerplate. Source availability must
remain adequate for the distribution arrangement. [GPL section 6](https://www.gnu.org/licenses/gpl.en.html#section6),
[GNU source-availability FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#SourceAndBinaryOnDifferentSites).

## Boundaries and maintenance

FPGALab-authored build/relocation code is covered by the project's
AGPL-3.0-or-later declaration; third-party material retains its own terms. This
matrix does not assign that license to Ubuntu components or all assets in the
source tree. It does not review the PyInstaller application bundle's Python,
PyQt/Qt, plugins or artwork obligations; that is a separate package review.
Students' Labs and HDL designs are not included in the SDK source companion.

When the recipe, package versions, source inputs or selected artifacts change,
compare the new `source-packages.json` and `source-manifest.json`, refresh every
affected row/count/hash and reopen applicable items. Do not treat this SDK2
snapshot as approval of another build. Keep [source collection](../../../docs/en/development.md#sdk-sources-and-redistribution-review)
and actual release hosting separate from license-review decisions.
