# -*- coding: utf-8 -*-
"""按半年分片搜索 2025/2026 新增公告，并合并为一份待下载清单。

用法：python 04_脚本/02_EQR提取/01b_搜索新增公告.py
"""
import os, subprocess, sys
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(BASE, "01_中间数据", "巨潮公告清单")
SCRIPT = os.path.join(BASE, "02_代码", "02_EQR提取", "01_搜索公告清单.py")

SEGMENTS = [
    ("2025-01-01", "2025-06-30", "pages_2025H1", "公告清单_新增_2025H1"),
    ("2025-07-01", "2025-12-31", "pages_2025H2", "公告清单_新增_2025H2"),
    ("2026-01-01", "2026-08-06", "pages_2026H1", "公告清单_新增_2026H1"),
]

for sdate, edate, tag, prefix in SEGMENTS:
    print(f"\n===== 搜索 {sdate} ~ {edate} =====", flush=True)
    r = subprocess.run([
        sys.executable, SCRIPT,
        "--sdate", sdate, "--edate", edate,
        "--tag", tag, "--out-prefix", prefix,
        "--compact", "--filter",
    ], cwd=BASE)
    if r.returncode != 0:
        raise SystemExit(f"搜索失败: {sdate} ~ {edate}")

parts = [
    "公告清单_新增_2024H2_筛选.csv",
    "公告清单_新增_2025H1_筛选.csv",
    "公告清单_新增_2025H2_筛选.csv",
    "公告清单_新增_2026H1_筛选.csv",
]
frames = [pd.read_csv(os.path.join(OUT_DIR, p), encoding="utf-8-sig", dtype={"secCode": str})
          for p in parts]
df = pd.concat(frames, ignore_index=True)
df = df.drop_duplicates(subset=["url", "title"]).reset_index(drop=True)
df = df.sort_values(["secCode", "date"]).reset_index(drop=True)
out = os.path.join(OUT_DIR, "公告清单_新增_2024Q3-2026Q3_筛选.csv")
df.to_csv(out, index=False, encoding="utf-8-sig")
print("\n合并新增清单:", len(df), "->", out)
