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
import copy
import datetime as dt
import json
import sys
import uuid
from typing import Any, Dict, Iterable, List, Tuple, Optional

from curl_cffi import requests

BASE_URL = "https://reservations.ontarioparks.ca"
DEFAULT_COOKIE_PATH = "tmp/op_cookies.json"
DEFAULT_CONFIG_PATH = "config.json"
DEFAULT_AVAILABLE_CODE = 5  # Observed as "Available" in testing
DEFAULT_APP_LANGUAGE = "en-CA"
DEFAULT_APP_VERSION = "5.105.203"  # Observed in UI headers; may need updating later
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


def load_cookies(path: str) -> Tuple[requests.Cookies, Optional[str]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Cookie file not found: {path}. Export browser cookies to this path before running."
        ) from e
    jar = requests.Cookies()
    xsrf_token = None
    for c in cookies:
        if c.get("name") == "XSRF-TOKEN":
            xsrf_token = c.get("value")
        jar.set(c.get("name"), c.get("value"), domain=c.get("domain"), path=c.get("path"))
    return jar, xsrf_token


def load_config(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Config file not found: {path}. Create it from config.example.json."
        ) from e


def normalize_site_token(s: str) -> Optional[str]:
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits or None


def match_preference(resource_name: str, preferred: List[str]) -> Optional[int]:
    """
    Returns the index in the preference list if the resource_name matches.
    Matching logic:
    - Exact (case-insensitive) string match
    - Numeric token match (e.g., '472' matches 'Site 472')
    """
    name_norm = resource_name.strip().lower()
    name_digits = normalize_site_token(resource_name)
    for idx, pref in enumerate(preferred):
        pref_norm = str(pref).strip().lower()
        if pref_norm == name_norm:
            return idx
        pref_digits = normalize_site_token(pref_norm)
        if pref_digits and name_digits and pref_digits == name_digits:
            return idx
    return None


def get_json(session: requests.Session, path: str, params: Dict[str, Any] | None = None) -> Any:
    url = f"{BASE_URL}{path}"
    resp = session.get(url, params=params, impersonate="chrome110")
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code} for {url}: {resp.text[:200]}")
    return resp.json()


def post_json(session: requests.Session, path: str, payload: Dict[str, Any], headers: Dict[str, str] | None = None) -> Any:
    url = f"{BASE_URL}{path}"
    resp = session.post(url, json=payload, headers=headers, impersonate="chrome110")
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


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def cart_has_items(cart: Dict[str, Any]) -> bool:
    return bool(
        cart.get("bookings")
        or cart.get("lineItems")
        or cart.get("sales")
        or cart.get("shipments")
        or cart.get("giftCards")
    )


