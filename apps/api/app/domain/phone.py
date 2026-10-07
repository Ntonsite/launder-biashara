import re

_TZ_MOBILE = re.compile(r"^\+255[67]\d{8}$")


def normalize_tz_phone(raw: str) -> str:
    """Accepts 0712 345 678, 712345678, 255712345678 or +255 712 345 678 and returns +255712345678."""
    digits = re.sub(r"[^\d+]", "", raw or "")
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("255"):
        digits = digits[3:]
    elif digits.startswith("0"):
        digits = digits[1:]
    normalized = "+255" + digits
    if not _TZ_MOBILE.match(normalized):
        raise ValueError("Enter a valid Tanzanian mobile number")
    return normalized


def mask_phone(phone: str) -> str:
    return phone[:7] + "•••" + phone[-3:] if len(phone) > 10 else "•••"
