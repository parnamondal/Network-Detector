#!/usr/bin/env python3
"""
Deep Traceroute Analyzer
Shows EVERY hop on the path to the internet and identifies exactly
WHERE latency spikes or packets disappear.

Run: python3 traceroute_deep.py
     python3 traceroute_deep.py 8.8.8.8        (custom target)
     python3 traceroute_deep.py --all           (trace to 4 destinations)
"""

import subprocess
import re
import sys
import platform
from datetime import datetime

TARGETS = {
    "Google DNS":      "8.8.8.8",
    "Cloudflare DNS":  "1.1.1.1",
    "Google.com":      "google.com",
    "Amazon.com":      "amazon.com",
}

MAX_HOPS    = 20
PROBE_COUNT = 3          # packets per hop
TIMEOUT_SEC = 2


def bar_ms(ms, max_ms=200, width=20):
    """ASCII latency bar. Scales to max_ms."""
    if ms is None:
        return "░" * width
    filled = min(int((ms / max_ms) * width), width)
    return "█" * filled + "░" * (width - filled)


def color_ms(ms):
    """Return a label indicating latency quality."""
    if ms is None:    return "timeout "
    if ms < 20:       return f"{ms:>6.1f}ms  excellent"
    if ms < 50:       return f"{ms:>6.1f}ms  good     "
    if ms < 100:      return f"{ms:>6.1f}ms  fair     "
    if ms < 200:      return f"{ms:>6.1f}ms  poor     "
    return             f"{ms:>6.1f}ms  very poor"


def parse_traceroute(output):
    """
    Parse traceroute output into a list of hop dicts.
    Each hop: {num, ip, hostname, latencies: [ms|None, ...], avg_ms}
    """
    hops = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # Match hop number at start
        m = re.match(r"^\s*(\d+)\s+", line)
        if not m:
            continue
        hop_num = int(m.group(1))

        # All-timeout hop
        if re.match(r"^\s*\d+\s+\*\s+\*\s+\*", line):
            hops.append({
                "num": hop_num, "ip": None, "hostname": "*",
                "latencies": [None, None, None], "avg_ms": None
            })
            continue

        # Extract IPs
        ips = re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", line)
        ip  = ips[0] if ips else None

        # Extract hostname (word before the IP, if any)
        hostname = None
        m2 = re.search(r"([a-zA-Z][a-zA-Z0-9._-]+)\s+\(?" + re.escape(ip or ""), line)
        if m2 and ip:
            hostname = m2.group(1)

        # Extract latency values (all floats/ints followed by ms)
        latencies_raw = re.findall(r"([\d.]+)\s*ms", line)
        latencies = [float(v) for v in latencies_raw[:3]]

        # Pad to 3
        while len(latencies) < 3:
            latencies.append(None)

        valid = [v for v in latencies if v is not None]
        avg_ms = sum(valid) / len(valid) if valid else None

        hops.append({
            "num":       hop_num,
            "ip":        ip,
            "hostname":  hostname or ip or "*",
            "latencies": latencies,
            "avg_ms":    avg_ms,
        })

    return hops


