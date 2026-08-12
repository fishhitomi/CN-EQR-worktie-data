import os, pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = pd.read_csv(os.path.join(BASE, "01_中间数据", "WORKTIE", "WORKTIE_2020-2023.csv"),
                  encoding="utf-8-sig", dtype={"stkcd": str})
ann = pd.read_csv(os.path.join(BASE, "01_中间数据", "EQR提取", "EQR_公告级.csv"),
                  encoding="utf-8-sig", dtype={"secCode": str})
ann["has_eqr"] = ann["eqr"].notna() & (ann["eqr"].astype(str).str.strip() != "")
ann["date"] = pd.to_datetime(ann["date"], errors="coerce")
missing = out[out["eqr_name"].isna() | (out["eqr_name"].astype(str) == "")].copy()
missing["code6"] = missing["stkcd"].str.zfill(6)

# 桶1：有公告但无 EQR 提取 —— 统计公告标题关键词
titles = []
for _, r in missing.iterrows():
    code = r["code6"]; y = int(r["year"])
    lo = pd.Timestamp(f"{y-1}-10-01"); hi = pd.Timestamp(f"{y+1}-12-31")
    sub = ann[(ann["secCode"].astype(str).str.zfill(6) == code) & (ann["date"] >= lo) & (ann["date"] <= hi) & (~ann["has_eqr"])]
    titles.extend(sub["title"].astype(str).tolist())
print("桶1（有公告但无 EQR）公告标题总数:", len(titles))
def tcat(t):
    if "变更" in t: return "变更类"
    if "签字" in t: return "签字类"
    if "聘任" in t or "续聘" in t or "聘请" in t or "改聘" in t: return "聘任类"
    if "复核" in t: return "复核类"
    return "其他"
from collections import Counter
print(Counter(tcat(t) for t in titles).most_common(10))
print("\n其他类样例（前20）:")
for t in [t for t in titles if tcat(t) == "其他"][:20]:
    print(" -", t[:80])

# 桶2：有 EQR 公告但未映射到该年 —— 看这些公告的标题年度/日期
print("\n===== 桶2（有 EQR 公告但未映射）=====")
cnt = 0
for _, r in missing.iterrows():
    code = r["code6"]; y = int(r["year"])
    lo = pd.Timestamp(f"{y-1}-10-01"); hi = pd.Timestamp(f"{y+1}-12-31")
    sub = ann[(ann["secCode"].astype(str).str.zfill(6) == code) & (ann["date"] >= lo) & (ann["date"] <= hi) & ann["has_eqr"]]
    if len(sub) == 0:
        continue
    print(f"--- {code} {y} 缺失；EQR 公告 {len(sub)} 条：")
    for _, a in sub.iterrows():
        print("   ", a["date"].date(), "| 提取ay=", a["audit_year"], "| eqr=", str(a["eqr"])[:20], "|", str(a["title"])[:55])
    cnt += 1
    if cnt >= 12:
        break
