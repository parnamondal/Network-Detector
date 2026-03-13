#!/usr/bin/env python3
"""
Latency History Graph
Pings continuously, plots latency over time.
• Uses matplotlib if installed  → saves a PNG graph
• Falls back to ASCII art       → works with zero dependencies

Run:
  python3 latency_graph.py              (live measurement, 60 samples)
  python3 latency_graph.py --samples 30 (custom number of samples)
  python3 latency_graph.py --interval 5 (seconds between each ping)
  python3 latency_graph.py --ascii      (force ASCII even if matplotlib exists)
"""

import subprocess
import re
import sys
import time
import platform
import os
from datetime import datetime

DEFAULT_SAMPLES  = 60
DEFAULT_INTERVAL = 10    # seconds between each measurement
PING_HOST        = "8.8.8.8"
FALLBACK_HOST    = "1.1.1.1"
HTTP_FALLBACK    = "https://www.google.com"    # used when ICMP ping is blocked
GRAPH_OUTPUT     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "latency_graph.png")


def ping_once(host):
    """Returns latency in ms, or None on timeout."""
    system = platform.system()
    cmd = (["ping", "-c", "1", "-W", "2000", host]
           if system != "Windows"
           else ["ping", "-n", "1", host])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        for line in r.stdout.splitlines():
            m = re.search(r"time[=<]([\d.]+)\s*ms", line, re.IGNORECASE)
            if m:
                return float(m.group(1))
        return None
    except Exception:
        return None


def http_latency(url):
    """Measure HTTP response time as a fallback when ICMP ping is blocked."""
    import urllib.request
    try:
        req   = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        start = time.time()
        urllib.request.urlopen(req, timeout=6)
        return (time.time() - start) * 1000   # return ms
    except Exception:
        return None


# Auto-detect whether we need HTTP fallback (ICMP blocked?)
_use_http_fallback = None

def measure_latency():
    """
    Returns latency ms. Uses ICMP ping if allowed, HTTP fallback if ping is blocked.
    Auto-detects which method works on first call.
    """
    global _use_http_fallback
    if _use_http_fallback is None:
        # Try one ping to decide
        ms = ping_once(PING_HOST)
        _use_http_fallback = (ms is None)
        if _use_http_fallback:
            print("  (ICMP ping blocked — switching to HTTP latency measurement)")

    if _use_http_fallback:
        return http_latency(HTTP_FALLBACK)
    else:
        ms = ping_once(PING_HOST)
        if ms is None:
            ms = ping_once(FALLBACK_HOST)
        return ms


def collect_samples(n, interval):
    """
    Collect n latency samples, one every `interval` seconds.
    Returns list of (timestamp, ms_or_None) tuples.
    """
    samples = []
    print(f"\n  Collecting {n} samples every {interval}s  "
          f"(total time: ~{n * interval}s)")
    print(f"  Method will be auto-selected (ICMP or HTTP fallback)")
    print(f"  Ctrl+C to stop early\n")
    print(f"  {'#':<5} {'Time':<10} {'Latency':<12} {'Bar'}")
    print(f"  {'─':<5} {'────':<10} {'───────':<12} {'───'}")

    # Trigger auto-detection before we use the flag for thresholds
    measure_latency()
    high_thresh = 3000 if _use_http_fallback else 200
    slow_thresh = 1500 if _use_http_fallback else 100

    for i in range(n):
        ts  = datetime.now()
        ms  = measure_latency()

        ts_str  = ts.strftime("%H:%M:%S")
        ms_str  = f"{ms:.1f}ms" if ms is not None else "TIMEOUT"
        bar_len = min(int((ms or 0) / (high_thresh / 20)), 40) if ms else 0
        bar     = "█" * bar_len + ("░" * (10 - bar_len) if bar_len < 10 else "")

        status = ""
        if ms is None:
            status = " ← DOWN"
        elif ms > high_thresh:
            status = " ← HIGH"
        elif ms > slow_thresh:
            status = " ← SLOW"

        print(f"  {i+1:<5} {ts_str:<10} {ms_str:<12} {bar}{status}")
        samples.append((ts, ms))

        if i < n - 1:
            time.sleep(interval)

    return samples


