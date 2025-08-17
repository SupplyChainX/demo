"""Geospatial helpers and static lookup tables for ports and cities.

Used to replace placeholder 0.0 coordinates deterministically.
"""
from __future__ import annotations

PORT_COORDS = {
    'CAVAN': (49.2827, -123.1207),  # Vancouver
    'NLRTM': (51.9225, 4.4792),     # Rotterdam
    'CNSHA': (31.2304, 121.4737),   # Shanghai
    'USLAX': (33.7553, -118.2769),  # Los Angeles
    'AEJEA': (25.2769, 55.2962),    # Dubai / Jebel Ali
    'SGSIN': (1.2966, 103.8060),    # Singapore
    'DEHAM': (53.5459, 9.9681),     # Hamburg
    'HKHKG': (22.3069, 114.2293),   # Hong Kong
}

CITY_COORDS = {
    'vancouver': (49.2827, -123.1207),
    'rotterdam': (51.9225, 4.4792),
    'shanghai': (31.2304, 121.4737),
    'los angeles': (34.0522, -118.2437),
    'dubai': (25.2769, 55.2962),
    'singapore': (1.3521, 103.8198),
    'hamburg': (53.5511, 9.9937),
    'hong kong': (22.3193, 114.1694),
}

def lookup_port(unlocode: str | None):
    if not unlocode:
        return None
    return PORT_COORDS.get(unlocode.upper())

def lookup_city(name: str | None):
    if not name:
        return None
    return CITY_COORDS.get(name.lower())

def enrich_waypoints(waypoints):
    enriched = []
    for wp in waypoints or []:
        lat = wp.get('lat')
        lon = wp.get('lon')
        if (lat in (None, 0.0) and lon in (None, 0.0)):
            coords = lookup_port(wp.get('unlocode')) or lookup_city(wp.get('city'))
            if coords:
                wp = {**wp, 'lat': coords[0], 'lon': coords[1]}
        enriched.append(wp)
    return enriched
