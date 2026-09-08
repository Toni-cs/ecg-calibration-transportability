"""下载 nstdb（多种方式尝试）。"""
import os
import sys

os.makedirs("data/nstdb", exist_ok=True)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

import urllib.request

base_urls = [
    "https://physionet.org/files/nstdb/1.0.0/",
    "https://physionet.org/static/published-projects/noise-stress-test-database/noise-stress-test-database-1.0.0/",
]
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

ok, fail = 0, 0
for rec in ["bwam", "ma", "em"]:
    for ext in [".hea", ".dat"]:
        fn = rec + ext
        path = os.path.join("data/nstdb", fn)
        if os.path.exists(path) and os.path.getsize(path) > 100:
            print(f"SKIP {fn} (已存在)", flush=True)
            ok += 1
            continue
        downloaded = False
        for base in base_urls:
            url = base + fn
            try:
                if HAS_REQUESTS:
                    r = requests.get(url, headers=headers, timeout=30, stream=True)
                    if r.status_code == 200:
                        with open(path, "wb") as f:
                            for chunk in r.iter_content(8192):
                                f.write(chunk)
                        print(f"OK {fn} {os.path.getsize(path)} bytes (requests, {base[:40]})", flush=True)
                        ok += 1
                        downloaded = True
                        break
                    else:
                        print(f"FAIL {fn} HTTP {r.status_code} ({base[:40]})", flush=True)
                else:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        with open(path, "wb") as f:
                            f.write(resp.read())
                    print(f"OK {fn} {os.path.getsize(path)} bytes (urllib, {base[:40]})", flush=True)
                    ok += 1
                    downloaded = True
                    break
            except Exception as e:
                print(f"FAIL {fn}: {type(e).__name__}: {e} ({base[:40]})", flush=True)
        if not downloaded:
            fail += 1

print(f"\n完成: {ok} OK, {fail} FAIL", flush=True)
