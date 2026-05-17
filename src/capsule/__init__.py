try:
    from importlib.metadata import version
    __version__ = version("capsule")
except Exception:
    try:
        from capsule._version import __version__
    except ImportError:
        __version__ = "unknown"
