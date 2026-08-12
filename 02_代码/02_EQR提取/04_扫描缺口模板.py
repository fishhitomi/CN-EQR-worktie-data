# -*- coding: utf-8 -*-
"""扫描无 EQR 公告：用当前提取规则重跑，统计新提取量并归纳仍漏的正文格式。

输出：
  02_中间数据/EQR提取/缺口扫描_新提取.csv   修复规则后能从原“无 EQR”公告中新提取到 EQR 的公告
  02_中间数据/EQR提取/缺口扫描_仍漏片段.csv  仍无法提取且含复核人标签的上下文片段（供归纳模板）
"""
import os, re, sys, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE, "02_代码", "02_EQR提取"))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "ext", os.path.join(BASE, "02_代码", "02_EQR提取", "03_提取EQR姓名.py"))
ext = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ext)

OUT_DIR = os.path.join(BASE, "01_中间数据", "EQR提取")

def scan(row):
    aid = str(row["announcementId"]) if row.get("announcementId") else ""
    date = str(row.get("date") or "")[:10]
    sub = date.replace("-", "") or "nodate"
    pdf = os.path.join(ext.PDF_DIR, sub, f"{aid}.PDF")
    text = ext.extract_text(pdf) if os.path.exists(pdf) else ""
    title = str(row.get("title") or "")
    eqr = ext.extract_names(text)
    if eqr:
        return {"code": row["secCode"], "date": date, "aid": aid, "title": title,
                "eqr_new": "、".join(eqr), "still_miss": False, "frag": ""}
    # 仍漏：找复核相关标签上下文
    t = ext.collapse(text)
    frags = []
    for m in re.finditer(r"项目质量控制复核人|项目质量控制负责人|项目质量复核人员|独立复核合伙人|独立复核人|质量控制复核合伙人|质量控制复核人|质量控制负责人|质量复核人员|质量复核合伙人|质量复核人|复核合伙人|复核人", t):
        s = max(0, m.start() - 8)
        e = min(len(t), m.end() + 18)
        frags.append(t[s:e])
    return {"code": row["secCode"], "date": date, "aid": aid, "title": title,
            "eqr_new": "", "still_miss": bool(frags), "frag": " || ".join(frags[:6])}

def main():
    ext.NAME_SET = ext.load_name_sets()
    df = pd.read_csv(os.path.join(BASE, "01_中间数据", "EQR提取", "EQR_公告级.csv"),
                     encoding="utf-8-sig", dtype={"secCode": str})
    miss = df[df["eqr"].isna() | (df["eqr"].astype(str).str.strip() == "")].copy()
    # 优先处理标题可能含 EQR 的公告，其余也扫
    miss = miss[miss["title"].astype(str).str.contains(
        "聘任|续聘|聘请|变更|审计机构|会计师事务所|质量控制|复核", na=False)]
    print("待扫描公告:", len(miss))
    rows = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(scan, r): i for i, r in miss.iterrows()}
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                rows.append(fut.result())
            except Exception as e:
                rows.append({"code": futs[fut], "error": str(e), "still_miss": False, "frag": ""})
            if done % 1000 == 0 or done == len(futs):
                print(f"进度 {done}/{len(futs)} 用时 {time.time()-t0:.0f}s", flush=True)
    out = pd.DataFrame(rows)
    new = out[out["eqr_new"] != ""]
    print("\n修复后新增可提取公告:", len(new), f"({100*len(new)/len(out):.1f}%)")
    print("仍漏且含复核标签:", int((out["still_miss"] == True).sum()))
    new.to_csv(os.path.join(OUT_DIR, "缺口扫描_新提取.csv"), index=False, encoding="utf-8-sig")
    still = out[out["still_miss"] == True].copy()
    still.to_csv(os.path.join(OUT_DIR, "缺口扫描_仍漏片段.csv"), index=False, encoding="utf-8-sig")
    # 聚类片段：按“标签词+后 10 字”统计
    pat = Counter()
    samples = defaultdict(list)
    for f in still["frag"].dropna():
        for part in f.split(" || "):
            key = re.sub(r"[\u4e00-\u9fa5·]{2,4}(?:先生|女士)?$", "<名>", part)[:20]
            pat[key] += 1
            if len(samples[key]) < 3:
                samples[key].append(part)
    print("\n仍漏片段 top 模式（标签+前 8 后 18 字）：")
    for k, c in pat.most_common(35):
        print(f"  [{c}] {k}")
        for s in samples[k]:
            print(f"      例: {s}")

if __name__ == "__main__":
    main()