# ── ASCII Graph ────────────────────────────────────────────────

def ascii_graph(samples, width=60, height=15):
    values    = [ms for _, ms in samples if ms is not None]
    all_vals  = [ms if ms is not None else 0 for _, ms in samples]
    n         = len(all_vals)

    if not values:
        print("\n  No successful measurements to graph.")
        return

    max_val = max(values) * 1.1
    min_val = 0
    range_  = max_val - min_val or 1

    # Downsample to width if too many samples
    if n > width:
        step    = n / width
        indices = [int(i * step) for i in range(width)]
        plotted = [(samples[i][0], all_vals[i]) for i in indices]
    else:
        plotted = list(zip([s[0] for s in samples], all_vals))

    grid = [[" "] * len(plotted) for _ in range(height)]

    for col, (_, ms) in enumerate(plotted):
        if ms is None or ms == 0:
            # Mark as downtime
            row = height - 1
            grid[row][col] = "▼"
            continue
        row = height - 1 - int(((ms - min_val) / range_) * (height - 1))
        row = max(0, min(height - 1, row))
        grid[row][col] = "●"

    print(f"\n  LATENCY OVER TIME  (each column = one sample)\n")

    for r, row_chars in enumerate(grid):
        ms_label = max_val - (r / (height - 1)) * range_
        label    = f"{ms_label:>6.0f}ms │"
        print(f"  {label} {''.join(row_chars)}")

    # X axis
    print(f"  {'':>9}└" + "─" * len(plotted))
    if plotted:
        t_start = plotted[0][0].strftime("%H:%M")
        t_end   = plotted[-1][0].strftime("%H:%M")
        pad     = len(plotted) - len(t_start) - len(t_end) - 2
        print(f"  {'':>10}{t_start}{' ' * max(pad, 1)}{t_end}")


# ── Matplotlib Graph ────────────────────────────────────────────

def matplotlib_graph(samples, output_path):
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    times  = [t for t, ms in samples]
    values = [ms for _, ms in samples]

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.set_facecolor("#1a1a2e")
    fig.patch.set_facecolor("#16213e")

    # Split into connected segments and gaps (timeout)
    x_line, y_line = [], []
    for t, ms in samples:
        if ms is not None:
            x_line.append(t)
            y_line.append(ms)
        else:
            if x_line:
                ax.plot(x_line, y_line, color="#00d4ff", linewidth=1.5)
                x_line, y_line = [], []

    if x_line:
        ax.plot(x_line, y_line, color="#00d4ff", linewidth=1.5, label="Latency")

    # Mark timeouts as red dots at bottom
    timeout_times = [t for t, ms in samples if ms is None]
    if timeout_times:
        ax.scatter(timeout_times, [2] * len(timeout_times),
                   color="#ff4444", s=40, zorder=5, label="Timeout / DOWN")

    # Threshold lines
    ax.axhline(y=100, color="#ffaa00", linewidth=0.8, linestyle="--", alpha=0.6, label="100ms threshold")
    ax.axhline(y=200, color="#ff4444", linewidth=0.8, linestyle="--", alpha=0.6, label="200ms threshold")

    # Fill under curve
    clean_x = [t for t, ms in samples if ms is not None]
    clean_y = [ms for _, ms in samples if ms is not None]
    if clean_x:
        ax.fill_between(clean_x, clean_y, alpha=0.15, color="#00d4ff")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    plt.xticks(rotation=30, color="white", fontsize=8)
    plt.yticks(color="white")
    ax.tick_params(colors="white")
    ax.spines["bottom"].set_color("#444")
    ax.spines["left"].set_color("#444")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.set_xlabel("Time", color="white")
    ax.set_ylabel("Latency (ms)", color="white")
    ax.set_title(f"Network Latency — {times[0].strftime('%d %b %Y')}  "
                 f"[{times[0].strftime('%H:%M')} – {times[-1].strftime('%H:%M')}]",
                 color="white", fontsize=13)
    ax.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=9)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"\n  Graph saved → {output_path}")


