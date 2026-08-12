# -*- coding: utf-8 -*-
"""生成最终交付数据集：WORKTIE（2020-2024，公司-年度，dta）。

样本口径：
  1) 审计年度 2020-2024；
  2) 剔除金融业（证监会行业代码 J 开头）；
  3) 剔除年末 ST/PT；
  4) 剔除未披露质量控制复核人（EQR）的观测；
  5) 不因缺少财务/控制变量而删样本。

输出：
  03_输出/WORKTIE_2020-2024.dta
  30 个变量（含签字审计师姓名、PersonID、共事项目明细等配套标识变量），
  每个变量均带中文标签，0/1 哑变量带「否/是」值标签。
"""
import os
import re
from pathlib import Path

import pandas as pd


BASE = Path(__file__).resolve().parents[2]
WORKTIE_CSV = BASE / "01_中间数据" / "WORKTIE" / "WORKTIE_2020-2025.csv"

# 外部数据（行业/ST 识别），通过环境变量 EARNINGS_MGMT_DIR 指向
# 「应计盈余管理（修正的琼斯模型）2000-2024年」所在目录
EARNINGS_MGMT_DIR = os.environ.get("EARNINGS_MGMT_DIR", "")
COMPANY_DTA = Path(EARNINGS_MGMT_DIR) / "公司文件.dta"
ST_DTA = Path(EARNINGS_MGMT_DIR) / "是否ST或PT.dta"

OUT_DIR = BASE / "03_输出"
OUT_FILE = OUT_DIR / "WORKTIE_2020-2024.dta"

# 输出变量顺序（与交付 dta 保持一致）
COLUMN_ORDER = [
    "code", "year", "eng1_name", "eng2_name", "eqr_name",
    "worktie", "worktie_eng1", "worktie_eng2", "worktie_eng1_eng2",
    "tie_count", "tie_count_eng1", "tie_count_eng2",
    "tie_first_year", "tie_last_year", "tie_recency",
    "tie_has_aud", "tie_has_ipo", "tie_has_seo", "tie_has_rio",
    "tie_has_capital", "tie_high_complexity",
    "tie_similar_industry", "tie_same_province", "tie_same_city",
    "tie_similar_client", "tie_projects", "eqr_ann_date",
    "eng1_pid", "eng2_pid", "eqr_pid",
]

# 0/1 哑变量（应用「否/是」值标签）
DUMMY_COLS = [
    "worktie", "worktie_eng1", "worktie_eng2", "worktie_eng1_eng2",
    "tie_has_aud", "tie_has_ipo", "tie_has_seo", "tie_has_rio",
    "tie_has_capital", "tie_high_complexity",
    "tie_similar_industry", "tie_same_province", "tie_same_city",
    "tie_similar_client",
]

VARIABLE_LABELS = {
    "code": "公司代码（6位股票代码）",
    "year": "审计年度",
    "eng1_name": "第一签字项目合伙人姓名",
    "eng2_name": "第二签字项目合伙人姓名",
    "eqr_name": "质量控制复核人（EQR）姓名",
    "worktie": "核心解释变量：EQR与至少一位签字合伙人此前曾在同一上市公司审计或资本市场项目共同作为签字审计师执业（0/1）",
    "worktie_eng1": "EQR与第一签字合伙人既往共事（0/1）",
    "worktie_eng2": "EQR与第二签字合伙人既往共事（0/1）",
    "worktie_eng1_eng2": "两位签字项目合伙人之间既往共事（0/1）",
    "tie_count": "既往合作项目总数（去重后，含年报审计+资本市场项目）",
    "tie_count_eng1": "EQR与第一签字合伙人既往合作项目数",
    "tie_count_eng2": "EQR与第二签字合伙人既往合作项目数",
    "tie_first_year": "首次合作年份",
    "tie_last_year": "最近一次合作年份",
    "tie_recency": "距最近一次合作的时间间隔（审计年度−最近合作年份，单位：年）",
    "tie_has_aud": "既往共事是否含年报审计项目（0/1）",
    "tie_has_ipo": "既往共事是否含IPO申报项目（0/1）",
    "tie_has_seo": "既往共事是否含增发项目（0/1）",
    "tie_has_rio": "既往共事是否含配股项目（0/1）",
    "tie_has_capital": "既往共事是否含资本市场项目（IPO/增发/配股，0/1）",
    "tie_high_complexity": "是否含高复杂度共事项目（以资本市场项目作为代理，0/1）",
    "tie_similar_industry": "既往共事项目中是否有与当前客户同行业（证监会行业代码）的项目（0/1）",
    "tie_same_province": "既往共事项目中是否有与当前客户同省份的项目（0/1）",
    "tie_same_city": "既往共事项目中是否有与当前客户同城市的项目（0/1）",
    "tie_similar_client": "相似客户（0/1）：既往共事项目客户与当前审计客户同证监会行业门类或同城市注册，二者满足其一取1（不含同省）",
    "tie_projects": "WORKTIE=1时的共事项目明细（公司代码-年度），含类型前缀：AUD（年报）、IPO、SEO（增发）、RIO（配股）",
    "eqr_ann_date": "EQR信息来源公告日期（数值型，%td格式，取该年度最新公告）",
    "eng1_pid": "第一签字合伙人PersonID（CSMAR审计师唯一标识，可多个，以；分隔）",
    "eng2_pid": "第二签字合伙人PersonID（CSMAR审计师唯一标识，可多个，以；分隔）",
    "eqr_pid": "质量控制复核人PersonID（CSMAR审计师唯一标识，可多个，以；分隔）",
}

