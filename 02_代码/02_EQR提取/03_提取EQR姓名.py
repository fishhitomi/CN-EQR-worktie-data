# -*- coding: utf-8 -*-
"""从公告 PDF 提取 EQR（项目质量控制复核人）姓名。

策略：规则初筛 + CPA 姓名库校验；同时提取项目合伙人/签字会计师作为参考。
输出：02_中间数据/EQR提取/EQR_公告级.csv
"""
import os, re, subprocess, time, argparse, glob
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF_DIR = os.path.join(BASE, "00_原始数据", "巨潮公告", "公告PDF_全量")
OUT_DIR = os.path.join(BASE, "01_中间数据", "EQR提取")
os.makedirs(OUT_DIR, exist_ok=True)

STOP_WORDS = ["公司", "名称", "证券", "股票", "代码", "公告", "年度", "审计", "事务所",
              "会计师", "报告", "股东", "会议", "临时", "拟聘", "变更", "复核", "质量",
              "项目", "签字", "注册", "关于", "先生", "女士", "从业", "经历", "执业",
              "资质", "负责", "担任", "安排", "独立", "本期", "上年", "本年", "期间",
              "情况", "姓名", "职务", "性别", "年龄", "学历", "的", "为", "与", "和",
              "及", "或", "在", "是", "等", "之", "其", "该", "这", "个", "上", "由",
              "暂未拟定", "委任", "指派", "拟任", "改任", "拟定", "待定", "暂定", "未定", "确定"]

def is_bad_name(n):
    if any(w in n for w in STOP_WORDS):
        return True
    if n.endswith(("拟", "员", "近", "派", "息", "师", "伙", "计", "人", "为", "担", "女", "男")):
        return True
    if "近" in n:
        return True
    return False

def load_name_sets():
    names = set()
    import zipfile, io
    # AR_CPAINFO
    zp = os.path.join(BASE, "00_原始数据", "CSMAR", glob.glob(os.path.join(CSMAR, "*注册会计师个人情况表*.zip"))[0] if glob.glob(os.path.join(CSMAR, "*注册会计师个人情况表*.zip")) else "")
    with zipfile.ZipFile(zp) as z:
        with z.open("AR_CPAINFO.dta") as f:
            cpa = pd.read_stata(io.BytesIO(f.read()))
    names.update(cpa["Name"].dropna().astype(str).str.strip())
    # CPA_MARK (带出生日期)
    mark = pd.read_stata(r"os.environ.get("CPA_MARK_DTA", "")")
    names.update(mark["Auditor"].dropna().astype(str).str.strip())
    names = {n for n in names if re.fullmatch(r"[\u4e00-\u9fa5·]{2,4}", n or "")}
    return names

NAME_SET = None

