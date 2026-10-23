"""girls2-fc.jp のリンク切れ判定の事前調査: 本物のブラウザ(Chromium)で開き、数秒後のURLと表示タイトルを記録する。
存在しないページは、ブラウザ上の処理でトップへ自動遷移するらしいので、その遷移が観測できるかを確かめる。データは変更しない。"""
import json
import os
import random
import time
from playwright.sync_api import sync_playwright

LOGS = "data/logs/logs.json"
HOME = "https://girls2-fc.jp/"
N_REAL = 12
WAIT_MS = 6000


def main():
    rows = json.load(open(LOGS, encoding="utf-8"))
    real = [r["url"] for r in rows if isinstance(r.get("url"), str) and "girls2-fc.jp/page/" in r["url"]]
    random.seed(2)
    sample = random.sample(real, N_REAL)
    fake = ["https://girls2-fc.jp/page/familyNews/0000000000000000000",
            "https://girls2-fc.jp/page/lucky2blogs/1111111111111111111",
            "https://girls2-fc.jp/page/gtube/222222222222222222"]
    todo = [("fake", u) for u in fake] + [("real", u) for u in sample]
    out = ["| kind | start url | final url | moved to home | title | seconds |", "|---|---|---|---|---|---|"]
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(locale="ja-JP")
        for kind, u in todo:
            page = ctx.new_page()
            t0 = time.time()
            seen = []
            page.on("framenavigated", lambda f: seen.append(f.url) if f == page.main_frame else None)
            try:
                page.goto(u, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(WAIT_MS)
                final, title = page.url, page.title()
            except Exception as e:
                final, title = "ERR " + type(e).__name__, str(e)[:50]
            moved = final.rstrip("/") == HOME.rstrip("/")
            out.append(f"| {kind} | {u[-60:]} | {final[-60:]} | {moved} | {title[:40].replace('|', '/')} | {time.time() - t0:.1f} |")
            page.close()
            time.sleep(1)
        b.close()
    text = "\n".join(out)
    print(text)
    s = os.environ.get("GITHUB_STEP_SUMMARY")
    if s:
        open(s, "a", encoding="utf-8").write("## link probe (browser)\n\n" + text + "\n")


if __name__ == "__main__":
    main()