def _http_path_check(target):
    """
    Fallback when ICMP/UDP traceroute is blocked.
    Measures HTTP response time to multiple targets to approximate
    relative network distance and health.
    """
    import urllib.request
    import time

    # If target is an IP, try HTTPS to it; otherwise use as hostname
    test_targets = [
        ("Your router gateway",  None),           # local
        ("Cloudflare edge",      "https://www.cloudflare.com"),
        ("Google",               "https://www.google.com"),
        ("Amazon",               "https://www.amazon.com"),
        ("GitHub",               "https://github.com"),
    ]

    print(f"  {'DESTINATION':<28} {'HTTP LATENCY':<16} {'QUALITY'}")
    print(f"  {'───────────':<28} {'────────────':<16} {'───────'}")

    prev_ms = None
    for label, url in test_targets:
        if url is None:
            # Ping the local router
            gw = get_gateway()
            if gw:
                ok, ms = ping_fast(gw)
                ms_str = f"{ms:.1f}ms" if ms else "—"
                print(f"  {label:<28} {ms_str:<16} {'🟢 LOCAL'}")
            continue
        try:
            req   = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            start = time.time()
            urllib.request.urlopen(req, timeout=8)
            ms    = (time.time() - start) * 1000
            ms_str = f"{ms:.0f}ms"
            quality = "🟢 Good" if ms < 1500 else ("🟡 Slow" if ms < 3000 else "🔴 Very slow")
            print(f"  {label:<28} {ms_str:<16} {quality}")
            prev_ms = ms
        except Exception:
            print(f"  {label:<28} {'unreachable':<16} 🔴 Blocked/Down")

    print(f"""
  NOTE: Full hop-by-hop trace is not possible because
  this network (corporate/VPN) blocks ICMP and UDP probes.
  The HTTP latency table above shows relative reachability
  at each major internet layer.""")


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


def classify_hop(ip):
    """Label hop as: LOCAL, ISP, CDN, BACKBONE, or INTERNET."""
    if ip is None:
        return "UNKNOWN"
    # Private ranges
    if (ip.startswith("192.168.") or ip.startswith("10.") or
            ip.startswith("172.16.") or ip.startswith("172.17.")):
        return "LOCAL"
    # Well-known CDN/DNS
    cdn_prefixes = ["8.8.", "1.1.", "104.16.", "151.101.", "23.32.",
                    "104.17.", "104.18.", "104.19.", "13.107."]
    if any(ip.startswith(p) for p in cdn_prefixes):
        return "CDN/DNS"
    # ISP-style (heuristic: if hostname contains isp keywords)
    return "INTERNET"


def find_spike(hops):
    """Find the hop where latency first jumps significantly (>2x previous)."""
    prev_ms = None
    for hop in hops:
        if hop["avg_ms"] is None:
            continue
        if prev_ms and hop["avg_ms"] > prev_ms * 2.5 and hop["avg_ms"] > 30:
            return hop["num"], hop["avg_ms"], prev_ms
        prev_ms = hop["avg_ms"]
    return None, None, None


