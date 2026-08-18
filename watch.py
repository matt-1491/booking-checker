#!/usr/bin/env python3
"""
Bunga 90 availability watcher.

Polls the SevenRooms widget availability API for a target date and
party-size range, and pushes an ntfy notification when anything opens
up inside the target time window.

No secrets required. Just set NTFY_TOPIC below to something unguessable.
"""

import sys
import json
import time
import urllib.parse
import urllib.request

# ---------------------------------------------------------------- CONFIG ----

VENUE = "bungacoventgarden"          # SevenRooms venue slug for Bunga 90
DATE = "09-26-2026"                  # MM-DD-YYYY, the date you want
PARTY_SIZES = range(4, 21, 2)        # 4, 6, 8 ... 20
WINDOW_START = "19:00"               # earliest acceptable slot (UK time)
WINDOW_END = "21:00"                 # latest acceptable slot (UK time)
CENTRE_TIME = "20:00"                # midpoint of your window
HALO = 16                            # wide net, we filter afterwards
INCLUDE_REQUESTABLE = False           # also alert on "request" slots

# CHANGE THIS to your own random string before you push the repo.
NTFY_TOPIC = "kd833L290CXnMQ"

BOOKING_URL = f"https://www.sevenrooms.com/reservations/{VENUE}"
API = "https://www.sevenrooms.com/api-yoa/availability/widget/range"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": BOOKING_URL,
    "Origin": "https://www.sevenrooms.com",
}

# ------------------------------------------------------------- HELPERS ------


def to_minutes(label: str) -> int:
    """Turn '7:30 PM', '19:30', or '2026-09-26 19:30:00' into minutes past midnight."""
    s = str(label).strip().upper()
    if " " in s and "-" in s.split(" ")[0]:      # ISO-ish datetime
        s = s.split(" ")[1]
    ampm = None
    if s.endswith("AM") or s.endswith("PM"):
        ampm = s[-2:]
        s = s[:-2].strip()
    parts = s.split(":")
    try:
        hh, mm = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return -1
    if ampm == "PM" and hh != 12:
        hh += 12
    if ampm == "AM" and hh == 12:
        hh = 0
    return hh * 60 + mm


LO = to_minutes(WINDOW_START)
HI = to_minutes(WINDOW_END)


def walk_slots(node):
    """Recursively pull out every dict that looks like a bookable time slot.

    Written defensively so it keeps working if SevenRooms reshuffles the JSON.
    """
    if isinstance(node, dict):
        if "time" in node and "type" in node:
            yield node
        for value in node.values():
            yield from walk_slots(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_slots(item)


def fetch(party_size: int):
    params = {
        "venue": VENUE,
        "time_slot": CENTRE_TIME,
        "party_size": party_size,
        "halo_size_interval": HALO,
        "start_date": DATE,
        "num_days": 1,
        "channel": "SEVENROOMS_WIDGET",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def notify(text: str):
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=text.encode("utf-8"),
        headers={
            "Title": "Bunga 90 availability",
            "Priority": "high",
            "Tags": "tada",
            "Click": BOOKING_URL,
        },
    )
    urllib.request.urlopen(req, timeout=25).read()


# ---------------------------------------------------------------- MAIN ------


def main():
    sizes = list(PARTY_SIZES)
    hits = []
    errors = 0

    for size in sizes:
        try:
            data = fetch(size)
        except Exception as exc:                      # noqa: BLE001
            errors += 1
            print(f"party {size:>2}: request failed -> {exc}")
            time.sleep(2)
            continue

        found = []
        for slot in walk_slots(data):
            slot_type = str(slot.get("type", "")).lower()
            if slot_type not in ("book", "request"):
                continue
            if slot_type == "request" and not INCLUDE_REQUESTABLE:
                continue
            label = slot.get("real_datetime_of_slot") or slot.get("time")
            mins = to_minutes(label)
            if mins < 0 or not (LO <= mins <= HI):
                continue
            found.append(f"{slot.get('time')} ({slot_type})")

        found = sorted(set(found))
        print(f"party {size:>2}: {len(found)} slot(s) {found if found else ''}")
        if found:
            hits.append(f"{size} people: {', '.join(found)}")

        time.sleep(1.5)          # be polite, don't hammer them

    if errors == len(sizes):
        print("ALL requests failed - the endpoint or params probably need refreshing.")
        sys.exit(1)

    if hits:
        msg = (
            f"26 Sept  |  {WINDOW_START}-{WINDOW_END}\n\n"
            + "\n".join(hits)
            + f"\n\nBook: {BOOKING_URL}"
        )
        print(msg)
        notify(msg)
    else:
        print("No availability in window.")


if __name__ == "__main__":
    main()
