import distutils
from distutils.core import setup, Extension

import sdss3tools
import os, numpy

FLI_module = Extension('fli_device',
    library_dirs = ['c/libfli-1.104'],
    libraries = ['fli'],
    sources = ['c/fli_device.c'],
    include_dirs = [numpy.get_include()],
    )

sdss3tools.setup(
    description = "Subaru PFI AGC actor.",
    ext_modules = [FLI_module],
    )

