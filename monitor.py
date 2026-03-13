#!/usr/bin/env python3
"""
Continuous Network Monitor
Runs every 30 seconds, logs health, detects degradation trends.
Run: python3 monitor.py
Stop: Ctrl+C  (shows summary at end)
"""

import subprocess
import socket
import re
import time
import sys
import platform
from datetime import datetime
from collections import deque

# ── Config ───────────────────────────────────────────────
CHECK_INTERVAL_SEC  = 30        # how often to check
HISTORY_SIZE        = 20        # keep last N readings
ALERT_LOSS_PCT      = 10        # alert if loss exceeds this
ALERT_LATENCY_MS    = 150       # alert if latency exceeds this
PING_HOST           = "8.8.8.8" # what to ping for internet check
LOG_FILE            = "network_log.txt"

# ── State ────────────────────────────────────────────────
history   = deque(maxlen=HISTORY_SIZE)
was_down  = False
outage_start = None


def ping_once(host):
    """Single ping. Returns (ok, ms, loss_pct)."""
    system = platform.system()
    cmd = (
        ["ping", "-c", "3", "-W", "2000", host]
        if system != "Windows"
        else ["ping", "-n", "3", host]
    )
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout + result.stderr
        loss, avg_ms = 100.0, None

        for line in output.splitlines():
            m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(packet\s*)?loss", line, re.IGNORECASE)
            if m:
                loss = float(m.group(1))
            m = re.search(r"[\d.]+/([\d.]+)/[\d.]+", line)
            if m:
                avg_ms = float(m.group(1))
            m = re.search(r"Average\s*=\s*(\d+)\s*ms", line, re.IGNORECASE)
            if m:
                avg_ms = float(m.group(1))

        return (loss < 100), avg_ms, loss
    except Exception:
        return False, None, 100.0


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


def check_dns():
    try:
        socket.setdefaulttimeout(3)
        socket.getaddrinfo("google.com", None)
        return True
    except Exception:
        return False


def classify_health(ok, ms, loss):
    """Returns (label, symbol) based on connection quality."""
    if not ok:
        return "DOWN",      "🔴"
    if loss > ALERT_LOSS_PCT or (ms and ms > ALERT_LATENCY_MS):
        return "DEGRADED",  "🟡"
    return "HEALTHY",       "🟢"


def log_event(message):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    print(f"\n  *** ALERT: {message} ***")
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def trend_analysis():
    """Look at recent history and warn if degradation is building."""
    if len(history) < 5:
        return
    recent = list(history)[-5:]
    losses    = [r["loss"] for r in recent if r["ok"]]
    latencies = [r["ms"]   for r in recent if r["ok"] and r["ms"]]

    if not losses:
        return

    avg_loss    = sum(losses) / len(losses)
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    # Worsening trend
    if len(latencies) >= 3:
        if latencies[-1] > latencies[-2] > latencies[-3]:
            print(f"  ⚠️  TREND: Latency rising each check "
                  f"({latencies[-3]:.0f} → {latencies[-2]:.0f} → {latencies[-1]:.0f}ms)")

    if avg_loss > ALERT_LOSS_PCT:
        print(f"  ⚠️  TREND: Average loss over last 5 checks = {avg_loss:.0f}%")


def print_summary():
    if not history:
        return
    print("\n\n" + "="*52)
    print("  SESSION SUMMARY")
    print("="*52)

    total   = len(history)
    healthy = sum(1 for r in history if r["label"] == "HEALTHY")
    down    = sum(1 for r in history if r["label"] == "DOWN")
    degraded= total - healthy - down

    print(f"  Total checks:  {total}")
    print(f"  🟢 Healthy:    {healthy}  ({healthy/total*100:.0f}%)")
    print(f"  🟡 Degraded:   {degraded}")
    print(f"  🔴 Down:       {down}")

    working = [r for r in history if r["ok"] and r["ms"]]
    if working:
        avg_ms = sum(r["ms"] for r in working) / len(working)
        print(f"  Avg latency:   {avg_ms:.1f}ms")

    avg_loss = sum(r["loss"] for r in history) / total
    print(f"  Avg loss:      {avg_loss:.1f}%")
    print(f"\n  Log saved to:  {LOG_FILE}")
    print("="*52 + "\n")


def run():
    global was_down, outage_start

    print("\n" + "="*52)
    print("  CONTINUOUS NETWORK MONITOR")
    print(f"  Checking every {CHECK_INTERVAL_SEC}s   |   Ctrl+C to stop")
    print("="*52)
    print(f"  {'TIME':<10} {'STATUS':<12} {'LATENCY':<12} {'LOSS':<10} {'NOTES'}")
    print(f"  {'────':<10} {'──────':<12} {'───────':<12} {'────':<10} {'─────'}")

    try:
        while True:
            now     = datetime.now()
            ts      = now.strftime("%H:%M:%S")
            gateway = get_gateway()
            dns_ok  = check_dns()

            if not gateway:
                label, symbol = "NO NETWORK", "🔴"
                ok, ms, loss  = False, None, 100.0
                notes = "No gateway — WiFi off or disconnected"
            else:
                ok, ms, loss  = ping_once(PING_HOST)
                label, symbol = classify_health(ok, ms, loss)
                notes_parts   = []
                if not dns_ok:
                    notes_parts.append("DNS failing")
                if ms and ms > ALERT_LATENCY_MS:
                    notes_parts.append(f"High latency")
                if loss > ALERT_LOSS_PCT:
                    notes_parts.append(f"Packet loss {loss:.0f}%")
                notes = " | ".join(notes_parts) if notes_parts else ""

            ms_str   = f"{ms:.1f}ms" if ms else "—"
            loss_str = f"{loss:.0f}%"

            print(f"  {ts:<10} {symbol} {label:<10} {ms_str:<12} {loss_str:<10} {notes}")

            # ── Alert: Connection went down ──────────────
            if not ok and not was_down:
                was_down    = True
                outage_start = now
                log_event(f"OUTAGE STARTED — internet unreachable")

            # ── Alert: Connection came back up ───────────
            if ok and was_down:
                was_down = False
                duration = (now - outage_start).seconds if outage_start else 0
                mins, secs = divmod(duration, 60)
                log_event(f"RESTORED — outage lasted {mins}m {secs}s")
                outage_start = None

            # ── Record history ───────────────────────────
            history.append({"ok": ok, "ms": ms, "loss": loss,
                             "label": label, "time": now})

            # ── Trend check every 5 readings ─────────────
            if len(history) % 5 == 0:
                trend_analysis()

            time.sleep(CHECK_INTERVAL_SEC)

    except KeyboardInterrupt:
        print_summary()


if __name__ == "__main__":
    run()
