"""Tests for Android platform models."""

from pathlib import Path

from src.models import (
    AndroidSDKConfig,
    BuildLogInfo,
    Config,
    DelphiConfig,
    PathsConfig,
    Platform,
    SystemPaths,
)


class TestPlatformEnum:
    """Tests for Android entries in Platform enum."""

    def test_android_platform_exists(self):
        assert Platform.ANDROID.value == "Android"

    def test_android64_platform_exists(self):
        assert Platform.ANDROID64.value == "Android64"


class TestAndroidSDKConfig:
    """Tests for AndroidSDKConfig model."""

    def test_default_values(self):
        sdk = AndroidSDKConfig()
        assert sdk.compiler_rt is None
        assert sdk.libpaths == []
        assert sdk.linker is None

    def test_with_all_values(self):
        sdk = AndroidSDKConfig(
            compiler_rt=Path("C:/ndk/lib/libclang_rt.builtins-aarch64-android.a"),
            libpaths=[Path("C:/ndk/sysroot/usr/lib/aarch64-linux-android/23")],
            linker=Path("C:/ndk/bin/ld.lld.exe"),
        )
        assert sdk.compiler_rt is not None
        assert len(sdk.libpaths) == 1
        assert sdk.linker is not None

    def test_string_paths_converted(self):
        sdk = AndroidSDKConfig(
            compiler_rt="C:/ndk/lib/libclang_rt.a",
            libpaths=["C:/ndk/lib1", "C:/ndk/lib2"],
            linker="C:/ndk/bin/ld.lld.exe",
        )
        assert isinstance(sdk.compiler_rt, Path)
        assert all(isinstance(p, Path) for p in sdk.libpaths)
        assert isinstance(sdk.linker, Path)


class TestDelphiConfigAndroidCompilers:
    """Tests for Android compiler fields in DelphiConfig."""

    def test_default_none(self):
        cfg = DelphiConfig(version="23.0", root_path=Path("C:/Embarcadero"))
        assert cfg.compiler_android is None
        assert cfg.compiler_android64 is None

    def test_can_set_compilers(self):
        cfg = DelphiConfig(
            version="23.0",
            root_path=Path("C:/Embarcadero"),
            compiler_android=Path("C:/bin/dccaarm.exe"),
            compiler_android64=Path("C:/bin/dccaarm64.exe"),
        )
        assert cfg.compiler_android == Path("C:/bin/dccaarm.exe")
        assert cfg.compiler_android64 == Path("C:/bin/dccaarm64.exe")


class TestSystemPathsAndroid:
    """Tests for Android lib path fields in SystemPaths."""

    def test_android_lib_paths_default_none(self):
        sp = SystemPaths(
            rtl=Path("C:/rtl"),
            vcl=Path("C:/vcl"),
        )
        assert sp.lib_android_release is None
        assert sp.lib_android_debug is None
        assert sp.lib_android64_release is None
        assert sp.lib_android64_debug is None

    def test_can_set_android_lib_paths(self):
        sp = SystemPaths(
            rtl=Path("C:/rtl"),
            vcl=Path("C:/vcl"),
            lib_android_release=Path("C:/lib/Android/Release"),
            lib_android_debug=Path("C:/lib/Android/Debug"),
            lib_android64_release=Path("C:/lib/Android64/Release"),
            lib_android64_debug=Path("C:/lib/Android64/Debug"),
        )
        assert sp.lib_android_release is not None
        assert sp.lib_android64_debug is not None


class TestBuildLogInfoAndroidFields:
    """Tests for android_compiler_rt and android_linker fields in BuildLogInfo."""

    def _make_build_log_info(self, **kwargs):
        """Helper to create a BuildLogInfo with required fields plus overrides."""
        defaults = dict(
            compiler_path=Path("C:/bin/dccaarm64.exe"),
            delphi_version="23.0",
            platform=Platform.ANDROID64,
            build_config="Release",
            search_paths=[Path("C:/lib")],
        )
        defaults.update(kwargs)
        return BuildLogInfo(**defaults)

    def test_default_values_are_none(self):
        info = self._make_build_log_info()
        assert info.android_compiler_rt is None
        assert info.android_linker is None

    def test_can_set_with_path_values(self):
        info = self._make_build_log_info(
            android_compiler_rt=Path("C:/ndk/lib/libclang_rt.builtins-aarch64-android.a"),
            android_linker=Path("C:/ndk/bin/ld.lld.exe"),
        )
        assert info.android_compiler_rt == Path("C:/ndk/lib/libclang_rt.builtins-aarch64-android.a")
        assert info.android_linker == Path("C:/ndk/bin/ld.lld.exe")

    def test_string_paths_converted_to_path_objects(self):
        info = self._make_build_log_info(
            android_compiler_rt="C:/ndk/lib/libclang_rt.builtins-aarch64-android.a",
            android_linker="C:/ndk/bin/ld.lld.exe",
        )
        assert isinstance(info.android_compiler_rt, Path)
        assert isinstance(info.android_linker, Path)
        assert info.android_compiler_rt == Path("C:/ndk/lib/libclang_rt.builtins-aarch64-android.a")
        assert info.android_linker == Path("C:/ndk/bin/ld.lld.exe")


class TestConfigWithAndroidSDK:
    """Tests for Config model with android_sdk field."""

    def test_default_android_sdk(self):
        cfg = Config(
            delphi=DelphiConfig(version="23.0", root_path=Path("C:/Embarcadero")),
            paths=PathsConfig(system=SystemPaths(rtl=Path("C:/rtl"), vcl=Path("C:/vcl"))),
        )
        assert cfg.android_sdk is not None
        assert cfg.android_sdk.compiler_rt is None
