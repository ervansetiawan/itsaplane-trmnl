"""Daily RCE (Remote Code Execution) CVE dashboard backed by CISA KEV."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import time
import requests

CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
CVE_API_URL = "https://cveawg.mitre.org/api/cve/{cve_id}"
EPSS_API_URL = "https://api.first.org/data/v1/epss"
RCE_KEYWORDS = (
    "remote code execution",
    "arbitrary code",
    "code execution",
    "command execution",
    "command injection",
    " rce",
)

MAJOR_VENDORS = (
    "microsoft",
    "apple",
    "google",
    "cisco",
    "fortinet",
    "palo alto",
    "vmware",
    "citrix",
    "ivanti",
    "linux",
    "apache",
    "atlassian",
    "oracle",
    "sap",
    "juniper",
    "sonicwall",
    "adobe",
    "check point",
    "f5",
    "gitlab",
    "github",
    "kubernetes",
    "docker",
    "openssl",
    "nginx",
    "php",
    "python",
    "wordpress",
    "mozilla",
    "samsung",
    "qualcomm",
    "synology",
    "dell",
    "hp",
    "hpe",
    "ibm",
    "redhat",
    "canonical",
)

_CACHE: dict = {"ts": 0.0, "data": None}
_CVSS_CACHE: dict[str, tuple[float | None, str]] = {}
_CACHE_TTL_SECONDS = 1800


def _fetch_cvss(cve_id: str) -> tuple[float | None, str]:
    if not cve_id:
        return None, ""
    if cve_id in _CVSS_CACHE:
        return _CVSS_CACHE[cve_id]
    try:
        resp = requests.get(CVE_API_URL.format(cve_id=cve_id), timeout=4)
        if resp.status_code == 200:
            cna = resp.json().get("containers", {})
            metrics = list(cna.get("cna", {}).get("metrics", []))
            for adp in cna.get("adp", []):
                metrics.extend(adp.get("metrics", []))
            for m in metrics:
                for key in ("cvssV3_1", "cvssV3_0", "cvssV4_0"):
                    if key in m:
                        score = m[key].get("baseScore")
                        sev = (m[key].get("baseSeverity") or "").upper()
                        res = (float(score) if score is not None else None, sev)
                        _CVSS_CACHE[cve_id] = res
                        return res
    except (requests.RequestException, ValueError, TypeError):
        pass
    _CVSS_CACHE[cve_id] = (None, "")
    return None, ""


def _fetch_epss_batch(cve_ids: list[str]) -> dict[str, tuple[str, int]]:
    ids = [c for c in cve_ids if c]
    if not ids:
        return {}
    try:
        resp = requests.get(EPSS_API_URL, params={"cve": ",".join(ids)}, timeout=4)
        if resp.status_code == 200:
            out = {}
            for row in resp.json().get("data", []):
                cve = row.get("cve")
                val = row.get("epss")
                if cve and val is not None:
                    pct = float(val) * 100
                    out[cve] = (f"{pct:.1f}%", max(2, min(100, round(pct))))
            return out
    except (requests.RequestException, ValueError, TypeError):
        pass
    return {}


def _is_rce(vuln: dict) -> bool:
    haystack = f"{vuln.get('vulnerabilityName', '')} {vuln.get('shortDescription', '')}".lower()
    return any(kw in haystack for kw in RCE_KEYWORDS)


def _is_important(vuln: dict) -> bool:
    if vuln.get("knownRansomwareCampaignUse") == "Known":
        return True
    vendor = f"{vuln.get('vendorProject', '')} {vuln.get('product', '')}".lower()
    return any(mv in vendor for mv in MAJOR_VENDORS)


def _format_item(vuln: dict, short_desc_limit: int = 150, epss_map: dict[str, tuple[str, int]] | None = None, today: date | None = None) -> dict:
    desc = (vuln.get("shortDescription") or "").strip()
    if len(desc) > short_desc_limit:
        desc = desc[: short_desc_limit - 3].rstrip() + "..."
    action = (vuln.get("requiredAction") or "").strip()
    if len(action) > 120:
        action = action[:117].rstrip() + "..."
    cwes = vuln.get("cwes") or []
    cwe = cwes[0] if isinstance(cwes, list) and cwes else ""
    due_date = vuln.get("dueDate", "")
    due_label = f"DUE {due_date}" if due_date else ""
    if due_date and today:
        try:
            delta = (date.fromisoformat(due_date) - today).days
            if delta < 0:
                due_label = f"OVERDUE {abs(delta)}d"
            elif delta == 0:
                due_label = "DUE TODAY"
            elif delta <= 14:
                due_label = f"DUE IN {delta}d"
        except ValueError:
            pass
    cve_id = vuln.get("cveID", "")
    cvss, severity = _fetch_cvss(cve_id)
    epss, epss_pct = (epss_map or {}).get(cve_id, ("", 0))
    cvss_pct = max(0, min(100, round(cvss * 10))) if cvss is not None else 0
    return {
        "cve_id": cve_id,
        "vendor": vuln.get("vendorProject", ""),
        "product": vuln.get("product", ""),
        "name": vuln.get("vulnerabilityName", ""),
        "description": desc,
        "action": action,
        "cwe": cwe,
        "date_added": vuln.get("dateAdded", ""),
        "due_date": due_date,
        "due_label": due_label,
        "ransomware": vuln.get("knownRansomwareCampaignUse", "Unknown") == "Known",
        "cvss": cvss,
        "cvss_pct": cvss_pct,
        "severity": severity,
        "epss": epss,
        "epss_pct": epss_pct,
    }


def _build_monthly_bars(vulns: list[dict], d: date) -> list[dict]:
    """Builds 12 monthly bar coordinates (viewBox 0 0 240 42) for RCE KEV trend."""
    months = []
    y, m = d.year, d.month
    for _ in range(12):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()

    totals = {ym: 0 for ym in months}
    rw_totals = {ym: 0 for ym in months}
    for v in vulns:
        ym = (v.get("dateAdded") or "")[:7]
        if ym in totals:
            totals[ym] += 1
            if v.get("knownRansomwareCampaignUse") == "Known":
                rw_totals[ym] += 1

    peak = max(totals.values() or [1]) or 1
    bars = []
    for idx, ym in enumerate(months):
        tot = totals[ym]
        rw = rw_totals[ym]
        h = max(2, round(tot / peak * 34)) if tot else 0
        rh = max(2, round(rw / peak * 34)) if rw else 0
        bars.append(
            {
                "ym": ym,
                "x": idx * 20 + 3,
                "y": 38 - h,
                "h": h,
                "ry": 38 - rh,
                "rh": rh,
            }
        )
    return bars


def fetch_rce_dashboard(today: date | None = None, vendor_filter: str = "") -> dict:
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL_SECONDS:
        raw = _CACHE["data"]
    else:
        try:
            resp = requests.get(CISA_KEV_URL, timeout=10)
            resp.raise_for_status()
            raw = resp.json()
            _CACHE["ts"] = now
            _CACHE["data"] = raw
        except requests.RequestException:
            if _CACHE["data"] is not None:
                raw = _CACHE["data"]
            else:
                raise

    d = today or date.today()
    cutoff_30d = (d - timedelta(days=30)).isoformat()

    vulns = raw.get("vulnerabilities", [])
    rce_vulns = [v for v in vulns if _is_rce(v)]
    important_rce = [v for v in rce_vulns if _is_important(v)]
    vfilter = (vendor_filter or "").strip().lower()
    if vfilter:
        tokens = [t.strip() for t in vfilter.split(",") if t.strip()]
        filtered = [
            v for v in important_rce
            if any(t in f"{v.get('vendorProject', '')} {v.get('product', '')}".lower() for t in tokens)
        ]
        if filtered:
            important_rce = filtered
    important_rce.sort(key=lambda x: x.get("dateAdded", ""), reverse=True)

    top_vulns = important_rce[:6]
    top_ids = [v.get("cveID", "") for v in top_vulns]
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(_fetch_cvss, top_ids))
    epss_map = _fetch_epss_batch(top_ids)

    formatted = [
        _format_item(v, short_desc_limit=150 if idx == 0 else 95, epss_map=epss_map, today=d)
        for idx, v in enumerate(top_vulns)
    ]
    ransomware_count = sum(1 for v in important_rce if v.get("knownRansomwareCampaignUse") == "Known")
    recent_30d = sum(1 for v in important_rce if v.get("dateAdded", "") >= cutoff_30d)

    return {
        "title": "Daily RCE Dashboard",
        "date": d.strftime("%b %d, %Y").upper(),
        "catalog_version": raw.get("catalogVersion", ""),
        "total_kev": len(vulns),
        "total_rce": len(important_rce),
        "ransomware_count": ransomware_count,
        "recent_30d": recent_30d,
        "monthly_bars": _build_monthly_bars(important_rce, d),
        "featured": formatted[0] if formatted else None,
        "items": formatted[1:6],
    }
