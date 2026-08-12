import os, pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

out = pd.read_csv(os.path.join(BASE, "01_中间数据", "WORKTIE", "WORKTIE_2020-2023.csv"),
                  encoding="utf-8-sig", dtype={"stkcd": str})
ann = pd.read_csv(os.path.join(BASE, "01_中间数据", "EQR提取", "EQR_公告级.csv"),
                  encoding="utf-8-sig", dtype={"secCode": str})
ann["has_eqr"] = ann["eqr"].notna() & (ann["eqr"].astype(str).str.strip() != "")
ann["date"] = pd.to_datetime(ann["date"], errors="coerce")

missing = out[out["eqr_name"].isna() | (out["eqr_name"].astype(str) == "")].copy()
print("缺 EQR 的公司-年:", len(missing))
missing["code6"] = missing["stkcd"].str.zfill(6)

rows = []
for _, r in missing.iterrows():
    code = r["code6"]
    y = int(r["year"])
    lo = pd.Timestamp(f"{y-1}-10-01")
    hi = pd.Timestamp(f"{y+1}-12-31")
    sub = ann[(ann["secCode"].astype(str).str.zfill(6) == code) &
              (ann["date"] >= lo) & (ann["date"] <= hi)]
    n_ann = len(sub)
    n_eqr = int(sub["has_eqr"].sum())
    rows.append({"code": code, "year": y, "n_announcements": n_ann, "n_with_eqr": n_eqr})

gap = pd.DataFrame(rows)
print("\n缺口分类：")
print(gap["n_announcements"].value_counts().sort_index().head(10).to_string())
print("\n完全无公告的缺口:", (gap["n_announcements"] == 0).sum())
print("有公告但无 EQR 提取的缺口:", ((gap["n_announcements"] > 0) & (gap["n_with_eqr"] == 0)).sum())
print("有公告且至少一条提取到 EQR（说明是其他问题）:", ((gap["n_announcements"] > 0) & (gap["n_with_eqr"] > 0)).sum())

# 有公告但没提取到 EQR 的样例（聘任/续聘类标题）
miss_ann = ann[~ann["has_eqr"]]
miss_ann = miss_ann[miss_ann["title"].astype(str).str.contains("聘任|续聘|聘请|改聘", na=False)]
miss_ann = miss_ann[miss_ann["audit_year"].astype(str).str.match(r"^20(18|19|20|21|22|23|24)$")]
print("\n聘任/续聘类标题但未提取到 EQR 的公告数:", len(miss_ann))
print(miss_ann[["secCode", "date", "title", "audit_year", "text_len"]].head(25).to_string())
