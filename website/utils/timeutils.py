import os
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app, has_app_context

DEFAULT_GYM_TIMEZONE = "Europe/Athens"


def gym_timezone_name():
    if has_app_context():
        return current_app.config.get("GYM_TIMEZONE", DEFAULT_GYM_TIMEZONE)
    return os.environ.get("GYM_TIMEZONE", DEFAULT_GYM_TIMEZONE)


def now_gym():
    """Naive datetime in the gym's local timezone."""
    return datetime.now(ZoneInfo(gym_timezone_name())).replace(tzinfo=None)
