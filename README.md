# Ontario Parks Roofed Availability Watcher

This is a small **personal-use** script that checks roofed accommodation availability on the Ontario Parks reservation site. By default it only reports availability so you can decide when to book. There is an **optional** auto-reserve mode that adds a matching site to your cart (you still complete checkout manually).

## Who This Is For
- Family and friends who want a simple way to check roofed accommodation availability.
- You do **not** need to be a programmer, but you do need to follow the steps below once.

## What You Need
- A computer with Python 3 installed
- Access to the Ontario Parks reservation site in a web browser

## Setup (One Time)

1. Open a terminal in this folder.
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

## Export Cookies (Required)
The site blocks automated requests. This script works by reusing **your** browser session cookies.

1. Open `https://reservations.ontarioparks.ca/` in your browser.
2. Make sure the page fully loads.
3. Export the site cookies to a JSON file named:
   ```
   tmp/op_cookies.json
   ```

**How to export cookies** (pick one):
- Use a browser extension that exports cookies as JSON (for example: “Cookie-Editor”).
- Or use DevTools if you are comfortable doing so.

**Important:** Cookies are private. Do **not** share them or commit them to GitHub.

## Run The Script
Basic example:
```bash
.venv/bin/python scripts/op_roofed_watch.py \
  --start 2026-07-15 --end 2026-07-17 --party-size 2 \
  --parks "Pinery Provincial Park, Killbear Provincial Park"
```

### Use A Config File (Recommended)
Copy `config.example.json` to `config.json` and edit the parks and preferred sites:

```bash
cp config.example.json config.json
```

Then run:
```bash
.venv/bin/python scripts/op_roofed_watch.py --use-config
```

**Preferred sites** are in priority order (first is highest priority). If any preferred site is available, the script reports the highest-ranked match.

### Optional: Auto-Reserve (Adds To Cart)
If enabled, the script will attempt to add the top-ranked matching site to your cart (a temporary hold). You still need to complete checkout in the browser.

Enable in `config.json`:
```json
{
  "auto_reserve": true,
  "reserve_mode": "first",
  "allow_existing_cart": false
}
```

Or on the command line:
```bash
.venv/bin/python scripts/op_roofed_watch.py --use-config --reserve
```

Notes:
- `reserve_mode` can be `first` (default) or `all`.
- If your cart already has items, auto-reserve is skipped unless `allow_existing_cart` is true.
- Auto-reserve requires the `XSRF-TOKEN` cookie to be present in `tmp/op_cookies.json`.
- If auto-reserve fails with a 400/403, update `app_version` in `config.json` from the latest browser request headers.

### Useful Options
- `--list-parks` Show all park names the system knows about
- `--list-categories` Show the roofed categories detected by keywords
- `--park` Repeatable single park name (instead of comma-separated list)
- `--category-keyword` Override what counts as “roofed”
- `--available-code` If availability codes change (default is `5`)
- `--use-config` Read search criteria and preferred sites from `config.json`
- `--config` Use a different config path
- `--reserve` Attempt to add the best match to the cart
- `--reserve-mode` `first` or `all`
- `--allow-existing-cart` Allow auto-reserve even if cart already has items

### Output
The script prints JSON that looks like this:
```json
{
  "start": "2026-07-15",
  "end": "2026-07-17",
  "partySize": 2,
  "availableCode": 5,
  "results": [
    {
      "park": "Pinery Provincial Park",
      "resourceLocationId": -2147483568,
      "available": [
        {"resourceId": -2147470000, "name": "Cabin 1", "categoryId": -2147483645}
      ],
      "preferredMatch": {"resourceId": -2147470000, "name": "Cabin 1", "categoryId": -2147483645}
    }
  ]
}
```

If the `available` list is empty, nothing matches right now.
If a preferred site is found, the script prints a `MATCH:` line to stderr (useful for cron/email piping).
If auto-reserve is enabled and succeeds, the script prints a `RESERVED:` line to stderr.

## Troubleshooting

**“Cookie file not found”**
- Make sure `tmp/op_cookies.json` exists.

**“HTTP 403” or “Azure WAF”**
- Your cookies are missing or expired. Re-export them.

**No availability**
- Try different dates or parks.
- Run `--list-categories` to confirm your roofed category filter.

## Safety / Respectful Use
- This is intended for **personal use** only.
- Use a reasonable polling interval (don’t hammer the API).
- Follow Ontario Parks’ rules and terms.

## More Details
See `docs/op_api_notes.md` for the internal endpoint notes and availability code observations.
