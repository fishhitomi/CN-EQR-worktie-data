import os, pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = pd.read_csv(os.path.join(BASE, "01_中间数据", "WORKTIE", "WORKTIE_2020-2023.csv"),
                  encoding="utf-8-sig", dtype={"stkcd": str})
cov = out[out["eqr_name"].notna() & (out["eqr_name"].astype(str) != "")].copy()
print("总样本(2020-2023 A股):", len(out))
print("有EQR:", len(cov), f"({100*len(cov)/len(out):.1f}%)")
print("唯一 EQR 姓名:", cov["eqr_name"].nunique())
print("唯一公司:", out["stkcd"].nunique())
print()
print("按年：")
g = cov.groupby("year").agg(
    n=("stkcd", "count"),
    worktie_mean=("worktie", "mean"),
    eng12_mean=("worktie_eng1_eng2", "mean"),
)
g["worktie_mean"] = (g["worktie_mean"] * cov.groupby("year")["stkcd"].count())
print(cov.groupby("year").agg(n=("stkcd","count"), wt=("worktie","mean"),
      wt12=("worktie_eng1_eng2","mean")).to_string())
print()
print("总体条件均值: WORKTIE =", cov["worktie"].mean(),
      "| WORKTIE_ENG1_ENG2 =", cov["worktie_eng1_eng2"].mean())
print()
print("WORKTIE=1 的行数:", int(cov["worktie"].sum()))
print("tie_projects 非空(有明细):", cov["tie_projects"].notna().sum())
print()
print("按年覆盖（有EQR/总）:")
tot = out.groupby("year").size()
print(pd.DataFrame({"total": tot, "has_eqr": cov.groupby("year").size()}).to_string())
