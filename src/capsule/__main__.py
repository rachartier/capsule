from capsule.app import app
from capsule.config import setup_logging


def main() -> None:
    setup_logging()
    app()


if __name__ == "__main__":
    main()
