import logging
import logging.config
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog


class JsonlRotatingFileHandler(RotatingFileHandler):
    def __init__(self, filename: str, **kwargs: Any) -> None:
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        super().__init__(filename, encoding="utf-8", **kwargs)


def configure_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {
                "app_file": {
                    "()": JsonlRotatingFileHandler,
                    "filename": str(log_dir / "app.jsonl"),
                    "maxBytes": 10_000_000,
                    "backupCount": 5,
                },
                "protocol_file": {
                    "()": JsonlRotatingFileHandler,
                    "filename": str(log_dir / "protocol-events.jsonl"),
                    "maxBytes": 10_000_000,
                    "backupCount": 5,
                },
                "workers_file": {
                    "()": JsonlRotatingFileHandler,
                    "filename": str(log_dir / "workers.jsonl"),
                    "maxBytes": 10_000_000,
                    "backupCount": 5,
                },
                "errors_file": {
                    "()": JsonlRotatingFileHandler,
                    "filename": str(log_dir / "errors.jsonl"),
                    "maxBytes": 10_000_000,
                    "backupCount": 5,
                    "level": "ERROR",
                },
                "console": {"class": "logging.StreamHandler"},
            },
            "root": {"handlers": ["app_file", "errors_file", "console"], "level": level},
            "loggers": {
                "protocol.events": {"handlers": ["protocol_file"], "level": level, "propagate": True},
                "protocol.workers": {"handlers": ["workers_file"], "level": level, "propagate": True},
                "uvicorn.access": {"handlers": [], "level": "WARNING", "propagate": False},
            },
        }
    )
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "l2l3_protocol") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
