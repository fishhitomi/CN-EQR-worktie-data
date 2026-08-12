# -*- coding: utf-8 -*-
"""精简巨潮公告 PDF：把未提取到 EQR 的 PDF 移入回收目录（可恢复）。

默认只生成待清理清单（dry-run）；确认后加 --execute 才会移动文件。
移动不跨盘，速度很快；如需真正释放磁盘空间，之后可手动删除回收目录。

用法：
  python 04_脚本/07_PDF精简/01_清理未命中PDF.py
  python 04_脚本/07_PDF精简/01_清理未命中PDF.py --execute
  python 04_脚本/07_PDF精简/01_清理未命中PDF.py --execute --delete
"""
import os, re, shutil, subprocess, argparse, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF_ROOT = os.path.join(BASE, "00_原始数据", "巨潮公告", "公告PDF_全量")
OLD_ROOT = os.path.join(BASE, "00_原始数据", "巨潮公告", "公告PDF")
EQR_FILE = os.path.join(BASE, "01_中间数据", "EQR提取", "EQR_公告级.csv")
OUT_DIR = os.path.join(BASE, "01_中间数据", "PDF精简")
os.makedirs(OUT_DIR, exist_ok=True)

# 与搜索脚本一致的精简标题规则：可用来判断“相关但未提取到 EQR”的公告
TITLE_FILTER_RE = re.compile(
    r"(?:会计师事务所|会计事务所|会计师事务|会计师|审计机构|审计单位|审计中介|审计师|审计机|财务审机构).*"
    r"(?:聘任|续聘|聘用|聘请|变更|更换|改聘|拟聘|选聘|任聘|履职|履行|评估|年度|审阅|审计)"
    r"|(?:聘任|续聘|聘用|聘请|变更|更换|改聘|拟聘|选聘|任聘).*"
    r"(?:会计师事务所|会计事务所|会计师事务|会计师|审计机构|审计单位|审计中介|审计师|审计机|审计单位)"
    r"|质量控制|项目质量复核|复核人|签字注册|签字会计师|审计中介|境内审计师"
)


def norm(p):
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true",
                    help="真正把未命中 PDF 移入回收目录（默认仅生成清单）")
    ap.add_argument("--delete", action="store_true",
                    help="移动后立即删除回收目录（不可恢复，需谨慎）")
    ap.add_argument("--keep-relevant", action="store_true",
                    help="保留标题相关但未提取到 EQR 的 PDF（默认全部移走）")
    ap.add_argument("--archive-text", action="store_true",
                    help="移动前先把未命中 PDF 全文导出为 CSV（便于以后改进规则）")
    args = ap.parse_args()

    eqr = pd.read_csv(EQR_FILE, encoding="utf-8-sig", dtype={"secCode": str})
    eqr["has_eqr"] = eqr["eqr"].notna() & (eqr["eqr"].astype(str).str.strip() != "")
    used = set()
    meta = {}
    for _, r in eqr.iterrows():
        p = str(r.get("pdf") or "")
        if not p:
            continue
        full = os.path.join(BASE, p)
        if os.path.exists(full):
            n = norm(full)
            meta[n] = (str(r["announcementId"]), str(r["title"]), bool(r["has_eqr"]))
            if r["has_eqr"]:
                used.add(n)

    candidates = []
    for root in (PDF_ROOT, OLD_ROOT):
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for fn in files:
                if not fn.lower().endswith(".pdf"):
                    continue
                full = os.path.join(dirpath, fn)
                n = norm(full)
                if n in used:
                    continue
                ann_id, title, has = meta.get(n, ("", "", False))
                relevant = bool(TITLE_FILTER_RE.search(title))
                if args.keep_relevant and relevant:
                    continue
                candidates.append({
                    "path": os.path.relpath(full, BASE),
                    "size": os.path.getsize(full),
                    "announcementId": ann_id,
                    "title": title,
                    "has_eqr": has,
                    "relevant_title": relevant,
                })

    df = pd.DataFrame(candidates)
    list_path = os.path.join(OUT_DIR, "待清理PDF清单.csv")
    df.to_csv(list_path, index=False, encoding="utf-8-sig")
    total_gb = df["size"].sum() / 1024**3 if len(df) else 0
    print(f"已生成待清理清单: {list_path}")
    print(f"未命中 EQR 的 PDF: {len(df)} 个，合计 {total_gb:.2f} GB")
    if len(df) and not args.execute:
        print("这是 dry-run，未移动任何文件。确认后加 --execute 再执行。")
        return
    if not len(df):
        return

    if args.archive_text:
        def extract_text(row):
            cmd = ["pdftotext", "-layout", os.path.join(BASE, row["path"]), "-"]
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=60)
                return row["path"], r.stdout.decode("utf-8", errors="replace")
            except Exception:
                return row["path"], ""
        texts = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(extract_text, r) for _, r in df.iterrows()]
            for i, fut in enumerate(as_completed(futs), 1):
                p, t = fut.result()
                texts[p] = t
                if i % 5000 == 0:
                    print(f"文本导出进度 {i}/{len(df)}")
        df["text"] = df["path"].map(texts)
        text_archive = os.path.join(OUT_DIR, "未命中PDF文本.csv")
        df.to_csv(text_archive, index=False, encoding="utf-8-sig")
        print("已导出文本归档:", text_archive,
              f"（{df['text'].str.len().sum() / 1024 / 1024:.0f} MB）")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    trash = os.path.join(BASE, "00_原始数据", "巨潮公告", f"公告PDF_未命中EQR_回收_{stamp}")
    os.makedirs(trash, exist_ok=True)
    moved = 0
    for _, r in df.iterrows():
        src = os.path.join(BASE, r["path"])
        rel = os.path.relpath(src, PDF_ROOT) if src.startswith(PDF_ROOT) else os.path.basename(src)
        dst = os.path.join(trash, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            continue
        os.rename(src, dst)
        moved += 1
    print(f"已移动 {moved}/{len(df)} 个 PDF 到: {trash}")

    # 清理原目录中变空的日期文件夹（只删空目录）
    for root in (PDF_ROOT, OLD_ROOT):
        for dirpath, dirnames, _ in os.walk(root, topdown=False):
            try:
                os.rmdir(dirpath)
            except OSError:
                pass

    if args.delete:
        shutil.rmtree(trash)
        print("已删除回收目录（不可恢复）。")


if __name__ == "__main__":
    main()
