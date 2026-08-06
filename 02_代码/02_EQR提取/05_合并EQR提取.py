# -*- coding: utf-8 -*-
"""合并两批 EQR 公告级提取结果（按 announcementId 去重，旧结果优先保留）。"""
import os, argparse
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.join(BASE, "02_中间数据", "EQR提取", "EQR_公告级.csv"))
    ap.add_argument("--new", required=True)
    ap.add_argument("--out", default=os.path.join(BASE, "02_中间数据", "EQR提取", "EQR_公告级.csv"))
    args = ap.parse_args()

    base = pd.read_csv(args.base, encoding="utf-8-sig", dtype={"secCode": str})
    new = pd.read_csv(args.new, encoding="utf-8-sig", dtype={"secCode": str})
    print("旧:", len(base), "新:", len(new))
    if "announcementId" not in base.columns or "announcementId" not in new.columns:
        raise SystemExit("缺少 announcementId 列")
    new_ids = set(new["announcementId"].astype(str))
    old_ids = set(base["announcementId"].astype(str))
    overlap = old_ids & new_ids
    merged = pd.concat([base, new[~new["announcementId"].astype(str).isin(old_ids)]],
                       ignore_index=True)
    merged = merged.drop_duplicates(subset=["announcementId"], keep="first")
    merged = merged.sort_values(["secCode", "date"]).reset_index(drop=True)
    merged.to_csv(args.out, index=False, encoding="utf-8-sig")
    print("合并后:", len(merged), "| 重叠:", len(overlap))


if __name__ == "__main__":
    main()
