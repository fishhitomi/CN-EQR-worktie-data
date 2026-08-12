# -*- coding: utf-8 -*-
"""合并多批公告清单（按 url+title 去重）。"""
import os, argparse
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(BASE, "01_中间数据", "巨潮公告清单")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    frames = [pd.read_csv(os.path.join(OUT_DIR, p), encoding="utf-8-sig", dtype={"secCode": str})
              for p in args.inputs]
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["url", "title"]).reset_index(drop=True)
    df = df.sort_values(["secCode", "date"]).reset_index(drop=True)
    df.to_csv(os.path.join(OUT_DIR, args.out), index=False, encoding="utf-8-sig")
    print("合并后:", len(df))


if __name__ == "__main__":
    main()
