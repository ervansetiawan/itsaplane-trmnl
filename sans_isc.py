"""SANS Internet Storm Center (ISC) InfoCon & Top Attacked Ports monitor."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import time
import requests

ISC_INFOCON_URL = "https://isc.sans.edu/api/infocon?json"
ISC_TOPPORTS_URL = "https://isc.sans.edu/api/topports/records/6?json"
_HEADERS = {"User-Agent": "itsaplane-trmnl/1.0 (https://github.com/ervansetiawan/itsaplane-trmnl)"}

PORT_SERVICES = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    135: "MS-RPC",
    139: "NetBIOS",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    1433: "MSSQL",
    3306: "MySQL",
    3389: "RDP",
    5060: "SIP",
    5900: "VNC",
    6379: "Redis",
    8080: "HTTP-Alt",
    8443: "HTTPS-Alt",
}

_CACHE: dict = {"ts": 0.0, "data": None}
_CACHE_TTL_SECONDS = 900


def _fmt_compact(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _fetch_json(url: str):
    resp = requests.get(url, headers=_HEADERS, timeout=6)
    resp.raise_for_status()
    return resp.json()


def fetch_sans_isc() -> dict:
    """Fetches current InfoCon status and top 6 attacked ports from SANS ISC."""
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL_SECONDS:
        return _CACHE["data"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        infocon_fut = pool.submit(_fetch_json, ISC_INFOCON_URL)
        ports_fut = pool.submit(_fetch_json, ISC_TOPPORTS_URL)
        infocon_raw = infocon_fut.result()
        ports_raw = ports_fut.result()

    infocon = str((infocon_raw or {}).get("status", "green")).upper()

    if isinstance(ports_raw, dict):
        rows = [
            ports_raw[k]
            for k in sorted(ports_raw.keys(), key=lambda x: int(x) if str(x).isdigit() else 999)
            if isinstance(ports_raw[k], dict)
        ]
    elif isinstance(ports_raw, list):
        rows = ports_raw
    else:
        rows = []
    parsed_ports = []
    for row in rows[:6]:
        try:
            port = int(row.get("targetport", 0))
            records = int(float(row.get("records", 0) or 0))
            targets = int(float(row.get("targets", 0) or 0))
            sources = int(float(row.get("sources", 0) or 0))
        except (ValueError, TypeError):
            continue
        parsed_ports.append(
            {
                "port": port,
                "service": PORT_SERVICES.get(port, f"TCP/{port}"),
                "records": records,
                "records_fmt": _fmt_compact(records),
                "targets": targets,
                "targets_fmt": _fmt_compact(targets),
                "sources": sources,
                "sources_fmt": _fmt_compact(sources),
            }
        )

    max_records = max((p["records"] for p in parsed_ports), default=1) or 1
    for p in parsed_ports:
        p["bar_pct"] = max(8, min(100, round(p["records"] / max_records * 100)))

    top_port = parsed_ports[0] if parsed_ports else None
    total_records = sum(p["records"] for p in parsed_ports)
    total_targets = sum(p["targets"] for p in parsed_ports)

    result = {
        "title": "SANS ISC Threat Monitor",
        "date": datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC").upper(),
        "infocon": infocon,
        "top_port": top_port,
        "total_records_fmt": _fmt_compact(total_records),
        "total_targets_fmt": _fmt_compact(total_targets),
        "port_count": len(parsed_ports),
        "top_ports": parsed_ports,
    }
    _CACHE["ts"] = now
    _CACHE["data"] = result
    return result
