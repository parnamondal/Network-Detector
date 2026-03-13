#!/usr/bin/env python3
"""
Cron-Compatible Network State Checker
• Runs a quick check and compares to last known state (stored in JSON)
• Sends an alert (console + optional email) when state CHANGES
• Keeps a rolling log of all state changes

Run manually:
  python3 cron_check.py

Set up as cron job (check every 5 minutes):
  crontab -e
  Add line:  */5 * * * * /usr/bin/python3 /path/to/cron_check.py >> /tmp/net_cron.log 2>&1

Configure email alerts:  edit EMAIL_CONFIG below
"""

import subprocess
import socket
import urllib.request
import json
import os
import re
import time
import smtplib
import platform
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ── Paths ───────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
STATE_FILE  = os.path.join(SCRIPT_DIR, "net_state.json")
HISTORY_FILE= os.path.join(SCRIPT_DIR, "net_history.jsonl")

# ── Email config (optional) ──────────────────────────────────
# Leave SMTP_USER empty to skip email alerts entirely.
EMAIL_CONFIG = {
    "smtp_host":  "smtp.gmail.com",
    "smtp_port":  587,
    "smtp_user":  "",                   # your Gmail address
    "smtp_pass":  "",                   # Gmail App Password (not account password)
    "send_to":    "",                   # recipient address
}

# ── What to probe ────────────────────────────────────────────
CHECK_HOST    = "8.8.8.8"
CHECK_DOMAIN  = "google.com"
CHECK_URL     = "https://www.google.com"
PING_COUNT    = 3


# ── Core checks ──────────────────────────────────────────────

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


def ping(host, count=3):
    system = platform.system()
    cmd = (["ping", "-c", str(count), "-W", "2000", host]
           if system != "Windows"
           else ["ping", "-n", str(count), host])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = r.stdout
        loss, avg_ms = 100.0, None
        for line in output.splitlines():
            m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(packet\s*)?loss", line, re.IGNORECASE)
            if m:
                loss = float(m.group(1))
            m = re.search(r"[\d.]+/([\d.]+)/[\d.]+", line)
            if m:
                avg_ms = float(m.group(1))
        return (loss < 100), avg_ms, loss
    except Exception:
        return False, None, 100.0


def check_dns(domain):
    try:
        socket.setdefaulttimeout(4)
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False


def check_http(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        urllib.request.urlopen(req, timeout=6)
        return True
    except Exception:
        return False


# ── State classification ──────────────────────────────────────

def get_current_state():
    """
    Returns a dict describing the current network state.
    status: "UP" | "DOWN" | "DEGRADED" | "NO_NETWORK"
    """
    ts      = datetime.now().isoformat()
    gateway = get_gateway()

    if not gateway:
        return {"status": "NO_NETWORK", "ts": ts, "gateway": None,
                "ping_ok": False, "dns_ok": False, "http_ok": False,
                "latency_ms": None, "loss_pct": 100}

    ping_ok, latency_ms, loss_pct = ping(gateway, count=PING_COUNT)

    if not ping_ok:
        return {"status": "NO_NETWORK", "ts": ts, "gateway": gateway,
                "ping_ok": False, "dns_ok": False, "http_ok": False,
                "latency_ms": None, "loss_pct": 100}

    # Router OK → check internet
    inet_ping_ok, inet_ms, inet_loss = ping(CHECK_HOST, count=PING_COUNT)
    dns_ok  = check_dns(CHECK_DOMAIN)
    http_ok = check_http(CHECK_URL)

    internet_ok = inet_ping_ok or dns_ok or http_ok

    if not internet_ok:
        status = "DOWN"
    elif inet_loss > 20 or (inet_ms and inet_ms > 200):
        status = "DEGRADED"
    elif not inet_ping_ok and (dns_ok or http_ok):
        # Firewall blocks ping but HTTP works — corporate/VPN
        status = "UP"
    else:
        status = "UP"

    return {
        "status":     status,
        "ts":         ts,
        "gateway":    gateway,
        "ping_ok":    ping_ok,
        "dns_ok":     dns_ok,
        "http_ok":    http_ok,
        "latency_ms": inet_ms,
        "loss_pct":   inet_loss,
    }


# ── State persistence ─────────────────────────────────────────

def load_last_state():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def append_history(entry):
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Alerts ────────────────────────────────────────────────────

def format_alert_message(prev, curr):
    now = datetime.fromisoformat(curr["ts"]).strftime("%d %b %Y %H:%M:%S")
    if prev:
        prev_ts   = datetime.fromisoformat(prev["ts"]).strftime("%H:%M:%S")
        prev_stat = prev["status"]
    else:
        prev_ts   = "—"
        prev_stat = "unknown"

    # Calculate outage duration if coming back up
    duration_str = ""
    if prev and prev["status"] in ("DOWN", "NO_NETWORK") and curr["status"] == "UP":
        try:
            t1 = datetime.fromisoformat(prev["ts"])
            t2 = datetime.fromisoformat(curr["ts"])
            secs = int((t2 - t1).total_seconds())
            mins, s = divmod(secs, 60)
            hrs,  m = divmod(mins, 60)
            if hrs:
                duration_str = f"  Outage duration: {hrs}h {m}m\n"
            else:
                duration_str = f"  Outage duration: {m}m {s}s\n"
        except Exception:
            pass

    lat_str = f"{curr['latency_ms']:.1f}ms" if curr['latency_ms'] else 'N/A'
    body = (
        f"Network Status Changed\n"
        f"{'='*40}\n"
        f"  Time:     {now}\n"
        f"  Previous: {prev_stat} (at {prev_ts})\n"
        f"  Current:  {curr['status']}\n"
        f"{duration_str}"
        f"  Gateway:  {curr['gateway'] or 'none'}\n"
        f"  DNS:      {'OK' if curr['dns_ok'] else 'FAIL'}\n"
        f"  HTTP:     {'OK' if curr['http_ok'] else 'FAIL'}\n"
        f"  Latency:  {lat_str}\n"
        f"  Loss:     {curr['loss_pct']:.0f}%\n"
    )
    return body


def send_email_alert(subject, body):
    cfg = EMAIL_CONFIG
    if not cfg["smtp_user"] or not cfg["send_to"]:
        return False
    try:
        msg = MIMEMultipart()
        msg["From"]    = cfg["smtp_user"]
        msg["To"]      = cfg["send_to"]
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"])
        server.starttls()
        server.login(cfg["smtp_user"], cfg["smtp_pass"])
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"  [email] Failed to send: {e}")
        return False


