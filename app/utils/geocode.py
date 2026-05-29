"""Reverse geocoding for evidence PDFs.
Resolves a GPS coordinate to a human-readable place name via OpenStreetMap Nominatim.
On any failure, returns None and lets the caller omit the place name.
"""
import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "Evidentix/1.0 (forensic evidence platform; admin@evidenceanalyzer.com)"
TIMEOUT_SECONDS = 8


def reverse_geocode(lat, lon):
    """Resolve (lat, lon) to a readable place label, or None on any failure.

    Returns a compact label (e.g. 'Laxey, Isle of Man') built from the most
    specific address components, falling back to Nominatim's display_name.
    Never raises; returns None instead.
    """
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={
                "lat": lat,
                "lon": lon,
                "format": "jsonv2",
                "zoom": 14,
                "addressdetails": 1,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()

        addr = data.get("address") or {}
        locality = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("hamlet")
            or addr.get("suburb")
            or addr.get("county")
        )
        region = addr.get("state") or addr.get("region")
        country = addr.get("country")

        label_parts = []
        for p in (locality, region, country):
            if p and p not in label_parts:
                label_parts.append(p)
        if label_parts:
            return ", ".join(label_parts)

        return data.get("display_name") or None
    except Exception:
        return None