def extract_text(pdf):
    cmd = ["pdftotext", "-layout", pdf, "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        if r.returncode == 0:
            return r.stdout.decode("utf-8", errors="replace")
        return r.stdout.decode("utf-8", errors="replace")
    except Exception:
        return ""

def collapse(s):
    return re.sub(r"\s+", "", s or "")

def audit_year_from_text(text, title):
    ct = collapse(title) or ""
    m = re.search(r"(20\d{2})\s*年度", ct)
    if m:
        return m.group(1)
    m = re.search(r"(20\d{2})\s*年(?:度)?(?:财务报告|财务报表|会计师事务所|审计机构|审计)", ct)
    if m:
        return m.group(1)
    ct = collapse(text)
    for pat in [r"20\d{2}年度财务(?:报表|报告)?审计", r"20\d{2}年(?:年度)?财务(?:报表|报告)?审计",
                r"审计20\d{2}年度", r"20\d{2}年(?:年度)?财务报表审计"]:
        m = re.search(pat, ct)
        if m:
            return re.search(r"20\d{2}", m.group(0)).group(0)
    # 取“20xx年度”出现频率最高的年份
    years = re.findall(r"(20\d{2})\s*年度", ct)
    if years:
        from collections import Counter
        c = Counter(years)
        top = c.most_common(1)[0][0]
        if 2018 <= int(top) <= 2025:
            return top
    return ""

def extract_names(text):
    t = collapse(text)
    labels = list(re.finditer(
        r"项目质量控制复核人员|项目质量控制复核人|项目质量控制负责人|项目质量复核人员|项目质量复核人|独立复核合伙人|独立复核人|独立复核人员|质量控制复核合伙人|质量控制复核人|质量控制复核员|质量控制负责人|质量复核人员|质量复核合伙人|质量复核人|复核合伙人|复核人员", t))
    cands = []
    for m in labels:
        after = t[m.end():m.end() + 30]
        # 1) 标签后：为/：/:/是 后接名字（含称谓）
        mm = re.match(
            r"(?:（[^（）]{1,6}）)?(?:为|：|:)\s*([\u4e00-\u9fa5·]{2,4}?)(?:先生|女士)?"
            r"(?=先生|女士|[，,。；;]|从业|担任|负责|拥有|该|拟|时间|工作单位|职务|成为|开始|注册|具备|上市公司|签署|\d|年|第|$)",
            after)
        if mm:
            n = mm.group(1)
            if not is_bad_name(n):
                cands.append((m.start(), n))
        else:
            # 2) 标签后直接跟名字（如“项目质量控制复核合伙人张逸，中国注册会计师”）
            #    注意：名字须非贪婪并单独消费“先生/女士”称谓，避免把称谓吞进姓名后被停用词过滤
            mm = re.match(
                r"(?:（[^（）]{1,6}）)?([\u4e00-\u9fa5·]{2,4}?)(?:先生|女士)?"
                r"(?=[，,。、；;]|中国注册会计师|\d|年|第|从业|担任|负责|拥有|该|拟|时间|工作单位|职务|成为|开始|注册|具备|上市公司|签署|$)",
                after)
            if mm:
                n = mm.group(1)
                if not is_bad_name(n):
                    cands.append((m.start(), n))
        # 3) 变更式：由XX变更为YY（在标签后 60 字内）
        win60 = t[m.end():m.end() + 60]
        for n in re.findall(r"由([\u4e00-\u9fa5·]{2,4})(?:先生|女士)?变更为([\u4e00-\u9fa5·]{2,4})(?:先生|女士)?", win60):
            if not is_bad_name(n[0]):
                cands.append((m.start(), n[0]))
            if not is_bad_name(n[1]):
                cands.append((m.start(), n[1]))
        # 4) “项目质量控制负责人”的从业经历：王皓东（标签后 40 字内）
        win40 = t[m.end():m.end() + 40]
        mm = re.search(r"的从业经历[:：]\s*([\u4e00-\u9fa5·]{2,4})", win40)
        if mm and not is_bad_name(mm.group(1)):
            cands.append((m.start(), mm.group(1)))
        # 5) “XX担任项目质量复核人员/质量控制复核人”（标签后 60 字内）
        for mm in re.finditer(r"(?<=[：:，,、为是人])([\u4e00-\u9fa5·]{2,4})担任(?:项目)?(?:质量复核人员|质量控制复核人|质量复核人)", win60):
            n = mm.group(1)
            if not is_bad_name(n):
                cands.append((m.start(), n))
        # 6) “XX担任项目质量复核人员”名字在标签前（如“拟安排合伙人宋治忠担任项目质量复核人员”）
        pre = t[max(0, m.start() - 30):m.start()]
        mm = re.search(r"(?<=[：:，,、为是人])([\u4e00-\u9fa5·]{2,4})(?:及其团队)?拟?担任(?:项目)?$", pre)
        if mm and not is_bad_name(mm.group(1)):
            cands.append((m.start(), mm.group(1)))
        # 8) “姓名：XXX”或“姓名XXX”模式（如“质量控制复核人近三年从业情况：姓名：肖菲时间”）
        win40 = t[m.end():m.end() + 40]
        mm = re.search(r"姓名[:：]?\s*([\u4e00-\u9fa5·]{2,4}?)(?:先生|女士)?"
                       r"(?=时间|从业|工作单位|职务|成为|注册|[，,。、；;]|\d|年|$)", win40)
        if mm and not is_bad_name(mm.group(1)):
            cands.append((m.start(), mm.group(1)))
        # 7) 转置表格：名字在标签前（如“陈华质量控制复核人”）
        pre12 = t[max(0, m.start() - 12):m.start()]
        mm = re.search(r"([\u4e00-\u9fa5·]{2,4}?)(?:先生|女士)?$", pre12)
        if mm:
            n = mm.group(1)
            ok_pos = mm.start() == 0 or pre12[mm.start() - 1] in "：:，,、为是"
            if ok_pos and not is_bad_name(n):
                cands.append((m.start(), n))
    # 排序：按出现位置，优先保留姓名库命中的候选
    uniq = []
    seen = set()
    for pos, n in sorted(cands, key=lambda x: (x[1] not in NAME_SET, x[0])):
        if n not in seen:
            seen.add(n)
            uniq.append((pos, n))
    uniq.sort(key=lambda x: x[0])
    eqr = [n for _, n in uniq]
    seen = set()
    out = []
    for n in eqr:
        if n not in seen:
            seen.add(n)
            out.append(n)
    if NAME_SET and any(n in NAME_SET for n in out):
        out = [n for n in out if n in NAME_SET]
    return out

def extract_eng(text):
    t = collapse(text)
    eng = []
    m = re.search(r"项目合伙人(?:及|和)?(?:第一)?签字注册会计师[:：]?\s*([\u4e00-\u9fa5·]{2,4})(?:先生|女士)?", t)
    if m:
        eng.append(m.group(1))
    m = re.search(r"项目合伙人为([\u4e00-\u9fa5·]{2,4})(?:先生|女士)?", t)
    if m and m.group(1) not in eng:
        eng.append(m.group(1))
    cpa = []
    m = re.search(r"签字注册会计师[:：]?\s*([\u4e00-\u9fa5·]{2,4}(?:[、,，]?[\u4e00-\u9fa5·]{2,4})*)", t)
    if m:
        cpa = [n for n in re.split(r"[、,，]", m.group(1)) if re.fullmatch(r"[\u4e00-\u9fa5·]{2,4}", n)]
    m = re.search(r"另一签字注册会计师为([\u4e00-\u9fa5·]{2,4})(?:先生|女士)?", t)
    if m and m.group(1) not in cpa:
        cpa.append(m.group(1))
    return eng, cpa

def process(row):
    aid = str(row["announcementId"]) if row.get("announcementId") else ""
    if not aid:
        m = re.search(r"/(\d+)\.PDF$", str(row["url"]))
        aid = m.group(1) if m else ""
    date = str(row.get("date") or "")[:10]
    sub = date.replace("-", "") or "nodate"
    pdf = os.path.join(PDF_DIR, sub, f"{aid}.PDF")
    text = extract_text(pdf) if os.path.exists(pdf) else ""
    title = str(row.get("title") or "")
    eqr = extract_names(text)
    eng, cpa = extract_eng(text)
    # 排除与项目合伙人/签字会计师同名的误提取
    exclude = set(eng) | set(cpa)
    if exclude:
        eqr = [n for n in eqr if n not in exclude]
    ay = audit_year_from_text(text, title)
    verified = [n for n in eqr if n in NAME_SET]
    return {
        "secCode": row["secCode"], "secName": row.get("secName", ""), "title": title,
        "date": date, "announcementId": aid, "pdf": os.path.relpath(pdf, BASE),
        "audit_year": ay, "eqr": "、".join(eqr), "eqr_verified": "、".join(verified),
        "eng_partner": "、".join(eng), "signing_cpa": "、".join(cpa),
        "text_len": len(text),
    }

def main():
    global NAME_SET
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=str,
                    default=os.path.join(BASE, "01_中间数据", "EQR提取", "EQR_公告级.csv"),
                    help="输出 CSV 路径")
    ap.add_argument("--list", type=str,
                    default=os.path.join(BASE, "01_中间数据", "巨潮公告清单", "公告清单_筛选.csv"))
    args = ap.parse_args()
    NAME_SET = load_name_sets()
    print("CPA 姓名库规模:", len(NAME_SET))
    df = pd.read_csv(args.list, encoding="utf-8-sig", dtype={"secCode": str})
    if args.limit:
        df = df.head(args.limit)
    rows = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process, r): i for i, r in df.iterrows()}
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                rows.append(fut.result())
            except Exception as e:
                rows.append({"secCode": futs[fut], "error": str(e)})
            if done % 1000 == 0 or done == len(futs):
                print(f"进度 {done}/{len(futs)}  用时 {time.time()-t0:.0f}s", flush=True)
    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")
    has = out[out["eqr"].notna() & (out["eqr"].astype(str).str.strip() != "")]
    print("总公告:", len(out), "提取到 EQR:", len(has), f"({100*len(has)/len(out):.1f}%)")
    print("EQR 姓名经姓名库校验:", (has["eqr_verified"].astype(str).str.strip() != "").sum())
    if "audit_year" in has.columns:
        print(has["audit_year"].value_counts().head(8).to_string())

if __name__ == "__main__":
    main()
