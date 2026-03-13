#!/usr/bin/env python3
"""
Speed Test — No external libraries needed.
Downloads a test file and measures real throughput at each layer.
Run: python3 speedtest.py
"""

import urllib.request
import socket
import subprocess
import time
import re
import platform
from datetime import datetime

# ── Test file URLs (public CDN files of known size) ──────
# Multiple fallback URLs in case some are blocked by firewall
SPEED_TEST_URLS = [
    ("10 MB",  "https://speed.cloudflare.com/__down?bytes=10000000"),
    ("10 MB",  "http://ipv4.download.thinkbroadband.com/10MB.zip"),
    ("5 MB",   "https://speed.hetzner.de/5MB.bin"),
    ("1 MB",   "https://httpbin.org/bytes/1000000"),
    ("1 MB",   "http://ipv4.download.thinkbroadband.com/1MB.zip"),
]

LATENCY_HOSTS = [
    ("Google DNS",      "8.8.8.8"),
    ("Cloudflare DNS",  "1.1.1.1"),
    ("Your Router",     None),       # filled in dynamically
]


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


def measure_latency(host, count=5):
    """Returns (avg_ms, min_ms, max_ms, loss_pct)."""
    system = platform.system()
    cmd = (
        ["ping", "-c", str(count), "-W", "2000", host]
        if system != "Windows"
        else ["ping", "-n", str(count), host]
    )
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        output = r.stdout
        loss, avg_ms, min_ms, max_ms = 100.0, None, None, None

        for line in output.splitlines():
            m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(packet\s*)?loss", line, re.IGNORECASE)
            if m:
                loss = float(m.group(1))
            # Mac/Linux: min/avg/max/stddev
            m = re.search(r"([\d.]+)/([\d.]+)/([\d.]+)/[\d.]+\s*ms", line)
            if m:
                min_ms = float(m.group(1))
                avg_ms = float(m.group(2))
                max_ms = float(m.group(3))

        return avg_ms, min_ms, max_ms, loss
    except Exception:
        return None, None, None, 100.0


