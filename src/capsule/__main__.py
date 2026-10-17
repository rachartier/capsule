"""Entry point of the capsule CLI."""

from capsule.app import app
from capsule.config import setup_logging


def main() -> None:
    """Sets up logging and runs the capsule CLI."""
    setup_logging()
    app()


if __name__ == "__main__":
    main()