def trigger_alert(prev, curr):
    body    = format_alert_message(prev, curr)
    subject = f"[Network Alert] Status: {curr['status']}"

    # Always print to console / log file
    print("\n" + "!"*50)
    print("  *** STATE CHANGE ALERT ***")
    print("!"*50)
    print(body)

    # Email if configured
    if EMAIL_CONFIG["smtp_user"]:
        sent = send_email_alert(subject, body)
        print(f"  Email alert: {'sent ✅' if sent else 'failed ❌'}")

    # Append to history
    history_entry = {
        "ts":      curr["ts"],
        "event":   "STATE_CHANGE",
        "from":    prev["status"] if prev else "unknown",
        "to":      curr["status"],
        "latency": curr["latency_ms"],
        "loss":    curr["loss_pct"],
    }
    append_history(history_entry)


# ── Main ──────────────────────────────────────────────────────

def run():
    ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts_str}] Running network check...")

    curr  = get_current_state()
    prev  = load_last_state()

    status_icons = {
        "UP":         "✅",
        "DOWN":       "❌",
        "DEGRADED":   "⚠️ ",
        "NO_NETWORK": "🔴",
    }
    icon = status_icons.get(curr["status"], "?")
    ms_str = f"{curr['latency_ms']:.1f}ms" if curr["latency_ms"] else "—"
    print(f"  Status:  {icon} {curr['status']}")
    print(f"  Latency: {ms_str}  |  Loss: {curr['loss_pct']:.0f}%")
    print(f"  DNS: {'OK' if curr['dns_ok'] else 'FAIL'}  "
          f"HTTP: {'OK' if curr['http_ok'] else 'FAIL'}")

    # Detect state change
    prev_status = prev["status"] if prev else None
    if prev_status != curr["status"]:
        trigger_alert(prev, curr)
    else:
        print(f"  No change (still {curr['status']} since {prev['ts'][:16] if prev else 'first run'})")

    save_state(curr)
    print()


def show_history():
    """Print the last 20 state change events."""
    if not os.path.exists(HISTORY_FILE):
        print("No history yet.")
        return
    print("\n── STATE CHANGE HISTORY ───────────────────────────")
    with open(HISTORY_FILE) as f:
        lines = f.readlines()
    for line in lines[-20:]:
        try:
            e = json.loads(line)
            ts  = e["ts"][:16].replace("T", " ")
            ms  = f"{e['latency']:.0f}ms" if e.get("latency") else "—"
            print(f"  {ts}  {e['from']:<12} → {e['to']:<12}  latency: {ms}")
        except Exception:
            pass
    print()


def print_cron_setup():
    script_path = os.path.abspath(__file__)
    python_path = subprocess.run(["which", "python3"],
                                 capture_output=True, text=True).stdout.strip()
    print("\n── HOW TO SET UP AS CRON JOB ──────────────────────")
    print("  Run this command to open your crontab:")
    print("    crontab -e")
    print()
    print("  Then paste ONE of these lines:")
    print()
    print(f"  # Check every 5 minutes:")
    print(f"  */5 * * * * {python_path} {script_path} >> /tmp/net_cron.log 2>&1")
    print()
    print(f"  # Check every 1 minute:")
    print(f"  * * * * * {python_path} {script_path} >> /tmp/net_cron.log 2>&1")
    print()
    print("  To view the log:  tail -f /tmp/net_cron.log")
    print("  To remove cron:   crontab -r")
    print()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "history":
        show_history()
    elif len(sys.argv) > 1 and sys.argv[1] == "setup":
        print_cron_setup()
    else:
        run()
        if "--setup" in sys.argv:
            print_cron_setup()
