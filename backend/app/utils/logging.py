from loguru import logger
import sys
from app.core.config import get_settings


def setup_logging():
    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level.upper(), backtrace=True, diagnose=False, enqueue=True)
    return logger
