from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("capsule")
except PackageNotFoundError:
    __version__ = "unknown"
