import logging
from pythonjsonlogger import jsonlogger


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if root.handlers:
        return

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