STATA_EPOCH = pd.Timestamp("1960-01-01")


def z6(x):
    """把股票代码统一成 6 位字符串；无效返回空串。"""
    s = str(x).strip()
    m = re.match(r"(\d{1,6})(?:\.0+)?$", s)
    return m.group(1).zfill(6) if m else ""


def clean_pid(s):
    """清理 PersonID：去浮点残留（'30545475.0' -> '30545475'），
    去除因浮点/整数双写产生的重复 ID，统一以 '；' 分隔多个 ID。"""
    if pd.isna(s):
        return ""
    parts = [p.strip() for p in re.split(r"[、;,，；]", str(s)) if p.strip()]
    cleaned = [re.sub(r"\.0+$", "", p) for p in parts]
    seen = set()
    uniq = []
    for p in cleaned:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return "；".join(uniq)


def main():
    if not EARNINGS_MGMT_DIR:
        print("警告：未设置环境变量 EARNINGS_MGMT_DIR（指向应计盈余管理数据目录），"
              "无法读取 公司文件.dta / 是否ST或PT.dta，将跳过金融业/ST 剔除。")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("读取 WORKTIE 基础数据 ...")
    df = pd.read_csv(WORKTIE_CSV, encoding="utf-8-sig", dtype={"stkcd": str})
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df = df[df["year"].between(2020, 2024)].copy()
    df["stkcd"] = df["stkcd"].str.zfill(6)
    print("2020-2024 公司-年总数:", len(df))

    if EARNINGS_MGMT_DIR:
        print("读取公司文件（金融业识别） ...")
        comp = pd.read_stata(COMPANY_DTA, convert_categoricals=False)
        comp["code6"] = comp["stkcd"].map(z6)
        comp = comp.drop_duplicates("code6")
        comp["fin"] = (
            comp["Industry"].astype(str).str.strip().str.upper().str.startswith("J")
        )
        df = df.merge(comp[["code6", "fin"]], left_on="stkcd", right_on="code6",
                      how="left")
        df["fin"] = df["fin"].fillna(False)

        print("读取 ST/PT 状态 ...")
        st = pd.read_stata(ST_DTA, convert_categoricals=False)
        st["code6"] = st["stkcd"].map(z6)
        st["year"] = pd.to_numeric(st["year"], errors="coerce").astype("Int64")
        st = st[["code6", "year", "年末是否ST或PT"]].drop_duplicates(["code6", "year"])
        st = st.rename(columns={"年末是否ST或PT": "is_st"})
        df = df.merge(st, on=["code6", "year"], how="left")
        df["is_st"] = df["is_st"].fillna(0).astype(int)
    else:
        df["fin"] = False
        df["is_st"] = 0

    df["has_eqr"] = df["eqr_name"].notna() & (
        df["eqr_name"].astype(str).str.strip() != ""
    )

    mask = (~df["fin"]) & (df["is_st"] == 0) & df["has_eqr"]
    print("剔除金融:", int(df["fin"].sum()),
          "| 剔除 ST/PT:", int((df["is_st"] == 1).sum()),
          "| 保留有 EQR:", int(df["has_eqr"].sum()))
    print("最终样本（2020-2024）:", int(mask.sum()))

    out = df.loc[mask].copy()
    out = out.rename(columns={"stkcd": "code"})
    out["code"] = out["code"].astype(str).str.zfill(6)
    out["year"] = out["year"].astype(int)

    # 数值化合作计数/年份类变量
    for col in ["tie_count", "tie_count_eng1", "tie_count_eng2",
                "tie_first_year", "tie_last_year", "tie_recency"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    # 0/1 哑变量统一为整数
    for col in DUMMY_COLS:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)

    # EQR 公告日期 -> Stata %td（1960-01-01 起天数）
    out["eqr_ann_date"] = (
        pd.to_datetime(out["eqr_ann_date"], errors="coerce") - STATA_EPOCH
    ).dt.days

    # PersonID 清理
    for col in ["eng1_pid", "eng2_pid", "eqr_pid"]:
        out[col] = out[col].map(clean_pid)

    # 共事项目明细：空值置为空串
    out["tie_projects"] = out["tie_projects"].fillna("")

    out = out.sort_values(["code", "year"]).reset_index(drop=True)
    out = out[COLUMN_ORDER]

    out.to_stata(
        OUT_FILE,
        version=118,
        write_index=False,
        variable_labels=VARIABLE_LABELS,
        value_labels={col: {0: "否", 1: "是"} for col in DUMMY_COLS},
        data_label="EQR-签字合伙人既往共事经历（WORKTIE）2020-2025",
    )
    print("已输出:", OUT_FILE)

    print("\n按年样本量：")
    print(out.groupby("year").agg(
        n=("code", "count"),
        worktie_mean=("worktie", "mean"),
        tied=("worktie", "sum"),
    ).to_string())
    print("\n核心变量描述：")
    print(out[["worktie", "worktie_eng1_eng2", "tie_count",
               "tie_last_year", "tie_recency",
               "tie_high_complexity", "tie_similar_client"]].describe().to_string())


if __name__ == "__main__":
    main()
