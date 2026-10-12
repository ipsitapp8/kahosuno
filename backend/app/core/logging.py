import json
import logging
import re
import sys

_STD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

# Join tokens travel in the websocket URL (?token=...). A token is a password for a seat in a
# room, so it must never be written to a log, including uvicorn's own access log.
_TOKEN = re.compile(r"(token=)[^&\s\"']+")
_REDACTED = r"\1<redacted>"


class RedactTokens(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _TOKEN.sub(_REDACTED, record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                _TOKEN.sub(_REDACTED, a) if isinstance(a, str) else a for a in record.args
            )
        return True


_FILTER = RedactTokens()
_NOISY_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error", "httpx", "websockets")


def install_token_redaction() -> None:
    """Attach the filter to the root logger's handlers and to the loggers that print URLs.

    Safe to call more than once. Uvicorn reconfigures its loggers at startup, so the app calls
    this again from its lifespan, after uvicorn is done."""
    for name in ("", *_NOISY_LOGGERS):
        logger = logging.getLogger(name)
        if _FILTER not in logger.filters:
            logger.addFilter(_FILTER)
        for handler in logger.handlers:
            if _FILTER not in handler.filters:
                handler.addFilter(_FILTER)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, object] = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        out.update({k: v for k, v in record.__dict__.items() if k not in _STD})
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    install_token_redaction()
