"""Car rental, transfers, eSIM, insurance and tours: affiliate links set in config."""
from app.config import settings

LABELS = {
    "car_rental": ("Compare car hire prices", "Car rental"),
    "transfer": ("Book an airport or hotel transfer", "Transfers"),
    "esim": ("Get a travel eSIM for mobile data", "eSIM"),
    "insurance": ("Get a travel insurance quote", "Insurance"),
    "tours": ("Tours, tickets and activities", "Tours"),
}


def get_extra_links(categories: list[str], destination: str | None = None) -> dict:
    links, missing = [], []
    for cat in categories:
        url = settings.extra_links.get(cat)
        if url:
            label, partner = LABELS.get(cat, (cat, cat))
            links.append({"category": cat, "label": label, "partner": partner, "url": url})
        else:
            missing.append(cat)
    return {"type": "extras", "destination": destination, "results": links, "not_available": missing}
