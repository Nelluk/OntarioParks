# Ontario Parks Reservations – Internal API Notes (Roofed Accommodations)

This doc summarizes internal endpoints observed on `https://reservations.ontarioparks.ca/` and how to use them for personal availability checks.

## WAF / Bot Protection
- Direct `curl` to the origin returns an Azure WAF JS challenge (403).
- `curl_cffi` can access the API **if you provide cookies from a real browser session**.
- Export cookies from a real session to `tmp/op_cookies.json` and reuse them for API calls.
- **Do not commit cookies** to a public repo. Treat them as secrets.

Minimal example (using `curl_cffi`):
```python
from curl_cffi import requests
import json

cookies = json.load(open("tmp/op_cookies.json"))
s = requests.Session()
for c in cookies:
    s.cookies.set(c['name'], c['value'], domain=c.get('domain'), path=c.get('path'))

resp = s.get("https://reservations.ontarioparks.ca/api/resourceLocation", impersonate="chrome110")
print(resp.status_code, resp.headers.get("content-type"))
```

## Key Endpoints (Observed)

### Booking / Search Metadata
- `GET /api/bookingcategories`
  - Lists booking categories. **Roofed Accommodation** appears with `bookingCategoryId = 2`.
- `GET /api/searchcriteriatabs`
  - Groups booking categories into UI tabs (Campsite, Roofed, Backcountry, etc.).
- `GET /api/capacitycategory/capacitycategories`
  - Party size definitions. The UI uses `capacityCategoryId = -32768` for “Total Party Size – Number Only”.

### Parks / Locations
- `GET /api/resourceLocation`
  - Full list of parks (“resource locations”). Each entry has:
    - `resourceLocationId`
    - `rootMapId`
    - `resourceCategoryIds`

### Maps / Resources
- `GET /api/maps?resourceLocationId={id}`
  - Returns all maps for a park.
  - Each map can include `mapResources` with `resourceId` values.
  - Use the list of map IDs with resources to query availability.

- `GET /api/resourcelocation/resources?resourceLocationId={id}`
  - Returns a **dictionary keyed by `resourceId`**.
  - Each entry has `localizedValues` (name), `resourceCategoryId`, `mapIds`, etc.
  - This is how you map availability IDs to site/cabin names.

### Availability (Core)
- `GET /api/availability/map`

Example parameters:
```
mapId={mapId}
bookingCategoryId=2
startDate=2026-07-15
endDate=2026-07-17
getDailyAvailability=true
peopleCapacityCategoryCounts=[{"capacityCategoryId":-32768,"subCapacityCategoryId":null,"count":2}]
cartUid=...
cartTransactionUid=...
```

Notes:
- The endpoint accepts **blank** `bookingUid` and `groupHoldUid` in testing.
- `cartUid` and `cartTransactionUid` can be obtained from `GET /api/cart`.
- `resourceAvailabilities` is an object keyed by `resourceId`.
- With `getDailyAvailability=true`, each resource has an array of daily `{ availability, remainingQuota }` entries.

### Other Useful Endpoints
- `GET /api/cart` → `cartUid`, `cartTransactionUid` needed for availability.
- `GET /api/resourcecategory` → category names (filter to “Cabin”, “Cottage”, “Soft-sided Shelter”, etc.).
- `GET /api/dateschedule/resourcelocationid?resourceLocationId={id}` → operating seasons and date schedules.

## Availability Codes (Observed)
These are inferred from live testing and may change:
- `5` → **Available** (observed for summer roofed/cabin resources)
- `2` → **Unavailable / Not Operating** (observed for winter dates)
- Map-level `mapAvailabilities` used other codes (`0`, `6`) in some cases; resource-level codes are more reliable for scripting.

If you observe different codes, adjust your logic accordingly.

## Script Provided
See `scripts/op_roofed_watch.py` for a working example that:
- Loads cookies from `tmp/op_cookies.json`
- Resolves park names to `resourceLocationId`
- Filters resources to roofed category names
- Queries availability per map
- Outputs available roofed accommodations as JSON

Example:
```bash
.venv/bin/python scripts/op_roofed_watch.py \
  --start 2026-07-15 --end 2026-07-17 --party-size 2 \
  --parks "Pinery Provincial Park, Killbear Provincial Park"
```

## Cookie Export (General)
Use any browser method you prefer to export cookies after you have visited the site (extensions, DevTools, or Playwright). Save them to `tmp/op_cookies.json` in this format:

```json
[
  {
    "name": "XSRF-TOKEN",
    "value": "...",
    "domain": "reservations.ontarioparks.ca",
    "path": "/"
  }
]
```

Then reuse them with `curl_cffi` as shown above.
