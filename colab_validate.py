"""
THANAWYA DATA VALIDATOR v2 — for Google Colab
Compares ALL fields: degree, branch, and per-subject marks
Prints every result LIVE. Resume-capable.

USAGE:
  1. Change PART = 1 below to 1-10
  2. Run all cells
  3. Open 10 Colab tabs for all parts in parallel
"""
import sys,json,ssl,re,time,os
from html import unescape as h
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.request import Request,urlopen,HTTPCookieProcessor,build_opener,HTTPSHandler

# Colab handles UTF-8 natively - no TextIOWrapper needed

# CHANGE THIS for each Colab tab (1-10):
PART = 1
# Set to None for ALL 92K, or a number for quick test:
LIMIT = None

WORKERS = 8
TIMEOUT = 25

BASE = "https://raw.githubusercontent.com/keroles-salah/thanawya-results-2026/master"
SEATS_URL = f"{BASE}/seats_part{PART:02d}.json"
DATA_BASE = f"{BASE}/data"
PROGRESS_FILE = f"progress_v2_{PART:02d}.json"

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = False

# Load seats
print(f"Part {PART:02d}: Loading seat list...")
resp = urlopen(SEATS_URL)
all_seats = json.loads(resp.read().decode('utf-8'))
if LIMIT:
    all_seats = all_seats[:LIMIT]
print(f"Loaded {len(all_seats):,} seats")

# Resume
if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
        done_list = json.load(f)
    done_set = set(done_list)
    print(f"Resuming: {len(done_list):,} already checked")
else:
    done_set = set()
    done_list = []

queue = [s for s in all_seats if s not in done_set]
print(f"Queue: {len(queue):,} remaining")

# Pre-load our data
print("Loading our JSON data...")
our_data = {}
data_cache = {}
for seat in queue:
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

# YOUM7 SCRAPER
def scrape_youm7(seat_no):
    cj = HTTPCookieProcessor()
    op = build_opener(cj, HTTPSHandler(context=ssl_ctx))
    try:
        op.open(Request('https://natega.youm7.com/',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}), timeout=TIMEOUT)
        import urllib.parse
        d = urllib.parse.urlencode({'seating_no': str(seat_no), 'system': '1'}).encode()
        resp = op.open(Request('https://natega.youm7.com/Result/1', data=d, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://natega.youm7.com', 'Referer': 'https://natega.youm7.com/',
        }), timeout=TIMEOUT)
        body = resp.read().decode('utf-8', errors='replace')
        r = {"ok": True}

        nm = re.search(r'student-result__name[^>]*>([^<]+)', body)
        if nm: r['name'] = h(nm.group(1)).replace('الاسم: ', '').strip()

        total_m = re.search(r'summary-value--marks[^>]*>([\d.]+) / ([\d.]+)', body)
        if total_m: r['total'] = float(total_m.group(1)); r['max'] = int(total_m.group(2))

        bm = re.search(r'الشعبة:\s*([^<\n]+)', body)
        if bm: r['branch'] = bm.group(1).strip()

        # Per-subject marks
        subjects = []
        table_m = re.search(r'<tbody>(.*?)</tbody>', body, re.DOTALL)
        if table_m:
            rows = re.findall(r'<tr>(.*?)</tr>', table_m.group(1), re.DOTALL)
            for row in rows:
                cols = re.findall(r'<td>(.*?)</td>', row, re.DOTALL)
                cols = [re.sub(r'<[^>]+>', '', h(c)).strip() for c in cols]
                if len(cols) >= 2:
                    subjects.append({"subject": cols[0], "mark": cols[1]})
        r['subjects'] = subjects

        return (str(seat_no), r)
    except Exception as e:
        return (str(seat_no), {"ok": False, "error": str(e)[:80]})

# Compare subjects — only the 9 youm7 subjects
Y7_SUBJECT_NAMES = [
    'اللغة العربية', 'اللغة الأجنبية الأولى', 'مجموع الرياضيات البحتة',
    'التاريخ', 'الجغرافيا', 'الكيمياء', 'الأحياء', 'الفيزياء', 'الإحصاء'
]

def compare_subjects(our_subs, y7_subs):
    if not y7_subs:
        return []
    our_map = {}
    if our_subs:
        for s in our_subs:
            our_map[s['subject'].strip()] = s.get('mark', '').strip()
    y7_map = {}
    for s in y7_subs:
        y7_map[s['subject'].strip()] = s.get('mark', '').strip()
    issues = []
    for subj in Y7_SUBJECT_NAMES:
        o = our_map.get(subj, '')
        y = y7_map.get(subj, '')
        if not o and not y:
            continue
        o_norm = re.sub(r'\s+/\s*', r' / ', o)
        y_norm = re.sub(r'\s+/\s*', r' / ', y)
        if o_norm != y_norm:
            issues.append(f"{subj[:20]}:{o}!={y}")
    return issues

