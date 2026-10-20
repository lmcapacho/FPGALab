"""Required Linux Qt runtime libraries: fail builds instead of shipping gaps."""

import sys


XCB_LIBRARIES = (
    "libxcb-cursor.so.0", "libxcb-icccm.so.4", "libxcb-image.so.0",
    "libxcb-keysyms.so.1", "libxcb-render-util.so.0", "libxcb-util.so.1",
    "libxcb-xkb.so.1", "libxkbcommon-x11.so.0",
)


def collect_linux_qt_runtime(resolve_library, *, platform_name=sys.platform):
    if not platform_name.startswith("linux"):
        return []
    binaries, missing = [], []
    for name in XCB_LIBRARIES:
        path = resolve_library(name)
        if path:
            binaries.append((str(path), "."))
        else:
            missing.append(name)
    if missing:
        raise RuntimeError(
            "Missing Linux Qt/XCB build dependencies: " + ", ".join(missing) +
            ". On Ubuntu install libxcb-cursor0 libxcb-icccm4 libxcb-image0 "
            "libxcb-keysyms1 libxcb-render-util0 libxcb-util1 libxcb-xkb1 libxkbcommon-x11-0. "
            "These libraries must be collected into the portable package."
        )
    return binaries
