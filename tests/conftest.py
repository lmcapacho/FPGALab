"""Isolate persistent user data before test modules create Qt singletons."""

import hashlib
from pathlib import Path
import tempfile

import pytest


def pytest_configure(config):
    directory = tempfile.TemporaryDirectory(prefix="fpgalab-tests-user-")
    root = Path(directory.name)
    patch = pytest.MonkeyPatch()
    config.add_cleanup(directory.cleanup)
    config.add_cleanup(patch.undo)
    config._fpgalab_user_data = root
    home = root / "home"
    home.mkdir()
    # Also cover macOS data paths and legacy cache migration, which use
    # Path.home rather than XDG. Do not change the shell's HOME variable.
    patch.setattr(Path, "home", classmethod(lambda cls: home))
    for variable, child in (
        ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"), ("APPDATA", "roaming"),
        ("LOCALAPPDATA", "local"), ("FPGALAB_WORKSPACE", "workspace"),
        ("FPGALAB_PERIPHERALS_DIR", "peripherals"),
    ):
        location = root / child
        location.mkdir()
        patch.setenv(variable, str(location))
    patch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PyQt6 import QtCore
    settings_type = QtCore.QSettings

    class IsolatedSettings(settings_type):
        """Use real INI storage, never the user's native registry/plist/store.

        Changing XDG paths is insufficient on Windows/macOS, and Qt's explicit
        organization constructor ignores setDefaultFormat. Keep explicit file
        constructors for tmp_path fixtures; redirect all organization overloads.
        """

        def __init__(self, *args, **kwargs):
            if "fileName" in kwargs or (len(args) > 1 and isinstance(args[1], settings_type.Format)):
                super().__init__(*args, **kwargs)
            else:
                values = list(args)
                if values and isinstance(values[0], settings_type.Format):
                    values.pop(0)
                scope = values.pop(0) if values and isinstance(values[0], settings_type.Scope) else settings_type.Scope.UserScope
                organization = kwargs.get("organization", values.pop(0) if values and isinstance(values[0], str)
                                          else QtCore.QCoreApplication.organizationName())
                application = kwargs.get("application", values.pop(0) if values and isinstance(values[0], str)
                                         else QtCore.QCoreApplication.applicationName())
                parent = kwargs.get("parent", values[0] if values else None)
                identity = repr((scope.value, organization, application)).encode()
                filename = root / "settings" / (hashlib.sha256(identity).hexdigest() + ".ini")
                super().__init__(str(filename), settings_type.Format.IniFormat, parent)
            self.setFallbacksEnabled(False)

    patch.setattr(QtCore, "QSettings", IsolatedSettings)


@pytest.fixture(scope="session")
def isolated_user_data(request):
    return request.config._fpgalab_user_data
