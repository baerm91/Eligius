"""Hilfsfunktionen für Datei-Importe."""
from decimal import Decimal, InvalidOperation


def parse_object_id(value):
    """Objekt-ID aus einer Import-Zelle.

    Excel liefert ganze Zahlen oft als Float ("12.0"); das ist erlaubt.
    "12.5" o. Ä. wird abgelehnt, statt still Objekt 12 zuzuweisen.
    """
    text = str(value).strip()
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f'Ungültige Objekt-ID: {value!r}') from None
    if not number.is_finite() or number != number.to_integral_value() or number < 1:
        raise ValueError(f'Ungültige Objekt-ID: {value!r}')
    return int(number)
