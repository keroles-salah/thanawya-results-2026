# ============================================================
# THANAWYA 2026 DATA VALIDATOR - Google Colab
# ============================================================
# Compares ALL data from GitHub against natega.youm7.com
# Prints every student result LIVE. Resume-capable.
#
# HOW TO USE:
#   1. CHANGE PART = 1 below to 1-10
#   2. Run all cells
#   3. Open 10 Colab tabs for all parts in parallel
#   Total: ~2.5 hours for ALL 919K students
# ============================================================

"""
THANAWYA DATA VALIDATOR for Google Colab - Compares our data vs live youm7
Just change PART= at the top and run all cells.
"""
import sys,json,ssl,re,time,os
from html import unescape as h
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.request import Request,urlopen,HTTPCookieProcessor,build_opener,HTTPSHandler

# Colab doesn't need this wrapper - it handles UTF-8 natively

# CHANGE THIS for each Colab tab (1-10):
PART=1
# Set to None for ALL 92K, or a number for quick test:
LIMIT=None
WORKERS=8
TIMEOUT=25

BASE="https://raw.githubusercontent.com/keroles-salah/thanawya-results-2026/master"
SEATS_URL=f"{BASE}/seats_part{PART:02d}.json"
DATA_BASE=f"{BASE}/data"
PROGRESS_FILE=f"progress_validate_{PART:02d}.json"

ssl_ctx=ssl.create_default_context()
ssl_ctx.check_hostname=False
ssl_ctx.verify_mode=False

# ===== LOAD OUR DATA =====
print(f"Part {PART:02d}: Loading seat list...")
resp=urlopen(SEATS_URL)
all_seats=json.loads(resp.read().decode('utf-8'))
all_seats=all_seats[:LIMIT]
print(f"Loaded {len(all_seats):,} seats")

# Load progress if resuming
if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE,'r',encoding='utf-8') as f:
        done_list=json.load(f)
    done_set=set(done_list)
    print(f"Resuming: {len(done_list):,} already checked")
else:
    done_set=set()
    done_list=[]

# Filter queue
queue=[s for s in all_seats if s not in done_set]
print(f"Queue: {len(queue):,} remaining")

# Pre-load our data for queue
print("Loading our JSON data...")
our_data={}
data_cache={}
for seat in queue:
    prefix=seat[:4]
    if prefix not in data_cache:
        try:
            r=urlopen(f"{DATA_BASE}/{prefix}.json")
            data_cache[prefix]=json.loads(r.read().decode('utf-8'))
        except:
            data_cache[prefix]={}
    if seat in data_cache[prefix]:
        our_data[seat]=data_cache[prefix][seat]
print(f"Cached {len(our_data):,} students")

# ===== YOU M7 SCRAPER =====
def scrape_youm7(seat_no):
    cj=HTTPCookieProcessor()
    op=build_opener(cj,HTTPSHandler(context=ssl_ctx))
    try:
        op.open(Request('https://natega.youm7.com/',
            headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}),timeout=TIMEOUT)
        import urllib.parse
        d=urllib.parse.urlencode({'seating_no':str(seat_no),'system':'1'}).encode()
        resp=op.open(Request('https://natega.youm7.com/Result/1',data=d,headers={
            'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type':'application/x-www-form-urlencoded',
            'Origin':'https://natega.youm7.com','Referer':'https://natega.youm7.com/',
        }),timeout=TIMEOUT)
        body=resp.read().decode('utf-8',errors='replace')
        r={"ok":True}
        nm=re.search(r'student-result__name[^>]*>([^<]+)',body)
        if nm:r['name']=h(nm.group(1)).replace('الاسم: ','').strip()
        total_m=re.search(r'summary-value--marks[^>]*>([\d.]+) / ([\d.]+)',body)
        if total_m:r['total']=float(total_m.group(1));r['max']=int(total_m.group(2))
        bm=re.search(r'الشعبة:\s*([^<\n]+)',body)
        if bm:r['branch']=bm.group(1).strip()
        return (str(seat_no),r)
    except Exception as e:
        return (str(seat_no),{"ok":False,"error":str(e)[:80]})

