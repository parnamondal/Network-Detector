#!/usr/bin/env python3
"""
Area vs Local Fault Detector
Answers: "Is it just me, or is the whole area/region affected?"

Logic:
  Router slow/dead     → Problem is in YOUR device or WiFi
  Router OK, ISP dead  → Problem is YOUR area (local fiber/cable)
  ISP OK, some sites   → Routing issue (not a full outage)
  Everything dead      → Broad regional or ISP-wide outage

Run: python3 area_compare.py
"""

import subprocess
import socket
import urllib.request
import re
import platform
import time
from datetime import datetime

# ── Probe targets grouped by network zone ──────────────────
# Hitting many diverse targets lets us fingerprint WHICH part of
# the internet is broken, not just WHETHER it is broken.

PROBE_GROUPS = {
    "ISP Infrastructure": [
        # These are ISP/carrier-level DNS and infrastructure IPs.
        # If these fail but public internet targets work → ISP routing issue.
        ("Airtel DNS",   "122.160.67.98"),
        ("Jio DNS",      "49.45.85.136"),
        ("BSNL DNS",     "61.0.0.83"),
        ("Google DNS",   "8.8.8.8"),
        ("Cloudflare",   "1.1.1.1"),
        ("OpenDNS",      "208.67.222.222"),
    ],
    "Global CDN Nodes": [
        # Major CDN edge nodes. If these fail → regional/global issue.
        ("Akamai",       "23.32.3.96"),
        ("Fastly",       "151.101.1.69"),
        ("Cloudflare CF","104.16.132.229"),
        ("AWS edge",     "54.239.28.85"),
    ],
    "Major Services": [
        # If CDNs work but these don't → DNS or routing to specific ASN.
        ("Google.com",   "142.250.80.46"),
        ("YouTube",      "142.250.80.78"),
        ("Amazon.com",   "205.251.242.103"),
        ("Microsoft",    "20.112.52.29"),
    ],
}

HTTP_PROBES = [
    ("Google",      "https://www.google.com"),
    ("Cloudflare",  "https://www.cloudflare.com"),
    ("Amazon",      "https://www.amazon.com"),
    ("GitHub",      "https://github.com"),
]

DNS_NAMES = ["google.com", "youtube.com", "facebook.com", "amazon.com"]


