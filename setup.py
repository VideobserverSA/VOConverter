__author__ = 'Rui'

from cx_Freeze import setup, Executable

setup(
    name="Vo Converter",
    version="0.1",
    description="Vo Converter Util",
    options = {"build_exe": {"include_files": {"version.ini", "silence.wav", "icon.ico", "ffmpeg.exe", "ffprobe.exe",
                                               "msvcr100.dll", "test.conf"}}},
    executables=[Executable("main.py", base="Win32GUI", icon="icon.ico",
                            targetName="voconverter.exe")]
    )
