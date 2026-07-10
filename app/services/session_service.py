import requests
from user_agents import parse as parse_ua
from fastapi import Request
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.user_session import UserSession


IPWHO_URL = "https://ipwho.is/{}"
IPWHO_TIMEOUT = 3


def _get_client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        # Could be comma separated
        return xff.split(",")[0].strip()
    client = getattr(request, "client", None)
    if client:
        return client.host
    return None


def _fetch_ip_info(ip: str) -> dict | None:
    try:
        resp = requests.get(IPWHO_URL.format(ip), timeout=IPWHO_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success", True) is False:
                return None
            return data
    except Exception:
        return None


def _parse_user_agent(ua_string: str) -> dict:
    ua = parse_ua(ua_string or "")
    device_type = "Desktop"
    if ua.is_mobile:
        device_type = "Mobile"
    elif ua.is_tablet:
        device_type = "Tablet"
    elif ua.is_pc:
        device_type = "Desktop"
    elif ua.is_bot:
        device_type = "Bot"

    return {
        "browser": ua.browser.family,
        "browser_version": ua.browser.version_string,
        "os": ua.os.family,
        "os_version": ua.os.version_string,
        "device_type": device_type,
    }


def _extract_language(request: Request) -> str | None:
    return request.headers.get("accept-language")


def update_or_create_session_on_login(db: Session, user, request: Request):
    """Create or update the user's single session on login.
    Sets login_at and last_active_at to now and marks active.
    """
    ip = _get_client_ip(request)
    ip_info = None
    geo = {}
    if ip:
        ip_info = _fetch_ip_info(ip)
    if ip_info:
        geo = {
            "country": ip_info.get("country"),
            "region": ip_info.get("region"),
            "city": ip_info.get("city"),
            "latitude": ip_info.get("latitude"),
            "longitude": ip_info.get("longitude"),
            "timezone": ip_info.get("timezone", {}).get("id") if isinstance(ip_info.get("timezone"), dict) else ip_info.get("timezone"),
            "isp": (ip_info.get("connection") or {}).get("isp") if isinstance(ip_info.get("connection"), dict) else None,
            "organization": (ip_info.get("connection") or {}).get("org") if isinstance(ip_info.get("connection"), dict) else None,
        }

    ua_string = request.headers.get("user-agent")
    ua = _parse_user_agent(ua_string)
    language = _extract_language(request)

    now = datetime.now(timezone.utc)

    sess = db.query(UserSession).filter(UserSession.user_id == user.id).first()
    if not sess:
        sess = UserSession(user_id=user.id)
        db.add(sess)

    sess.ip_address = ip
    sess.country = geo.get("country")
    sess.region = geo.get("region")
    sess.city = geo.get("city")
    sess.latitude = geo.get("latitude")
    sess.longitude = geo.get("longitude")
    sess.timezone = geo.get("timezone")
    sess.isp = geo.get("isp")
    sess.organization = geo.get("organization")

    sess.browser = ua.get("browser")
    sess.browser_version = ua.get("browser_version")
    sess.os = ua.get("os")
    sess.os_version = ua.get("os_version")
    sess.device_type = ua.get("device_type")
    sess.user_agent = ua_string
    sess.language = language

    sess.login_at = now
    sess.last_active_at = now
    sess.is_active = True

    db.commit()
    db.refresh(sess)
    return sess


def update_session_on_refresh(db: Session, user, request: Request):
    """Update last_active_at and refresh location fields only when the IP changes. Keep login_at intact."""
    ip = _get_client_ip(request)
    ua_string = request.headers.get("user-agent")
    ua = _parse_user_agent(ua_string)
    language = _extract_language(request)

    now = datetime.now(timezone.utc)

    sess = db.query(UserSession).filter(UserSession.user_id == user.id).first()
    if not sess:
        sess = UserSession(user_id=user.id)
        db.add(sess)

    ip_changed = bool(ip and sess.ip_address != ip) or (ip is None and sess.ip_address is not None)
    geo = {}
    if ip_changed and ip:
        ip_info = _fetch_ip_info(ip)
        if ip_info:
            geo = {
                "country": ip_info.get("country"),
                "region": ip_info.get("region"),
                "city": ip_info.get("city"),
                "latitude": ip_info.get("latitude"),
                "longitude": ip_info.get("longitude"),
                "timezone": ip_info.get("timezone", {}).get("id") if isinstance(ip_info.get("timezone"), dict) else ip_info.get("timezone"),
                "isp": (ip_info.get("connection") or {}).get("isp") if isinstance(ip_info.get("connection"), dict) else None,
                "organization": (ip_info.get("connection") or {}).get("org") if isinstance(ip_info.get("connection"), dict) else None,
            }

    sess.ip_address = ip
    if ip_changed:
        sess.country = geo.get("country")
        sess.region = geo.get("region")
        sess.city = geo.get("city")
        sess.latitude = geo.get("latitude")
        sess.longitude = geo.get("longitude")
        sess.timezone = geo.get("timezone")
        sess.isp = geo.get("isp")
        sess.organization = geo.get("organization")

    sess.browser = ua.get("browser")
    sess.browser_version = ua.get("browser_version")
    sess.os = ua.get("os")
    sess.os_version = ua.get("os_version")
    sess.device_type = ua.get("device_type")
    sess.user_agent = ua_string
    sess.language = language

    sess.last_active_at = now

    db.commit()
    db.refresh(sess)
    return sess


def deactivate_session_on_logout(db: Session, user):
    now = datetime.now(timezone.utc)
    sess = db.query(UserSession).filter(UserSession.user_id == user.id).first()
    if not sess:
        return None
    sess.is_active = False
    sess.last_active_at = now
    db.commit()
    db.refresh(sess)
    return sess
