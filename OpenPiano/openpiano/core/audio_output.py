from __future__ import annotations

import ctypes
import sys

WINDOWS_OUTPUT_DRIVERS: tuple[str, ...] = ("wasapi", "dsound", "waveout")


def list_output_drivers(module=None, settings=None) -> list[str]:
    if sys.platform == "win32":
        preferred = list(WINDOWS_OUTPUT_DRIVERS)
        binder = getattr(module, 'cfunc', None)
        if settings is None or not callable(binder):
            return preferred
        try:
            callback_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p)
            available: set[str] = set()
            callback = callback_type(lambda _data, _name, option: available.add(option.decode('utf-8')))
            enumerate_options = binder('fluid_settings_foreach_option', None,
                ('settings', ctypes.c_void_p, 1), ('name', ctypes.c_char_p, 1),
                ('data', ctypes.c_void_p, 1), ('callback', callback_type, 1))
            enumerate_options(settings, b'audio.driver', None, callback)
            return [driver for driver in preferred if driver in available]
        except (AttributeError, TypeError, ValueError):
            return preferred
    return []


def default_output_driver() -> str:
    if sys.platform == "win32":
        return WINDOWS_OUTPUT_DRIVERS[0]
    return ""


def output_profiles(driver: str, *, native_callback: bool) -> list[dict[str, object]]:
    if driver == 'wasapi' and native_callback:
        return [dict(driver=driver, period_size=256, periods=3, sample_format='float'),
                dict(driver=driver, period_size=512, periods=4, sample_format='float'),
                dict(driver=driver, period_size=512, periods=8, sample_format='16bits')]
    return [dict(driver=driver, period_size=512, periods=8, sample_format='16bits')]
