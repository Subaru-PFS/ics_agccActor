from distutils.extension import Extension
from Cython.Distutils import build_ext
import sdss3tools
import os.path
import numpy

FLI_module = Extension(
    "fli_camera",
    ["python/agccActor/fli/fli_camera.pyx"],
    library_dirs = ["c/libfli-1.104"],
    libraries = ["fli"],
    include_dirs = ["c/libfli-1.104",
                    "python/agccActor/fli",
                    numpy.get_include()],
)

sdss3tools.setup(
    name = "agcc",
    description = "Subaru PFI AGCC actor.",
    cmdclass = {"build_ext": build_ext},
    ext_modules = [FLI_module]
)

