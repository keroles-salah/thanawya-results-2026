#!/usr/bin/env python3
"""
Google Colab — Thanawya 2026 Parallel Scraper
Scrapes ALL 919,396 students from natega.youm7.com in parallel.
Saves to Google Drive. Resume-capable. 10-20 workers.

INSTRUCTIONS:
1. Upload "all_seats.json" + "enrich_progress.json" to your Google Drive root
2. Open this in Colab: https://colab.research.google.com
3. Run each cell in order
"""

# ============================================================
# CELL 1: Mount Google Drive + Install (nothing to install)
# ============================================================
from google.colab import drive
drive.mount('/content/drive')

# ============================================================
# CELL 2: Imports & Config
# ============================================================
import json, time, re, ssl
from html import unescape as h
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen, HTTPCookieProcessor, build_opener, HTTPSHandler
from collections import defaultdict

# CONFIG — tweak these
WORKERS = 15          # parallel threads (15-20 works well on Colab)
BATCH_SIZE = 500      # save every N students
TIMEOUT = 20          # seconds per request
SLEEP = 0.1           # sleep between requests per worker

DRIVE_BASE = "/content/drive/MyDrive"
SEATS_FILE = f"{DRIVE_BASE}/all_seats.json"
PROGRESS_FILE = f"{DRIVE_BASE}/enrich_progress.json"
RESULTS_DIR = f"{DRIVE_BASE}/thanawya_results"

import os
os.makedirs(RESULTS_DIR, exist_ok=True)

# ============================================================
# CELL 3: SSL + Scraper Function
# ============================================================
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

def scrape_one(seat_no):
    """Scrape one student from natega.youm7.com"""
    cj = HTTPCookieProcessor()
    opener = build_opener(cj, HTTPSHandler(context=ssl_ctx))
    
    try:
        # Step 1: Get cookies
        opener.open(Request('https://natega.youm7.com/',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}),
            timeout=TIMEOUT)
        
        # Step 2: Search
        import urllib.parse
        data = urllib.parse.urlencode({'seating_no': str(seat_no), 'system': '1'}).encode()
        resp = opener.open(Request('https://natega.youm7.com/Result/1', data=data, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://natega.youm7.com',
            'Referer': 'https://natega.youm7.com/',
        }), timeout=TIMEOUT)
        
        body = resp.read().decode('utf-8', errors='replace')
        r = {"seat": str(seat_no)}
        
        # Name
        nm = re.search(r'student-result__name[^>]*>([^<]+)', body)
        if nm: r['name'] = h(nm.group(1)).replace('الأسم: ', '').strip()
        
        # Status
        sm = re.search(r'حالة الطالب:\s*([^<\n]+)', body)
        if sm: r['status'] = sm.group(1).strip()
        
        # School type
        st = re.search(r'نوعية التعليم:\s*([^<\n]+)', body)
        if st: r['school_type'] = h(st.group(1)).strip()
        
        # Branch
        bm = re.search(r'الشعبة:\s*([^<\n]+)', body)
        if bm: r['branch'] = bm.group(1).strip()
        
        # Total marks
        total_m = re.search(r'summary-value--marks[^>]*>([\d.]+) / ([\d.]+)', body)
        if total_m:
            r['total'] = float(total_m.group(1))
            r['max_marks'] = int(total_m.group(2))
        
        # Subjects table
        subjects = []
        table_m = re.search(r'<tbody>(.*?)</tbody>', body, re.DOTALL)
        if table_m:
            rows = re.findall(r'<tr>(.*?)</tr>', table_m.group(1), re.DOTALL)
            for row in rows:
                cols = re.findall(r'<td>(.*?)</td>', row, re.DOTALL)
                cols = [re.sub(r'<[^>]+>', '', h(c)).strip() for c in cols]
                if len(cols) >= 2:
                    subjects.append({
                        "subject": cols[0],
                        "mark": cols[1],
                        "pct": cols[2] if len(cols) > 2 else ""
                    })
        r['subjects'] = subjects
        r['ok'] = bool(r.get('name'))
        
        return (str(seat_no), r)
    except Exception as e:
        return (str(seat_no), {"ok": False, "error": str(e)[:200]})

