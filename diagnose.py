#!/usr/bin/env python3
"""
Network Fault Detector
Detects WHERE your internet is failing — router, ISP, fiber, or DNS.
Run: python3 diagnose.py
"""

import subprocess
import socket
import platform
import urllib.request
import re
import sys
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────────
PUBLIC_IPS      = ["8.8.8.8", "1.1.1.1", "208.67.222.222"]   # Google, Cloudflare, OpenDNS
TEST_DOMAINS    = ["google.com", "youtube.com", "amazon.com"]
HTTP_CHECK_URL  = "http://connectivitycheck.gstatic.com/generate_204"
PING_COUNT      = 4
HIGH_LATENCY_MS = 150   # ms above this = degraded
HIGH_LOSS_PCT   = 20    # % packet loss above this = degraded


# ── Helpers ──────────────────────────────────────────────────────────────────

def header(title):
    print(f"\n{'─'*52}")
    print(f"  {title}")
    print(f"{'─'*52}")

def status(ok, label, detail=""):
    icon = "✅" if ok else "❌"
    print(f"  {icon}  {label}" + (f"  |  {detail}" if detail else ""))


def get_default_gateway():
    """Returns the router IP (default gateway) or None if not connected."""
    system = platform.system()
    try:
        if system == "Darwin":
            result = subprocess.run(
                ["route", "-n", "get", "default"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "gateway:" in line:
                    return line.split(":")[-1].strip()

        elif system == "Linux":
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True, timeout=5
            )
            parts = result.stdout.split()
            if "via" in parts:
                return parts[parts.index("via") + 1]

        elif system == "Windows":
            result = subprocess.run(
                ["ipconfig"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "Default Gateway" in line:
                    gw = line.split(":")[-1].strip()
                    if gw and gw != "":
                        return gw
    except Exception:
        pass
    return None


def ping(host, count=4):
    """
    Returns (reachable: bool, avg_ms: float|None, loss_pct: float)
    Works on Mac, Linux, Windows.
    """
    system = platform.system()
    cmd = (
        ["ping", "-c", str(count), "-W", "2000", host]
        if system != "Windows"
        else ["ping", "-n", str(count), host]
    )
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        output = result.stdout + result.stderr
        loss = 100.0
        avg_ms = None

        for line in output.splitlines():
            # Packet loss (Mac/Linux: "X% packet loss", Windows: "X% loss")
            m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(packet\s*)?loss", line, re.IGNORECASE)
            if m:
                loss = float(m.group(1))

            # Avg latency Mac/Linux: "min/avg/max/stddev = x/x/x/x ms"
            m = re.search(r"[\d.]+/([\d.]+)/[\d.]+", line)
            if m:
                avg_ms = float(m.group(1))

            # Windows: "Average = Xms"
            m = re.search(r"Average\s*=\s*(\d+)\s*ms", line, re.IGNORECASE)
            if m:
                avg_ms = float(m.group(1))

        return (loss < 100), avg_ms, loss

    except subprocess.TimeoutExpired:
        return False, None, 100.0
    except Exception:
        return False, None, 100.0


def check_dns(domain):
    """Returns True if DNS can resolve the domain name."""
    try:
        socket.setdefaulttimeout(5)
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False


def check_http():
    """Returns True if actual HTTP request succeeds (full connectivity)."""
    try:
        req = urllib.request.urlopen(HTTP_CHECK_URL, timeout=5)
        return req.status == 204
    except Exception:
        try:
            req = urllib.request.urlopen("https://www.google.com", timeout=5)
            return req.status == 200
        except Exception:
            return False


def get_traceroute_first_hop(gateway):
    """Gets the ISP-side gateway — the first hop BEYOND your router."""
    system = platform.system()
    cmd = (
        ["traceroute", "-m", "3", "-w", "2", "8.8.8.8"]
        if system != "Windows"
        else ["tracert", "-h", "3", "8.8.8.8"]
    )
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        lines = result.stdout.splitlines()
        for line in lines[1:]:           # skip header line
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
            if m:
                ip = m.group(1)
                if ip != gateway:       # skip the router itself
                    return ip
    except Exception:
        pass
    return None


# ── Main Diagnostic ───────────────────────────────────────────────────────────

def diagnose():
    print("\n" + "="*52)
    print("  NETWORK FAULT DETECTOR")
    print(f"  {datetime.now().strftime('%A %d %B %Y  %H:%M:%S')}")
    print("="*52)

    # ──────────────────────────────────────────────────────
    # WITHOUT ROUTER CHECK
    # If no default gateway exists → device is not connected to anything
    # ──────────────────────────────────────────────────────
    header("STEP 1 of 5 — Checking local network (router)")
    print("  Looking for your router / default gateway...")

    gateway = get_default_gateway()

    if not gateway:
        status(False, "No gateway found")
        print("""
  ┌─────────────────────────────────────────────┐
  │  DIAGNOSIS: WITHOUT ROUTER                  │
  │                                             │
  │  Your device is NOT connected to any        │
  │  network at all.                            │
  │                                             │
  │  What this means:                           │
  │  • WiFi is turned off, OR                   │
  │  • You are not connected to any WiFi SSID   │
  │  • No ethernet cable plugged in             │
  │  • Network interface is disabled            │
  │                                             │
  │  What to do:                                │
  │  → Turn on WiFi and connect to a network    │
  │  → Or plug in ethernet cable               │
  └─────────────────────────────────────────────┘""")
        sys.exit(1)

    status(True, f"Router / Gateway found", f"IP: {gateway}")

    # ──────────────────────────────────────────────────────
    # WITH ROUTER CHECK — Ping the router
    # ──────────────────────────────────────────────────────
    print(f"\n  Pinging your router at {gateway}...")
    router_ok, router_ms, router_loss = ping(gateway, count=PING_COUNT)

    if not router_ok:
        status(False, f"Router at {gateway} not responding")
        print(f"""
  ┌─────────────────────────────────────────────┐
  │  DIAGNOSIS: ROUTER IS DOWN / UNREACHABLE    │
  │                                             │
  │  Your device sees the router but cannot     │
  │  communicate with it.                       │
  │                                             │
  │  Likely causes:                             │
  │  • Router is powered off or crashed         │
  │  • WiFi signal too weak (move closer)       │
  │  • Router is overloaded (too many devices)  │
  │  • Faulty ethernet cable                    │
  │                                             │
  │  What to do:                                │
  │  → Unplug router power, wait 30 seconds,    │
  │    plug back in                             │
  │  → Move closer to the router               │
  │  → Try connecting via cable (not WiFi)      │
  └─────────────────────────────────────────────┘""")
        sys.exit(1)

    ms_str = f"{router_ms:.1f}ms" if router_ms else "unknown"
    status(True, f"Router responding", f"Latency: {ms_str} | Loss: {router_loss:.0f}%")

    if router_ms and router_ms > 20:
        print(f"  ⚠️   Router latency is high ({router_ms:.0f}ms). WiFi signal may be weak.")

    # ──────────────────────────────────────────────────────
    # ISP GATEWAY — 1 hop beyond the router
    # ──────────────────────────────────────────────────────
    header("STEP 2 of 5 — Checking ISP connection")
    print("  Finding ISP gateway (first hop beyond your router)...")
    isp_gateway = get_traceroute_first_hop(gateway)

    if isp_gateway:
        print(f"  ISP Gateway detected: {isp_gateway}")
        isp_ok, isp_ms, isp_loss = ping(isp_gateway, count=PING_COUNT)
        ms_str = f"{isp_ms:.1f}ms" if isp_ms else "timeout"
        status(isp_ok, f"ISP gateway {isp_gateway}", f"Latency: {ms_str} | Loss: {isp_loss:.0f}%")
    else:
        print("  (ISP gateway not detectable via traceroute — skipping)")

    # ──────────────────────────────────────────────────────
    # PUBLIC INTERNET — Google/Cloudflare DNS IPs
    # ──────────────────────────────────────────────────────
    header("STEP 3 of 5 — Checking public internet reach")
    inet_results = []
    for ip in PUBLIC_IPS:
        ok, ms, loss = ping(ip, count=PING_COUNT)
        inet_results.append((ip, ok, ms, loss))
        ms_str = f"{ms:.1f}ms" if ms else "timeout"
        status(ok, ip, f"Latency: {ms_str} | Loss: {loss:.0f}%")

    internet_ok = any(r[1] for r in inet_results)

    if not internet_ok:
        # Pings failed — but could be firewall blocking ICMP, not actual outage.
        # Fallback: try DNS and HTTP before concluding it's an ISP fault.
        print("\n  Pings blocked or failed. Running fallback check (DNS + HTTP)...")
        dns_fallback  = check_dns("google.com")
        http_fallback = check_http()

        if dns_fallback or http_fallback:
            print(f"  ⚠️   Ping is BLOCKED (firewall / corporate network policy)")
            print(f"  ✅   But DNS and HTTP work → internet IS reachable")
            print(f"\n  NOTE: This is a corporate or VPN network.")
            print(f"  ICMP ping packets are blocked by firewall rules.")
            print(f"  Switching to DNS/HTTP-based testing for remaining steps.\n")
            internet_ok = True   # continue with DNS/HTTP path
        else:
            print(f"""
  ┌─────────────────────────────────────────────┐
  │  DIAGNOSIS: ISP / FIBER ISSUE               │
  │                                             │
  │  Your router is working fine.               │
  │  BUT no signal is reaching the internet.    │
  │                                             │
  │  Where the fault likely is:                 │
  │  • Fiber optic cable cut (between your      │
  │    area and ISP exchange)                   │
  │  • ISP exchange is down                     │
  │  • WAN port on your router disconnected     │
  │  • ISP-side outage in your area             │
  │                                             │
  │  What to do:                                │
  │  → Check if neighbors have internet         │
  │  → Call your ISP and report outage          │
  │  → Check ISP's outage status page           │
  │  → Use mobile data as backup               │
  └─────────────────────────────────────────────┘""")
            sys.exit(1)

    # Calculate average latency and loss
    working = [(ms, loss) for (_, ok, ms, loss) in inet_results if ok and ms]
    avg_latency = sum(ms for ms, _ in working) / len(working) if working else 0
    avg_loss    = sum(loss for _, loss in working) / len(working) if working else 0

    # ──────────────────────────────────────────────────────
    # DNS CHECK
    # ──────────────────────────────────────────────────────
    header("STEP 4 of 5 — Checking DNS (name resolution)")
    dns_results = []
    for domain in TEST_DOMAINS:
        ok = check_dns(domain)
        dns_results.append(ok)
        status(ok, domain)

    dns_ok = any(dns_results)

    if not dns_ok:
        print(f"""
  ┌─────────────────────────────────────────────┐
  │  DIAGNOSIS: DNS FAILURE ONLY                │
  │                                             │
  │  Internet is reachable by IP address,       │
  │  but domain names cannot be resolved.       │
  │  (Like knowing roads exist but GPS is off)  │
  │                                             │
  │  Fix:                                       │
  │  → Go to Network Settings → DNS             │
  │  → Change DNS server to: 8.8.8.8           │
  │  → Secondary: 1.1.1.1                      │
  └─────────────────────────────────────────────┘""")
        sys.exit(1)

    # ──────────────────────────────────────────────────────
    # HTTP CHECK
    # ──────────────────────────────────────────────────────
    header("STEP 5 of 5 — Checking web connectivity (HTTP)")
    http_ok = check_http()
    status(http_ok, "HTTP web access")

    # ──────────────────────────────────────────────────────
    # FINAL DIAGNOSIS
    # ──────────────────────────────────────────────────────
    header("FINAL VERDICT")

    if avg_loss > HIGH_LOSS_PCT:
        print(f"""
  ⚠️   DEGRADED — HIGH PACKET LOSS
  Packet loss: {avg_loss:.0f}%  (acceptable: <5%)

  What this means:
  Data is being sent but packets are being
  dropped on the way. Internet exists but
  is unreliable.

  Likely causes:
  • Damaged fiber / cable (partial cut)
  • Overloaded ISP exchange in your area
  • Faulty router hardware
  • WiFi interference (change WiFi channel)

  Impact on you:
  → Video calls: Will drop and freeze
  → Gaming: Unplayable (high packet loss)
  → Downloads: Slow and may fail
  → Browsing: Intermittent""")

    elif avg_latency > HIGH_LATENCY_MS:
        print(f"""
  ⚠️   DEGRADED — HIGH LATENCY
  Average latency: {avg_latency:.0f}ms  (healthy: <50ms for broadband)

  What this means:
  Internet works but responses are slow.
  Like the road exists but traffic is heavy.

  Likely causes:
  • ISP network congestion (evening peak hours)
  • Long routing path (data going far away)
  • Shared bandwidth overloaded (too many users)

  Impact on you:
  → Video calls: Noticeable delay
  → Gaming: Lag (high ping)
  → Browsing: Loads but feels slow
  → Downloads: Normal speed""")

    elif not http_ok:
        print(f"""
  ⚠️   HTTP BLOCKED
  Pings work but web pages are blocked.

  Likely causes:
  • Network firewall blocking HTTP
  • Captive portal (hotel/public WiFi)
  • ISP blocking specific content""")

    else:
        print(f"""
  ✅  CONNECTION IS HEALTHY

  Router latency:   {router_ms:.1f}ms
  Internet latency: {avg_latency:.1f}ms
  Packet loss:      {avg_loss:.0f}%
  DNS:              Working
  HTTP:             Working

  Everything is fine. No faults detected.""")

    print("\n" + "="*52 + "\n")


if __name__ == "__main__":
    diagnose()