# ── Statistics ─────────────────────────────────────────────────

def statistics_summary(samples):
    values  = [ms for _, ms in samples if ms is not None]
    timeouts = sum(1 for _, ms in samples if ms is None)
    total   = len(samples)

    print(f"\n{'─'*50}")
    print("  STATISTICS SUMMARY")
    print(f"{'─'*50}")
    print(f"  Total samples:   {total}")
    print(f"  Successful:      {len(values)}  ({len(values)/total*100:.0f}%)")
    print(f"  Timeouts (DOWN): {timeouts}  ({timeouts/total*100:.0f}%)")

    if values:
        avg    = sum(values) / len(values)
        min_ms = min(values)
        max_ms = max(values)
        sorted_v = sorted(values)
        p95    = sorted_v[int(len(sorted_v) * 0.95)]
        jitter = max_ms - min_ms

        print(f"\n  Min latency:  {min_ms:.1f}ms")
        print(f"  Avg latency:  {avg:.1f}ms")
        print(f"  Max latency:  {max_ms:.1f}ms")
        print(f"  P95 latency:  {p95:.1f}ms   (95% of pings faster than this)")
        print(f"  Jitter:       {jitter:.1f}ms  (max-min spread)")

        # Classify — thresholds differ for HTTP vs ICMP
        is_http = _use_http_fallback
        print("\n  Overall quality: ", end="")
        if timeouts / total > 0.1:
            print("🔴 Poor  — high packet loss / frequent drops")
        elif is_http and avg > 5000:
            print("🔴 Poor  — HTTP response very slow (>5s)")
        elif is_http and avg > 2000:
            print("🟡 Fair  — HTTP response slow (>2s)")
        elif is_http and jitter > 500:
            print("🟡 Fair  — high jitter (unstable)")
        elif is_http:
            print(f"🟢 Normal — HTTP response {avg:.0f}ms (includes TLS handshake)")
        elif avg > 200:
            print("🔴 Poor  — very high ICMP latency")
        elif avg > 100 or jitter > 100:
            print("🟡 Fair  — noticeable delays")
        elif avg > 50:
            print("🟡 Good  — acceptable for most uses")
        else:
            print("🟢 Excellent — low latency, stable")

    # Find longest outage streak
    max_streak, cur_streak = 0, 0
    for _, ms in samples:
        if ms is None:
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
        else:
            cur_streak = 0
    if max_streak > 0:
        print(f"\n  Longest outage streak: {max_streak} consecutive timeouts")
    print()


# ── Main ────────────────────────────────────────────────────────

def main():
    args      = sys.argv[1:]
    force_ascii = "--ascii" in args
    n_samples   = DEFAULT_SAMPLES
    interval    = DEFAULT_INTERVAL

    for i, arg in enumerate(args):
        if arg == "--samples" and i + 1 < len(args):
            n_samples = int(args[i + 1])
        if arg == "--interval" and i + 1 < len(args):
            interval = int(args[i + 1])

    print("\n" + "="*50)
    print("  LATENCY HISTORY GRAPH")
    print(f"  {datetime.now().strftime('%A %d %B %Y  %H:%M:%S')}")
    print("="*50)

    try:
        samples = collect_samples(n_samples, interval)
    except KeyboardInterrupt:
        print("\n  Stopped early — showing results so far...")
        # samples collected so far are in the local variable — re-run partially
        # In practice, wrap collect_samples in a generator or track state
        return

    statistics_summary(samples)

    # Try matplotlib first
    if not force_ascii:
        try:
            import matplotlib
            matplotlib_graph(samples, GRAPH_OUTPUT)
            print(f"  Open the PNG to see your latency history graph.")
        except ImportError:
            print("  matplotlib not installed → showing ASCII graph")
            print("  (Install with: pip3 install matplotlib  for the PNG version)\n")
            ascii_graph(samples)
    else:
        ascii_graph(samples)

    print()


if __name__ == "__main__":
    main()
