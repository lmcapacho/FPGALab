"""Even forgotten settings injection must never reach real user preferences."""

from pathlib import Path

from PyQt6.QtCore import QSettings


def test_default_and_native_settings_stay_in_test_storage(isolated_user_data, tmp_path):
    assert Path.home() == isolated_user_data / "home"
    for args in ((), ("FPGALab", "FPGALab"),
                 (QSettings.Scope.SystemScope, "FPGALab", "FPGALab"),
                 (QSettings.Format.NativeFormat, QSettings.Scope.UserScope, "FPGALab", "FPGALab")):
        store = QSettings(*args)
        assert store.format() == QSettings.Format.IniFormat
        assert Path(store.fileName()).is_relative_to(isolated_user_data)
        assert not store.fallbacksEnabled()
        store.setValue("isolation/probe", "fixture")
        store.sync()
        assert store.status() == QSettings.Status.NoError
        assert Path(store.fileName()).is_file()
    explicit = QSettings(str(tmp_path / "explicit.ini"), QSettings.Format.IniFormat)
    assert Path(explicit.fileName()) == tmp_path / "explicit.ini"