# ===== VALIDATE =====
print(f"\n{'='*90}")
print(f"VALIDATING PART {PART:02d}: {len(queue):,} students")
print(f"{'='*90}")
print(f"{'SEAT':<10} {'NAME':<30} {'OUR':>8} {'Y7':>8} {'BRANCH':<14} RESULT")
print("-"*90)

total_ok=0
total_fail=0
deg_diff=0
branch_diff=0
not_found=0
start=time.time()
BATCH=200

for i in range(0,len(queue),BATCH):
    chunk=queue[i:i+BATCH]
    
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures={ex.submit(scrape_youm7,s):s for s in chunk}
        for fut in as_completed(futures):
            seat,data=fut.result()
            
            if not data.get('ok'):
                sys.stdout.write(f"{seat:<10} {'SCRAPE FAILED':<30} {'---':>8} {'---':>8} {'---':<14} ❌ SCRAPE_ERROR\n")
                sys.stdout.flush()
                total_fail+=1
                done_list.append(seat)
                continue
            
            our=our_data.get(seat,{})
            our_deg_raw=str(our.get('d','?'))
            y7_deg_raw=str(data.get('total','?'))
            our_branch=our.get('b','?')
            y7_branch=data.get('branch','?')
            our_name=our.get('n','?')
            
            # Compare degrees as floats (290 == 290.00)
            deg_mismatch=False
            try:
                od=float(our_deg_raw) if our_deg_raw!='?' else None
                yd=float(y7_deg_raw) if y7_deg_raw!='?' else None
                if od is not None and yd is not None:
                    deg_mismatch=(abs(od-yd)>0.001)
                else:
                    deg_mismatch=(our_deg_raw!=y7_deg_raw)
            except:
                deg_mismatch=(our_deg_raw!=y7_deg_raw)
            
            branch_mismatch=(our_branch!=y7_branch)
            
            # Display degrees (clean format)
            our_deg_disp=str(float(our_deg_raw)) if our_deg_raw!='?' and '.' not in str(our_deg_raw) else our_deg_raw
            y7_deg_disp=str(y7_deg_raw)
            
            name_short=our_name[:28] if our_name else '?'
            
            if not our_data.get(seat):
                status="⚠️ NOT_IN_DATA"
                not_found+=1
            elif not deg_mismatch and not branch_mismatch:
                status="✅ OK"
                total_ok+=1
            else:
                parts=[]
                if deg_mismatch:
                    parts.append(f"DEG:{our_deg_disp}!={y7_deg_disp}")
                    deg_diff+=1
                if branch_mismatch:
                    parts.append(f"BR:{our_branch}!={y7_branch}")
                    branch_diff+=1
                status="❌ "+" ".join(parts)
                total_fail+=1
            
            sys.stdout.write(f"{seat:<10} {name_short:<30} {our_deg_disp:>8} {y7_deg_disp:>8} {our_branch:<14} {status}\n")
            sys.stdout.flush()
            done_list.append(seat)
    
    # Save progress
    with open(PROGRESS_FILE,'w',encoding='utf-8') as f:
        json.dump(done_list,f)
    
    # Progress line
    done=i+len(chunk)
    elapsed=time.time()-start
    rate=done/elapsed if elapsed>0 else 0
    eta_m=(len(queue)-done)/rate/60 if rate>0 else 0
    print(f"\n--- [{done:,}/{len(queue):,}] {rate:.1f}/s ETA:{eta_m:.0f}m | ✅{total_ok} ❌{total_fail} | DEG≠{deg_diff} BR≠{branch_diff} ---\n")

elapsed=time.time()-start
print(f"\n{'='*60}")
print(f"PART {PART:02d} COMPLETE in {elapsed/60:.0f}m")
print(f"  ✅ OK:  {total_ok:,}")
print(f"  ❌ FAIL: {total_fail:,}")
print(f"  📊 Degree diffs: {deg_diff}")
print(f"  🎯 Branch diffs:  {branch_diff}")
print(f"  ⚠️  Not in data: {not_found}")
print(f"  📦 Total checked: {len(queue):,}")
if total_ok+total_fail>0:
    print(f"  🎯 ACCURACY: {total_ok/(total_ok+total_fail)*100:.2f}%")
