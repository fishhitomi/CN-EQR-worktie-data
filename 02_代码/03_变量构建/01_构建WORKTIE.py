# -*- coding: utf-8 -*-
"""构造 WORKTIE：EQR 与项目合伙人既往共事经历（解释变量）。

输入：FIN_Audit.dta、AR_LISTCOMPAUDIT.dta、AR_CPAINFO.dta、EQR_公告级.csv，
      以及 CSMAR 资本市场项目表（IPO 申报企业/增发/配股，带签字 CPA 姓名）
输出：02_中间数据/WORKTIE/WORKTIE_2020-2025.csv 与统计摘要

扩展变量：合作次数、最近合作年份/间隔、项目类型（年报/IPO/增发/配股）、
          相似客户（同行业/同城市）、高复杂度项目（资本市场项目）。

可选参数：
  --no-capital      不使用资本市场项目共事边（仅年报签字口径，用于对比）
  --start-year/--end-year  样本区间（默认 2020-2025）
"""
import os, zipfile, re, argparse
from collections import defaultdict
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSMAR = os.path.join(BASE, "00_原始数据", "CSMAR")
CM_DIR = os.path.join(CSMAR, "资本市场项目")
OUT = os.path.join(BASE, "01_中间数据", "WORKTIE")
os.makedirs(OUT, exist_ok=True)

PLACEHOLDER = {"没有单位", "无", "暂无", "未披露", "不适用", "待定", "nan", "None", ""}
JUNK_FIRST = {"事件ID", "公司名称", "证券代码", "披露日期", "签字会计师", "会计师经办人", "没有单位"}
EQR_GARBAGE = {"暂未确定", "暂未拟定", "未拟定", "近三年", "员近三年", "翁祖桂无", "拟定", "待定", "暂定", "未定"}
EQR_GARBAGE_RE = re.compile(r"(未确定|未拟定|近三|员近三|暂未|拟定|待定|暂定|未定)")

DATAWEB_AUDIT = r"os.environ.get("DATAWEB_AUDIT", "")"
INDUSTRY_DTA = os.path.join(r"os.environ.get("DATAWEB_FORECAST", "")",
                            "2001-2024行业代码.dta")
COMPANY_DTA = os.path.join(DATAWEB_AUDIT, "公司文件.dta")

import glob

def find_zip(keyword):
    """按关键词通配符匹配 zip 文件，避免暴露机构授权标识。"""
    matches = glob.glob(os.path.join(CSMAR, f"*{keyword}*.zip"))
    if not matches:
        raise FileNotFoundError(f"未在 00_原始数据/CSMAR/ 下找到含 '{keyword}' 的 zip 文件")
    return os.path.basename(matches[0])

def read_dta(zip_name, dta_name):
    with zipfile.ZipFile(os.path.join(CSMAR, zip_name)) as z:
        with z.open(dta_name) as f:
            return pd.read_stata(f)

def split_list(s):
    return [x.strip() for x in re.split(r"[、;；,，\s]+", str(s)) if x.strip()]

def clean_name(tok):
    """去掉姓名后的（已离职）/（已退休）等备注。"""
    return re.sub(r"[（(][^（）()]*[)）]", "", str(tok)).strip()

def split_names(s):
    """拆分签字人字段并剔除占位/备注内容。"""
    out = []
    for t in re.split(r"[、，,;；\s]+", str(s)):
        t = clean_name(t)
        if t and t not in PLACEHOLDER:
            out.append(t)
    return out

def code6_of(x):
    """把股票代码统一成 6 位字符串；无效返回空串。"""
    s = str(x).strip()
    if re.fullmatch(r"\d{1,6}(?:\.0+)?", s):
        return s.split(".")[0].zfill(6)
    return ""

def year_of(x):
    """从日期字符串中提取 19xx/20xx 年份，提取不到返回 None。"""
    m = re.search(r"((?:19|20)\d{2})", str(x))
    return int(m.group(1)) if m else None

