#!/usr/bin/env python3
"""
ISP Outage Checker
Checks whether your ISP has a known/reported outage — automatically.
Combines 3 methods:
  1. Probe ISP infrastructure IPs directly (are their own servers reachable?)
  2. Fetch ISP / Cloudflare status APIs
  3. Check Downdetector-style signals via HTTP probes

Run: python3 isp_status.py
     python3 isp_status.py --isp airtel
     python3 isp_status.py --isp jio
     python3 isp_status.py --isp bsnl
     python3 isp_status.py --isp all      (check all ISPs)
"""

import subprocess
import urllib.request
import socket
import re
import sys
import json
import time
import platform
from datetime import datetime

# ── ISP Definitions ──────────────────────────────────────────
# Each ISP has:
#   dns_ips       — their own DNS/resolver IPs (should always be up if ISP is up)
#   status_url    — their status/health page (if available)
#   probe_urls    — their main website (if ISP's own website is down, major outage)
#   name          — display name

ISP_PROFILES = {
    "airtel": {
        "name":        "Airtel (India)",
        "dns_ips":     ["122.160.67.98", "122.160.67.99", "203.88.141.1"],
        "probe_urls":  ["https://www.airtel.in", "https://wynk.in"],
        "status_url":  None,
        "keywords":    ["airtel", "bharti"],
    },
    "jio": {
        "name":        "Jio (Reliance India)",
        "dns_ips":     ["49.45.85.136", "116.73.36.251", "1.0.0.1"],
        "probe_urls":  ["https://www.jio.com", "https://www.reliancejio.com"],
        "status_url":  None,
        "keywords":    ["jio", "reliance"],
    },
    "bsnl": {
        "name":        "BSNL (India)",
        "dns_ips":     ["61.0.0.83", "61.1.96.52", "203.197.28.194"],
        "probe_urls":  ["https://www.bsnl.in", "https://bsnl.co.in"],
        "status_url":  None,
        "keywords":    ["bsnl", "sancharnet"],
    },
    "act": {
        "name":        "ACT Fibernet (India)",
        "dns_ips":     ["61.12.7.154", "203.110.80.81"],
        "probe_urls":  ["https://www.actfibernet.com"],
        "status_url":  None,
        "keywords":    ["act fibernet", "atria"],
    },
    "comcast": {
        "name":        "Comcast / Xfinity (USA)",
        "dns_ips":     ["75.75.75.75", "75.75.76.76"],
        "probe_urls":  ["https://www.xfinity.com", "https://comcast.net"],
        "status_url":  "https://www.xfinity.com/support/status/",
        "keywords":    ["xfinity", "comcast"],
    },
    "att": {
        "name":        "AT&T (USA)",
        "dns_ips":     ["68.94.156.1", "68.94.157.1"],
        "probe_urls":  ["https://www.att.com"],
        "status_url":  None,
        "keywords":    ["at&t", "att"],
    },
    "cloudflare": {
        "name":        "Cloudflare (Status Check)",
        "dns_ips":     ["1.1.1.1", "1.0.0.1"],
        "probe_urls":  ["https://www.cloudflare.com"],
        "status_url":  "https://www.cloudflarestatus.com/api/v2/summary.json",
        "keywords":    ["cloudflare"],
    },
}

# ── Generic probes (always checked regardless of ISP) ────────
ALWAYS_CHECK = [
    ("Google DNS",      "8.8.8.8"),
    ("Cloudflare DNS",  "1.1.1.1"),
    ("OpenDNS",         "208.67.222.222"),
]

TIMEOUT = 6


# ── Core network functions ────────────────────────────────────

def ping_ip(ip, count=3):
    system = platform.system()
    cmd = (["ping", "-c", str(count), "-W", "2000", ip]
           if system != "Windows"
           else ["ping", "-n", str(count), ip])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        output = r.stdout
        loss = 100.0
        avg_ms = None
        for line in output.splitlines():
            m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(packet\s*)?loss", line, re.IGNORECASE)
            if m:
                loss = float(m.group(1))
            m = re.search(r"[\d.]+/([\d.]+)/[\d.]+", line)
            if m:
                avg_ms = float(m.group(1))
        return (loss < 100), avg_ms
    except Exception:
        return False, None


