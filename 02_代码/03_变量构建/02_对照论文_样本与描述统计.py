# -*- coding: utf-8 -*-
"""对照论文 Qi, Seidel, Zhang & Zhang (2026, JAR)：
复现 Table 1 样本筛选漏斗与 WORKTIE 相关描述性统计（Table 2 中可复现部分）。

输出：
  02_中间数据/对比论文/样本筛选_对照.csv
  02_中间数据/对比论文/描述性统计_对照.csv
  02_中间数据/对比论文/样本_对照论文口径.csv
"""
import os, zipfile, re
from collections import defaultdict
import pandas as pd
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSMAR = os.path.join(BASE, "00_原始数据", "CSMAR")
OUT = os.path.join(BASE, "02_中间数据", "对比论文")
os.makedirs(OUT, exist_ok=True)

ACCR = r"os.environ.get("EARNINGS_MGMT_DIR", "")"
GEO = r"os.environ.get("GEO_DISTANCE_DTA", "")"

PAPER = {
    "total": 18709, "fin": 501, "st": 619, "no_eqr": 857, "miss": 491, "final": 16241,
}

def z6(x):
    s = str(x).strip()
    if re.fullmatch(r"\d{1,6}(?:\.0+)?", s):
        return s.split(".")[0].zfill(6)
    return ""

def is_a_code(c):
    return len(c) == 6 and c[0] in "036"

def read_zip(zip_path, dta_name, **kw):
    with zipfile.ZipFile(zip_path) as z:
        with z.open(dta_name) as f:
            return pd.read_stata(f, convert_categoricals=False, **kw)

def pidset(s):
    out = set()
    for x in str(s).split("、"):
        x = x.strip()
        if re.fullmatch(r"\d+(?:\.0+)?", x):
            out.add(x.split(".")[0])
    return out