def run_traceroute(target, label):
    system  = platform.system()
    cmd = (
        ["traceroute", "-m", str(MAX_HOPS), "-q", str(PROBE_COUNT),
         "-w", str(TIMEOUT_SEC), target]
        if system != "Windows"
        else ["tracert", "-h", str(MAX_HOPS), target]
    )

    print(f"\n{'='*62}")
    print(f"  TRACEROUTE → {label}  ({target})")
    print(f"  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*62}")
    print(f"  Running (max {MAX_HOPS} hops, {PROBE_COUNT} probes/hop)...")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=MAX_HOPS * PROBE_COUNT * TIMEOUT_SEC + 10
        )
        output = result.stdout
    except subprocess.TimeoutExpired:
        print("  Traceroute timed out.")
        return
    except Exception as e:
        print(f"  Error: {e}")
        return

    hops = parse_traceroute(output)

    if not hops:
        print("  No hops returned. Network may be completely unreachable.")
        return

    # Check if ALL hops timed out — likely corporate firewall blocking probes
    all_timeout = all(h["avg_ms"] is None for h in hops)
    if all_timeout:
        print("\n  All hops timed out — ICMP/UDP probes are blocked by firewall.")
        print("  Running HTTP-based path quality check as fallback...\n")
        _http_path_check(target)
        return

    # ── Table header ──────────────────────────────────────────
    print(f"\n  {'HOP':<4} {'IP ADDRESS':<18} {'LATENCY (avg)':<16}"
          f"{'QUALITY BAR':<22} {'ZONE'}")
    print(f"  {'───':<4} {'──────────':<18} {'─────────────':<16}"
          f"{'───────────':<22} {'────'}")

    spike_hop, spike_ms, before_ms = find_spike(hops)
    prev_avg = None

    for hop in hops:
        num  = hop["num"]
        ip   = hop["ip"] or "*"
        avg  = hop["avg_ms"]
        zone = classify_hop(hop["ip"])

        # Detect jump from previous hop
        jump_marker = ""
        if prev_avg and avg and avg > prev_avg * 2.5 and avg > 30:
            jump_marker = " ◄ SPIKE"
        elif avg is None:
            jump_marker = " ◄ TIMEOUT"

        lat_str = color_ms(avg)
        b       = bar_ms(avg)

        print(f"  {num:<4} {ip:<18} {lat_str:<16} {b:<22} {zone}{jump_marker}")
        prev_avg = avg if avg else prev_avg

    # ── Analysis ──────────────────────────────────────────────
    print(f"\n{'─'*62}")
    print("  ANALYSIS")
    print(f"{'─'*62}")

    last_ok = next((h for h in reversed(hops) if h["avg_ms"] is not None), None)
    all_timeout = all(h["avg_ms"] is None for h in hops)
    timeouts_at_end = all(h["avg_ms"] is None for h in hops[-3:]) if len(hops) >= 3 else False

    if all_timeout:
        print("  ❌ All hops timed out — likely no route to this destination.")
    elif timeouts_at_end and last_ok:
        print(f"  ⚠️  Path reaches hop {last_ok['num']} ({last_ok['ip']}) then disappears.")
        print(f"     Hops {last_ok['num']+1}+ do not respond.")
        print(f"     This may be a firewall filtering ICMP (not a real break).")
        print(f"     If HTTP to this destination works, it's just firewall policy.")
    else:
        print(f"  ✅ Route found to destination ({len(hops)} hops)")

    if spike_hop:
        print(f"\n  🔴 Latency spike at hop {spike_hop}: {before_ms:.0f}ms → {spike_ms:.0f}ms")
        spike_obj = next((h for h in hops if h["num"] == spike_hop), None)
        if spike_obj and spike_obj["ip"]:
            zone = classify_hop(spike_obj["ip"])
            if zone == "LOCAL":
                print(f"     → Spike is inside your LOCAL network. Check router/switch.")
            elif zone == "CDN/DNS":
                print(f"     → Spike is at a CDN/DNS node. Likely routing decision, not a fault.")
            else:
                print(f"     → Spike is in the INTERNET backbone (normal for long distances).")
    else:
        print("  ✅ No significant latency spike found on this path.")

    # ── Hop summary ───────────────────────────────────────────
    valid_hops = [h for h in hops if h["avg_ms"] is not None]
    if valid_hops:
        avg_all = sum(h["avg_ms"] for h in valid_hops) / len(valid_hops)
        max_hop = max(valid_hops, key=lambda h: h["avg_ms"])
        print(f"\n  Total hops:    {len(hops)}")
        print(f"  Avg latency:   {avg_all:.1f}ms across all hops")
        print(f"  Slowest hop:   Hop {max_hop['num']} ({max_hop['ip']}) at {max_hop['avg_ms']:.1f}ms")
    print()


def main():
    args = sys.argv[1:]

    if "--all" in args:
        targets = list(TARGETS.items())
    elif args and not args[0].startswith("--"):
        # Custom target
        targets = [(args[0], args[0])]
    else:
        # Default: just Google DNS
        targets = [("Google DNS", "8.8.8.8")]

    print("\n" + "="*62)
    print("  DEEP TRACEROUTE ANALYZER")
    print(f"  {datetime.now().strftime('%A %d %B %Y  %H:%M:%S')}")
    print("="*62)
    print("  Usage:")
    print("    python3 traceroute_deep.py              (trace to 8.8.8.8)")
    print("    python3 traceroute_deep.py 1.1.1.1      (custom target)")
    print("    python3 traceroute_deep.py --all        (trace 4 destinations)")

    for label, target in targets:
        run_traceroute(target, label)


if __name__ == "__main__":
    main()