def read_capital_projects():
    """读取 IPO/增发/配股三张 CSMAR 表，返回项目记录列表。"""
    if not os.path.isdir(CM_DIR):
        print("未找到资本市场项目目录:", CM_DIR)
        return []

    def load(fn):
        df = pd.read_excel(os.path.join(CM_DIR, fn))
        first = df.columns[0]
        df = df[~df[first].astype(str).str.strip().isin(JUNK_FIRST)]
        return df.dropna(how="all").drop_duplicates()

    projects = []
    seen = set()

    def add_projects(kind, df, name_col, date_cols, code_col, label_col=None):
        for _, r in df.iterrows():
            names = split_names(r[name_col])
            if len(names) < 2:
                continue
            years = [year_of(r[c]) for c in date_cols]
            years = [y for y in years if y is not None]
            if not years:
                continue
            y = min(years)
            code = code6_of(r[code_col])
            label = code or (str(r[label_col]).strip() if label_col else code)
            key = (kind, label, y, tuple(sorted(names)))
            if key in seen:
                continue
            seen.add(key)
            projects.append({
                "kind": kind,
                "code": code,
                "label": label,
                "year": y,
                "date": str(r[date_cols[0]]),
                "names": names,
            })

    # IPO：SignAccountant 签字会计师；同一项目按 公司/代码+年度+签字人 去重
    add_projects("IPO", load("IPO_NEWSHARECO.xlsx"),
                 "SignAccountant", ["DisclosureDate"], "Symbol", label_col="CoName")
    # 增发：Aicpa 会计师经办人；项目年度取意向书签署/发表、发行开始、上市公告/流通日的最早年份
    add_projects("SEO", load("RS_Aibasic.xlsx"), "Aicpa",
                 ["Aistsbdt", "Aistpbdt", "Aistdt", "Ailtadt", "Ailtdt"], "Stkcd")
    # 配股：Aicpa 会计师经办人；项目年度取说明书发表/签署、上市流通日的最早年份
    add_projects("RIO", load("RS_Robasic.xlsx"), "Aicpa",
                 ["Roadt", "Rosbdt", "Tlstdt"], "Stkcd")

    return projects

print("读取 FIN_Audit ...")
fin = read_dta(find_zip("审计意见表"), "FIN_Audit.dta")
fin["year"] = pd.to_datetime(fin["Accper"], errors="coerce").dt.year
fin = fin[fin["year"].between(1998, 2025)].copy()
fin = fin[fin["Stkcd"].astype(str).str.zfill(6).map(lambda c: len(c) == 6 and c[0] in "036")]
fin["code6"] = fin["Stkcd"].astype(str).str.zfill(6)
print("FIN_Audit 有效行（1998-2025, A 股）:", len(fin))

print("读取 AR_LISTCOMPAUDIT ...")
lst = read_dta(find_zip("审计机构列表"), "AR_LISTCOMPAUDIT.dta")
lst["year"] = pd.to_datetime(lst["EndDate"], errors="coerce").dt.year
lst["Symbol_s"] = lst["Symbol"].astype(str).str.zfill(6)

print("构建姓名/PersonID 字典 ...")
name_pid_fy = defaultdict(set)
for _, r in lst.iterrows():
    names = split_list(r["SignatureCPA"])
    pids = split_list(r["PersonID"])
    if not names:
        continue
    if len(pids) == len(names):
        for n, p in zip(names, pids):
            name_pid_fy[(r["Symbol_s"], r["year"], n)].add(p)
    else:
        for n in names:
            name_pid_fy[(r["Symbol_s"], r["year"], n)].add("")

print("读取 CPA 个人表 ...")
cpa = read_dta(find_zip("注册会计师个人情况表"), "AR_CPAINFO.dta")
name_pid_cpa = defaultdict(set)
for _, r in cpa.iterrows():
    n = str(r["Name"]).strip()
    p = str(r["PersonID"]).strip()
    if n and p and p != "nan":
        name_pid_cpa[n].add(p)

def get_pids(name, code, year):
    name = str(name).strip()
    return set(name_pid_fy.get((code, year, name), set())) | name_pid_cpa.get(name, set())

print("读取行业/地区映射 ...")
industry_map = {}
static_industry = {}
province_map = {}
city_map = {}

if os.path.exists(INDUSTRY_DTA):
    ind_df = pd.read_stata(INDUSTRY_DTA)
    for _, r in ind_df.iterrows():
        c = code6_of(r["id"])
        y = int(r["year"]) if pd.notna(r["year"]) else None
        if c and y:
            industry_map[(c, y)] = str(r["Indcd1"]).strip()
    print("行业代码表（年度）:", len(industry_map), "条")
else:
    print("未找到年度行业代码表:", INDUSTRY_DTA)

