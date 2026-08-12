import os, pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = pd.read_csv(os.path.join(BASE, "01_中间数据", "WORKTIE", "WORKTIE_2020-2023.csv"),
                  encoding="utf-8-sig", dtype={"stkcd": str})
cov = out[out["eqr_name"].notna() & (out["eqr_name"].astype(str) != "")].copy()
cov["eqr_pid_ok"] = cov["eqr_pid"].notna() & (cov["eqr_pid"].astype(str).str.strip() != "")
print("覆盖:", len(cov), "/", len(out))
print("按年条件 WORKTIE 均值:")
print(cov.groupby("year").agg(n=("stkcd", "count"), worktie=("worktie", "mean")).to_string())
print("\n按 EQR 是否有 PersonID:")
print(cov.groupby("eqr_pid_ok").agg(n=("stkcd", "count"), worktie=("worktie", "mean")).to_string())

# 同名公司-年的多条公告 EQR 是否一致
ann = pd.read_csv(os.path.join(BASE, "01_中间数据", "EQR提取", "EQR_公告级.csv"),
                  encoding="utf-8-sig", dtype={"secCode": str})
ann["has_eqr"] = ann["eqr"].notna() & (ann["eqr"].astype(str).str.strip() != "")
dup = ann[ann["has_eqr"]].copy()
dup["code6"] = dup["secCode"].str.zfill(6)

# 用与构建脚本相同的年度校正（简化：标题年度/日期推断），这里只统计同一公司同一年提取年度下 EQR 不同
dup2 = dup.groupby(["code6", "audit_year"])["eqr"].nunique()
multi = dup2[dup2 > 1]
print("\n同一(公司, 提取年度)下出现多个不同 EQR 文本的组合数:", len(multi))
if len(multi) > 0:
    print(multi.head(10).to_string())

# 抽查 30 个覆盖样本
print("\n抽查 30 个覆盖样本:")
sample = cov.sample(30, random_state=7)
for _, r in sample.iterrows():
    tp = str(r['tie_projects'])[:40] if pd.notna(r['tie_projects']) else ""
    print(f"{r['stkcd']} {int(r['year'])} | ENG1={r['eng1_name']} ENG2={r['eng2_name']} | EQR={r['eqr_name']} (pid:{r['eqr_pid']}) | WT={int(r['worktie'])} | 公告日={r['eqr_ann_date']} | ties={tp}")

print("\n抽查 12 个 worktie=1 样本（含 tie 明细）:")
wt1 = cov[cov["worktie"] == 1].sample(12, random_state=11)
for _, r in wt1.iterrows():
    print(f"{r['stkcd']} {int(r['year'])} | ENG1={r['eng1_name']} ENG2={r['eng2_name']} | EQR={r['eqr_name']} | ties={r['tie_projects']}")