print("== 1. 读取 FIN_Audit ==")
fin = read_zip(os.path.join(CSMAR, "审计意见表.zip")  # Use glob to find actual file, "FIN_Audit.dta")
fin["year"] = pd.to_datetime(fin["Accper"], errors="coerce").dt.year
fin["month"] = pd.to_datetime(fin["Accper"], errors="coerce").dt.month
fin["code6"] = fin["Stkcd"].astype(str).str.zfill(6)
fin = fin[(fin["year"].between(2020, 2023)) & (fin["month"] == 12) &
          (fin["code6"].map(is_a_code))].copy()
fin = fin.drop_duplicates(["code6", "year"])
print("FIN_Audit 2020-2023 A股公司-年:", len(fin))

print("== 2. 合并 WORKTIE 输出 ==")
wt = pd.read_csv(os.path.join(BASE, "02_中间数据", "WORKTIE", "WORKTIE_2020-2023.csv"),
                 encoding="utf-8-sig", dtype={"stkcd": str})
wt = wt.rename(columns={"worktie": "WORKTIE", "worktie_eng1_eng2": "WORKTIE_ENG1_ENG2"})
df = fin.merge(wt[["stkcd", "year", "eng1_name", "eng2_name", "eqr_name",
                   "eng1_pid", "eng2_pid", "eqr_pid", "WORKTIE", "WORKTIE_ENG1_ENG2"]],
               left_on=["code6", "year"], right_on=["stkcd", "year"], how="left")
df["has_eqr"] = df["eqr_name"].notna() & (df["eqr_name"].astype(str) != "")

print("== 3. 公司文件（行业/SOE/上市日期） ==")
comp = pd.read_stata(os.path.join(ACCR, "公司文件.dta"), convert_categoricals=False)
comp["code6"] = comp["stkcd"].map(z6)
comp = comp.drop_duplicates("code6")
comp["list_year"] = pd.to_datetime(comp["上市日期"], errors="coerce").dt.year
comp["fin_ind"] = comp["Industry"].astype(str).str.strip().str.upper().str.startswith("J")
comp["soe"] = comp["上市公司经营性质"].astype(str).str.contains("国有", na=False)
df = df.merge(comp[["code6", "list_year", "fin_ind", "soe"]], on="code6", how="left")

print("== 4. ST 状态 ==")
st = pd.read_stata(os.path.join(ACCR, "是否ST或PT.dta"), convert_categoricals=False)
st["code6"] = st["stkcd"].map(z6)
st["year"] = pd.to_numeric(st["year"], errors="coerce").astype("Int64")
st = st[["code6", "year", "年末是否ST或PT"]].drop_duplicates(["code6", "year"])
st.columns = ["code6", "year", "is_st"]
df = df.merge(st, on=["code6", "year"], how="left")
df["is_st"] = df["is_st"].fillna(0).astype(int)

print("== 5. 基础财务数据 ==")
base_all = pd.read_stata(os.path.join(ACCR, "基础数据.dta"), convert_categoricals=False)
base_all["code6"] = base_all["stkcd"].map(z6)
base_all["year"] = pd.to_numeric(base_all["year"], errors="coerce")
base = base_all[base_all["year"].between(2020, 2023)].copy()
base = base[["code6", "year", "资产总计", "净利润", "营业收入", "经营活动产生的现金流量净额",
             "应收账款净额"]].drop_duplicates(["code6", "year"])
base.columns = ["code6", "year", "asset", "ni", "rev", "cfo", "recv"]
df = df.merge(base, on=["code6", "year"], how="left")

# 平均总资产（t 与 t-1）
base_all["year_int"] = pd.to_numeric(base_all["year"], errors="coerce").astype(int)
base_all["asset_lag"] = base_all["资产总计"]
lag = base_all[["code6", "year", "asset_lag"]].rename(columns={"year": "year_lag"})
lag["year"] = lag["year_lag"] + 1
lag = lag.drop_duplicates(["code6", "year"])
df = df.merge(lag[["code6", "year", "asset_lag"]], on=["code6", "year"], how="left")
df["year"] = df["year"].astype(int)

print("== 6. 资产负债表（负债/存货，2020-2023 子集） ==")
bs_parts = []
with zipfile.ZipFile(r"os.environ.get("CSMAR_BALANCE_ZIP", "")") as z:
    with z.open("FS_Combas.dta") as f:
        it = pd.read_stata(f, convert_categoricals=False, iterator=True, chunksize=500000)
        for chunk in it:
            chunk["year"] = pd.to_datetime(chunk["Accper"], errors="coerce").dt.year
            chunk = chunk[chunk["year"].between(2020, 2023)]
            if len(chunk):
                bs_parts.append(chunk[["Stkcd", "year", "A001000000", "A002000000", "A001123000"]])
bs = pd.concat(bs_parts, ignore_index=True)
bs["code6"] = bs["Stkcd"].astype(str).str.zfill(6)
bs = bs.drop_duplicates(["code6", "year"])
bs.columns = ["stkcd_", "year", "asset_bs", "liab", "inv", "code6"]
df = df.merge(bs[["code6", "year", "liab", "inv"]], on=["code6", "year"], how="left")
df["asset"] = df["asset"].fillna(df["asset_bs"]) if "asset_bs" in df else df["asset"]

print("== 7. ABSDA（修正琼斯模型） ==")
da = pd.read_stata(os.path.join(ACCR, "计算结果.dta"), convert_categoricals=False)
da["code6"] = da["code"].map(z6)
da["year"] = pd.to_numeric(da["year"], errors="coerce").astype(int)
da = da.rename(columns={"AbsDA": "ABSDA"})
df = df.merge(da[["code6", "year", "ABSDA"]], on=["code6", "year"], how="left")

print("== 8. CPA 表（性别/学校） ==")
cpa = read_zip(os.path.join(CSMAR, "注册会计师个人情况表.zip")  # Use glob to find actual file,
               "AR_CPAINFO.dta")
cpa["pid"] = cpa["PersonID"].astype(str).str.extract(r"(\d+)")[0]
cpa["name"] = cpa["Name"].astype(str).str.strip()
cpa["gender"] = cpa["Gender"].astype(str).str.strip().str.upper()
cpa["school"] = cpa["GraduationSchool"].astype(str).str.strip()
cpa["school"] = cpa["school"].replace({"nan": "", "None": ""})
pid_gender = cpa.dropna(subset=["gender"]).groupby("pid")["gender"].agg(
    lambda s: s[s != ""].mode().iat[0] if (s != "").any() else "")
pid_school = cpa[cpa["school"] != ""].groupby("pid")["school"].agg(lambda s: set(s))
name_gender = cpa.dropna(subset=["gender"]).groupby("name")["gender"].agg(
    lambda s: s[s != ""].mode().iat[0] if (s != "").any() else "")
name_school = cpa[cpa["school"] != ""].groupby("name")["school"].agg(lambda s: set(s))

# CPA_MARK（博论衍生）补充性别/学校
cpa_mark = pd.read_stata(r"os.environ.get("CPA_MARK_DTA", "")", convert_categoricals=False)
cpa_mark["name"] = cpa_mark["Auditor"].astype(str).str.strip()
cpa_mark["gender"] = cpa_mark["Gender"].astype(str).str.strip().str.upper()
cpa_mark["school"] = cpa_mark["GraduationSchool"].astype(str).str.strip()
mark_gender = cpa_mark[cpa_mark["gender"].isin(["M", "F"])].groupby("name")["gender"].agg(
    lambda s: s.mode().iat[0])

print("== 9. 审计机构列表（TENURE/网络/合伙人组合） ==")
lst = read_zip(os.path.join(CSMAR, "审计机构列表.zip")  # Use glob to find actual file,
               "AR_LISTCOMPAUDIT.dta")
lst["year"] = pd.to_datetime(lst["EndDate"], errors="coerce").dt.year
lst["code6"] = lst["Symbol"].astype(str).str.zfill(6)
lst["tenure"] = pd.to_numeric(lst["AuditorTenure"], errors="coerce")
tenure = lst.dropna(subset=["tenure"]).sort_values("tenure", ascending=False) \
    .drop_duplicates(["code6", "year"])[["code6", "year", "tenure"]] \
    .rename(columns={"tenure": "TENURE"})
df = df.merge(tenure, on=["code6", "year"], how="left")

print("== 10. EQR 公告级（COREVIEW） ==")
eqr_ann = pd.read_csv(os.path.join(BASE, "02_中间数据", "EQR提取", "EQR_公告级.csv"),
                      encoding="utf-8-sig", dtype={"secCode": str})
eqr_ann["code6"] = eqr_ann["secCode"].str.zfill(6)
eqr_ann["year"] = pd.to_numeric(eqr_ann["audit_year"], errors="coerce")
eqr_ann = eqr_ann[eqr_ann["year"].notna() & eqr_ann["eqr"].notna()].copy()
eqr_ann["year"] = eqr_ann["year"].astype(int)

print("== 11. 地理距离（LOCAL） ==")
geo = pd.read_stata(GEO, convert_categoricals=False)
geo["code6"] = geo["code"].astype(str).str.zfill(6)
geo["year"] = pd.to_numeric(geo["year"], errors="coerce").astype("Int64")
geo = geo[["code6", "year", "LOCALUMP_O", "LOCALUMP_R"]].drop_duplicates(["code6", "year"])
df = df.merge(geo, on=["code6", "year"], how="left")

print("== 12. 市值（年末收盘价 × 总股本） ==")
price = pd.read_excel(r"os.environ.get("PRICE_DATA_DIR", "")\股价.xlsx")
price = price[price["证券代码"].astype(str).str.match(r"^\d{6}$")].copy()
price["code6"] = price["证券代码"].astype(str)
price["ym"] = price["交易月份"].astype(str)
price["year"] = price["ym"].str.slice(0, 4)
price["month"] = price["ym"].str.slice(5, 7)
dec = price[price["month"] == "12"].copy()
dec["year"] = dec["year"].astype(int)
dec = dec.sort_values(["code6", "year", "ym"]).drop_duplicates(["code6", "year"], keep="last")
dec = dec[["code6", "year", "月收盘价(元/股)"]].rename(columns={"月收盘价(元/股)": "price_dec"})
shr = pd.read_stata(r"os.environ.get("DATAWEB_FORECAST", "")\2001-2024总股数.dta",
                    convert_categoricals=False)
shr["code6"] = shr["id"].map(z6)
shr["year"] = pd.to_numeric(shr["year"], errors="coerce").astype(int)
shr = shr[["code6", "year", "Nshrttl"]].drop_duplicates(["code6", "year"])
df = df.merge(dec, on=["code6", "year"], how="left").merge(shr, on=["code6", "year"], how="left")
df["mktcap"] = df["price_dec"] * df["Nshrttl"]

print("== 13. 变量计算 ==")
df["MAO"] = (df["Audittyp"] != "标准无保留意见").astype(int)
df["SIZE"] = np.log(df["asset"] / 1e6)
df["LEV"] = df["liab"] / df["asset"]
avg_asset = (df["asset"] + df["asset_lag"]) / 2
df["ROA"] = df["ni"] / avg_asset
df["LOSS"] = (df["ni"] < 0).astype(int)
df["CFO"] = df["cfo"] / avg_asset
df["INV"] = df["inv"] / df["asset"]
df["REC"] = df["recv"] / df["asset"]
df["TURNOVER"] = df["rev"] / avg_asset
age_years = df["year"] - df["list_year"]
df["AGE"] = np.where(age_years > 0, np.log(age_years), np.nan)
df["SOE"] = df["soe"].astype(int)
df["BM"] = (df["asset"] - df["liab"]) / df["mktcap"]
df["LOCAL_O"] = pd.to_numeric(df["LOCALUMP_O"], errors="coerce")
df["LOCAL_R"] = pd.to_numeric(df["LOCALUMP_R"], errors="coerce")
df["LOCAL"] = df["LOCAL_O"]

# SIZE_AF：事务所-年客户总资产（非金融客户口径）
firm_assets = df.loc[~df["fin_ind"].fillna(False)].groupby(["DadtunitID", "year"])["asset"].transform("sum")
df["SIZE_AF"] = np.log(firm_assets / 1e6)

def gender_of(name, pid):
    if pid and pid in pid_gender:
        return pid_gender[pid]
    if name and name in name_gender:
        return name_gender[name]
    if name and name in mark_gender:
        return mark_gender[name]
    return ""

def school_of(name, pid):
    out = set()
    for p in pidset(pid):
        out |= pid_school.get(p, set())
    if name and name in name_school:
        out |= name_school[name]
    return out

df["eqr_gender"] = [gender_of(str(n) if pd.notna(n) else "", p) for n, p in
                    zip(df["eqr_name"], df["eqr_pid"].fillna(""))]
df["eng1_gender"] = [gender_of(str(n) if pd.notna(n) else "", p) for n, p in
                     zip(df["eng1_name"], df["eng1_pid"].fillna(""))]
df["eng2_gender"] = [gender_of(str(n) if pd.notna(n) else "", p) for n, p in
                     zip(df["eng2_name"], df["eng2_pid"].fillna(""))]
df["SAMEGEN"] = np.where(
    (df["eqr_gender"] == "") | ((df["eng1_gender"] == "") & (df["eng2_gender"] == "")),
    np.nan,
    ((df["eqr_gender"] == df["eng1_gender"]) | (df["eqr_gender"] == df["eng2_gender"])).astype(int))
df["eqr_school"] = [school_of(str(n) if pd.notna(n) else "", p) for n, p in
                    zip(df["eqr_name"], df["eqr_pid"].fillna(""))]
df["eng1_school"] = [school_of(str(n) if pd.notna(n) else "", p) for n, p in
                     zip(df["eng1_name"], df["eng1_pid"].fillna(""))]
df["eng2_school"] = [school_of(str(n) if pd.notna(n) else "", p) for n, p in
                     zip(df["eng2_name"], df["eng2_pid"].fillna(""))]
df["ALUM_TIE"] = [1 if (s1 and (s1 & s2 or s1 & s3)) else 0
                  for s1, s2, s3 in zip(df["eqr_school"], df["eng1_school"], df["eng2_school"])]

print("== 14. TEAM（三年窗口连通分量） ==")
def norm_pid(s):
    m = re.fullmatch(r"\d+(?:\.0+)?", str(s).strip())
    return m.group(0).split(".")[0] if m else None

lst["pid_list"] = lst["PersonID"].astype(str).str.split(",")
lst["name_list"] = lst["SignatureCPA"].astype(str).str.split(",")

class DSU:
    def __init__(self):
        self.p = {}
    def find(self, x):
        if x not in self.p:
            self.p[x] = x
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra

team_map = {}
for t in range(2020, 2024):
    dsu = DSU()
    win = lst[lst["year"].between(t - 3, t - 1)]
    for _, r in win.iterrows():
        pids = [norm_pid(x) for x in r["pid_list"]]
        names = [x.strip() for x in r["name_list"]]
        nodes = [("P", p) for p in pids if p] or [("N", n) for n in names if n]
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                dsu.union(nodes[i], nodes[j])
    team_map[t] = dsu

def in_team(eqr_pid, eqr_name, eng_pid, eng_name, t):
    dsu = team_map[t]
    e_nodes = [("P", p) for p in pidset(eqr_pid)] or ([("N", str(eqr_name).strip())] if eqr_name else [])
    g_nodes = [("P", p) for p in pidset(eng_pid)] or ([("N", str(eng_name).strip())] if eng_name else [])
    for a in e_nodes:
        for b in g_nodes:
            if a == b:
                return True
            if dsu.find(a) == dsu.find(b):
                return True
    return False

df["TEAM"] = [
    1 if (has_e and (in_team(e_p, e_n, g1_p, g1_n, y) or in_team(e_p, e_n, g2_p, g2_n, y))) else 0
    for has_e, e_p, e_n, g1_p, g1_n, g2_p, g2_n, y in zip(
        df["has_eqr"], df["eqr_pid"].fillna(""), df["eqr_name"].fillna(""),
        df["eng1_pid"].fillna(""), df["eng1_name"].fillna(""),
        df["eng2_pid"].fillna(""), df["eng2_name"].fillna(""), df["year"])
]

print("== 15. COREVIEW（EQR-ENG 监督关系历史） ==")
sup = set()
fin_eng_by_cy = defaultdict(set)
for _, fr in fin.iterrows():
    fin_eng_by_cy[(fr["code6"], int(fr["year"]))].update(
        x.strip() for x in str(fr["Auditor"]).split(",") if x.strip())
for _, r in eqr_ann.iterrows():
    if pd.isna(r["year"]) or r["year"] not in (2020, 2021, 2022, 2023):
        continue
    eqr_names = set(x.strip() for x in str(r["eqr"]).split("、") if x.strip())
    eng_names = fin_eng_by_cy.get((r["code6"], int(r["year"])), set())
    for e in eqr_names:
        for g in eng_names:
            if e != g:
                sup.add((e, g, int(r["year"])))

def coreview(eqr_name, eng1_name, eng2_name, t):
    e = str(eqr_name).strip() if pd.notna(eqr_name) else ""
    g1 = str(eng1_name).strip() if pd.notna(eng1_name) else ""
    g2 = str(eng2_name).strip() if pd.notna(eng2_name) else ""
    if not e:
        return 0
    for y in range(2020, t):
        if (e, g1, y) in sup or (e, g2, y) in sup:
            return 1
    return 0

df["COREVIEW"] = [coreview(e, g1, g2, int(y)) for e, g1, g2, y in
                  zip(df["eqr_name"], df["eng1_name"], df["eng2_name"], df["year"])]

print("== 16. CI 与 DSPEC（合伙人客户组合） ==")
pid_assets = {}
for _, r in lst[lst["year"].between(2020, 2023)].iterrows():
    pids = [norm_pid(x) for x in r["pid_list"]]
    a = base_all[(base_all["code6"] == r["code6"]) & (base_all["year"] == r["year"])]["资产总计"]
    a = a.iloc[0] if len(a) else np.nan
    for p in pids:
        if p:
            pid_assets.setdefault((p, int(r["year"])), []).append((r["code6"], a))
portfolio = {k: np.nansum([a for _, a in v]) for k, v in pid_assets.items()}

def portfolio_size(pid, year):
    vals = [portfolio.get((p, year), np.nan) for p in pidset(pid)]
    vals = [v for v in vals if pd.notna(v)]
    return float(np.mean(vals)) if vals else np.nan

df["CI"] = [row_asset / ((portfolio_size(p1, y) + portfolio_size(p2, y)) / 2)
            if ((portfolio_size(p1, y) + portfolio_size(p2, y)) > 0) else np.nan
            for row_asset, p1, p2, y in zip(
                df["asset"], df["eng1_pid"].fillna(""), df["eng2_pid"].fillna(""), df["year"])]

# 行业份额：合伙人-年-行业（top quartile = 行业专家）
ind_map = comp.set_index("code6")["Industry"].astype(str).str.strip().str.upper()
pid_ind_assets = defaultdict(lambda: defaultdict(float))
ind_year_total = defaultdict(float)
for (p, y), items in pid_assets.items():
    for code, a in items:
        if pd.isna(a) or code not in ind_map:
            continue
        ind = ind_map[code]
        if not ind:
            continue
        pid_ind_assets[(p, y)][ind] += a
        ind_year_total[(ind, y)] += a
pid_share = {}
for (p, y), inds in pid_ind_assets.items():
    for ind, a in inds.items():
        tot = ind_year_total.get((ind, y), np.nan)
        if tot and pd.notna(tot):
            pid_share[(p, y, ind)] = a / tot

share_df = pd.DataFrame(
    [(p, y, ind, s) for (p, y, ind), s in pid_share.items()],
    columns=["pid", "year", "ind", "share"])
# 行业-年组内合伙人不足 10 人的不定义“行业专家”，避免小行业虚高
grp_size = share_df.groupby(["year", "ind"])["pid"].transform("nunique")
share_df = share_df[grp_size >= 10].copy()
thr = share_df.groupby(["year", "ind"])["share"].quantile(.75)
share_df["leader"] = share_df.apply(
    lambda r: r["share"] > thr.get((r["year"], r["ind"]), np.inf), axis=1)
leader_keys = set(zip(share_df[share_df["leader"]]["pid"],
                      share_df[share_df["leader"]]["year"]))

def is_leader(pid, year):
    return any((p, year) in leader_keys for p in pidset(pid))

df["DSPEC_ENG"] = [1 if (is_leader(p1, y) or is_leader(p2, y)) else 0
                   for p1, p2, y in zip(df["eng1_pid"].fillna(""), df["eng2_pid"].fillna(""), df["year"])]
df["DSPEC_EQR"] = [1 if is_leader(p, y) else 0
                   for p, y in zip(df["eqr_pid"].fillna(""), df["year"])]

print("== 17. 样本筛选漏斗 ==")
df["miss_feature"] = (
    df["SIZE"].isna() | df["LEV"].isna() | df["ROA"].isna() | df["CFO"].isna() |
    df["INV"].isna() | df["REC"].isna() | df["TURNOVER"].isna() |
    df["TENURE"].isna() | df["SIZE_AF"].isna() | df["LOCAL_O"].isna() |
    df["TEAM"].isna() | df["COREVIEW"].isna()
).astype(int)

total = len(df)
fin_mask = df["fin_ind"].fillna(False)
st_mask = df["is_st"] == 1
noeqr_mask = ~df["has_eqr"]
miss_mask = df["miss_feature"] == 1

steps = [
    ("total", "Total A股公司-年（FIN_Audit 2020-2023）", total, PAPER["total"]),
    ("fin", "剔除金融业", int((fin_mask).sum()), PAPER["fin"]),
    ("st", "再剔除 ST/PT", int((~fin_mask & st_mask).sum()), PAPER["st"]),
    ("no_eqr", "再剔除无 EQR 披露", int((~fin_mask & ~st_mask & noeqr_mask).sum()), PAPER["no_eqr"]),
    ("miss", "再剔除缺客户特征", int((~fin_mask & ~st_mask & ~noeqr_mask & miss_mask).sum()), PAPER["miss"]),
]
sel = pd.DataFrame(steps, columns=["step", "label", "ours", "paper"])
sel["diff"] = sel["ours"] - sel["paper"]
final_mask = ~fin_mask & ~st_mask & ~noeqr_mask & (miss_mask == 0)
sel.loc[len(sel)] = ["final", "最终样本", int(final_mask.sum()), PAPER["final"],
                     int(final_mask.sum()) - PAPER["final"]]
sel.to_csv(os.path.join(OUT, "样本筛选_对照.csv"), index=False, encoding="utf-8-sig")
print(sel.to_string(index=False))

print("== 18. 描述性统计（最终样本） ==")
sample = df[final_mask].copy()
paper_stats = {
    "WORKTIE": (16241, .092, .289, 0, 0, 0),
    "WORKTIE_ENG1_ENG2": (16241, .658, .474, 0, 1, 1),
    "ALUM_TIE": (16241, .060, .237, 0, 0, 0),
    "TEAM": (16241, .224, .417, 0, 0, 0),
    "COREVIEW": (16241, .453, .498, 0, 0, 1),
    "MAO": (16241, .032, .176, 0, 0, 0),
    "ABSDA": (15543, .057, .101, .016, .037, .070),
    "SIZE": (16241, 8.542, 1.310, 7.597, 8.300, 9.257),
    "LEV": (16241, .412, .205, .248, .403, .558),
    "ROA": (16241, .034, .073, .009, .036, .071),
    "LOSS": (16241, .181, .385, 0, 0, 0),
    "BM": (16241, .358, .173, .233, .339, .466),
    "CFO": (16241, .053, .073, .012, .050, .093),
    "SUBS": (16241, 2.755, 1.014, 2.079, 2.708, 3.401),
    "AGE": (16241, 2.101, .949, 1.386, 2.303, 2.944),
    "TURNOVER": (16241, .616, .466, .347, .524, .755),
    "SOE": (16241, .290, .454, 0, 0, 1),
    "TENURE": (16241, 7.054, 4.799, 4, 6, 10),
    "SIZE_AF": (16241, 14.854, 1.198, 14.113, 15.374, 15.699),
    "DSPEC_ENG": (16241, .373, .484, 0, 0, 1),
    "DSPEC_EQR": (16241, .354, .478, 0, 0, 1),
    "SAMEGEN": (16241, .783, .412, 1, 1, 1),
    "CI": (16241, .436, .328, .144, .355, .714),
    "LOCAL": (16241, .654, .476, 0, 1, 1),
    "INV": (16241, .124, .110, .050, .101, .164),
    "REC": (16241, .125, .101, .046, .105, .181),
}

cont_vars = ["ABSDA", "SIZE", "LEV", "ROA", "BM", "CFO", "AGE", "TURNOVER",
             "TENURE", "SIZE_AF", "CI", "INV", "REC"]
for v in cont_vars:
    if v in sample:
        q1, q99 = sample[v].quantile([.01, .99])
        sample[v] = sample[v].clip(q1, q99)

rows = []
for v, p in paper_stats.items():
    if v not in sample.columns:
        rows.append({"var": v, "note": "本数据集未构建"})
        continue
    s = sample[v]
    rows.append({
        "var": v,
        "paper_n": p[0], "paper_mean": p[1], "paper_sd": p[2],
        "paper_p25": p[3], "paper_median": p[4], "paper_p75": p[5],
        "our_n": int(s.notna().sum()),
        "our_mean": round(float(s.mean()), 4) if s.notna().any() else np.nan,
        "our_sd": round(float(s.std()), 4) if s.notna().sum() > 1 else np.nan,
        "our_p25": round(float(s.quantile(.25)), 4) if s.notna().any() else np.nan,
        "our_median": round(float(s.median()), 4) if s.notna().any() else np.nan,
        "our_p75": round(float(s.quantile(.75)), 4) if s.notna().any() else np.nan,
    })
desc = pd.DataFrame(rows)
desc.to_csv(os.path.join(OUT, "描述性统计_对照.csv"), index=False, encoding="utf-8-sig")
print(desc.to_string(index=False))

sample_out = df.copy()
sample_out.to_csv(os.path.join(OUT, "样本_对照论文口径.csv"), index=False, encoding="utf-8-sig")
print("\n最终样本:", int(final_mask.sum()), "| 已保存中间文件至", OUT)
