"""Static map rendering for evidence PDFs.

Renders an OpenStreetMap-tile static image around a GPS coordinate.
On any failure, returns None and lets the caller render a fallback.
"""
import os
import tempfile
from staticmap import StaticMap, CircleMarker

DEFAULT_WIDTH = 400
DEFAULT_HEIGHT = 300
DEFAULT_ZOOM = 14
MARKER_COLOR = "#E24B4A"
MARKER_RADIUS = 12
USER_AGENT = "Evidentix/1.0 (forensic evidence platform; admin@evidenceanalyzer.com)"


def render_map_png(lat, lon, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, zoom=DEFAULT_ZOOM):
    """Render a static OSM map centered on (lat, lon) with a marker.

    Returns the path to a temporary PNG file on success, or None on any failure.
    The caller is responsible for deleting the returned file.
    """
    try:
        m = StaticMap(width, height, url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png", headers={"User-Agent": USER_AGENT})
        m.add_marker(CircleMarker((lon, lat), MARKER_COLOR, MARKER_RADIUS))
        image = m.render(zoom=zoom)
        fd, path = tempfile.mkstemp(suffix=".png", prefix="evid_map_")
        os.close(fd)
        image.save(path)
        return path
    except Exception:
        return None