if os.path.exists(COMPANY_DTA):
    comp = pd.read_stata(COMPANY_DTA)
    for _, r in comp.iterrows():
        c = code6_of(r["stkcd"])
        if not c:
            continue
        ind = str(r.get("行业代码D") or r.get("行业代码C") or "").strip()
        if ind:
            static_industry[c] = ind
        p = str(r.get("所属省份") or "").strip()
        ci = str(r.get("所属城市") or "").strip()
        if p:
            province_map[c] = p
        if ci:
            city_map[c] = ci
    print("公司静态行业/地区映射:", len(static_industry), "家")
else:
    print("未找到公司文件:", COMPANY_DTA)

def get_industry(code, year):
    v = industry_map.get((code, year), "")
    return v or static_industry.get(code, "")

def get_region(code):
    return province_map.get(code, ""), city_map.get(code, "")

print("解析签字人并映射 PersonID ...")
rows = []
for _, r in fin.iterrows():
    names = split_list(r["Auditor"])
    if len(names) < 2:
        continue
    pids = [get_pids(n, r["code6"], r["year"]) for n in names]
    rows.append({"code": r["code6"], "year": int(r["year"]), "names": names, "pids": pids})
print("签字记录行（至少 2 名签字人）:", len(rows))
fin_years = {(r["code"], r["year"]) for r in rows}

print("构建历史共事边（年报签字） ...")
edges = defaultdict(list)
for rec in rows:
    y = rec["year"]
    code = rec["code"]
    names = rec["names"]
    pids = rec["pids"]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ida = [("PID", p) for p in pids[i]] + [("NAME", names[i])]
            idb = [("PID", p) for p in pids[j]] + [("NAME", names[j])]
            for a in ida:
                for b in idb:
                    if a == b:
                        continue
                    key = tuple(sorted((a, b), key=lambda x: (x[0], x[1])))
                    prov, city = get_region(code)
                    edges[key].append({
                        "code": code, "label": code, "year": y, "kind": "AUD",
                        "industry": get_industry(code, y), "province": prov, "city": city,
                    })

argp = argparse.ArgumentParser()
argp.add_argument("--no-capital", action="store_true", help="不使用资本市场项目共事边")
argp.add_argument("--start-year", type=int, default=2020)
argp.add_argument("--end-year", type=int, default=2025)
args = argp.parse_args()
year_tag = f"{args.start_year}-{args.end_year}"
OUT_FILE = f"WORKTIE_{year_tag}_仅年报.csv" if args.no_capital else f"WORKTIE_{year_tag}.csv"

projects = []
if args.no_capital:
    print("按 --no-capital 运行：仅使用年报签字共事边")
else:
    print("读取资本市场项目表 ...")
    projects = read_capital_projects()
    print("资本市场项目数:", len(projects),
          "| 按类型:", pd.Series([p["kind"] for p in projects]).value_counts().to_dict())
    pd.DataFrame(projects).to_csv(
        os.path.join(OUT, "共事边_资本市场项目.csv"), index=False, encoding="utf-8-sig")
    print("构建历史共事边（资本市场项目） ...")
    for p in projects:
        pids = [get_pids(n, p["code"], p["year"]) for n in p["names"]]
        prov, city = get_region(p["code"])
        ind = get_industry(p["code"], p["year"])
        for i in range(len(p["names"])):
            for j in range(i + 1, len(p["names"])):
                ida = [("PID", p) for p in pids[i]] + [("NAME", p["names"][i])]
                idb = [("PID", p) for p in pids[j]] + [("NAME", p["names"][j])]
                for a in ida:
                    for b in idb:
                        if a == b:
                            continue
                        key = tuple(sorted((a, b), key=lambda x: (x[0], x[1])))
                        edges[key].append({
                            "code": p["code"], "label": p["label"], "year": p["year"],
                            "kind": p["kind"], "industry": ind, "province": prov, "city": city,
                        })

print("共事边（去重键）总数:", len(edges))

def has_tie(person_pids, person_name, other_pids, other_name, before_year):
    cand_self = [("PID", p) for p in person_pids] or [("NAME", person_name)]
    cand_other = [("PID", p) for p in other_pids] or [("NAME", other_name)]
    all_hits = []
    for a in cand_self:
        for b in cand_other:
            key = tuple(sorted((a, b), key=lambda x: (x[0], x[1])))
            all_hits.extend(proj for proj in edges.get(key, []) if proj["year"] < before_year)
    return (True, all_hits) if all_hits else (False, [])

def dedupe_hits(hits):
    out = []
    seen = set()
    for h in hits:
        key = (h["kind"], h["code"] or h["label"], h["year"])
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out

