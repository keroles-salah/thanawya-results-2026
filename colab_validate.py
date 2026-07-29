# 🧪 Thanaweya 2026 — Validator for Google Colab
# Compares ALL data from GitHub against natega.youm7.com
# Prints every single student result LIVE.

# ⚠️ CHANGE THIS for each Colab tab:
PART = 1  # 1 to 10
LIMIT = None  # None = ALL 92K students. Or set to 100 for quick test.

# ============================================================
import json,ssl,re,time,os,urllib.parse
from html import unescape as h
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.request import Request,urlopen,HTTPCookieProcessor,build_opener,HTTPSHandler

WORKERS = 8
TIMEOUT = 25

BASE = "https://raw.githubusercontent.com/keroles-salah/thanawya-results-2026/master"
SEATS_URL = f"{BASE}/seats_part{PART:02d}.json"
DATA_BASE = f"{BASE}/data"

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = False

# ===== LOAD OUR DATA =====
print(f"Part {PART:02d}: Loading seat list...")
resp = urlopen(SEATS_URL)
all_seats = json.loads(resp.read().decode('utf-8'))
if LIMIT: all_seats = all_seats[:LIMIT]
print(f"Loaded {len(all_seats):,} seats")

print("Loading our JSON data files into cache...")
our_data = {}
data_cache = {}
for seat in all_seats:
    px = seat[:4]
    if px not in data_cache:
        try:
            r = urlopen(f"{DATA_BASE}/{px}.json")
            data_cache[px] = json.loads(r.read().decode('utf-8'))
        except:
            data_cache[px] = {}
    if seat in data_cache[px]:
        our_data[seat] = data_cache[px][seat]
print(f"Cached {len(our_data):,} students")

# ===== YOUM7 SCRAPER =====
def scrape_youm7(seat_no):
    cj = HTTPCookieProcessor()
    op = build_opener(cj, HTTPSHandler(context=ssl_ctx))
    try:
        op.open(Request('https://natega.youm7.com/',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}), timeout=TIMEOUT)
        d = urllib.parse.urlencode({'seating_no': str(seat_no), 'system': '1'}).encode()
        resp = op.open(Request('https://natega.youm7.com/Result/1', data=d, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://natega.youm7.com', 'Referer': 'https://natega.youm7.com/',
        }), timeout=TIMEOUT)
        body = resp.read().decode('utf-8', errors='replace')
        r = {"ok": True}
        nm = re.search(r'student-result__name[^>]*>([^<]+)', body)
        if nm: r['name'] = h(nm.group(1)).replace('الأسم: ', '').strip()
        total_m = re.search(r'summary-value--marks[^>]*>([\d.]+) / ([\d.]+)', body)
        if total_m: r['total'] = total_m.group(1); r['max'] = total_m.group(2)
        bm = re.search(r'الشعبة:\s*([^<\n]+)', body)
        if bm: r['branch'] = bm.group(1).strip()
        return (str(seat_no), r)
    except Exception as e:
        return (str(seat_no), {"ok": False, "error": str(e)[:80]})

# ===== VALIDATE =====
print(f"\n🔍 Validating {len(all_seats):,} students against youm7...")
print(f"{'SEAT':>10} {'NAME':<30} {'OUR':>6} {'Y7':>6} {'BRANCH':<14} {'STATUS'}")
print("—" * 90)

ok = 0
fail = 0
deg_diff = 0
branch_diff = 0
not_found = 0
start = time.time()
SAVE_EVERY = 300  # Save progress every 300 students

for i in range(0, len(all_seats), SAVE_EVERY):
    chunk = all_seats[i:i+SAVE_EVERY]
    
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(scrape_youm7, s): s for s in chunk}
        for fut in as_completed(futures):
            seat, data = fut.result()
            
            if not data.get('ok'):
                print(f"{seat:>10} {'SCRAPE FAILED':<30} {'?':>6} {'?':>6} {'?':<14} ❌ SCRAPE_ERROR")
                fail += 1
                continue
            
            our = our_data.get(seat, {})
            our_deg = str(our.get('d', '?'))
            y7_deg = data.get('total', '?')
            our_branch = our.get('b', '?')
            y7_branch = data.get('branch', '?')
            our_name = our.get('n', '?')
            
            issues = []
            if our_deg != y7_deg:
                issues.append(f"DEG:{our_deg}!={y7_deg}")
                deg_diff += 1
            if our_branch != y7_branch:
                issues.append(f"BR:{our_branch}!={y7_branch}")
                branch_diff += 1
            
            if not our_data.get(seat):
                status = "⚠️ NOT_IN_DATA"
                not_found += 1
            elif not issues:
                status = "✅ OK"
                ok += 1
            else:
                status = "❌ " + " ".join(issues)
                fail += 1
            
            name_short = our_name[:28] if our_name else '?'
            print(f"{seat:>10} {name_short:<30} {our_deg:>6} {y7_deg:>6} {our_branch:<14} {status}")
    
    # Progress
    elapsed = time.time() - start
    done = i + len(chunk)
    rate = done / elapsed if elapsed > 0 else 0
    eta_m = (len(all_seats) - done) / rate / 60 if rate > 0 else 0
    total_ok = ok
    total_fail = fail
    print(f"\n—— [{done:,}/{len(all_seats):,}] {rate:.1f}/s ETA:{eta_m:.0f}m | ✅{total_ok} ❌{total_fail} | DEG≠{deg_diff} BR≠{branch_diff} ——\n")

elapsed = time.time() - start
print(f"\n{'='*60}")
print(f"PART {PART:02d} COMPLETE! {elapsed/60:.0f} minutes")
print(f"  ✅ OK: {ok:,}")
print(f"  ❌ FAIL: {fail:,}")
print(f"  📊 Degree differences: {deg_diff}")
print(f"  🎯 Branch differences: {branch_diff}")
print(f"  ⚠️  Not in data: {not_found}")
print(f"  📦 Total checked: {len(all_seats):,}")
if ok + fail > 0:
    print(f"  🎯 ACCURACY: {ok/(ok+fail)*100:.2f}%")
