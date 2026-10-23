"""リンク切れチェックの事前調査: 実際のURLを少数だけ取得し、サイトごとの応答(ステータス・転送先・本文の先頭)を表にする。
GitHub Actions(link_probe.yml)から手動で実行する。データは変更しない。"""
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

LOGS = "data/logs/logs.json"
UA = "Mozilla/5.0 (compatible; gllogs-linkcheck/0.1)"
PER_SITE = 6  # サイトごとの調査件数
SITES = ["girls2-fc.jp", "youtube.com", "youtu.be", "x.com", "instagram.com", "cl-live.com", "tokyoheadline.com", "maps.app.goo.gl", "vt.tiktok.com"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def probe(url):
    """戻り値: (status, location, title/本文の先頭)。転送は追わず、そのまま報告する"""
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    try:
        with opener.open(req, timeout=20) as r:
            body = r.read(60000).decode("utf-8", "replace")
            m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
            return r.status, "", (m.group(1).strip() if m else re.sub(r"\s+", " ", body[:80]))[:80]
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location", "") or "", ""
    except Exception as e:  # DNS失敗・タイムアウトなど
        return "ERR", "", type(e).__name__ + ": " + str(e)[:60]


def main():
    rows = json.load(open(LOGS, encoding="utf-8"))
    urls = {}
    for r in rows:
        for k in ("url", "map"):
            u = r.get(k)
            if isinstance(u, str) and u.startswith("http"):
                urls.setdefault(urllib.parse.urlparse(u).netloc.replace("www.", ""), []).append(u)
    random.seed(1)
    out = ["| site | status | location | title / error | url |", "|---|---|---|---|---|"]
    fake = ["https://girls2-fc.jp/page/familyNews/0000000000000000000", "https://girls2-fc.jp/page/nosuchpage/1"]
    todo = [("(fake)", u) for u in fake]
    for s in SITES:
        lst = urls.get(s, [])
        for u in random.sample(lst, min(PER_SITE, len(lst))):
            todo.append((s, u))
    for s, u in todo:
        st, loc, info = probe(u)
        out.append(f"| {s} | {st} | {loc[:60]} | {info.replace('|', '/')} | {u[:70]} |")
        time.sleep(1.5)
    text = "\n".join(out)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## link probe\n\n" + text + "\n")


if __name__ == "__main__":
    sys.exit(main())