print("汇总 EQR 公司-年度 ...")
eqr = pd.read_csv(os.path.join(BASE, "01_中间数据", "EQR提取", "EQR_公告级.csv"),
                  encoding="utf-8-sig", dtype={"secCode": str})
eqr["code6"] = eqr["secCode"].str.zfill(6)
eqr["year"] = pd.to_numeric(eqr["audit_year"], errors="coerce")
eqr = eqr[(eqr["year"].between(2018, 2026)) &
          (eqr["eqr"].notna()) & (eqr["eqr"].astype(str).str.strip() != "")].copy()
eqr["year"] = eqr["year"].astype(int)
eqr["eqr_list"] = eqr["eqr"].astype(str).str.split("、")
eqr["is_change"] = eqr["title"].astype(str).str.contains("变更", na=False)

def correct_year(code, title, date, extracted):
    """确定公告对应的审计年度：标题年度 > 提取年度（fin_years 校验）> 日期推断。"""
    t = re.sub(r"\s+", "", str(title))
    m = re.search(r"(20\d{2})\s*年度", t)
    base = None
    if m:
        base = int(m.group(1))
    else:
        ext = int(extracted) if pd.notna(extracted) else 0
        # 提取年度来自公告标题/正文模式与年份频率，优先采用（须公司当年存在年报）
        if ext and (code, ext) in fin_years:
            return ext if args.start_year <= ext <= args.end_year else 0
        d = pd.to_datetime(date, errors="coerce")
        if pd.notna(d):
            base = d.year + (1 if d.month >= 10 else 0)
        else:
            base = ext
    cands = [base, base - 1, base + 1]
    for c in cands:
        if (code, c) in fin_years:
            return c
    return base if args.start_year <= base <= args.end_year else 0

eqr_primary = {}
eqr_all = defaultdict(list)
eqr_meta = {}
remap_count = 0
for _, r in eqr.sort_values(["code6", "year", "date"]).iterrows():
    code = r["code6"]
    y = correct_year(code, r["title"], r["date"], r["year"])
    if y != int(r["year"]):
        remap_count += 1
    if not (args.start_year <= y <= args.end_year):
        continue
    names = r["eqr_list"]
    clean_names = [n for n in names if n not in EQR_GARBAGE and not EQR_GARBAGE_RE.search(n)]
    if not clean_names:
        continue
    primary = clean_names[-1] if (r["is_change"] and clean_names) else clean_names[0]
    eqr_primary[(code, y)] = primary
    eqr_all[(code, y)].extend(names)
    eqr_meta[(code, y)] = {"date": r["date"], "title": r["title"], "ann": r["announcementId"]}
print("审计年度重映射条数:", remap_count, f"；有 EQR 的公司-年（{year_tag}）:", len(eqr_primary))

