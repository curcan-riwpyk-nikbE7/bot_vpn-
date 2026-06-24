import datetime
import time


def format_date(timestamp: float) -> str:
    return datetime.datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y %H:%M")


def days_left(expires_at: float) -> int:
    return max(0, int((expires_at - time.time()) / 86400))
