# -*- coding: utf-8 -*-
"""生成最终交付数据集：WORKTIE 核心变量（2020-2024，公司-年度，dta）。

样本口径：
  1) 审计年度 2020-2024；
  2) 剔除金融业（证监会行业代码 J 开头）；
  3) 剔除年末 ST/PT；
  4) 剔除未披露质量控制复核人（EQR）的观测；
  5) 不因缺少财务/控制变量而删样本。

输出：
  03_数据集/WORKTIE_核心变量_2020-2024.dta
  每个变量均带中文标签。
"""
from pathlib import Path
import re

import pandas as pd


BASE = Path(__file__).resolve().parents[2]
WORKTIE_CSV = BASE / "02_中间数据" / "WORKTIE" / "WORKTIE_2020-2025.csv"
COMPANY_DTA = Path(
    r"os.environ.get("EARNINGS_MGMT_DIR", "")\公司文件.dta"
)
ST_DTA = Path(
    r"os.environ.get("EARNINGS_MGMT_DIR", "")\是否ST或PT.dta"
)
OUT_DIR = BASE / "03_输出"
OUT_FILE = OUT_DIR / "WORKTIE_核心变量_2020-2024.dta"


def z6(x):
    """把股票代码统一成 6 位字符串；无效返回空串。"""
    s = str(x).strip()
    m = re.match(r"(\d{1,6})(?:\.0+)?$", s)
    return m.group(1).zfill(6) if m else ""


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("读取 WORKTIE 基础数据 ...")
    df = pd.read_csv(WORKTIE_CSV, encoding="utf-8-sig", dtype={"stkcd": str})
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df = df[df["year"].between(2020, 2024)].copy()
    df["stkcd"] = df["stkcd"].str.zfill(6)
    print("2020-2024 公司-年总数:", len(df))

    print("读取公司文件（金融业识别） ...")
    comp = pd.read_stata(COMPANY_DTA, convert_categoricals=False)
    comp["code6"] = comp["stkcd"].map(z6)
    comp = comp.drop_duplicates("code6")
    comp["fin"] = (
        comp["Industry"].astype(str).str.strip().str.upper().str.startswith("J")
    )
    df = df.merge(comp[["code6", "fin"]], left_on="stkcd", right_on="code6", how="left")
    df["fin"] = df["fin"].fillna(False)

    print("读取 ST/PT 状态 ...")
    st = pd.read_stata(ST_DTA, convert_categoricals=False)
    st["code6"] = st["stkcd"].map(z6)
    st["year"] = pd.to_numeric(st["year"], errors="coerce").astype("Int64")
    st = st[["code6", "year", "年末是否ST或PT"]].drop_duplicates(["code6", "year"])
    st = st.rename(columns={"年末是否ST或PT": "is_st"})
    df = df.merge(st, on=["code6", "year"], how="left")
    df["is_st"] = df["is_st"].fillna(0).astype(int)

    df["has_eqr"] = df["eqr_name"].notna() & (
        df["eqr_name"].astype(str).str.strip() != ""
    )

    mask = (~df["fin"]) & (df["is_st"] == 0) & df["has_eqr"]
    print("剔除金融:", int(df["fin"].sum()),
          "| 剔除 ST/PT:", int((df["is_st"] == 1).sum()),
          "| 保留有 EQR:", int(df["has_eqr"].sum()))
    print("最终样本（2020-2024）:", int(mask.sum()))

    keep = [
        "stkcd", "year", "worktie", "worktie_eng1_eng2",
        "tie_count", "tie_last_year", "tie_recency",
        "tie_high_complexity", "tie_similar_client",
    ]
    out = df.loc[mask, keep].copy()
    out = out.rename(columns={"stkcd": "code"})
    out["code"] = out["code"].astype(str).str.zfill(6)
    out["year"] = out["year"].astype(int)

    for col in ["tie_count", "tie_last_year", "tie_recency"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    for col in ["worktie", "worktie_eng1_eng2", "tie_high_complexity", "tie_similar_client"]:
        out[col] = out[col].astype(int)

    out = out.sort_values(["code", "year"]).reset_index(drop=True)

    variable_labels = {
        "code": "公司代码",
        "year": "审计年度",
        "worktie": "质量控制复核人与签字合伙人既往共事（0/1）",
        "worktie_eng1_eng2": "两位签字合伙人既往共事（0/1）",
        "tie_count": "既往合作项目次数",
        "tie_last_year": "最近一次合作年份",
        "tie_recency": "距最近合作时间间隔（年）",
        "tie_high_complexity": "是否含资本市场项目（高复杂度代理，0/1）",
        "tie_similar_client": "是否相似客户（同行业或同城市，0/1）",
    }

    out.to_stata(
        OUT_FILE,
        version=118,
        write_index=False,
        variable_labels=variable_labels,
        data_label="EQR-签字合伙人既往共事核心变量（2020-2024）",
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
