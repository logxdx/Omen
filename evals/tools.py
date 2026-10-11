"""Deterministic fake tools for evals.

They measure how well the *model + harness* call tools, independent of real
services (no network, no flaky data). Real skills get their own tasks later.
"""

from __future__ import annotations

from omen.core import tool

WEATHER = {
    "paris": {"temp_c": 18, "condition": "light rain"},
    "tokyo": {"temp_c": 24, "condition": "sunny"},
    "mumbai": {"temp_c": 31, "condition": "humid, cloudy"},
}

CONTACTS = {
    "priya": {"name": "Priya Sharma", "email": "priya.sharma@example.com", "phone": "+91 98200 11223"},
    "tom": {"name": "Tom Becker", "email": "tom@becker.dev", "phone": "+49 151 2345 6789"},
}

NOTES = [
    "Dentist appointment moved to Friday 4pm.",
    "Wi-Fi password for the cabin: pinecone-42.",
    "Book club is reading 'The Left Hand of Darkness' this month.",
]

RATES_TO_USD = {"USD": 1.0, "EUR": 1.08, "INR": 0.012, "GBP": 1.27, "JPY": 0.0067}

REMINDERS: list[dict] = []


@tool
def get_weather(city: str, units: str = "celsius") -> str:
    """Current weather for a city.

    Args:
        city: City name, e.g. "Paris".
        units: "celsius" or "fahrenheit".
    """
    data = WEATHER.get(city.strip().lower())
    if data is None:
        raise ValueError(f"no weather data for '{city}'")
    temp = data["temp_c"] if units.startswith("c") else round(data["temp_c"] * 9 / 5 + 32)
    unit = "°C" if units.startswith("c") else "°F"
    return f"{city.title()}: {temp}{unit}, {data['condition']}"


@tool
def lookup_contact(name: str) -> dict:
    """Find a contact's email and phone number by first name.

    Args:
        name: First name of the contact.
    """
    contact = CONTACTS.get(name.strip().split()[0].lower())
    if contact is None:
        raise ValueError(f"no contact named '{name}'")
    return contact


@tool
def create_reminder(text: str, when: str) -> str:
    """Set a reminder.

    Args:
        text: What to remind the user about.
        when: When to remind, e.g. "tomorrow 9am".
    """
    REMINDERS.append({"text": text, "when": when})
    return f"Reminder set for {when}: {text}"


@tool
def search_notes(query: str) -> str:
    """Search the user's personal notes by keyword.

    Args:
        query: One or two keywords.
    """
    words = [w.lower() for w in query.split()]
    hits = [n for n in NOTES if any(w in n.lower() for w in words)]
    return "\n".join(hits) if hits else "No matching notes."


@tool
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert money between currencies (USD, EUR, INR, GBP, JPY).

    Args:
        amount: Amount to convert.
        from_currency: 3-letter code, e.g. "EUR".
        to_currency: 3-letter code, e.g. "INR".
    """
    src, dst = from_currency.upper(), to_currency.upper()
    if src not in RATES_TO_USD or dst not in RATES_TO_USD:
        raise ValueError("supported currencies: " + ", ".join(RATES_TO_USD))
    value = amount * RATES_TO_USD[src] / RATES_TO_USD[dst]
    return f"{amount:g} {src} = {value:,.2f} {dst}"


EVAL_TOOLS = [get_weather, lookup_contact, create_reminder, search_notes, convert_currency]
