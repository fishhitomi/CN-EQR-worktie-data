# -*- coding: utf-8 -*-
"""巨潮资讯全量搜索：标题检索聘任/变更/质量控制复核类公告，输出公告清单。

输出：
  02_中间数据/巨潮公告清单/{prefix}_原始.csv   全部去重结果
  02_中间数据/巨潮公告清单/{prefix}_筛选.csv   仅 A 股 + 标题相关（可再按精简标题规则过滤）
断点续传：已抓取的页面存于 02_中间数据/巨潮公告清单/{tag}/，重跑自动跳过。

用法：
  python 01_搜索公告清单.py
  python 01_搜索公告清单.py --sdate 2024-07-02 --edate 2026-08-06 --tag 2024Q3-2026Q3 --out-prefix 公告清单_2024Q3-2026Q3 --filter
"""
import os, re, json, time, html, argparse
import urllib.request, urllib.parse
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(BASE, "02_中间数据", "巨潮公告清单")

KEYWORDS = [
    "拟聘任会计师事务所",
    "拟续聘会计师事务所",
    "聘任会计师事务所",
    "续聘会计师事务所",
    "拟变更会计师事务所",
    "变更会计师事务所",
    "质量控制复核人",
    "项目质量控制复核",
    "质量复核人",
    "签字注册会计师",
    "聘请会计师事务所",
    "签字会计师",
    "审计机构",
    "会计师事务所",
    "改聘",
    "更换会计师事务所",
    "聘用会计师事务所",
    "年审机构",
    "年度会计师事务所",
    "年度审计机构",
    # 2026-08-06 补抓：单字/变体关键词
    "聘",
    "聘用",
    "聘任",
    "续聘",
    "拟聘",
    "聘请",
    "变更审计机构",
    "审计机构变更",
    "年审会计师",
    "会计师事务所变更",
    "财务报告审计机构",
    "年度审计会计师事务所",
]

# 精简关键词集：覆盖 2024/2025 扩展窗口，保留 99.9% 以上 EQR 公告，减少冗余请求
COMPACT_KEYWORDS = [
    "会计师事务所",
    "会计事务所",
    "会计师事务",
    "会计师",
    "审计机构",
    "审计单位",
    "审计中介",
    "审计师",
    "审计机",
    "财务审机构",
    "质量控制复核人",
    "项目质量控制复核",
    "质量复核人",
    "签字注册会计师",
    "签字会计师",
    "境内审计师",
]

PAGE_SIZE = 30
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
URL = "https://www.cninfo.com.cn/new/fulltextSearch/full"

# 精简下载标题规则：在保留 99.9% EQR 命中率的前提下，显著减少无关公告
TITLE_FILTER_RE = re.compile(
    r"(?:会计师事务所|会计事务所|会计师事务|会计师|审计机构|审计单位|审计中介|审计师|审计机|财务审机构).*"
    r"(?:聘任|续聘|聘用|聘请|变更|更换|改聘|拟聘|选聘|任聘|履职|履行|评估|年度|审阅|审计)"
    r"|(?:聘任|续聘|聘用|聘请|变更|更换|改聘|拟聘|选聘|任聘).*"
    r"(?:会计师事务所|会计事务所|会计师事务|会计师|审计机构|审计单位|审计中介|审计师|审计机|审计单位)"
    r"|质量控制|项目质量复核|复核人|签字注册|签字会计师|审计中介|境内审计师"
)

def post_form(data, retries=4):
    body = urllib.parse.urlencode(data).encode("utf-8")
    for i in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print("  retry", i + 1, "after error:", e)
            time.sleep(2 + 2 * i)
    return None

def strip_tags(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return html.unescape(s).strip()

def fetch_all(keyword, sdate, edate, page_dir):
    page = 1
    total = None
    rows = []
    while True:
        fname = os.path.join(page_dir, re.sub(r"[^\w]", "_", keyword) + f"_{page:04d}.json")
        if os.path.exists(fname):
            with open(fname, encoding="utf-8") as f:
                j = json.load(f)
            print(f"[cache] {keyword} page {page}")
        else:
            data = {
                "searchkey": keyword, "isfulltext": "false",
                "sortName": "pubdate", "sortType": "desc",
                "pageNum": page, "pageSize": PAGE_SIZE,
                "sdate": sdate, "edate": edate,
            }
            txt = post_form(data)
            if txt is None:
                print(f"[FAIL] {keyword} page {page}")
                break
            j = json.loads(txt)
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(j, f, ensure_ascii=False)
            print(f"[ok] {keyword} page {page}")
            time.sleep(0.4)
        anns = j.get("announcements") or []
        if not anns:
            break
        total = j.get("totalAnnouncement")
        for a in anns:
            ts = a.get("announcementTime")
            rows.append({
                "secCode": a.get("secCode", ""),
                "secName": a.get("secName", ""),
                "title": strip_tags(a.get("announcementTitle", "")),
                "date": time.strftime("%Y-%m-%d", time.localtime(ts / 1000)) if ts else "",
                "url": "http://static.cninfo.com.cn/" + (a.get("adjunctUrl") or ""),
                "announcementId": a.get("announcementId", ""),
                "keyword": keyword,
            })
        if page * PAGE_SIZE >= (total or 0):
            break
        page += 1
    print(f"== {keyword}: total={total}, collected={len(rows)}")
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sdate", default="2019-10-01")
    ap.add_argument("--edate", default="2024-07-01")
    ap.add_argument("--tag", default="pages", help="页面缓存子目录名")
    ap.add_argument("--out-prefix", default="公告清单", help="输出 CSV 前缀")
    ap.add_argument("--filter", action="store_true",
                    help="筛选时应用精简标题规则（保留约 99.9% EQR 命中）")
    ap.add_argument("--compact", action="store_true",
                    help="使用精简关键词集（推荐用于新增 2024/2025 窗口）")
    args = ap.parse_args()
    sdate, edate = args.sdate, args.edate
    page_dir = os.path.join(OUT_DIR, args.tag)
    os.makedirs(page_dir, exist_ok=True)

    all_rows = []
    kws = COMPACT_KEYWORDS if args.compact else KEYWORDS
    for kw in kws:
        all_rows.extend(fetch_all(kw, sdate, edate, page_dir))
    df = pd.DataFrame(all_rows)
    if df.empty:
        print("无结果")
        return
    df = df.drop_duplicates(subset=["url", "title"]).reset_index(drop=True)
    df.to_csv(os.path.join(OUT_DIR, f"{args.out_prefix}_原始.csv"), index=False,
              encoding="utf-8-sig")

    # 筛选：A 股代码 + 标题含关键业务词
    code_ok = df["secCode"].astype(str).str.match(r"^(0|3|6)\d{5}$")
    title_ok = df["title"].str.contains("聘任|续聘|变更|会计师事务所|复核|签字注册", na=False)
    sel = df[code_ok & title_ok].copy()
    if args.filter:
        sel = sel[sel["title"].astype(str).str.contains(TITLE_FILTER_RE, na=False, regex=True)].copy()
    sel = sel.sort_values(["secCode", "date"]).reset_index(drop=True)
    sel.to_csv(os.path.join(OUT_DIR, f"{args.out_prefix}_筛选.csv"), index=False,
               encoding="utf-8-sig")
    print("原始去重:", len(df), "筛选后:", len(sel))
    print(sel.groupby("keyword").size().to_string())

if __name__ == "__main__":
    main()
