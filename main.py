#!/usr/bin/env python3
"""
Network Detector — Main Menu
Unified launcher for all detection tools.

Run: python3 main.py
"""

import subprocess
import sys
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TOOLS = [
    {
        "key":    "1",
        "name":   "Full Diagnostic",
        "desc":   "5-layer check: router → ISP → internet → DNS → HTTP",
        "file":   "diagnose.py",
        "args":   [],
    },
    {
        "key":    "2",
        "name":   "Area vs Local Fault Detector",
        "desc":   "Is it just you, or your whole area? Maps reach across network zones.",
        "file":   "area_compare.py",
        "args":   [],
    },
    {
        "key":    "3",
        "name":   "Continuous Monitor",
        "desc":   "Checks every 30s, alerts when connection drops or restores.",
        "file":   "monitor.py",
        "args":   [],
    },
    {
        "key":    "4",
        "name":   "Cron Check (State Tracker)",
        "desc":   "One-shot check with state comparison. Use with cron for auto-alerts.",
        "file":   "cron_check.py",
        "args":   [],
        "submenu": [
            ("Run check now",        []),
            ("Show state history",   ["history"]),
            ("Show cron setup guide",["setup"]),
        ],
    },
    {
        "key":    "5",
        "name":   "Deep Traceroute",
        "desc":   "Shows every hop to the internet, finds where latency spikes.",
        "file":   "traceroute_deep.py",
        "args":   [],
        "submenu": [
            ("Trace to Google DNS (8.8.8.8)", []),
            ("Trace to Cloudflare (1.1.1.1)", ["1.1.1.1"]),
            ("Trace to all 4 destinations",   ["--all"]),
        ],
    },
    {
        "key":    "6",
        "name":   "Latency History Graph",
        "desc":   "Pings over time, shows trend. ASCII or PNG graph.",
        "file":   "latency_graph.py",
        "args":   [],
        "submenu": [
            ("Quick test (10 samples, 5s each)",    ["--samples", "10", "--interval", "5"]),
            ("Standard (60 samples, 10s each)",     ["--samples", "60", "--interval", "10"]),
            ("Long run (120 samples, 30s each)",    ["--samples", "120", "--interval", "30"]),
            ("Force ASCII output",                  ["--samples", "20", "--interval", "5", "--ascii"]),
        ],
    },
    {
        "key":    "7",
        "name":   "ISP Outage Checker",
        "desc":   "Check if your ISP has a known outage. Supports Airtel, Jio, BSNL, Comcast...",
        "file":   "isp_status.py",
        "args":   [],
        "submenu": [
            ("Auto-detect my ISP",       []),
            ("Check Airtel",             ["--isp", "airtel"]),
            ("Check Jio",                ["--isp", "jio"]),
            ("Check BSNL",               ["--isp", "bsnl"]),
            ("Check Cloudflare status",  ["--isp", "cloudflare"]),
            ("Check all ISPs",           ["--isp", "all"]),
        ],
    },
    {
        "key":    "8",
        "name":   "Speed Test",
        "desc":   "Measures download speed and tells you what you can/can't do.",
        "file":   "speedtest.py",
        "args":   [],
    },
]


def clear():
    os.system("clear" if os.name != "nt" else "cls")


def print_menu():
    clear()
    print("\n" + "="*58)
    print("  NETWORK OUTAGE DETECTOR  —  MAIN MENU")
    print(f"  {datetime.now().strftime('%A %d %B %Y  %H:%M:%S')}")
    print("="*58)
    for tool in TOOLS:
        print(f"\n  [{tool['key']}]  {tool['name']}")
        print(f"       {tool['desc']}")
    print(f"\n  [0]  Exit")
    print("="*58)


def run_tool(file, args):
    path = os.path.join(SCRIPT_DIR, file)
    cmd  = [sys.executable, path] + [str(a) for a in args]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n  Stopped.")


def submenu(tool):
    options = tool.get("submenu", [])
    if not options:
        run_tool(tool["file"], tool["args"])
        return

    print(f"\n── {tool['name']} ─────────────────────────────")
    for i, (label, _) in enumerate(options, 1):
        print(f"  [{i}]  {label}")
    print(f"  [0]  Back")
    choice = input("\n  Choose: ").strip()
    if choice == "0":
        return
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(options):
            _, args = options[idx]
            run_tool(tool["file"], args)
    except (ValueError, IndexError):
        print("  Invalid choice.")


def main():
    while True:
        print_menu()
        choice = input("\n  Enter number: ").strip()

        if choice == "0":
            print("\n  Goodbye.\n")
            break

        tool = next((t for t in TOOLS if t["key"] == choice), None)
        if tool:
            print()
            if "submenu" in tool:
                submenu(tool)
            else:
                run_tool(tool["file"], tool["args"])
            input("\n  Press Enter to return to menu...")
        else:
            print("  Invalid choice.")
            input("  Press Enter to continue...")


if __name__ == "__main__":
    main()