def get_gateway():
    system = platform.system()
    try:
        if system == "Darwin":
            r = subprocess.run(["route", "-n", "get", "default"],
                               capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                if "gateway:" in line:
                    return line.split(":")[-1].strip()
        elif system == "Linux":
            r = subprocess.run(["ip", "route", "show", "default"],
                               capture_output=True, text=True, timeout=5)
            parts = r.stdout.split()
            if "via" in parts:
                return parts[parts.index("via") + 1]
    except Exception:
        pass
    return None


def ping_fast(host, count=2):
    """Quick 2-ping check. Returns (ok, avg_ms)."""
    system = platform.system()
    cmd = (["ping", "-c", str(count), "-W", "2000", host]
           if system != "Windows"
           else ["ping", "-n", str(count), host])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = r.stdout
        avg_ms = None
        loss = 100.0
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


def http_reachable(url):
    """Returns (ok, ms)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        start = time.time()
        urllib.request.urlopen(req, timeout=6)
        ms = (time.time() - start) * 1000
        return True, ms
    except Exception:
        return False, None


def dns_resolve(name):
    try:
        socket.setdefaulttimeout(4)
        socket.getaddrinfo(name, None)
        return True
    except Exception:
        return False


def bar(ok_count, total, width=20):
    filled = int((ok_count / total) * width) if total else 0
    return "█" * filled + "░" * (width - filled)


def classify_fault(router_ok, router_ms, group_scores, http_scores, dns_ok):
    """
    Returns (fault_level, plain_english_diagnosis)
    Fault levels: LOCAL, BUILDING, AREA, ISP, REGIONAL, NONE
    """
    if not router_ok:
        return "LOCAL", (
            "Your device cannot reach even the router.\n"
            "  Problem is between YOUR DEVICE and your router.\n"
            "  → WiFi off, bad cable, or router is physically off."
        )

    isp_score  = group_scores.get("ISP Infrastructure", (0, 0))
    cdn_score  = group_scores.get("Global CDN Nodes", (0, 0))
    svc_score  = group_scores.get("Major Services", (0, 0))
    http_ok_ct = sum(1 for ok, _ in http_scores if ok)
    http_total = len(http_scores)

    isp_pct  = isp_score[0]  / isp_score[1]  if isp_score[1]  else 1
    cdn_pct  = cdn_score[0]  / cdn_score[1]  if cdn_score[1]  else 1
    http_pct = http_ok_ct    / http_total     if http_total    else 1

    # Pings blocked but HTTP works → corporate/VPN network
    if isp_pct == 0 and cdn_pct == 0 and http_pct > 0.5 and dns_ok:
        return "NONE", (
            "ICMP (ping) is blocked by your network (corporate/VPN firewall).\n"
            "  HTTP and DNS work fine → internet is fully reachable.\n"
            "  No fault detected."
        )

    if isp_pct == 0 and http_pct == 0 and not dns_ok:
        return "AREA", (
            "Router is alive but NOTHING beyond it responds.\n"
            "  This looks like a LOCAL AREA OUTAGE.\n"
            "  → Fiber/cable cut between your building and ISP exchange.\n"
            "  → All ~1000 people in your area are likely affected.\n"
            "  → Action: Report to ISP, check with neighbors."
        )

    if isp_pct < 0.3 and cdn_pct > 0.5:
        return "ISP", (
            "CDN and global nodes reachable, but ISP-side infrastructure failing.\n"
            "  → Partial ISP routing issue (not a full fiber cut).\n"
            "  → Your ISP's internal network has a fault.\n"
            "  → Contact ISP support."
        )

    if cdn_pct < 0.3 and http_pct < 0.3:
        return "REGIONAL", (
            "ISP infrastructure partially works but global CDN is unreachable.\n"
            "  → Possible REGIONAL internet disruption.\n"
            "  → Could be a major submarine cable or peering issue.\n"
            "  → Affects a wide geographic area, not just your ISP."
        )

    if isp_pct > 0.5 and http_pct < 0.3 and not dns_ok:
        return "DNS", (
            "Pings work but DNS is failing → can't find websites by name.\n"
            "  Fix: Set DNS manually to 8.8.8.8 in your network settings."
        )

    if router_ms and router_ms > 50:
        return "BUILDING", (
            f"Router latency is high ({router_ms:.0f}ms, should be <5ms).\n"
            "  → Problem is between your device and router.\n"
            "  → WiFi congestion, interference, or overloaded router.\n"
            "  → Try restarting router or moving closer."
        )

    return "NONE", "All layers healthy. No fault detected."


def run():
    print("\n" + "="*58)
    print("  AREA vs LOCAL FAULT DETECTOR")
    print(f"  {datetime.now().strftime('%A %d %B %Y  %H:%M:%S')}")
    print("="*58)

    # ── Router check ─────────────────────────────────────────
    gateway = get_gateway()
    print(f"\n  Router gateway: {gateway if gateway else '❌ Not found'}")
    if gateway:
        router_ok, router_ms = ping_fast(gateway, count=3)
        ms_str = f"{router_ms:.1f}ms" if router_ms else "no response"
        icon = "✅" if router_ok else "❌"
        print(f"  Router ping:    {icon} {ms_str}")
    else:
        router_ok, router_ms = False, None

    # ── Probe each group ─────────────────────────────────────
    print(f"\n{'─'*58}")
    print("  PROBING NETWORK ZONES")
    print(f"{'─'*58}")

    group_scores = {}
    for group_name, targets in PROBE_GROUPS.items():
        print(f"\n  [{group_name}]")
        ok_count = 0
        for label, ip in targets:
            ok, ms = ping_fast(ip)
            icon  = "✅" if ok else "❌"
            ms_str = f"{ms:.0f}ms" if ms else "blocked/timeout"
            print(f"    {icon}  {label:<18} {ip:<18} {ms_str}")
            if ok:
                ok_count += 1
        total = len(targets)
        pct = int((ok_count / total) * 100)
        print(f"    Reachable: {ok_count}/{total}  {bar(ok_count, total)} {pct}%")
        group_scores[group_name] = (ok_count, total)

    # ── HTTP probes ───────────────────────────────────────────
    print(f"\n{'─'*58}")
    print("  HTTP REACHABILITY CHECK")
    print(f"{'─'*58}")
    http_scores = []
    for label, url in HTTP_PROBES:
        ok, ms = http_reachable(url)
        icon   = "✅" if ok else "❌"
        ms_str = f"{ms:.0f}ms" if ms else "failed"
        print(f"  {icon}  {label:<14} {ms_str}")
        http_scores.append((ok, ms))

    # ── DNS check ────────────────────────────────────────────
    print(f"\n{'─'*58}")
    print("  DNS NAME RESOLUTION")
    print(f"{'─'*58}")
    dns_results = [dns_resolve(d) for d in DNS_NAMES]
    dns_ok = any(dns_results)
    for name, ok in zip(DNS_NAMES, dns_results):
        print(f"  {'✅' if ok else '❌'}  {name}")

    # ── Final classification ──────────────────────────────────
    fault_level, diagnosis = classify_fault(
        router_ok, router_ms, group_scores, http_scores, dns_ok
    )

    level_icons = {
        "NONE": "✅",
        "LOCAL": "🔵",
        "BUILDING": "🟡",
        "AREA": "🔴",
        "ISP": "🟠",
        "REGIONAL": "🔴",
        "DNS": "🟡",
    }

    print(f"\n{'='*58}")
    print(f"  {level_icons.get(fault_level, '⚠️')}  VERDICT: {fault_level} ISSUE")
    print(f"{'='*58}")
    print()
    for line in diagnosis.splitlines():
        print(f"  {line}")

    # ── Visual summary ────────────────────────────────────────
    print(f"\n{'─'*58}")
    print("  NETWORK REACH MAP")
    print(f"{'─'*58}")
    isp_ok_ct, isp_tot = group_scores.get("ISP Infrastructure", (0, 1))
    cdn_ok_ct, cdn_tot = group_scores.get("Global CDN Nodes", (0, 1))
    svc_ok_ct, svc_tot = group_scores.get("Major Services", (0, 1))
    http_ok_ct = sum(1 for ok, _ in http_scores if ok)

    def reach_icon(ok, total):
        pct = ok / total if total else 0
        if pct >= 0.8:   return "🟢 Reachable"
        if pct >= 0.4:   return "🟡 Partial"
        return "🔴 Unreachable"

    router_icon = "🟢 OK" if router_ok else "🔴 Dead"
    print(f"""
  Your Device
       │
       ▼
  [ Router ]           {router_icon}
       │
       ▼
  [ ISP Infrastructure ] {reach_icon(isp_ok_ct, isp_tot)}
       │
       ▼
  [ Global CDN Nodes ]   {reach_icon(cdn_ok_ct, cdn_tot)}
       │
       ▼
  [ Major Services ]     {reach_icon(svc_ok_ct, svc_tot)}
  [ HTTP Access    ]     {reach_icon(http_ok_ct, len(HTTP_PROBES))}
  [ DNS Resolution ]     {"🟢 Working" if dns_ok else "🔴 Failing"}
""")
    print("="*58 + "\n")


if __name__ == "__main__":
    run()
