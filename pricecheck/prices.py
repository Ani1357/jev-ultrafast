"""Deterministic Dutch price, size, and promotion arithmetic. No model calls."""

import re
import unicodedata

UNITS = {
    "kg": ("kg", 1),
    "kilo": ("kg", 1),
    "g": ("kg", 0.001),
    "gr": ("kg", 0.001),
    "gram": ("kg", 0.001),
    "l": ("l", 1),
    "lt": ("l", 1),
    "liter": ("l", 1),
    "cl": ("l", 0.01),
    "ml": ("l", 0.001),
    "st": ("stuk", 1),
    "stuk": ("stuk", 1),
    "stuks": ("stuk", 1),
}
SIZE = re.compile(
    r"(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*(" + "|".join(sorted(UNITS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
NUMBER = r"\d+(?:[.,]\d{1,2})?"


def parse_price(text):
    """'€ 2,49', '2.49', '2,-', '1.299,00', '2 49' -> euros as float, or None."""
    if not isinstance(text, str):
        return None
    s = re.sub(r"(?i)€|eur(o)?", "", text).strip()
    s = re.sub(r"[,.]\s*-+$", "", s)
    if m := re.fullmatch(r"(\d+)\s+(\d{2})", s):
        return round(int(m[1]) + int(m[2]) / 100, 2)
    if not re.fullmatch(r"\d[\d.,]*", s):
        return None
    last = max(s.rfind(","), s.rfind("."))
    if last == -1:
        return float(s)
    whole, fraction = s[:last], s[last + 1 :]
    if len(fraction) == 3:
        # "1.299" uses a thousands separator, not a decimal one.
        return float(re.sub(r"[.,]", "", s))
    if len(fraction) not in (1, 2):
        return None
    whole = re.sub(r"[.,]", "", whole)
    return round(float(f"{whole or 0}.{fraction}"), 2)


def parse_size(text):
    """'800 g' -> (0.8, 'kg'); '6 x 200 ml' -> (1.2, 'l'); '4 stuks' -> (4, 'stuk')."""
    if not isinstance(text, str):
        return None
    m = SIZE.search(text)
    if not m:
        return None
    count = int(m[1]) if m[1] else 1
    base, factor = UNITS[m[3].lower()]
    amount = float(m[2].replace(",", ".")) * count * factor
    return (round(amount, 6), base) if amount > 0 else None


def parse_promo(text, price):
    """Return (promo type, effective price for one item when the promotion is used)."""
    if not text or price is None:
        return None, price
    t = text.lower().replace("€", " ").replace(" ", " ")
    if m := re.search(r"(\d+)\s*\+\s*(\d+)", t):
        paid, free = int(m[1]), int(m[2])
        return f"{paid}+{free} gratis", price * paid / (paid + free)
    if m := re.search(r"(\d+)\s*halen,?\s*(\d+)\s*betalen", t):
        take, pay = int(m[1]), int(m[2])
        return f"{take} halen {pay} betalen", price * pay / take
    if re.search(r"(2e|tweede)\s*(artikel\s*)?gratis", t):
        return "1+1 gratis", price / 2
    if re.search(r"(2e|tweede)\s*(artikel\s*)?halve\s*prijs", t):
        return "2e halve prijs", price * 0.75
    if m := re.search(r"(2e|tweede)\s*(artikel\s*)?(\d+)\s*%", t):
        return f"2e {m[3]}% korting", price * (2 - int(m[3]) / 100) / 2
    if m := re.search(rf"(\d+)\s*(?:voor|for)\s*({NUMBER})", t):
        count, total = int(m[1]), parse_price(m[2])
        if count > 1 and total:
            return f"{count} voor €{total:.2f}", total / count
    # Percentage and "bonus" labels are assumed to be reflected in the shown price already.
    return text.strip()[:60], price


def normalize(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z]+|\d+", text)


def matches_query(query, title):
    """Every query word and number must appear as a whole token of the product title."""
    wanted, have = normalize(query), set(normalize(title))
    return bool(wanted) and all(token in have for token in wanted)


def price_in_text(price, text):
    """Grounding: the price must be written on the page (2,49 / 2.49 / 2 49 / 2,-)."""
    euros, cents = int(price), round(price * 100) % 100
    if cents:
        pattern = rf"(?<![\d.,]){euros}\s*[.,]?\s*{cents:02d}"
    else:
        # A bare integer is too common to count; whole euros need "€" or ",00"/",-".
        pattern = rf"(?:€\s*{euros}(?:\s*[.,]\s*(?:00|-))?|(?<![\d.,]){euros}\s*[.,]\s*(?:00|-))"
    return re.search(pattern + r"(?![.,]?\d)", text or "") is not None


def title_in_text(title, text):
    words = [w for w in normalize(title) if len(w) > 1 or w.isdigit()]
    have = set(normalize(text))
    return bool(words) and sum(w in have for w in words) / len(words) >= 0.6


def unit_label(base):
    return {"kg": "€/kg", "l": "€/l", "stuk": "€/stuk"}[base]
