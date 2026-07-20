from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "INR": "₹", "GBP": "£"}


def currency_symbol(user):
    return CURRENCY_SYMBOLS.get(getattr(user, "currency", "EUR"), "€")


def symbol_for(currency_code):
    return CURRENCY_SYMBOLS.get(currency_code or "EUR", f"{currency_code or 'EUR'} ")


def user_zone(user):
    try:
        return ZoneInfo(getattr(user, "timezone", "Europe/Berlin"))
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")
