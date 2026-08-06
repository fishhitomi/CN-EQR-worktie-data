# -*- coding: utf-8 -*-
"""CNINFO 搜索接口探针：确认参数与返回结构（仅测试，不保存）。"""
import urllib.request, urllib.parse, json

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def post_form(url, data):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")

def probe_announcement(keyword, column="sse"):
    url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    data = {
        "pageNum": 1, "pageSize": 30, "column": column, "tabName": "fulltext",
        "plate": "", "stock": "", "searchkey": keyword, "secid": "",
        "category": "", "trade": "", "seDate": "2019-10-01~2024-07-01",
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    txt = post_form(url, data)
    print("POST", column, keyword, "-> len:", len(txt))
    j = json.loads(txt)
    print("totalAnnouncement:", j.get("totalAnnouncement"))
    for a in (j.get("announcements") or [])[:10]:
        print("  ", a.get("secCode"), a.get("secName"), "|", a.get("announcementTitle"),
              "|", a.get("adjunctUrl"), "|", a.get("announcementTime"))

def probe_fulltext(keyword):
    url = "https://www.cninfo.com.cn/new/fulltextSearch/full"
    data = {
        "searchkey": keyword, "isfulltext": "false", "sortName": "pubdate",
        "sortType": "desc", "pageNum": 1, "pageSize": 30,
    }
    txt = post_form(url, data)
    print("fulltextSearch", keyword, "-> len:", len(txt))
    print(txt[:500])

if __name__ == "__main__":
    probe_announcement("拟聘任会计师事务所", "sse")
    probe_announcement("质量控制复核人", "sse")
    probe_fulltext("拟聘任会计师事务所")