def download_speed_test(label, url, size_bytes):
    """Downloads a file and returns speed in Mbps. Tries all URLs, stops at first success."""
    print(f"  Downloading {label} test file...", end="", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        start   = time.time()
        resp    = urllib.request.urlopen(req, timeout=30)
        data    = resp.read()
        elapsed = time.time() - start

        actual_bytes = len(data)
        if actual_bytes < 10000:          # too small = likely an error page
            print(f"  Skipped (response too small: {actual_bytes} bytes)")
            return None
        mbps = (actual_bytes * 8) / (elapsed * 1_000_000)
        print(f"  {mbps:.1f} Mbps  ({elapsed:.1f}s, {actual_bytes/1_000_000:.1f} MB)")
        return mbps
    except Exception as e:
        print(f"  Blocked/Failed ({type(e).__name__})")
        return None


def classify_speed(mbps):
    if mbps is None:
        return "Cannot test"
    if mbps >= 100:  return "Excellent  (100+ Mbps)"
    if mbps >= 50:   return "Good       (50-100 Mbps)"
    if mbps >= 20:   return "Fair       (20-50 Mbps)"
    if mbps >= 5:    return "Poor       (5-20 Mbps)"
    if mbps >= 1:    return "Very Poor  (1-5 Mbps)"
    return "Unusable   (<1 Mbps)"


def classify_latency(ms):
    if ms is None:   return "Cannot test"
    if ms < 20:      return "Excellent  (<20ms)"
    if ms < 50:      return "Good       (20-50ms)"
    if ms < 100:     return "Fair       (50-100ms)"
    if ms < 200:     return "Poor       (100-200ms)"
    return "Very Poor  (>200ms)"


def what_can_you_do(mbps):
    """Plain-English usability report."""
    if mbps is None or mbps < 0.5:
        return [
            "❌ Video calls: Not possible",
            "❌ YouTube:     Not possible",
            "❌ Downloads:   Not possible",
            "⚠️  WhatsApp:   Maybe text only",
        ]
    checks = [
        ("✅" if mbps >= 1   else "❌",  "WhatsApp / Telegram messages"),
        ("✅" if mbps >= 2   else "❌",  "Audio calls"),
        ("✅" if mbps >= 5   else "⚠️ ", "YouTube 480p"),
        ("✅" if mbps >= 10  else "❌",  "Video calls (Zoom / Meet)"),
        ("✅" if mbps >= 15  else "⚠️ ", "YouTube 1080p HD"),
        ("✅" if mbps >= 25  else "❌",  "Multiple devices streaming"),
        ("✅" if mbps >= 50  else "❌",  "4K streaming / large downloads"),
    ]
    return [f"{icon} {label}" for icon, label in checks]


def run():
    print("\n" + "="*52)
    print("  NETWORK SPEED & QUALITY TESTER")
    print(f"  {datetime.now().strftime('%A %d %B %Y  %H:%M:%S')}")
    print("="*52)

    gateway = get_gateway()

    # ── Latency at each layer ─────────────────────────────
    print("\n── LATENCY BY LAYER ─────────────────────────────\n")

    layer_results = {}

    # Router latency (local, no internet needed)
    if gateway:
        avg, mn, mx, loss = measure_latency(gateway, count=5)
        ms_str = f"{avg:.1f}ms" if avg else "no response"
        loss_str = f"Loss: {loss:.0f}%"
        print(f"  Your Router  ({gateway})  →  {ms_str}  |  {loss_str}")
        layer_results["router"] = avg
        if avg and avg > 5:
            print(f"  ⚠️   Router latency {avg:.0f}ms is high (should be <2ms on good WiFi)")
    else:
        print("  Your Router  →  ❌ Not found (no network)")

    # ISP / Internet latency
    for label, host in [("Google DNS", "8.8.8.8"), ("Cloudflare", "1.1.1.1")]:
        avg, mn, mx, loss = measure_latency(host, count=5)
        if avg:
            print(f"  {label:<16} ({host})  →  {avg:.1f}ms  |  Loss: {loss:.0f}%  |  {classify_latency(avg)}")
            layer_results["internet"] = avg
        else:
            print(f"  {label:<16} ({host})  →  ❌ No response")

    # ── Download Speed ────────────────────────────────────
    print("\n── DOWNLOAD SPEED ───────────────────────────────\n")

    speeds = []
    for label, url in SPEED_TEST_URLS:
        mbps = download_speed_test(label, url, None)
        if mbps:
            speeds.append(mbps)
            break    # stop after first successful download

    avg_speed = sum(speeds) / len(speeds) if speeds else None

    if avg_speed:
        print(f"\n  Average download speed: {avg_speed:.1f} Mbps")
        print(f"  Quality rating:         {classify_speed(avg_speed)}")
    else:
        print("  Could not measure speed (no internet)")

    # ── What can you actually do? ─────────────────────────
    print("\n── WHAT CAN YOU DO WITH THIS CONNECTION? ────────\n")
    for line in what_can_you_do(avg_speed):
        print(f"  {line}")

    # ── Where is the bottleneck? ──────────────────────────
    print("\n── WHERE IS THE BOTTLENECK? ─────────────────────\n")

    router_ms  = layer_results.get("router")
    inet_ms    = layer_results.get("internet")

    if not router_ms:
        print("  Problem: Cannot reach router → Device/WiFi issue")
    elif not inet_ms and not avg_speed:
        print("  Problem: Router OK, but internet unreachable")
        print("  → Fault between router and ISP (fiber/cable/WAN)")
    elif not inet_ms and avg_speed:
        print("  Note: ICMP ping blocked (corporate/VPN firewall)")
        print("  → Bottleneck analysis based on download speed only")
        if avg_speed < 5:
            print(f"  → Speed is low ({avg_speed:.1f} Mbps) — ISP congestion or throttling")
        else:
            print(f"  → Speed is {avg_speed:.1f} Mbps — connection is functional")
    elif router_ms > 10:
        print(f"  Bottleneck: Router ({router_ms:.0f}ms) — weak WiFi or overloaded router")
    elif avg_speed and avg_speed < 5:
        inet_ok = inet_ms and inet_ms < 100
        if inet_ok:
            print(f"  Bottleneck: ISP is throttling or congested")
            print(f"  (Pings work fine at {inet_ms:.0f}ms, but download is slow)")
            print(f"  → ISP exchange overloaded, or your plan is limited")
        else:
            print(f"  Bottleneck: Both latency and speed are poor")
            print(f"  → Likely cable fault between your area and ISP")
    elif avg_speed and avg_speed > 50:
        print(f"  ✅ No bottleneck detected. Connection is healthy.")
    else:
        print(f"  Partial performance. May be ISP-side congestion.")

    print("\n" + "="*52 + "\n")


if __name__ == "__main__":
    run()