print("构建 WORKTIE 样本 ...")
samples = [r for r in rows if args.start_year <= r["year"] <= args.end_year]
out_rows = []
no_eqr = 0
capital_tie_count = 0
for rec in samples:
    code = rec["code"]
    y = rec["year"]
    names = rec["names"]
    pids = rec["pids"]
    eng1, eng2 = names[0], names[1]
    pid1, pid2 = pids[0], pids[1]
    eqr_name = eqr_primary.get((code, y), "")
    if not eqr_name:
        no_eqr += 1
    eqr_pids = get_pids(eqr_name, code, y) if eqr_name else set()
    wt1, hits1 = has_tie(eqr_pids, eqr_name, pid1, eng1, y)
    wt2, hits2 = has_tie(eqr_pids, eqr_name, pid2, eng2, y)
    wt12, hits12 = has_tie(pid1, eng1, pid2, eng2, y)
    hits = (hits1 + hits2) if (wt1 or wt2) else []
    uniq_hits = dedupe_hits(hits)
    uniq_hits1 = dedupe_hits(hits1)
    uniq_hits2 = dedupe_hits(hits2)
    has_capital_tie = any(h["kind"] != "AUD" for h in uniq_hits)
    if has_capital_tie:
        capital_tie_count += 1
    tie_years = [h["year"] for h in uniq_hits]
    kinds = sorted({h["kind"] for h in uniq_hits})
    cur_ind = get_industry(code, y)
    cur_prov, cur_city = get_region(code)
    tie_similar_industry = any(
        h["industry"] and cur_ind and h["industry"] == cur_ind for h in uniq_hits)
    tie_same_province = any(
        h["province"] and cur_prov and h["province"] == cur_prov for h in uniq_hits)
    tie_same_city = any(
        h["city"] and cur_city and h["city"] == cur_city for h in uniq_hits)
    tie_high_complexity = any(h["kind"] != "AUD" for h in uniq_hits)
    tie_str = ";".join(
        f"{h['kind']}-{h['label']}-{h['year']}" for h in uniq_hits) if uniq_hits else ""
    out_rows.append({
        "stkcd": code, "year": y,
        "eng1_name": eng1, "eng2_name": eng2,
        "eng1_pid": "、".join(sorted(pid1)), "eng2_pid": "、".join(sorted(pid2)),
        "eqr_name": eqr_name,
        "eqr_pid": "、".join(sorted(eqr_pids)),
        "eqr_ann_date": eqr_meta.get((code, y), {}).get("date", ""),
        "worktie": int(wt1 or wt2),
        "worktie_eng1": int(wt1),
        "worktie_eng2": int(wt2),
        "worktie_eng1_eng2": int(wt12),
        "tie_count": len(uniq_hits) if uniq_hits else 0,
        "tie_count_eng1": len(uniq_hits1) if uniq_hits1 else 0,
        "tie_count_eng2": len(uniq_hits2) if uniq_hits2 else 0,
        "tie_first_year": min(tie_years) if tie_years else "",
        "tie_last_year": max(tie_years) if tie_years else "",
        "tie_recency": (y - max(tie_years)) if tie_years else "",
        "tie_has_aud": int("AUD" in kinds),
        "tie_has_ipo": int("IPO" in kinds),
        "tie_has_seo": int("SEO" in kinds),
        "tie_has_rio": int("RIO" in kinds),
        "tie_has_capital": int(tie_high_complexity),
        "tie_high_complexity": int(tie_high_complexity),
        "tie_similar_industry": int(tie_similar_industry),
        "tie_same_province": int(tie_same_province),
        "tie_same_city": int(tie_same_city),
        "tie_similar_client": int(tie_similar_industry or tie_same_city),
        "tie_projects": tie_str,
    })

out = pd.DataFrame(out_rows)

old_mean = None
annual_only_path = os.path.join(OUT, f"WORKTIE_{year_tag}_仅年报.csv")
if os.path.exists(annual_only_path) and not args.no_capital:
    try:
        old = pd.read_csv(annual_only_path, encoding="utf-8-sig")
        oc = old[old["eqr_name"].notna() & (old["eqr_name"].astype(str).str.strip() != "")]
        old_mean = oc["worktie"].mean()
    except Exception:
        pass

out.to_csv(os.path.join(OUT, OUT_FILE), index=False, encoding="utf-8-sig")
print("样本行数:", len(out), "缺 EQR:", no_eqr)
cov = out[out["eqr_name"].notna() & (out["eqr_name"].astype(str) != "")]
print("WORKTIE 均值（有 EQR 样本）:", cov["worktie"].mean(), "样本数:", len(cov))
if old_mean is not None:
    print(f"旧口径（仅年报）均值: {old_mean:.6f}；增量: {cov['worktie'].mean() - old_mean:+.6f}")
print("WORKTIE_ENG1_ENG2 均值:", out["worktie_eng1_eng2"].mean())
print(out.groupby("year").agg(
    n=("stkcd", "count"),
    has_eqr=("eqr_name", lambda s: (s.notna() & (s.astype(str) != "")).sum()),
    worktie=("worktie", "mean")).to_string())
if projects:
    print("含资本市场项目共事边（不截断）的 WORKTIE=1 行数:", capital_tie_count)

tied = cov[cov["worktie"] == 1]
if len(tied):
    print("\nWORKTIE=1 样本的扩展变量摘要：")
    print("tie_count 均值:", round(tied["tie_count"].mean(), 3),
          "| 中位数:", tied["tie_count"].median())
    print("tie_recency 均值:", round(tied["tie_recency"].mean(), 2),
          "| 最近一年合作占比:", round((tied["tie_recency"] == 1).mean(), 3))
    print("项目类型占比 AUD/IPO/SEO/RIO:",
          round(tied["tie_has_aud"].mean(), 3),
          round(tied["tie_has_ipo"].mean(), 3),
          round(tied["tie_has_seo"].mean(), 3),
          round(tied["tie_has_rio"].mean(), 3))
    print("高复杂度(资本市场)占比:", round(tied["tie_high_complexity"].mean(), 3),
          "| 相似客户(同行业或同城)占比:", round(tied["tie_similar_client"].mean(), 3))
