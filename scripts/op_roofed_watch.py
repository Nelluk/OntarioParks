#!/usr/bin/env python3
"""
Check Ontario Parks roofed accommodation availability via internal API.

Prereqs:
- Export cookies from a real browser session to tmp/op_cookies.json
- Install curl_cffi in .venv

Example:
  .venv/bin/python scripts/op_roofed_watch.py \
    --start 2026-07-15 --end 2026-07-17 --party-size 2 \
    --parks "Pinery Provincial Park, Killbear Provincial Park"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Any, Dict, Iterable, List, Tuple

from curl_cffi import requests

BASE_URL = "https://reservations.ontarioparks.ca"
DEFAULT_COOKIE_PATH = "tmp/op_cookies.json"
DEFAULT_AVAILABLE_CODE = 5  # Observed as "Available" in testing
DEFAULT_KEYWORDS = [
    "cabin",
    "cottage",
    "shelter",
    "roof",
    "yurt",
    "oTent",
    "otent",
    "rustic",
    "soft-sided",
]


def parse_date(value: str) -> str:
    try:
        dt.date.fromisoformat(value)
        return value
    except ValueError:
        raise argparse.ArgumentTypeError("Use ISO date format YYYY-MM-DD")


def load_cookies(path: str) -> requests.Cookies:
    with open(path, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    jar = requests.Cookies()
    for c in cookies:
        jar.set(c.get("name"), c.get("value"), domain=c.get("domain"), path=c.get("path"))
    return jar


def get_json(session: requests.Session, path: str, params: Dict[str, Any] | None = None) -> Any:
    url = f"{BASE_URL}{path}"
    resp = session.get(url, params=params, impersonate="chrome110")
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code} for {url}: {resp.text[:200]}")
    return resp.json()


def normalize(s: str) -> str:
    return " ".join(s.lower().split())


def pick_location(locations: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
    q = normalize(query)
    exact = [l for l in locations if normalize(l.get("localizedValues", [{}])[0].get("fullName", "")) == q]
    if exact:
        return exact[0]
    partial = [l for l in locations if q in normalize(l.get("localizedValues", [{}])[0].get("fullName", ""))]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise ValueError(f"No park matches: {query}")
    names = ", ".join(l.get("localizedValues", [{}])[0].get("fullName", "") for l in partial[:10])
    raise ValueError(f"Multiple parks match '{query}': {names}...")


def build_roofed_category_ids(categories: List[Dict[str, Any]], keywords: List[str]) -> List[int]:
    out = []
    keys = [k.lower() for k in keywords]
    for c in categories:
        name = (c.get("localizedValues", [{}])[0].get("name", "") or "").lower()
        if any(k in name for k in keys):
            out.append(c.get("resourceCategoryId"))
    return sorted(set(out))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, type=parse_date)
    parser.add_argument("--end", required=True, type=parse_date)
    parser.add_argument("--party-size", type=int, default=2)
    parser.add_argument("--parks", help="Comma-separated park names")
    parser.add_argument("--park", action="append", help="Park name (repeatable)")
    parser.add_argument("--cookie-file", default=DEFAULT_COOKIE_PATH)
    parser.add_argument("--available-code", type=int, default=DEFAULT_AVAILABLE_CODE)
    parser.add_argument(
        "--category-keyword",
        action="append",
        help="Override roofed-category keywords (repeatable). If omitted, defaults are used.",
    )
    parser.add_argument("--list-parks", action="store_true")
    parser.add_argument("--list-categories", action="store_true")
    args = parser.parse_args()

    session = requests.Session()
    session.cookies = load_cookies(args.cookie_file)

    locations = get_json(session, "/api/resourceLocation")
    if args.list_parks:
        for l in locations:
            print(l.get("localizedValues", [{}])[0].get("fullName", ""))
        return 0

    categories = get_json(session, "/api/resourcecategory")
    keywords = args.category_keyword or DEFAULT_KEYWORDS
    roofed_category_ids = set(build_roofed_category_ids(categories, keywords))

    if args.list_categories:
        for c in categories:
            if c.get("resourceCategoryId") in roofed_category_ids:
                print(f"{c.get('resourceCategoryId')}: {c.get('localizedValues', [{}])[0].get('name', '')}")
        return 0

    park_inputs: List[str] = []
    if args.parks:
        park_inputs.extend([p.strip() for p in args.parks.split(",") if p.strip()])
    if args.park:
        park_inputs.extend(args.park)
    if not park_inputs:
        parser.error("Provide at least one park via --parks or --park")

    # Fetch cart IDs (required by availability API)
    cart = get_json(session, "/api/cart")
    cart_uid = cart.get("cartUid")
    cart_tx_uid = cart.get("newTransaction", {}).get("cartTransactionUid") or cart.get("createTransactionUid")

    results = []
    for park_name in park_inputs:
        try:
            loc = pick_location(locations, park_name)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            continue

        resource_location_id = loc.get("resourceLocationId")
        display_name = loc.get("localizedValues", [{}])[0].get("fullName", park_name)

        resources = get_json(session, "/api/resourcelocation/resources", {"resourceLocationId": resource_location_id})
        # resources is an object keyed by resourceId
        roofed_resources = {
            int(rid): r
            for rid, r in resources.items()
            if r.get("resourceCategoryId") in roofed_category_ids
        }

        maps = get_json(session, "/api/maps", {"resourceLocationId": resource_location_id})
        map_ids = [m.get("mapId") for m in maps if (m.get("mapResources") or [])]

        available: List[Dict[str, Any]] = []
        for map_id in map_ids:
            params = {
                "mapId": map_id,
                "bookingCategoryId": 2,  # Roofed Accommodation
                "equipmentCategoryId": "",
                "subEquipmentCategoryId": "",
                "cartUid": cart_uid,
                "cartTransactionUid": cart_tx_uid,
                "bookingUid": "",
                "groupHoldUid": "",
                "startDate": args.start,
                "endDate": args.end,
                "getDailyAvailability": "true",
                "isReserving": "true",
                "filterData": "[]",
                "boatLength": 0,
                "boatDraft": 0,
                "boatWidth": 0,
                "peopleCapacityCategoryCounts": json.dumps([
                    {"capacityCategoryId": -32768, "subCapacityCategoryId": None, "count": args.party_size}
                ]),
                "numEquipment": 0,
                "seed": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            availability = get_json(session, "/api/availability/map", params)
            for rid_str, daily in (availability.get("resourceAvailabilities") or {}).items():
                rid = int(rid_str)
                if rid not in roofed_resources:
                    continue
                # daily is list of {availability, remainingQuota}
                if daily and all(d.get("availability") == args.available_code for d in daily):
                    r = roofed_resources[rid]
                    name = r.get("localizedValues", [{}])[0].get("name", str(rid))
                    available.append({
                        "resourceId": rid,
                        "name": name,
                        "categoryId": r.get("resourceCategoryId"),
                    })

        results.append({
            "park": display_name,
            "resourceLocationId": resource_location_id,
            "available": sorted(available, key=lambda x: x["name"]),
        })

    print(json.dumps({
        "start": args.start,
        "end": args.end,
        "partySize": args.party_size,
        "availableCode": args.available_code,
        "results": results,
    }, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
