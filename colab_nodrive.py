"""
NO-DRIVE Google Colab — Thanawya 2026 Parallel Scraper
Pulls seat numbers from GitHub directly. Downloads results to your PC.
ZERO Google Drive needed.

INSTRUCTIONS:
1. Open https://colab.research.google.com → New Notebook
2. Copy-paste each cell below → Run All
3. At the end, file auto-downloads to your PC
"""

# ============================================================
# CELL 1: Imports & Config
# ============================================================
import json, re, ssl, time, os, urllib.parse, urllib.request
from html import unescape as h
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ⚙️ CHANGE THESE for each Colab tab:
PART = "01"               # Which part: 01, 02, ..., 10
WORKERS = 20              # Parallel threads
TIMEOUT = 20              # Seconds per request
SAVE_EVERY = 500          # Save progress every N students

# 📡 GitHub Raw URL (no Drive needed!)
GITHUB_RAW = "https://raw.githubusercontent.com/keroles-salah/thanawya-results-2026/master"
SEATS_URL = f"{GITHUB_RAW}/seats_part{PART}.json"

# SSL
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

print(f"🔹 Part: {PART} | Workers: {WORKERS}")
print(f"🔹 Seats: {SEATS_URL}")

# ============================================================
# CELL 2: Download seat list from GitHub
# ============================================================
print("Downloading seat list from GitHub...")
resp = urllib.request.urlopen(SEATS_URL)
all_seats = json.loads(resp.read())
print(f"✅ Loaded {len(all_seats):,} seat numbers")

# ============================================================
# CELL 3: Scraper function
# ============================================================
def scrape_one(seat_no):
    cj = urllib.request.HTTPCookieProcessor()
    opener = urllib.request.build_opener(cj, urllib.request.HTTPSHandler(context=ssl_ctx))
    try:
        # Get cookies
        opener.open(urllib.request.Request('https://natega.youm7.com/',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}),
            timeout=TIMEOUT)
        # Search
        data = urllib.parse.urlencode({'seating_no': str(seat_no), 'system': '1'}).encode()
        resp = opener.open(urllib.request.Request('https://natega.youm7.com/Result/1',
            data=data, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://natega.youm7.com',
                'Referer': 'https://natega.youm7.com/',
            }), timeout=TIMEOUT)
        body = resp.read().decode('utf-8', errors='replace')
        r = {"seat": str(seat_no)}
        nm = re.search(r'student-result__name[^>]*>([^<]+)', body)
        if nm: r['name'] = h(nm.group(1)).replace('الأسم: ', '').strip()
        sm = re.search(r'حالة الطالب:\s*([^<\n]+)', body)
        if sm: r['status'] = sm.group(1).strip()
        st = re.search(r'نوعية التعليم:\s*([^<\n]+)', body)
        if st: r['school_type'] = h(st.group(1)).strip()
        bm = re.search(r'الشعبة:\s*([^<\n]+)', body)
        if bm: r['branch'] = bm.group(1).strip()
        total_m = re.search(r'summary-value--marks[^>]*>([\d.]+) / ([\d.]+)', body)
        if total_m:
            r['total'] = float(total_m.group(1))
            r['max_marks'] = int(total_m.group(2))
        subjects = []
        table_m = re.search(r'<tbody>(.*?)</tbody>', body, re.DOTALL)
        if table_m:
            rows = re.findall(r'<tr>(.*?)</tr>', table_m.group(1), re.DOTALL)
            for row in rows:
                cols = re.findall(r'<td>(.*?)</td>', row, re.DOTALL)
                cols = [re.sub(r'<[^>]+>', '', h(c)).strip() for c in cols]
                if len(cols) >= 2:
                    subjects.append({"subject": cols[0], "mark": cols[1],
                                     "pct": cols[2] if len(cols) > 2 else ""})
        r['subjects'] = subjects
        r['ok'] = bool(r.get('name'))
        return (str(seat_no), r)
    except Exception as e:
        return (str(seat_no), {"ok": False, "error": str(e)[:200]})

