# 🚀 Google Colab — سحب موازي لبيانات نتيجة الثانوية العامة 2026

## الخطوات (5 دقايق بس)

### Step 1: حمل ملفين من Google Drive

الملفات موجودة على GitHub (هتلاقيهم في الريبو بعد push):

| الملف | الرابط |
|-------|--------|
| `seats_part01.json` (988 KB) | [تحميل](https://raw.githubusercontent.com/keroles-salah/thanawya-results-2026/master/seats_part01.json) |
| `colab_progress.json` (381 KB) | [تحميل](https://raw.githubusercontent.com/keroles-salah/thanawya-results-2026/master/colab_progress.json) |

### Step 2: افتح Google Colab

1. روح على: https://colab.research.google.com
2. اعمل **New Notebook**
3. اضغط **Runtime → Change runtime type → GPU: None (CPU is fine)**
4. هات الكود الكامل من `colab_scraper.py` أو من تحت

### Step 3: الكود اللي تحطه في الخلايا

#### Cell 1 — Mount Drive
```python
from google.colab import drive
drive.mount('/content/drive')
```

#### Cell 2 — Setup
```python
import json, re, ssl, time, os, urllib.parse
from html import unescape as h
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen, HTTPCookieProcessor, build_opener, HTTPSHandler
from collections import defaultdict

# ⚙️ CONFIG
WORKERS = 20         # 20 thread متوازي
BATCH = 500          # save كل 500 طالب
TIMEOUT = 20         # seconds timeout

# 📁 Paths
DRIVE = "/content/drive/MyDrive"
# ⚠️ غير اسم الملف حسب الجزء اللي شغال عليه:
PART = "01"  # 01-10
SEATS_FILE = f"{DRIVE}/seats_part{PART}.json"
PROGRESS_FILE = f"{DRIVE}/enrich_progress_part{PART}.json"
RESULTS_FILE = f"{DRIVE}/enriched_part{PART}.json"

# SSL
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE
```

#### Cell 3 — Scraper function
```python
def scrape_one(seat_no):
    cj = HTTPCookieProcessor()
    opener = build_opener(cj, HTTPSHandler(context=ssl_ctx))
    try:
        opener.open(Request('https://natega.youm7.com/',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}), timeout=TIMEOUT)
        data = urllib.parse.urlencode({'seating_no': str(seat_no), 'system': '1'}).encode()
        resp = opener.open(Request('https://natega.youm7.com/Result/1', data=data, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://natega.youm7.com', 'Referer': 'https://natega.youm7.com/',
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
                    subjects.append({"subject": cols[0], "mark": cols[1], "pct": cols[2] if len(cols) > 2 else ""})
        r['subjects'] = subjects
        r['ok'] = bool(r.get('name'))
        return (str(seat_no), r)
    except Exception as e:
        return (str(seat_no), {"ok": False, "error": str(e)[:200]})
```

#### Cell 4 — Load Queue
```python
with open(SEATS_FILE, 'r') as f:
    all_seats = json.load(f)
if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, 'r') as f:
        progress = json.load(f)
else:
    progress = {}
queue = [s for s in all_seats if s not in progress or not progress[s].get('branch')]
done_before = len([v for v in progress.values() if v.get('branch')])
print(f"Total: {len(all_seats):,} | Queued: {len(queue):,} | Done: {done_before:,}")
print(f"Workers: {WORKERS} | Estimated: {len(queue)/WORKERS*3/3600:.1f}h")
```

#### Cell 5 — RUN 🚀
```python
ok = fail = 0
start = time.time()

for i in range(0, len(queue), BATCH):
    chunk = queue[i:i+BATCH]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(scrape_one, s): s for s in chunk}
        for fut in as_completed(futures):
            seat, data = fut.result()
            if data.get('ok'):
                progress[seat] = {"branch": data.get('branch',''), "school": data.get('school_type',''), "subjects": data.get('subjects',[])}
                ok += 1
            else:
                progress[seat] = {}
                fail += 1
    
    # Save every batch
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, ensure_ascii=False)
    
    done = len(progress)
    elapsed = time.time() - start
    rate = (i+len(chunk)) / elapsed if elapsed else 0
    eta_h = (len(queue)-i-len(chunk)) / rate / 3600 if rate else 0
    enriched = len([v for v in progress.values() if v.get('branch')])
    print(f"  [{i+len(chunk):,}/{len(queue):,}] OK:{ok} FAIL:{fail} | Enriched:{enriched:,} | {rate:.1f}/s | ETA:{eta_h:.1f}h")

elapsed = time.time() - start
enriched = len([v for v in progress.values() if v.get('branch')])
print(f"\nDONE in {elapsed/3600:.1f}h! Enriched: {enriched:,}")
```

#### Cell 6 — Export & Download
```python
enriched_list = [{"seat":s,"branch":p["branch"],"school":p["school"],"subjects":p["subjects"]}
                  for s,p in progress.items() if p.get("branch")]
with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
    json.dump(enriched_list, f, ensure_ascii=False)
print(f"Exported {len(enriched_list):,} students to {RESULTS_FILE}")

# Branch stats
branches = defaultdict(int)
for e in enriched_list: branches[e['branch']] += 1
print(f"Branches: {dict(branches)}")

# Download link
from google.colab import files
files.download(RESULTS_FILE)
```

### Step 4: التشغيل المتوازي

علشان تسحب **أسرع 10 أضعاف**:
- افتح 10 تبويبات مختلفة في Colab
- كل تبويب يشتغل على جزء مختلف (`PART = "01"`، `PART = "02"`، ... إلخ)
- كل جزء 92 ألف طالب → حوالي 1.5 ساعة بالـ 20 thread

| الجزء | أرقام الجلوس | الوقت المتوقع |
|-------|-------------|---------------|
| Part 01 | 2000001 - 2090038 | ~1.5h |
| Part 02 | 2090039 - 2180590 | ~1.5h |
| ... | ... | ... |
| Part 10 | 2902920 - 2994792 | ~1.5h |

**كله مع بعض = ~1.5 ساعة بدل 25 ساعة!**

### Step 5: دمج النتائج

بعد ما كل الأجزاء تخلص، حمل الـ 10 ملفات (`enriched_part01.json` ... `enriched_part10.json`) وهندمجهم على جهازك في ملف واحد.

---

**جاهز؟** كل الملفات موجودة على GitHub: https://github.com/keroles-salah/thanawya-results-2026
