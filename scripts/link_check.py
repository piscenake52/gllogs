"""logs.json の url / map のリンク切れを少しずつ調べ、結果を data/logs/ に保存する(link_check.yml から毎日実行)。
- 通常の閲覧・運営に影響が出ないよう、1回に調べる件数と時間に上限をかけ、待ち時間を入れ、画像などは読み込まない。
- 調べた順(古い順)に回すので、全件が一巡するまで何日かかかる。url を直した行は、次回の実行で優先して調べる。
- 切れと判定するのは、同じ実行の中で時間を空けて2回続けてNGだったときだけ(一時的な不通で誤検出しない)。
- 判定できないサイト(Instagram / TikTok / X / cl-live など)は対象外。
保存先: data/logs/link_state.json(全件の状態) / data/logs/link_report.json(切れだけ。helper の check タブが読む)"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import socket

LOGS = "data/logs/logs.json"
STATE = "data/logs/link_state.json"
REPORT = "data/logs/link_report.json"
LIMIT = int(os.environ.get("LINK_LIMIT", "250") or 250)          # 1回に調べる件数
MAX_SECONDS = int(os.environ.get("LINK_MAX_SECONDS", "1500") or 1500)  # 1回の実行時間の上限(秒)
RETRY_WAIT = 60                                                  # 最初のNGから再確認までの待ち(秒)
PAGE_DELAY = 1.0                                                 # ページを開く間隔(秒)
HTTP_DELAY = 0.5                                                 # ブラウザを使わない確認の間隔(秒)
UA = "Mozilla/5.0 (compatible; gllogs-linkcheck/1.0)"
HOME = "https://girls2-fc.jp/"
GENERIC_PREFIX = "Girls²(ガールズガールズ)"  # 存在しないページは、サイト共通のタイトル(これで始まる)のままになる
SKIP_HOSTS = ("instagram.com", "tiktok.com", "x.com", "twitter.com", "t.co", "cl-live.com", "facebook.com", "fb.com", "line.me", "lin.ee")


def host_of(url):
    return urllib.parse.urlparse(url).netloc.lower().replace("www.", "")


def classify(url):
    """確認の方法を返す: g2fc(ブラウザ) / yt / maps / http / None(対象外)"""
    if not re.match(r"https?://", url or ""):
        return None
    h = host_of(url)
    if any(h == s or h.endswith("." + s) for s in SKIP_HOSTS):
        return None
    if h == "girls2-fc.jp":
        return "g2fc" if urllib.parse.urlparse(url).path.startswith("/page/") else None
    if h in ("youtube.com", "m.youtube.com", "youtu.be"):
        return "yt" if yt_id(url) else None
    if h == "maps.app.goo.gl":
        return "maps"
    return "http"


def yt_id(url):
    u = urllib.parse.urlparse(url)
    h = host_of(url)
    if h == "youtu.be":
        v = u.path.strip("/").split("/")[0]
    elif u.path == "/watch":
        v = (urllib.parse.parse_qs(u.query).get("v") or [""])[0]
    else:
        m = re.match(r"^/(shorts|live|embed)/([\w-]{11})", u.path)
        v = m.group(2) if m else ""
    return v if re.fullmatch(r"[\w-]{11}", v or "") else ""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def fetch(url, follow=True):
    """戻り値: (status or None, location, error)"""
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    try:
        with opener.open(req, timeout=20) as r:
            r.read(2000)
            return r.status, "", ""
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location", "") or "", ""
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, socket.gaierror):
            return None, "", "dns"
        return None, "", type(reason).__name__
    except Exception as e:
        return None, "", type(e).__name__


def check_http(url):
    st, _, err = fetch(url)
    if st is None:
        return ("ng", "domain not found") if err == "dns" else ("unknown", err)
    if st in (404, 410):
        return "ng", f"HTTP {st}"
    if 200 <= st < 400:
        return "ok", ""
    return "unknown", f"HTTP {st}"


def check_yt(url):
    vid = yt_id(url)
    q = urllib.parse.urlencode({"format": "json", "url": "https://www.youtube.com/watch?v=" + vid})
    st, _, err = fetch("https://www.youtube.com/oembed?" + q)
    if st == 200:
        return "ok", ""
    if st == 404:
        return "ng", "video not found"
    return "unknown", f"HTTP {st}" if st else err


def check_maps(url):
    st, loc, err = fetch(url, follow=False)
    if st in (301, 302, 303, 307, 308):
        return ("ok", "") if "google." in loc else ("unknown", "redirect: " + loc[:40])
    if st == 404:
        return "ng", "HTTP 404"
    if st == 200:
        return "ok", ""
    return "unknown", f"HTTP {st}" if st else err


def check_g2fc(page, url):
    """ブラウザで開き、記事のタイトルが出れば ok。サイト共通のタイトルのまま、またはトップへ遷移したら ng"""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        return "unknown", "load error: " + type(e).__name__
    deadline = time.time() + 8
    title = ""
    while time.time() < deadline:
        if page.url.rstrip("/") == HOME.rstrip("/"):
            return "ng", "redirected to top"
        title = page.title() or ""
        if title and not title.startswith(GENERIC_PREFIX):
            return "ok", ""
        page.wait_for_timeout(500)
    if page.url.rstrip("/") == HOME.rstrip("/"):
        return "ng", "redirected to top"
    return ("ng", "page not found (site title only)") if title.startswith(GENERIC_PREFIX) else ("unknown", "no title")


def collect(rows):
    """{url: {"logids": [...], "fields": [...]}} (対象のURLだけ)"""
    out = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        for f in ("url", "map"):
            u = r.get(f)
            if isinstance(u, str) and classify(u):
                e = out.setdefault(u, {"logids": [], "fields": []})
                if r.get("logid") and r["logid"] not in e["logids"]:
                    e["logids"].append(r["logid"])
                if f not in e["fields"]:
                    e["fields"].append(f)
    return out


def pick(urls, state, limit):
    """未確認を先に、そのあとは確認が古い順に limit 件"""
    order = sorted(urls, key=lambda u: (state.get(u, {}).get("t", 0), u))
    return order[:limit]


def build_report(urls, state, now):
    items = []
    for u, info in urls.items():
        s = state.get(u)
        if s and s.get("s") == "ng":
            items.append({"url": u, "logids": info["logids"], "fields": info["fields"], "reason": s.get("r", ""), "since": s.get("since", s.get("t", 0))})
    items.sort(key=lambda x: (x["logids"][:1], x["url"]))
    return {"updated": now, "total": len(urls), "checked": sum(1 for u in urls if state.get(u, {}).get("t")), "ng": len(items), "items": items}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def run_checks(targets, urls, state, page_factory=None, clock=time.time, sleep=time.sleep):
    """targets を順に確認して state を更新する。最初にNGだったものは、最後にもう一度確認して、続けてNGなら切れとする"""
    t0 = clock()
    first_ng = []
    page = page_factory() if page_factory else None
    done = 0

    def one(u):
        k = classify(u)
        if k == "g2fc":
            return check_g2fc(page, u) if page else ("unknown", "no browser")
        return {"yt": check_yt, "maps": check_maps, "http": check_http}[k](u)

    for u in targets:
        if clock() - t0 > MAX_SECONDS:
            break
        res, why = one(u)
        sleep(PAGE_DELAY if classify(u) == "g2fc" else HTTP_DELAY)
        done += 1
        if res == "ng":
            first_ng.append(u)
            continue
        state[u] = {"t": int(clock()), "s": res, "r": why}
    if first_ng:
        sleep(RETRY_WAIT)
        for u in first_ng:
            res, why = one(u)
            sleep(PAGE_DELAY if classify(u) == "g2fc" else HTTP_DELAY)
            if res == "ng":
                prev = state.get(u, {})
                state[u] = {"t": int(clock()), "s": "ng", "r": why, "since": prev.get("since") if prev.get("s") == "ng" else int(clock())}
            else:
                state[u] = {"t": int(clock()), "s": res, "r": why}
    return done, len(first_ng)


def main():
    rows = load_json(LOGS, [])
    urls = collect(rows)
    state = {u: s for u, s in load_json(STATE, {}).items() if u in urls}  # logs から消えた(直した)URLの記録は捨てる
    targets = pick(urls, state, LIMIT)
    print(f"対象URL {len(urls)}件 / 今回 {len(targets)}件")
    pw = ctx = None
    page_factory = None
    if any(classify(u) == "g2fc" for u in targets):
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch()
        ctx = browser.new_context(locale="ja-JP", user_agent=UA)
        # 画像・動画・フォント・CSSは読み込まない(相手への負荷を減らす。タイトルの確認には不要)
        ctx.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "media", "font", "stylesheet") else route.continue_())
        page_factory = lambda: ctx.new_page()
    try:
        done, ng1 = run_checks(targets, urls, state, page_factory)
    finally:
        if pw:
            pw.stop()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_json(STATE, state)
    rep = build_report(urls, state, now)
    save_json(REPORT, rep)
    print(f"確認 {done}件 / 切れ候補 {ng1}件 / 切れ(累計) {rep['ng']}件 / 確認済み {rep['checked']}/{rep['total']}")


if __name__ == "__main__":
    sys.exit(main())