# VALIDATE
print(f"\n{'='*100}")
print(f"VALIDATING PART {PART:02d} v2: degree + branch + 9 subjects")
print(f"{'='*100}")
print(f"{'SEAT':<10} {'NAME':<22} {'DEG':>7} {'BR':<14} {'SUB':<35} RESULT")
print("-"*100)

total_ok = 0
total_fail = 0
deg_diff = 0
branch_diff = 0
sub_diff = 0
not_found = 0
start = time.time()
BATCH = 200

for i in range(0, len(queue), BATCH):
    chunk = queue[i:i+BATCH]

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(scrape_youm7, s): s for s in chunk}
        for fut in as_completed(futures):
            seat, data = fut.result()

            if not data.get('ok'):
                print(f"{seat:<10} {'SCRAPE FAILED':<22} {'---':>7} {'---':<14} {'---':<35} ❌ SCRAPE")
                total_fail += 1
                done_list.append(seat)
                continue

            our = our_data.get(seat, {})
            our_deg_raw = str(our.get('d', '?'))
            y7_deg_raw = str(data.get('total', '?'))
            our_branch = our.get('b', '?')
            y7_branch = data.get('branch', '?')
            our_name = our.get('n', '?')
            our_subs = our.get('sub', [])
            y7_subs = data.get('subjects', [])

            # Float-safe degree compare
            deg_mismatch = False
            try:
                od = float(our_deg_raw) if our_deg_raw != '?' else None
                yd = float(y7_deg_raw) if y7_deg_raw != '?' else None
                if od is not None and yd is not None:
                    deg_mismatch = abs(od - yd) > 0.001
                else:
                    deg_mismatch = our_deg_raw != y7_deg_raw
            except:
                deg_mismatch = our_deg_raw != y7_deg_raw

            branch_mismatch = (our_branch != y7_branch)
            sub_issues = compare_subjects(our_subs, y7_subs)
            sub_has_issues = len(sub_issues) > 0

            name_short = our_name[:20] if our_name else '?'

            if not our_data.get(seat):
                status = "⚠️ NOT_IN_DATA"
                not_found += 1
            elif not deg_mismatch and not branch_mismatch and not sub_has_issues:
                status = "✅ ALL OK"
                total_ok += 1
            else:
                parts = []
                if deg_mismatch:
                    parts.append(f"DEG")
                    deg_diff += 1
                if branch_mismatch:
                    parts.append(f"BR")
                    branch_diff += 1
                if sub_has_issues:
                    parts.append(f"SUB({len(sub_issues)})")
                    sub_diff += len(sub_issues)
                status = "❌ " + "+".join(parts)
                total_fail += 1

            sub_info = f"{len(sub_issues)} diffs" if sub_has_issues else (f"{len(y7_subs)} OK" if y7_subs else "no data")

            print(f"{seat:<10} {name_short:<22} {our_deg_raw:>7} {our_branch:<14} {sub_info:<35} {status}")

            # Print subject mismatch details
            if sub_has_issues:
                for iss in sub_issues[:5]:
                    print(f"  └─ {iss}")
                if len(sub_issues) > 5:
                    print(f"  └─ ... +{len(sub_issues)-5} more")

            done_list.append(seat)

    # Save progress
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(done_list, f)

    done = i + len(chunk)
    elapsed = time.time() - start
    rate = done / elapsed if elapsed > 0 else 0
    eta_m = (len(queue) - done) / rate / 60 if rate > 0 else 0
    print(f"\n--- [{done:,}/{len(queue):,}] {rate:.1f}/s ETA:{eta_m:.0f}m | ✅{total_ok} ❌{total_fail} | DEG≠{deg_diff} BR≠{branch_diff} SUB≠{sub_diff} ---\n")

elapsed = time.time() - start
print(f"\n{'='*60}")
print(f"PART {PART:02d} v2 COMPLETE in {elapsed/60:.0f}m")
print(f"  ✅ ALL OK:  {total_ok:,}")
print(f"  ❌ FAIL:     {total_fail:,}")
print(f"  📊 Degree diffs:  {deg_diff}")
print(f"  🎯 Branch diffs:   {branch_diff}")
print(f"  📝 Subject diffs:  {sub_diff}")
print(f"  ⚠️  Not in data:  {not_found}")
print(f"  📦 Total checked: {len(queue):,}")
if total_ok + total_fail > 0:
    print(f"  🎯 ACCURACY: {total_ok/(total_ok+total_fail)*100:.2f}%")