def http_get(url, timeout=TIMEOUT):
    """Returns (ok, status_code_or_None, response_text_or_None)."""
    try:
        req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        text = resp.read(4096).decode("utf-8", errors="ignore")
        return True, resp.status, text
    except urllib.error.HTTPError as e:
        return False, e.code, None
    except Exception:
        return False, None, None


def check_cloudflare_status_api():
    """
    Cloudflare publishes a public status API.
    Returns (overall_status, list_of_incidents)
    """
    url = "https://www.cloudflarestatus.com/api/v2/summary.json"
    ok, code, text = http_get(url)
    if not ok or not text:
        return "unknown", []
    try:
        data = json.loads(text)
        overall = data.get("status", {}).get("description", "unknown")
        incidents = [
            inc.get("name", "unknown incident")
            for inc in data.get("incidents", [])
            if inc.get("status") != "resolved"
        ]
        return overall, incidents
    except Exception:
        return "unknown", []


def detect_local_isp():
    """
    Try to guess which ISP you are on by looking at the gateway IP
    or doing a reverse DNS on the gateway.
    """
    system = platform.system()
    try:
        if system == "Darwin":
            r = subprocess.run(["route", "-n", "get", "default"],
                               capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                if "gateway:" in line:
                    gw = line.split(":")[-1].strip()
                    # Reverse DNS
                    try:
                        hostname = socket.gethostbyaddr(gw)[0].lower()
                        for isp_key, profile in ISP_PROFILES.items():
                            for kw in profile["keywords"]:
                                if kw in hostname:
                                    return isp_key, hostname
                    except Exception:
                        pass
                    return None, gw
    except Exception:
        pass
    return None, None


# ── ISP check ────────────────────────────────────────────────

def check_isp(isp_key):
    profile = ISP_PROFILES.get(isp_key)
    if not profile:
        print(f"  Unknown ISP: {isp_key}")
        return

    name = profile["name"]
    print(f"\n{'─'*56}")
    print(f"  CHECKING: {name}")
    print(f"{'─'*56}")

    dns_results  = []
    http_results = []

    # ── Probe ISP DNS IPs ────────────────────────────────────
    print("\n  [ISP Infrastructure IPs]")
    for ip in profile["dns_ips"]:
        ok, ms = ping_ip(ip)
        ms_str = f"{ms:.1f}ms" if ms else "timeout"
        icon   = "✅" if ok else "❌"
        print(f"    {icon}  {ip:<18} {ms_str}")
        dns_results.append(ok)

    # ── Probe ISP websites ───────────────────────────────────
    print("\n  [ISP Website Probes]")
    for url in profile["probe_urls"]:
        ok, code, _ = http_get(url)
        icon = "✅" if ok else "❌"
        code_str = f"HTTP {code}" if code else "unreachable"
        print(f"    {icon}  {url}")
        print(f"         {code_str}")
        http_results.append(ok)

    # ── Cloudflare Status API (if it's Cloudflare ISP) ───────
    if isp_key == "cloudflare":
        print("\n  [Cloudflare Status API]")
        cf_status, cf_incidents = check_cloudflare_status_api()
        print(f"    Overall: {cf_status}")
        if cf_incidents:
            print("    Active incidents:")
            for inc in cf_incidents[:3]:
                print(f"      ⚠️  {inc}")
        else:
            print("    ✅ No active incidents")

    # ── Custom status URL ────────────────────────────────────
    if profile["status_url"] and isp_key != "cloudflare":
        print(f"\n  [Status Page: {profile['status_url']}]")
        ok, code, text = http_get(profile["status_url"])
        if ok and text:
            lower = text.lower()
            outage_keywords = ["outage", "disruption", "incident", "degraded",
                               "down", "offline", "unavailable", "investigating"]
            found = [kw for kw in outage_keywords if kw in lower]
            if found:
                print(f"    ⚠️  Status page contains: {', '.join(found)}")
            else:
                print(f"    ✅ Status page loaded, no outage keywords found")
        else:
            print(f"    ❌ Could not reach status page")

    # ── Verdict ──────────────────────────────────────────────
    dns_ok  = any(dns_results)
    http_ok = any(http_results)

    print(f"\n  VERDICT for {name}:")
    if not dns_ok and not http_ok:
        print(f"  🔴 LIKELY DOWN — ISP infrastructure and websites unreachable")
        print(f"     Either you have no internet, or this ISP has a major outage")
    elif not dns_ok and http_ok:
        print(f"  🟡 PARTIAL — Website works but DNS IPs unreachable")
        print(f"     DNS infrastructure may have issues. Try changing DNS to 8.8.8.8")
    elif dns_ok and not http_ok:
        print(f"  🟡 PARTIAL — DNS IPs up but website unreachable")
        print(f"     Possible routing or CDN issue for this ISP")
    else:
        print(f"  🟢 UP — Infrastructure and websites reachable")


def check_generic():
    """Always-run check of global DNS servers."""
    print(f"\n{'─'*56}")
    print("  GLOBAL DNS REACHABILITY (always checked)")
    print(f"{'─'*56}")
    results = []
    for label, ip in ALWAYS_CHECK:
        ok, ms = ping_ip(ip)
        ms_str = f"{ms:.1f}ms" if ms else "blocked/timeout"
        icon   = "✅" if ok else "❌"
        print(f"  {icon}  {label:<18} ({ip})  {ms_str}")
        results.append(ok)

    ok_count = sum(results)
    if ok_count == 0:
        # Could be firewall blocking pings — check HTTP
        import urllib.request as ur
        try:
            ur.urlopen("https://www.google.com", timeout=5)
            print("  ⚠️  Pings blocked (firewall) but HTTP works → internet is UP")
        except Exception:
            print("  🔴 Nothing reachable — likely no internet or major outage")
    elif ok_count < len(ALWAYS_CHECK):
        print(f"  ⚠️  Only {ok_count}/{len(ALWAYS_CHECK)} global DNS servers reachable")
    else:
        print(f"  ✅ All {ok_count} global DNS servers reachable")


# ── Main ─────────────────────────────────────────────────────

def main():
    args    = sys.argv[1:]
    isp_arg = None
    for i, arg in enumerate(args):
        if arg == "--isp" and i + 1 < len(args):
            isp_arg = args[i + 1].lower()

    print("\n" + "="*56)
    print("  ISP OUTAGE CHECKER")
    print(f"  {datetime.now().strftime('%A %d %B %Y  %H:%M:%S')}")
    print("="*56)
    print(f"\n  Available ISPs: {', '.join(ISP_PROFILES.keys())}")
    print(f"  Usage: python3 isp_status.py --isp airtel\n")

    # Auto-detect ISP from gateway
    detected_key, detected_host = detect_local_isp()
    if detected_key:
        print(f"  Auto-detected ISP: {ISP_PROFILES[detected_key]['name']} ({detected_host})")
    else:
        print(f"  Could not auto-detect ISP from gateway reverse DNS")

    # Run global check
    check_generic()

    # Run ISP-specific check
    if isp_arg == "all":
        for key in ISP_PROFILES:
            check_isp(key)
    elif isp_arg and isp_arg in ISP_PROFILES:
        check_isp(isp_arg)
    elif detected_key:
        print(f"\n  Running check for auto-detected ISP: {detected_key}")
        check_isp(detected_key)
    else:
        print("\n  Tip: run with --isp <name> to check a specific ISP")
        print("  Running Cloudflare status check as example...")
        check_isp("cloudflare")

    print("\n" + "="*56 + "\n")


if __name__ == "__main__":
    main()
