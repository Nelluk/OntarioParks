# Windows Setup Guide (Ontario Parks Roofed Watcher)

This guide is for Windows users who are comfortable with Python but don’t code day‑to‑day. It walks you through setup and running the script.

## What You’ll Need
- Windows 10/11
- Python 3.10+ installed
- A browser (Chrome/Edge) to log in and export cookies

## 1. Install Python (if needed)
1. Go to `https://www.python.org/downloads/` and install Python 3.
2. **Important:** Check the box **“Add Python to PATH”** during install.
3. Open **PowerShell** and confirm:
   ```powershell
   python --version
   ```

## 2. Open the Project Folder
1. Open **PowerShell**.
2. `cd` into the project:
   ```powershell
   cd C:\path\to\OntarioParks
   ```

## 3. Quick Start (Recommended)
Use the helper script below. It creates the virtual environment, installs dependencies, and runs the watcher.

```powershell
.\run.ps1
```

If PowerShell blocks scripts, run:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

If you want auto‑reserve:
```powershell
.\run.ps1 -Reserve
```

If you want to pass extra arguments to the Python script, add `--` first:
```powershell
.\run.ps1 -- --list-parks
```

## 4. Manual Setup (If You Prefer)
Create a virtual environment:
```powershell
python -m venv .venv
```

Activate it:
```powershell
.venv\Scripts\Activate.ps1
```

If you see a policy error, run:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
Then try activating again.

Install dependencies:
```powershell
pip install -r requirements.txt
```

## 5. Export Cookies (Required)
The site blocks automation; the script reuses **your** session cookies.

1. Open `https://reservations.ontarioparks.ca/` in your browser.
2. Make sure the page fully loads (and you’re signed in if you want).
3. Export cookies to:
   ```
   tmp\op_cookies.json
   ```

**Recommended method:** Use a browser extension like **Cookie‑Editor** to export cookies as JSON.

**Important:** Cookies are private. Do **not** share or commit them.

## 6. Configure Your Search
Copy the example config:
```powershell
copy config.example.json config.json
```

Edit `config.json` to set:
- Start/end dates
- Party size
- Parks and preferred site list (in priority order)
- Optional auto‑reserve settings

## 7. Run the Script
If you used the quick start, you can run:
```powershell
.\run.ps1
```

If you want auto‑reserve:
```powershell
.\run.ps1 -Reserve
```

Manual run (after activating the venv):
```powershell
python scripts\op_roofed_watch.py --use-config
```

If you enabled auto‑reserve in `config.json`, add `--reserve`:
```powershell
python scripts\op_roofed_watch.py --use-config --reserve
```

## Troubleshooting
**“Cookie file not found”**
- Make sure `tmp\op_cookies.json` exists.

**HTTP 403 or 400**
- Cookies expired. Re‑export them.
- If auto‑reserve fails, update `app_version` in `config.json` from your browser’s request headers.

**No availability**
- Try different dates or parks.
- Make sure your preferred site list matches real site numbers.

## Notes on Auto‑Reserve
- Auto‑reserve only adds the site to your cart. You still need to finish checkout manually.
- If your cart already has items, auto‑reserve is skipped unless `allow_existing_cart` is true.