# ============================================================
# CELL 4: Load progress (if resuming)
# ============================================================
# Colab's /content/ persists during session. Save progress here.
PROGRESS_FILE = f"/content/progress_part{PART}.json"

if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
        progress = json.load(f)
    print(f"📂 Resuming: {len(progress):,} already processed")
else:
    progress = {}

queue = [s for s in all_seats if s not in progress or not progress[s].get('branch')]
done_before = len([v for v in progress.values() if v.get('branch')])
print(f"📊 Total: {len(all_seats):,} | Queued: {len(queue):,} | Enriched: {done_before:,}")
print(f"⏱️  Estimated: {len(queue)/WORKERS*3/3600:.1f}h with {WORKERS} workers")
print("=" * 60)

# ============================================================
# CELL 5: 🚀 RUN — Parallel Scraping
# ============================================================
ok = 0
fail = 0
start = time.time()

for i in range(0, len(queue), SAVE_EVERY):
    chunk = queue[i:i + SAVE_EVERY]
    
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(scrape_one, s): s for s in chunk}
        for fut in as_completed(futures):
            seat, data = fut.result()
            if data.get('ok'):
                progress[seat] = {
                    "branch": data.get('branch', ''),
                    "school": data.get('school_type', ''),
                    "subjects": data.get('subjects', [])
                }
                ok += 1
            else:
                progress[seat] = {}
                fail += 1
    
    # Save progress to /content (survives if Colab doesn't disconnect)
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False)
    
    done = len(progress)
    elapsed = time.time() - start
    rate = (i + len(chunk)) / elapsed if elapsed else 0
    enriched = len([v for v in progress.values() if v.get('branch')])
    eta_h = (len(queue) - i - len(chunk)) / rate / 3600 if rate and (len(queue) > i + len(chunk)) else 0
    
    print(f"  [{i+len(chunk):,}/{len(queue):,}] "
          f"OK:{ok} FAIL:{fail} | "
          f"Enriched:{enriched:,} | "
          f"{rate:.1f}/s | "
          f"ETA:{eta_h:.1f}h")

elapsed = time.time() - start
enriched = len([v for v in progress.values() if v.get('branch')])

print(f"\n{'='*60}")
print(f"✅ DONE! {elapsed/3600:.1f}h | {elapsed/60:.0f}min")
print(f"📊 Enriched: {enriched:,} / {len(all_seats):,} ({enriched/len(all_seats)*100:.1f}%)")
print(f"📊 OK: {ok} | FAIL: {fail}")

# ============================================================
# CELL 6: 📥 Export & Auto-Download
# ============================================================
OUTPUT = f"/content/enriched_part{PART}.json"

enriched_list = []
for s in all_seats:
    if s in progress and progress[s].get("branch"):
        enriched_list.append({
            "seating_no": s,
            "branch": progress[s]["branch"],
            "school_type": progress[s]["school"],
            "subjects": progress[s]["subjects"]
        })

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(enriched_list, f, ensure_ascii=False)

# Stats
branches = defaultdict(int)
for e in enriched_list:
    branches[e['branch']] += 1

import os as _os
size_mb = _os.path.getsize(OUTPUT) / (1024*1024)
print(f"\n📁 Saved: {OUTPUT}")
print(f"📏 Size: {size_mb:.1f} MB")
print(f"📊 Students: {len(enriched_list):,}")
print(f"🏷️  Branches: {dict(branches)}")

# Auto-download to your PC
from google.colab import files
files.download(OUTPUT)
print("\n⬇️  Download started! File will save to your Downloads folder.")

# ============================================================
# 🎯 TO RUN ALL 10 PARTS IN PARALLEL:
#    - Open 10 Colab tabs
#    - In each tab, change PART = "01", "02", ..., "10"
#    - Run all cells in each tab
#    - All 10 tabs run simultaneously → ~1.5 hours total
# ============================================================
