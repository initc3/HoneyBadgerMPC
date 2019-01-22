import sys

from setuptools import setup
from setuptools.command.test import test as test_command

try:
    from setuptools_rust import RustExtension
except ImportError:
    import subprocess

    errno = subprocess.call([sys.executable, "-m", "pip", "install", "setuptools-rust"])
    if errno:
        print("Please install setuptools-rust package")
        raise SystemExit(errno)
    else:
        from setuptools_rust import RustExtension


class PyTest(test_command):
    user_options = []

    def run(self):
        self.run_command("test_rust")

        import subprocess
        import sys

        subprocess.check_call([sys.executable, "-m", "pytest", "tests"])


setup_requires = ["setuptools-rust>=0.10.1", "wheel"]
install_requires = []
tests_require = install_requires + ["pytest", "pytest-benchmark"]

setup(
    name="pypairing",
    version="0.1.0",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Rust",
        "Operating System :: POSIX",
        "Operating System :: MacOS :: MacOS X",
    ],
    packages=["pypairing"],
    rust_extensions=[RustExtension("pypairing.pypairing", "Cargo.toml")],
    install_requires=install_requires,
    tests_require=tests_require,
    setup_requires=setup_requires,
    include_package_data=True,
    zip_safe=False,
    cmdclass=dict(test=PyTest),
)
