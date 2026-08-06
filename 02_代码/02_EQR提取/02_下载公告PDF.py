# -*- coding: utf-8 -*-
"""按公告清单批量下载 PDF（断点续传 + 并发 + 失败日志）。

用法：python 02_下载公告PDF.py [--limit N] [--workers 8]
"""
import os, re, sys, time, shutil, argparse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(BASE, "00_原始数据", "巨潮公告", "公告PDF_全量")
OLD = os.path.join(BASE, "00_原始数据", "巨潮公告", "公告PDF")
FAIL = os.path.join(BASE, "02_中间数据", "巨潮公告清单", "下载失败.csv")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def ann_id(row):
    if row.get("announcementId"):
        return str(row["announcementId"])
    m = re.search(r"/(\d+)\.PDF$", str(row["url"]))
    return m.group(1) if m else None

def dest_path(row):
    aid = ann_id(row)
    date = str(row.get("date") or "")[:10].replace("-", "")
    sub = date or "nodate"
    d = os.path.join(OUT, sub)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{aid}.PDF")

def already_have(row):
    p = dest_path(row)
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return p, True
    aid = ann_id(row)
    old = os.path.join(OLD, f"{aid}.PDF")
    if os.path.exists(old) and os.path.getsize(old) > 0:
        shutil.copy2(old, p)
        return p, True
    return p, False

def download_one(row):
    p, have = already_have(row)
    if have:
        return p, None
    url = str(row["url"])
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r, open(p + ".tmp", "wb") as f:
                shutil.copyfileobj(r, f)
            if os.path.getsize(p + ".tmp") > 0:
                os.replace(p + ".tmp", p)
                return p, None
        except Exception as e:
            time.sleep(1.5 * (i + 1))
    if os.path.exists(p + ".tmp"):
        try:
            os.remove(p + ".tmp")
        except Exception:
            pass
    return p, str(row.get("url"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--list", type=str,
                    default=os.path.join(BASE, "02_中间数据", "巨潮公告清单", "公告清单_筛选.csv"))
    args = ap.parse_args()
    df = pd.read_csv(args.list, encoding="utf-8-sig", dtype={"secCode": str})
    if args.limit:
        df = df.head(args.limit)
    print("待处理:", len(df))
    ok = 0
    fails = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(download_one, row): row for _, row in df.iterrows()}
        done = 0
        for fut in as_completed(futs):
            done += 1
            _, err = fut.result()
            if err:
                fails.append({"url": err, "row": done})
            else:
                ok += 1
            if done % 500 == 0 or done == len(futs):
                el = time.time() - t0
                print(f"进度 {done}/{len(futs)}  成功 {ok}  失败 {len(fails)}  用时 {el:.0f}s", flush=True)
    if fails:
        pd.DataFrame(fails).to_csv(FAIL, index=False, encoding="utf-8-sig")
    print("完成。成功:", ok, "失败:", len(fails), "总耗时:", round(time.time() - t0, 1), "s")

if __name__ == "__main__":
    main()