# ============================================================
# CELL 4: Load Queue
# ============================================================
print("Loading seat numbers...")
with open(SEATS_FILE, 'r', encoding='utf-8') as f:
    all_seats = json.load(f)
print(f"Total students: {len(all_seats):,}")

# Load progress if exists
if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
        progress = json.load(f)
    print(f"Already done: {len(progress):,}")
else:
    progress = {}

# Build work queue (not yet in progress or failed)
queue = [s for s in all_seats if s not in progress]
# Also retry failed ones
retry = [k for k, v in progress.items() if not v.get('branch')]
queue = queue + retry
queue = list(dict.fromkeys(queue))  # deduplicate

enriched_before = len([v for v in progress.values() if v.get('branch')])
print(f"Queue: {len(queue):,} (includes {len(retry)} retries)")
print(f"Already enriched: {enriched_before:,}")
print(f"Workers: {WORKERS}")
print(f"Estimated time: {len(queue) / WORKERS * 3 / 3600:.1f} hours")
print("=" * 60)

# ============================================================
# CELL 5: RUN — Parallel Scraping
# ============================================================
start_time = time.time()
ok_count = 0
fail_count = 0
last_save = time.time()
SAVE_INTERVAL = 30  # save every 30 seconds minimum

def save_progress():
    """Save progress to Google Drive + periodic backup"""
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False)
    
    # Also save timestamped backup every 10K
    enriched_now = len([v for v in progress.values() if v.get('branch')])
    if enriched_now % 10000 < BATCH_SIZE:
        backup_file = f"{RESULTS_DIR}/backup_{enriched_now:07d}.json"
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False)

# Process in chunks
for chunk_start in range(0, len(queue), BATCH_SIZE):
    chunk = queue[chunk_start:chunk_start + BATCH_SIZE]
    
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(scrape_one, s): s for s in chunk}
        
        for fut in as_completed(futures):
            seat, data = fut.result()
            
            if data.get('ok'):
                progress[seat] = {
                    "branch": data.get('branch', ''),
                    "school": data.get('school_type', ''),
                    "subjects": data.get('subjects', [])
                }
                ok_count += 1
            else:
                progress[seat] = {}
                fail_count += 1
    
    # Save periodically
    if time.time() - last_save >= SAVE_INTERVAL:
        save_progress()
        last_save = time.time()
    
    # Progress report
    total_done = len(progress)
    elapsed = time.time() - start_time
    rate = (total_done - len(progress) + len(chunk)) / elapsed if elapsed > 0 else 0
    eta_h = (len(all_seats) - total_done) / rate / 3600 if rate > 0 else 0
    
    enriched_now = len([v for v in progress.values() if v.get('branch')])
    print(f"  [{total_done:,}/{len(all_seats):,}] OK:{ok_count} FAIL:{fail_count} | Enriched:{enriched_now:,} | {rate:.1f}/s | ETA:{eta_h:.1f}h")

# Final save
save_progress()

elapsed = time.time() - start_time
enriched_final = len([v for v in progress.values() if v.get('branch')])

print(f"\n{'='*60}")
print(f"DONE in {elapsed/3600:.1f} hours!")
print(f"Enriched: {enriched_final:,} / {len(all_seats):,} ({enriched_final/len(all_seats)*100:.1f}%)")
print(f"OK: {ok_count}, FAIL: {fail_count}")
print(f"Results saved to: {PROGRESS_FILE}")
print(f"Backups in: {RESULTS_DIR}/")

# ============================================================
# CELL 6 (Optional): Export Final JSON
# ============================================================

# Export all enriched students to a single clean JSON array
print("Exporting final enriched_students.json...")
enriched_list = []
for seat in all_seats:
    if seat in progress and progress[seat].get('branch'):
        enriched_list.append({
            "seating_no": seat,
            "branch": progress[seat]["branch"],
            "school_type": progress[seat]["school"],
            "subjects": progress[seat]["subjects"]
        })

output_file = f"{DRIVE_BASE}/thanawya_enriched_{enriched_final:07d}.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(enriched_list, f, ensure_ascii=False)

print(f"Exported {len(enriched_list):,} students to: {output_file}")
print("Download this file and merge with your local data!")

# Branch distribution
branches = defaultdict(int)
for e in enriched_list:
    branches[e['branch']] += 1
print(f"\nBranches: {dict(branches)}")
