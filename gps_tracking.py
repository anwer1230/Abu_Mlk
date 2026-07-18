"""
gps_tracking.py
══════════════════════════════════════════════════════════════
نظام التعقب الجغرافي عبر GPS وعناوين IP — وحدة مستقلة
يُوفّر تحديد الموقع الدقيق للزوار عبر عدة مزودين بالتتابع
══════════════════════════════════════════════════════════════
"""

import logging

logger = logging.getLogger(__name__)


def geo_lookup(ip: str) -> dict:
    """
    تحديد الموقع الجغرافي من عنوان IP.
    يجرّب عدة مزودين بالتتابع حتى ينجح أحدهم:
      1. ip-api.com  (مجاني، 45 طلب/دقيقة)
      2. ipwho.is    (مجاني، بدون حد)
      3. ip.guide    (مجاني، بدون مصادقة)
    """
    if not ip or ip in ('127.0.0.1', '::1', 'غير معروف', '—', ''):
        return {}

    # ── المزوّد 1: ip-api.com ──────────────────────────────────────
    try:
        import requests as _req
        r = _req.get(
            f'http://ip-api.com/json/{ip}'
            '?lang=ar&fields=status,country,regionName,city,lat,lon,timezone,isp,org,as',
            timeout=4
        )
        if r.status_code == 200:
            d = r.json()
            if d.get('status') == 'success':
                return {
                    'country':  d.get('country', ''),
                    'region':   d.get('regionName', ''),
                    'city':     d.get('city', ''),
                    'lat':      d.get('lat', 0),
                    'lon':      d.get('lon', 0),
                    'isp':      d.get('isp', '') or d.get('org', ''),
                    'timezone': d.get('timezone', ''),
                    'source':   'ip-api',
                }
    except Exception as e:
        logger.debug(f"geo_lookup ip-api failed for {ip}: {e}")

    # ── المزوّد 2: ipwho.is ────────────────────────────────────────
    try:
        import requests as _req
        r = _req.get(f'https://ipwho.is/{ip}', timeout=4)
        if r.status_code == 200:
            d = r.json()
            if d.get('success'):
                return {
                    'country':  d.get('country', ''),
                    'region':   d.get('region', ''),
                    'city':     d.get('city', ''),
                    'lat':      d.get('latitude', 0),
                    'lon':      d.get('longitude', 0),
                    'isp':      d.get('connection', {}).get('isp', ''),
                    'timezone': d.get('timezone', {}).get('id', ''),
                    'source':   'ipwho',
                }
    except Exception as e:
        logger.debug(f"geo_lookup ipwho.is failed for {ip}: {e}")

    # ── المزوّد 3: ip.guide ────────────────────────────────────────
    try:
        import requests as _req
        r = _req.get(f'https://ip.guide/{ip}', headers={'Accept': 'application/json'}, timeout=4)
        if r.status_code == 200:
            d = r.json()
            loc  = d.get('location', {}) or {}
            net  = d.get('network', {}) or {}
            return {
                'country':  loc.get('country_name', ''),
                'region':   loc.get('region_name', ''),
                'city':     loc.get('city', ''),
                'lat':      loc.get('latitude', 0),
                'lon':      loc.get('longitude', 0),
                'isp':      net.get('name', ''),
                'timezone': loc.get('timezone', ''),
                'source':   'ip.guide',
            }
    except Exception as e:
        logger.debug(f"geo_lookup ip.guide failed for {ip}: {e}")

    return {}


def build_map_url(lat: float, lon: float, zoom: int = 16) -> str:
    """
    بناء رابط خريطة Google Maps من إحداثيات GPS
    (zoom=16 يُظهر الشارع بوضوح)
    """
    if not lat or not lon:
        return ''
    return f"https://maps.google.com/maps?q={lat},{lon}&z={zoom}"


def build_map_url_satellite(lat: float, lon: float) -> str:
    """رابط خريطة Google Maps بصورة القمر الاصطناعي"""
    if not lat or not lon:
        return ''
    return f"https://maps.google.com/maps?q={lat},{lon}&t=k&z=18"


def format_location(geo_data: dict) -> str:
    """
    تنسيق بيانات الموقع لعرضها بشكل قابل للقراءة
    """
    if not geo_data:
        return 'موقع غير معروف'
    parts = []
    if geo_data.get('city'):
        parts.append(geo_data['city'])
    if geo_data.get('region'):
        parts.append(geo_data['region'])
    if geo_data.get('country'):
        parts.append(geo_data['country'])
    return ' — '.join(parts) if parts else 'موقع غير معروف'


def enrich_install_record(record: dict, ip: str) -> dict:
    """
    إثراء سجل التثبيت ببيانات الموقع الجغرافي
    """
    if not record.get('geo'):
        geo = geo_lookup(ip)
        if geo:
            record['geo'] = geo
            record['map_url'] = build_map_url(geo.get('lat', 0), geo.get('lon', 0))
            record['map_url_sat'] = build_map_url_satellite(geo.get('lat', 0), geo.get('lon', 0))
            record['location_display'] = format_location(geo)
    return record
