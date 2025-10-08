from loguru import logger
import sys, os, pathlib
from app.core.config import get_settings


def setup_logging():
    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level.upper(), backtrace=True, diagnose=False, enqueue=True)
    # File sink for persistent pipeline diagnostics
    try:
        log_dir = pathlib.Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(str(log_dir / "pipeline.log"), level=settings.log_level.upper(), rotation="5 MB", retention=5, enqueue=True, backtrace=False, diagnose=False)
    except Exception:
        pass
    return logger