def build_cart_commit_payload(
    cart: Dict[str, Any],
    resource_id: int,
    resource_location_id: int,
    start_date: str,
    end_date: str,
    party_size: int,
    booking_category_id: int = 2,
    preferred_culture_name: str = DEFAULT_APP_LANGUAGE,
) -> Dict[str, Any]:
    cart_copy = copy.deepcopy(cart)
    cart_uid = cart_copy.get("cartUid")
    cart_tx_uid = (
        cart_copy.get("newTransaction", {}).get("cartTransactionUid")
        or cart_copy.get("createTransactionUid")
    )
    if not cart_uid or not cart_tx_uid:
        raise RuntimeError("Cart missing cartUid or cartTransactionUid. Try refreshing cookies.")

    booking_uid = str(uuid.uuid4())
    blocker_uid = str(uuid.uuid4())
    now = iso_now()

    booking = {
        "bookingUid": booking_uid,
        "cartUid": cart_uid,
        "bookingCategoryId": booking_category_id,
        "bookingModel": 0,
        "newVersion": {
            "cartTransactionUid": cart_tx_uid,
            "bookingMembers": [],
            "bookingVehicles": [],
            "bookingBoats": [],
            "bookingCapacityCategoryCounts": [
                {"capacityCategoryId": -32768, "subCapacityCategoryId": None, "count": party_size}
            ],
            "rateCategoryId": -32768,
            "resourceBlockerUids": [blocker_uid],
            "resourceNonSpecificBlockerUids": [],
            "resourceZoneBlockerUids": [],
            "resourceZoneEntryBlockerUids": [],
            "startDate": start_date,
            "endDate": end_date,
            "releasePersonalInformation": False,
            "equipmentCategoryId": None,
            "subEquipmentCategoryId": None,
            "occupant": {
                "contact": {
                    "email": "",
                    "contactName": "",
                    "phoneNumberCountryCode": None,
                    "phoneNumber": "",
                },
                "address": {},
                "allowMarketing": False,
                "phoneNumbers": {},
                "preferredCultureName": preferred_culture_name,
                "firstName": "",
                "lastName": "",
            },
            "requiresCheckout": False,
            "bookingStatus": 0,
            "completedDate": now,
            "arrivalComment": "",
            "entryPointResourceId": None,
            "exitPointResourceId": None,
            "bookingSurcharges": [],
            "consentToRelease": False,
            "equipmentDescription": "",
            "groupHoldUid": "",
            "organizationName": "",
            "passExpiryDate": None,
            "passNumber": "",
            "resourceLocationId": resource_location_id,
            "checkInTime": None,
            "checkOutTime": None,
            "deferredPayment": False,
        },
        "createTransactionUid": cart_tx_uid,
        "currentVersion": None,
        "history": [],
        "drafts": [],
        "referenceNumberPostfix": "",
    }

    resource_blocker = {
        "blockerType": 0,
        "cartUid": cart_uid,
        "resourceBlockerUid": blocker_uid,
        "bookingUid": booking_uid,
        "groupHoldUid": "",
        "isReservation": True,
        "newVersion": {
            "creationDate": now,
            "cartTransactionUid": cart_tx_uid,
            "startDate": start_date,
            "endDate": end_date,
            "resourceId": resource_id,
            "resourceLocationId": resource_location_id,
            "status": 0,
        },
    }

    # Ensure required fields exist
    cart_copy["createTransactionUid"] = cart_copy.get("createTransactionUid") or cart_tx_uid
    cart_copy["bookings"] = (cart_copy.get("bookings") or []) + [booking]
    cart_copy["resourceBlockers"] = (cart_copy.get("resourceBlockers") or []) + [resource_blocker]
    cart_copy.setdefault("resourceNonSpecificBlockers", [])
    cart_copy.setdefault("resourceZoneBlockers", [])
    cart_copy.setdefault("resourceZoneEntryBlockers", [])
    cart_copy.setdefault("waitlistApplications", [])
    cart_copy.setdefault("lineItems", [])
    cart_copy.setdefault("sales", [])
    cart_copy.setdefault("shipments", [])

    return {"cart": cart_copy}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to JSON config")
    parser.add_argument("--start", type=parse_date)
    parser.add_argument("--end", type=parse_date)
    parser.add_argument("--party-size", type=int, default=2)
    parser.add_argument("--parks", help="Comma-separated park names")
    parser.add_argument("--park", action="append", help="Park name (repeatable)")
    parser.add_argument("--cookie-file", default=DEFAULT_COOKIE_PATH)
    parser.add_argument("--available-code", type=int, default=DEFAULT_AVAILABLE_CODE)
    parser.add_argument("--reserve", action="store_true", help="Attempt to add best match to cart")
    parser.add_argument(
        "--reserve-mode",
        choices=["first", "all"],
        default=None,
        help="Reserve the first match only (default) or all matches",
    )
    parser.add_argument(
        "--allow-existing-cart",
        action="store_true",
        help="Allow auto-reserve even if cart already has items",
    )
    parser.add_argument("--app-version", default=None, help="Override app-version header for cart commit")
    parser.add_argument("--app-language", default=None, help="Override app-language header for cart commit")
    parser.add_argument(
        "--category-keyword",
        action="append",
        help="Override roofed-category keywords (repeatable). If omitted, defaults are used.",
    )
    parser.add_argument("--list-parks", action="store_true")
    parser.add_argument("--list-categories", action="store_true")
    parser.add_argument("--use-config", action="store_true", help="Read defaults from config file")
    args = parser.parse_args()

    config: Dict[str, Any] = {}
    if args.use_config:
        config = load_config(args.config)
        if args.start is None and config.get("start"):
            args.start = parse_date(config["start"])
        if args.end is None and config.get("end"):
            args.end = parse_date(config["end"])
        if args.party_size == 2 and config.get("party_size"):
            args.party_size = int(config["party_size"])
        if args.cookie_file == DEFAULT_COOKIE_PATH and config.get("cookie_file"):
            args.cookie_file = config["cookie_file"]
        if not args.reserve and config.get("auto_reserve"):
            args.reserve = True
        if args.reserve_mode is None and config.get("reserve_mode"):
            args.reserve_mode = config.get("reserve_mode")
        if not args.allow_existing_cart and config.get("allow_existing_cart"):
            args.allow_existing_cart = True
        if args.app_version is None and config.get("app_version"):
            args.app_version = config.get("app_version")
        if args.app_language is None and config.get("app_language"):
            args.app_language = config.get("app_language")

    if not args.start or not args.end:
        parser.error("Provide --start and --end (or use --use-config with start/end in config)")

    session = requests.Session()
    cookie_jar, xsrf_token = load_cookies(args.cookie_file)
    session.cookies = cookie_jar

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
    park_preferences: Dict[str, List[str]] = {}

    # Config-driven parks
    if args.use_config:
        for p in config.get("parks", []):
            name = p.get("name")
            if not name:
                continue
            park_inputs.append(name)
            prefs = p.get("preferred_sites") or []
            park_preferences[name] = [str(x) for x in prefs]

    # CLI overrides
    if args.parks:
        park_inputs.extend([p.strip() for p in args.parks.split(",") if p.strip()])
    if args.park:
        park_inputs.extend(args.park)
    if not park_inputs:
        parser.error("Provide at least one park via --parks/--park or enable --use-config")

    # Fetch cart IDs (required by availability API)
    cart = get_json(session, "/api/cart")
    cart_uid = cart.get("cartUid")
    cart_tx_uid = cart.get("newTransaction", {}).get("cartTransactionUid") or cart.get("createTransactionUid")
    if not cart_uid or not cart_tx_uid:
        raise RuntimeError("Cart UID missing from /api/cart response. Try re-exporting cookies.")

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

        preferred = park_preferences.get(display_name, []) or park_preferences.get(park_name, [])
        best_match = None
        if preferred:
            # Find the first preferred site that is available
            ranked = []
            for item in available:
                idx = match_preference(item["name"], preferred)
                if idx is not None:
                    ranked.append((idx, item))
            if ranked:
                ranked.sort(key=lambda x: x[0])
                best_match = ranked[0][1]

        results.append({
            "park": display_name,
            "resourceLocationId": resource_location_id,
            "available": sorted(available, key=lambda x: x["name"]),
            "preferredMatch": best_match,
        })

    print(json.dumps({
        "start": args.start,
        "end": args.end,
        "partySize": args.party_size,
        "availableCode": args.available_code,
        "results": results,
    }, indent=2))

    # Simple notification: print matches to stderr for easy cron/email piping
    matches = [r for r in results if r.get("preferredMatch")]
    if matches:
        for r in matches:
            m = r["preferredMatch"]
            print(f"MATCH: {r['park']} -> {m['name']} (resourceId {m['resourceId']})", file=sys.stderr)

    # Optional auto-reserve
    reserve_mode = args.reserve_mode or "first"
    app_language = args.app_language if args.app_language is not None else DEFAULT_APP_LANGUAGE
    app_version = args.app_version if args.app_version is not None else DEFAULT_APP_VERSION
    if args.reserve:
        if not xsrf_token:
            print("Warning: XSRF-TOKEN cookie missing; cannot auto-reserve.", file=sys.stderr)
            return 1
        if cart_has_items(cart) and not args.allow_existing_cart:
            print("Warning: Cart already has items. Auto-reserve skipped.", file=sys.stderr)
            return 1

        headers = {
            "x-xsrf-token": xsrf_token,
            "app-language": app_language,
            "app-version": app_version,
            "content-type": "application/json",
        }

        for r in matches:
            m = r["preferredMatch"]
            try:
                payload = build_cart_commit_payload(
                    cart=cart,
                    resource_id=m["resourceId"],
                    resource_location_id=r["resourceLocationId"],
                    start_date=args.start,
                    end_date=args.end,
                    party_size=args.party_size,
                    booking_category_id=2,
                    preferred_culture_name=app_language,
                )
                post_json(session, "/api/cart/commit?isCompleted=false&isSelfCheckIn=false", payload, headers=headers)
                print(f"RESERVED: {r['park']} -> {m['name']} (resourceId {m['resourceId']})", file=sys.stderr)
            except Exception as e:
                print(f"RESERVE FAILED: {r['park']} -> {m['name']}: {e}", file=sys.stderr)
            if reserve_mode == "first":
                break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
