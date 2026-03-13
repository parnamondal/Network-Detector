# Network Outage Detector
### Complete Beginner's Guide — What It Is, What It Does, How to Use It

---

## What Is This Project?

Imagine your internet stops working.

Most people do this:
1. Restart the router (maybe it helps, maybe it doesn't)
2. Call the ISP helpline (wait 30 minutes on hold)
3. Get told "we're looking into it"
4. Sit and wait with no information

**This project changes that.**

It is a set of Python scripts that run on your computer and automatically:
- Detect that internet is down (within seconds)
- Figure out WHERE the problem is (your device? router? ISP? fiber cable?)
- Tell you in plain English what is wrong and what to do
- Track the outage over time
- Alert you the moment it is fixed

**No installation of special software needed. Just Python, which is already on your Mac/Linux.**

---

## The Big Picture — How Internet Actually Works

Before understanding the scripts, understand this:

```
YOUR LAPTOP / PHONE
        │
        │  (WiFi or cable)
        ▼
   YOUR ROUTER                   ← sits in your home/office
        │
        │  (telephone line / fiber cable)
        ▼
  ISP JUNCTION BOX               ← on your street or building
        │
        │  (underground fiber optic cable)
        ▼
  ISP EXCHANGE BUILDING          ← Airtel/Jio/BSNL office nearby
        │
        │  (long-distance fiber)
        ▼
     INTERNET                    ← Google, YouTube, WhatsApp...
```

When something goes wrong, it happens at ONE of these layers.
The scripts find out WHICH layer is broken.

---

## What Each Problem Looks Like

| What You See | What Is Actually Broken | Script Diagnosis |
|---|---|---|
| WiFi icon missing | Your device is not connected to any network | `No gateway found` |
| WiFi connected but no internet | Router is working but ISP connection is dead | `ISP / Fiber issue` |
| Internet works but very slow | Cable damage or ISP congestion | `DEGRADED connection` |
| Some websites work, some don't | DNS failure | `DNS broken` |
| Everything seems fine but slow | Network overloaded | `High latency` |
| Drops in and out randomly | Packet loss — damaged cable or interference | `Packet loss detected` |

---

## Project Files — What Each One Does

```
network-detector/
│
├── main.py              ← START HERE — menu to launch everything
│
├── diagnose.py          ← "Doctor" — full checkup, finds the fault
├── area_compare.py      ← "Detective" — is it just you or whole area?
├── monitor.py           ← "Guard" — watches 24/7, alerts on change
├── speedtest.py         ← "Meter" — measures your actual speed
├── traceroute_deep.py   ← "Map" — shows every step packets travel
├── latency_graph.py     ← "Chart" — draws your connection quality over time
├── cron_check.py        ← "Scheduler" — auto-runs every 5 min via cron
└── isp_status.py        ← "Reporter" — checks if Airtel/Jio/BSNL is down
```

---

## How to Start (First Time Setup)

**Step 1** — Open Terminal on your Mac
```
Press Cmd + Space → type "Terminal" → press Enter
```

**Step 2** — Go to the project folder
```bash
cd ~/network-detector
```

**Step 3** — Run the main menu
```bash
python3 main.py
```

You will see:
```
====================================================
  NETWORK OUTAGE DETECTOR  —  MAIN MENU
====================================================

  [1]  Full Diagnostic
       5-layer check: router → ISP → internet → DNS → HTTP

  [2]  Area vs Local Fault Detector
       Is it just you, or your whole area?

  [3]  Continuous Monitor
       Checks every 30s, alerts when connection drops or restores.

  [4]  Cron Check (State Tracker)
       One-shot check with state comparison.

  [5]  Deep Traceroute
       Shows every hop to the internet, finds where latency spikes.

  [6]  Latency History Graph
       Pings over time, shows trend.

  [7]  ISP Outage Checker
       Check if Airtel/Jio/BSNL has an outage.

  [8]  Speed Test
       Measures download speed.

  [0]  Exit
```

Type a number and press Enter to run that tool.

---

---

# USE CASE 1 — "My Internet Is Not Working"

## Tool: `diagnose.py`

### When to Use
- Internet suddenly stopped working
- You want to know WHERE the problem is
- Before calling your ISP helpline

### How to Run
```bash
python3 ~/network-detector/diagnose.py
```

### What It Does — Step by Step

The script runs 5 checks in order, going deeper each time:

```
CHECK 1: Is your WiFi/cable connected at all?
    ↓ (if yes, continue)
CHECK 2: Can you reach your router?
    ↓ (if yes, continue)
CHECK 3: Can you reach the internet (8.8.8.8, 1.1.1.1)?
    ↓ (if yes, continue)
CHECK 4: Can you look up website names (DNS)?
    ↓ (if yes, continue)
CHECK 5: Can you load an actual webpage (HTTP)?
```

It stops the moment it finds the broken layer and tells you exactly what to do.

### Possible Outputs and What They Mean

**Output A — No Network At All**
```
❌  No gateway found

DIAGNOSIS: WITHOUT ROUTER
Your device is NOT connected to any network at all.

What to do:
→ Turn on WiFi and connect to a network
→ Or plug in ethernet cable
```
**Meaning:** Your laptop thinks it has no network. WiFi might be off.

---

**Output B — Router Not Responding**
```
✅  Router / Gateway found  |  IP: 192.168.1.1
❌  Router not responding

DIAGNOSIS: ROUTER IS DOWN / UNREACHABLE
Your device sees the router but cannot communicate with it.

What to do:
→ Unplug router power, wait 30 seconds, plug back in
→ Move closer to the router
```
**Meaning:** Router exists but is crashed or too far away.

---

**Output C — ISP / Fiber Problem**
```
✅  Router responding  |  Latency: 1.2ms
❌  8.8.8.8   timeout
❌  1.1.1.1   timeout

DIAGNOSIS: ISP / FIBER ISSUE
Your router is working fine.
BUT no signal is reaching the internet.

What to do:
→ Check if neighbors have internet
→ Call your ISP and report outage
→ Use mobile data as backup
```
**Meaning:** Your home equipment is fine. The fault is outside your house — at the ISP level or the fiber cable.

---

**Output D — Healthy**
```
✅  CONNECTION IS HEALTHY
Router latency:   1.2ms
Internet latency: 18.4ms
Packet loss:      0%
DNS:              Working
HTTP:             Working
```
**Meaning:** Everything is working fine. If a website is slow, it's that website's problem, not your internet.

---

### Real Life Trigger Example
```
Scenario: You sit down to work. Opens browser. Page doesn't load.
Action:   python3 diagnose.py
Result:   "ISP / Fiber issue" → you know NOT to waste time restarting router
          You immediately call Airtel and report outage
          You switch to mobile hotspot for work
Time saved: 20 minutes of guessing
```

---

---

# USE CASE 2 — "Is It Just Me or the Whole Area?"

## Tool: `area_compare.py`

### When to Use
- Internet is down and you want to know the scale
- You want to know if your neighbors are also affected
- Before deciding whether to call ISP or just restart router

### How to Run
```bash
python3 ~/network-detector/area_compare.py
```

### What It Does

It probes many different targets across different parts of the internet:

```
Layer 1: Your Router            (local — your house)
Layer 2: ISP Infrastructure     (Airtel/Jio servers)
Layer 3: Global CDN Nodes       (Cloudflare, Akamai, Fastly)
Layer 4: Major Services         (Google, YouTube, Amazon)
Layer 5: HTTP + DNS             (can you load websites?)
```

Then it **compares the results** to figure out which layer is broken.

### How It Classifies the Problem

| What It Detects | Verdict | What It Means |
|---|---|---|
| Router unreachable | `LOCAL` | Problem in YOUR device or WiFi |
| Router slow (>50ms) | `BUILDING` | WiFi weak or router overloaded |
| Nothing beyond router works | `AREA` | Fiber cut — your whole colony affected |
| ISP infra fails but CDN works | `ISP` | ISP internal routing fault |
| Both ISP and CDN fail | `REGIONAL` | Wider internet disruption |
| Pings blocked but HTTP works | `NONE` | Corporate firewall, not a real outage |

### Sample Output
```
  [ Router ]           🟢 OK
       │
       ▼
  [ ISP Infrastructure ] 🔴 Unreachable
       │
       ▼
  [ Global CDN Nodes ]   🔴 Unreachable
       │
       ▼
  [ Major Services ]     🔴 Unreachable
  [ HTTP Access    ]     🔴 Unreachable
  [ DNS Resolution ]     🔴 Failing

VERDICT: 🔴 AREA ISSUE
Router is alive but NOTHING beyond it responds.
→ Fiber/cable cut between your building and ISP exchange.
→ All ~1000 people in your area are likely affected.
```

### Real Life Trigger Example
```
Scenario: 500 families in a colony lose internet at 9 PM.
          One person runs area_compare.py
Result:   AREA ISSUE confirmed — ISP infrastructure unreachable
          ISP is called with exact fault description
          "Fiber cut between our area and your exchange"
          Technician dispatched to correct location immediately
Time saved: 2-3 hours of wrong troubleshooting
```

---

---

# USE CASE 3 — "Alert Me When Internet Goes Down or Comes Back"

## Tool: `monitor.py`

### When to Use
- You are working from home and need to know the second internet drops
- You want to track how reliable your connection is over time
- You want to catch short drops you might not notice manually

### How to Run
```bash
python3 ~/network-detector/monitor.py
```
Press `Ctrl+C` to stop. It will show a summary.

### What It Does

Runs a check every 30 seconds. Prints one line per check. Alerts immediately when status changes.

### Sample Output (Normal Connection)
```
  TIME       STATUS       LATENCY      LOSS       NOTES
  ────       ──────       ───────      ────       ─────
  10:00:01   🟢 HEALTHY   18.4ms       0%
  10:00:31   🟢 HEALTHY   19.1ms       0%
  10:01:01   🟢 HEALTHY   17.8ms       0%
```

### Sample Output (When Internet Drops)
```
  10:05:01   🟢 HEALTHY   18.2ms       0%
  10:05:31   🔴 DOWN      —            100%

  *** ALERT: OUTAGE STARTED — internet unreachable ***

  10:06:01   🔴 DOWN      —            100%
  10:06:31   🔴 DOWN      —            100%
  10:07:01   🟢 HEALTHY   19.4ms       0%

  *** ALERT: RESTORED — outage lasted 1m 30s ***
```

### Session Summary (when you press Ctrl+C)
```
  Total checks:  40
  🟢 Healthy:    37  (92%)
  🟡 Degraded:   2
  🔴 Down:       1
  Avg latency:   19.2ms
  Avg loss:      0.3%
```

### Real Life Trigger Example
```
Scenario: You are on a work-from-home day with video calls.
          Run monitor.py in a separate terminal window.
          When internet drops, you see the alert instantly.
          You switch to mobile hotspot BEFORE your meeting drops.
Time saved: Embarrassment of dropping off a client call
```

---

---

# USE CASE 4 — "How Fast Is My Internet Right Now?"

## Tool: `speedtest.py`

### When to Use
- Internet feels slow but you are not sure
- You pay for 100 Mbps but things feel like 2 Mbps
- You want to know if you can handle a video call or not

### How to Run
```bash
python3 ~/network-detector/speedtest.py
```

### What It Tests

1. **Latency at each layer** — how long packets take to reach your router, ISP, and internet
2. **Download speed** — downloads a real file and measures actual throughput
3. **What you can do** — translates speed into real activities
4. **Where the bottleneck is** — router? ISP? cable?

### Sample Output
```
── LATENCY BY LAYER ──────────────────────────────

  Your Router  (192.168.1.1)  →  1.2ms  |  Loss: 0%
  Google DNS   (8.8.8.8)     →  18.4ms  |  Loss: 0%
  Cloudflare   (1.1.1.1)     →  16.1ms  |  Loss: 0%

── DOWNLOAD SPEED ────────────────────────────────

  Downloading 10 MB test file...  42.3 Mbps  (1.9s, 10.0 MB)
  Quality rating: Fair (20-50 Mbps)

── WHAT CAN YOU DO WITH THIS CONNECTION? ─────────

  ✅ WhatsApp / Telegram messages
  ✅ Audio calls
  ✅ YouTube 480p
  ✅ Video calls (Zoom / Meet)
  ✅ YouTube 1080p HD
  ❌ Multiple devices streaming
  ❌ 4K streaming / large downloads

── WHERE IS THE BOTTLENECK? ──────────────────────

  Bottleneck: ISP is throttling or congested
  (Pings work fine at 18ms, but download is slow)
  → ISP exchange overloaded, or your plan is limited
```

### Speed Quality Reference
```
1-5 Mbps    → Basic browsing, WhatsApp only
5-20 Mbps   → YouTube, basic video calls
20-50 Mbps  → HD video, Zoom, normal work
50-100 Mbps → Multiple devices, 4K, fast downloads
100+ Mbps   → Excellent, handles anything
```

### Real Life Trigger Example
```
Scenario: You are paying for 100 Mbps Airtel plan.
          YouTube keeps buffering.
          Run speedtest.py
Result:   "Download: 4.2 Mbps — ISP throttling"
          You call Airtel with evidence: "I am getting 4 Mbps on a 100 Mbps plan"
          They fix it or give you credit
```

---

---

# USE CASE 5 — "Show Me Every Step My Data Takes"

## Tool: `traceroute_deep.py`

### When to Use
- Internet is slow and you want to know WHERE in the path the slowness is
- Technical troubleshooting — finding which router or ISP hop is the problem
- Learning how internet routing works

### How to Run
```bash
# Basic — trace to Google DNS
python3 ~/network-detector/traceroute_deep.py

# Trace to a specific destination
python3 ~/network-detector/traceroute_deep.py 1.1.1.1

# Trace to 4 destinations at once
python3 ~/network-detector/traceroute_deep.py --all
```

### What a Traceroute Is

Every time you load a website, your data travels through multiple routers (hops).
Like a package going through multiple warehouses before delivery.

```
YOUR LAPTOP → HOP 1 (your router) → HOP 2 (ISP gateway) →
HOP 3 (ISP core) → HOP 4 (internet backbone) → DESTINATION
```

Traceroute measures the time at each hop.

### Sample Output (Normal Home Network)
```
  HOP  IP ADDRESS         LATENCY    QUALITY BAR      ZONE
  ───  ──────────         ───────    ───────────      ────
  1    192.168.1.1        1.2ms      excellent        LOCAL
  2    10.45.0.1          4.8ms      excellent        LOCAL
  3    203.123.45.67      12.1ms     excellent        INTERNET
  4    72.14.194.67       15.4ms     excellent        CDN/DNS
  5    8.8.8.8            18.2ms     excellent        CDN/DNS

  ✅ Route found (5 hops)
  ✅ No latency spike detected
```

### Sample Output (Where Fault Is Detected)
```
  HOP  IP ADDRESS         LATENCY    ZONE
  ───  ──────────         ───────    ────
  1    192.168.1.1        1.2ms      LOCAL
  2    10.45.0.1          4.9ms      LOCAL
  3    203.123.45.67      8.1ms      INTERNET
  4    *                  timeout    UNKNOWN  ◄ SPIKE

  🔴 Path stops at hop 3 — fault between ISP hop 3 and hop 4
```

### On Corporate/VPN Networks (Firewall Blocks Traceroute)
The script automatically detects this and falls back to HTTP quality check:
```
  All hops timed out — firewall blocking probes.
  Running HTTP quality check instead...

  DESTINATION          HTTP LATENCY   QUALITY
  Your router          0.9ms          🟢 LOCAL
  Cloudflare           1376ms         🟢 Good
  Google               1369ms         🟢 Good
  GitHub               1230ms         🟢 Good
```

### Real Life Trigger Example
```
Scenario: Gaming is lagging badly (high ping).
          Run traceroute_deep.py --all
Result:   Hop 4 shows 450ms (all other hops are <20ms)
          The spike is at ISP's core router, not your home
          You share this evidence with your ISP to escalate
```

---

---

# USE CASE 6 — "Show Me a Graph of My Connection Over Time"

## Tool: `latency_graph.py`

### When to Use
- Internet is sometimes fast and sometimes slow
- You want to see if it gets worse at specific times (e.g. evenings)
- You want proof of connection instability to show your ISP

### How to Run

**Quick test (10 samples, 5 seconds each = 50 seconds total)**
```bash
python3 ~/network-detector/latency_graph.py --samples 10 --interval 5 --ascii
```

**Standard run (60 samples, 10 seconds each = 10 minutes)**
```bash
python3 ~/network-detector/latency_graph.py --samples 60 --interval 10 --ascii
```

**Save as PNG image (needs matplotlib)**
```bash
pip3 install matplotlib
python3 ~/network-detector/latency_graph.py --samples 60 --interval 10
# → saves latency_graph.png in same folder
```

### What the ASCII Graph Looks Like

```
  Collecting 10 samples every 5s

  #     Time       Latency      Bar
  ─     ────       ───────      ───
  1     10:00:00   18.4ms       ███░░░░░░░
  2     10:00:05   19.1ms       ███░░░░░░░
  3     10:00:10   TIMEOUT      ░░░░░░░░░░ ← DOWN
  4     10:00:15   245.0ms      █████████░ ← SLOW
  5     10:00:20   18.8ms       ███░░░░░░░
```

```
  LATENCY OVER TIME

  200ms │    ●
  150ms │
  100ms │
   50ms │
   20ms │ ●●   ●●●●●
    0ms │
        └──────────
         10:00  10:01
```

### Statistics You Get
```
  Total samples:   10
  Successful:      9   (90%)
  Timeouts (DOWN): 1   (10%)

  Min latency:  17.2ms
  Avg latency:  19.8ms
  Max latency:  245.0ms
  P95 latency:  22.1ms    ← 95% of the time faster than this
  Jitter:       227.8ms   ← big number = unstable connection

  Overall quality: 🟡 Fair — noticeable delays
  Longest outage streak: 1 consecutive timeout
```

### Real Life Trigger Example
```
Scenario: You suspect internet is slow every evening.
          Run at 8 PM: --samples 120 --interval 30 (1 hour of data)
Result:   Graph shows latency spikes from 8:30 PM to 10 PM
          Average goes from 20ms to 300ms during this window
          This is ISP congestion during peak hours
          You use this graph as evidence when complaining to ISP
```

---

---

# USE CASE 7 — "Set It and Forget It — Auto Alert Every 5 Minutes"

## Tool: `cron_check.py`

### When to Use
- You want automatic background monitoring without keeping a terminal open
- You want a log of all outages with timestamps
- You want email alerts when internet goes down

### How It Works

Unlike `monitor.py` which runs forever in a terminal, `cron_check.py` is designed to:
1. Run once, check the state
2. Compare to the last known state (saved in a file)
3. Print/alert if something changed
4. Exit

You then schedule it to run every 5 minutes automatically using **cron** (Mac's built-in task scheduler).

### Step 1 — Test It Manually First
```bash
python3 ~/network-detector/cron_check.py
```

Output:
```
[2026-03-13 10:00:00] Running network check...
  Status:  ✅ UP
  Latency: 18.4ms  |  Loss: 0%
  DNS: OK  HTTP: OK
  No change (still UP since 2026-03-13 09:30:00)
```

### Step 2 — See Past Events
```bash
python3 ~/network-detector/cron_check.py history
```

Output:
```
── STATE CHANGE HISTORY ───────────────────────────
  2026-03-13 09:30  unknown   → UP        latency: 18ms
  2026-03-13 11:45  UP        → DOWN      latency: —
  2026-03-13 12:10  DOWN      → UP        latency: 19ms
```

### Step 3 — Set Up Automatic Every-5-Minute Check
```bash
python3 ~/network-detector/cron_check.py setup
```

It prints the exact line to paste:
```
── HOW TO SET UP AS CRON JOB ──────────────────────
  Run: crontab -e
  Paste:
  */5 * * * * /opt/homebrew/bin/python3 /Users/yourname/network-detector/cron_check.py >> /tmp/net_cron.log 2>&1
```

```bash
crontab -e                    # opens editor
# paste the line, save and exit
tail -f /tmp/net_cron.log     # watch it running
```

### Step 4 — Email Alerts (Optional)

Edit `cron_check.py` and fill in:
```python
EMAIL_CONFIG = {
    "smtp_host":  "smtp.gmail.com",
    "smtp_port":  587,
    "smtp_user":  "your@gmail.com",
    "smtp_pass":  "your-app-password",   # Gmail App Password
    "send_to":    "your@gmail.com",
}
```

Now you get an email the moment internet goes down or comes back.

### Real Life Trigger Example
```
Scenario: You manage internet for a small office.
          Set up cron_check.py on a laptop that is always on.
          Configure email alerts to your phone.
Result:   At 3 AM, internet goes down due to fiber cut.
          You get an email: "OUTAGE STARTED at 03:14 AM"
          You get another email: "RESTORED at 05:22 AM — outage lasted 2h 8m"
          Next morning you have a full log without having stayed up all night.
```

---

---

# USE CASE 8 — "Check If Airtel/Jio Is Having an Outage"

## Tool: `isp_status.py`

### When to Use
- Your internet is down and you want to confirm it is the ISP's fault (not yours)
- Before calling customer care, check if there is already a known outage
- Check if a specific ISP is having problems right now

### How to Run
```bash
# Auto-detect your ISP and check it
python3 ~/network-detector/isp_status.py

# Check specific ISPs
python3 ~/network-detector/isp_status.py --isp airtel
python3 ~/network-detector/isp_status.py --isp jio
python3 ~/network-detector/isp_status.py --isp bsnl
python3 ~/network-detector/isp_status.py --isp cloudflare

# Check all ISPs at once
python3 ~/network-detector/isp_status.py --isp all
```

### Supported ISPs
```
airtel      → Airtel India
jio         → Reliance Jio India
bsnl        → BSNL India
act         → ACT Fibernet India
comcast     → Comcast / Xfinity USA
att         → AT&T USA
cloudflare  → Cloudflare (also checks their public status API)
```

### What It Checks For Each ISP

1. **Infrastructure IPs** — pings the ISP's own DNS and server IPs directly
2. **Website probe** — checks if the ISP's own website is reachable
3. **Status page** — fetches and scans their status page for outage keywords

### Sample Output
```
  CHECKING: Airtel (India)

  [ISP Infrastructure IPs]
    ❌  122.160.67.98      timeout
    ❌  122.160.67.99      timeout
    ❌  203.88.141.1       timeout
    Reachable: 0/3

  [ISP Website Probes]
    ✅  https://www.airtel.in    HTTP 200

  VERDICT for Airtel (India):
  🟡 PARTIAL — Website works but infrastructure IPs unreachable
     DNS infrastructure may have issues.
```

### Real Life Trigger Example
```
Scenario: Your Jio broadband stops working.
          Run: python3 isp_status.py --isp jio
Result:   "🔴 LIKELY DOWN — ISP infrastructure and website unreachable"
          You now KNOW it is Jio's problem, not your router
          You show this output to Jio customer care
          They escalate to network team instead of asking you to restart router
```

---

---

# Quick Reference — Which Tool for Which Problem?

| Your Situation | Run This |
|---|---|
| Internet stopped working, don't know why | `python3 diagnose.py` |
| Want to know if whole area is affected | `python3 area_compare.py` |
| Want to see real-time speed and quality | `python3 speedtest.py` |
| Want to monitor connection continuously | `python3 monitor.py` |
| Want auto-alerts without keeping terminal open | `python3 cron_check.py setup` |
| Want to see latency trend over time | `python3 latency_graph.py --samples 20 --interval 5 --ascii` |
| Want to see every network hop | `python3 traceroute_deep.py` |
| Want to check if Airtel/Jio is down | `python3 isp_status.py --isp airtel` |
| Want to do everything from one menu | `python3 main.py` |

---

# Troubleshooting Common Errors

**Error: `command not found: python3`**
```bash
# On Mac, install Python:
brew install python3
# Or download from python.org
```

**Error: `No such file or directory`**
```bash
# Make sure you are in the right folder:
cd ~/network-detector
ls    # should show all .py files
```

**Error: `Permission denied`**
```bash
chmod +x ~/network-detector/*.py
```

**Speed test shows "Failed" for all URLs**
- Your network may block those CDN URLs (corporate firewall)
- Try from home network for accurate results

**All pings show "timeout" but internet works**
- Normal on corporate/VPN networks
- Scripts auto-detect this and switch to HTTP mode
- No action needed

---

# Understanding the Output — Glossary

| Term | What It Means in Simple Words |
|---|---|
| **Latency / ms** | How long it takes for data to travel one way. Like reaction time. Lower = better. Good: <50ms |
| **Packet loss %** | Percentage of data that gets lost on the way. Like letters getting lost in post. Should be 0% |
| **Jitter** | How much the latency varies. Stable = low jitter. Unstable = high jitter. |
| **DNS** | The system that converts website names (google.com) to IP addresses. Like a phone book for the internet. |
| **Gateway / Router** | Your home router — the box with WiFi antenna. First step data takes out of your house. |
| **ISP** | Internet Service Provider — Airtel, Jio, BSNL, ACT. The company providing your internet. |
| **Fiber** | The glass cable underground that carries internet signal using light. Very fast. |
| **ICMP / Ping** | A simple test packet sent to check if a destination is alive. Like knocking on a door. |
| **Traceroute** | Sending packets that reveal every router (hop) on the path to a destination. |
| **HTTP/HTTPS** | The protocol used to load websites. S = secure (encrypted). |
| **Mbps** | Megabits per second — unit of internet speed. Higher = faster. |
| **P95 latency** | 95% of your requests were faster than this number. A better measure than average. |
| **Cron** | Mac/Linux built-in task scheduler. Runs commands at set times automatically. |

---

*Built for the EBC Cup 2026 — Network Outage Intelligence Platform*
*Generalizes the Major Incident Crisis Command Center concept to everyday users and communities*
