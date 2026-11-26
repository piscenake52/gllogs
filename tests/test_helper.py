"""helper(issue_helper_blogger.html)の自動テスト。Playwright(Chromium)で実際に開いて確認する。

準備:  pip install playwright pyyaml && playwright install chromium
実行:  python -m unittest tests.test_helper -v
helper の場所は環境変数 HELPER_HTML で指定(既定: リポジトリ直下の issue_helper_blogger.html)。
Playwright か helper が無い環境では全体を skip する。
通信はすべてモック(GitHub には何も送らない)、日付は 2026-11-20 12:00(JST)に固定する。
send した内容は、本物の inbox_to_json.py → merge_json.py に通して、登録結果まで確認する。
"""
import base64
import json
import os
import re
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from tests.helpers import Repo

ROOT = Path(__file__).resolve().parent.parent
HELPER = Path(os.environ.get("HELPER_HTML") or ROOT / "issue_helper_blogger.html")

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

NOW = "2026-11-20T12:00:00+09:00"
ORIGIN = "https://helper.test/gllogs/"

LOG = {"logid": "abc123abc123", "date": "20261101", "time": "1800", "contents": "LIVE", "title": "既存の公演",
       "url": "https://example.com/live", "venue": "既存の会場", "groups": ["G2"], "tags": ["Umbrella"]}
SONG = {"artist": "Girls²", "title": "テスト曲",
        "videos": [{"type": "MV", "url": "https://youtu.be/aaaaaaaaaaa", "tags": ["公式"]}]}

WALLPAPER = """Girls² 11月スペシャル壁紙プレゼントキャンペーン
【ダウンロード期間】
11/25(水)20:00-11/28(土)20:00
https://girls2-fc.jp/page/wallpaper/1252202976852836352
Umbrella GL² family Exclusive Visual"""

LOTTERY = """架空のテスト公演 先行
受付期間：12/5(土) 18:00 〜 12/13(日) 23:59
当落発表：12/18(金) 15:00
入金期限：12/21(月) 23:00
公演日：2027年1月10日(日)"""

_browser = {}


def setUpModule():
    if sync_playwright is not None and HELPER.exists():
        _browser["pw"] = sync_playwright().start()
        _browser["b"] = _browser["pw"].chromium.launch()


def tearDownModule():
    if _browser:
        _browser["b"].close()
        _browser["pw"].stop()
        _browser.clear()


@unittest.skipIf(sync_playwright is None, "playwright が無いので skip")
@unittest.skipUnless(HELPER.exists(), "helper が見つからないので skip (HELPER_HTML で指定)")
class HelperCase(Repo):
    def open(self, path="#logs", token=True, logs=(LOG,), songs=(SONG,), setlists=(), result=None, put_status=201):
        """helper を開く。self.sent に send した依頼(data/inbox/ への PUT)が入る"""
        ctx = _browser["b"].new_context(viewport={"width": 390, "height": 900},
                                        timezone_id="Asia/Tokyo", locale="ja-JP")
        self.addCleanup(ctx.close)
        if token:
            cfg = json.dumps({"repo": "test/repo", "branch": "main", "mode": "plain", "token": "dummy-token"})
            ctx.add_init_script("try{localStorage.setItem('glih_set',%s)}catch(e){}" % json.dumps(cfg))
        pg = ctx.new_page()
        pg.clock.set_fixed_time(NOW)
        self.errors, self.sent, self.outside = [], [], []
        pg.on("pageerror", lambda e: self.errors.append(str(e)))
        page = ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                + HELPER.read_text(encoding="utf-8"))
        data = {"data/logs/logs.json": list(logs), "data/logs/logs_index.json": list(logs),
                "data/songs/songs.json": list(songs), "data/setlist/setlist.json": list(setlists),
                "data/setlist/setlist_index.json": list(setlists), "data/albums/albums.json": []}
        cors = {"access-control-allow-origin": "*", "access-control-allow-headers": "*",
                "access-control-allow-methods": "GET,PUT,OPTIONS"}

        def reply(r, obj, status=200):
            r.fulfill(status=status, content_type="application/json", headers=cors,
                      body=json.dumps(obj, ensure_ascii=False))

        def handle(r):
            req, u = r.request, r.request.url
            if u.startswith(ORIGIN):
                return r.fulfill(content_type="text/html", body=page)
            if req.method == "OPTIONS":
                return r.fulfill(status=204, headers=cors)
            if req.method == "PUT":
                body = json.loads(req.post_data)
                self.sent.append({"url": u, "auth": req.headers.get("authorization"), "branch": body["branch"],
                                  "request": json.loads(base64.b64decode(body["content"]).decode("utf-8"))})
                return reply(r, {}, put_status)
            if "/data/inbox/results/" in u:
                return reply(r, result or {"status": "done"})
            m = re.search(r"(data/[a-z_]+/[a-z_]+\.json)", u)
            if m and m.group(1) in data:
                return reply(r, data[m.group(1)])
            if "api.github.com" in u and "/commits" in u:
                return reply(r, [{"sha": "v1"}])
            self.outside.append(u)
            return reply(r, {}, 404)

        pg.route("**/*", handle)
        pg.goto(ORIGIN + path)
        pg.wait_for_timeout(500)
        return pg

    # --- 操作 ---
    def new_log(self, pg, date="20261201", time="1800", **fields):
        pg.fill("#glih-fdd", date)
        pg.fill("#glih-fdt", time)
        pg.wait_for_selector("#glih-f-title")
        for k, v in fields.items():
            pg.fill("#glih-f-" + k, v)

    def issue(self, pg, button="#glih-go-find"):
        """Issue ボタンのリンクから、フォームに入る値を取り出す。送れない状態なら None"""
        pg.wait_for_timeout(300)
        href = pg.get_attribute(button, "href")
        if not href or pg.get_attribute(button, "aria-disabled") == "true":
            return None
        q = {k: v[0] for k, v in parse_qs(urlsplit(href).query).items()}
        return q

    def send(self, pg, button="#glih-go-find"):
        n = len(self.sent)
        pg.locator(button + " + .sendrow button.go").click()
        pg.wait_for_function("b => /^(done|not reflected|failed|sent, but)/.test("
                             "document.querySelector(b + ' + .sendrow + .sendst').textContent)", arg=button)
        self.assertEqual(len(self.sent), n + 1)
        return self.sent[-1]

    def status(self, pg, button="#glih-go-find"):
        return pg.inner_text(button + " + .sendrow + .sendst")

    def register(self, sent):
        """send した依頼を、本物のスクリプトで登録する"""
        self.write("data/inbox/20261120120000-test.json", sent["request"])
        r = self.run_script("inbox_to_json.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.merge_ok()
        r = self.run_script("inbox_to_json.py", "--finish")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = self.read("data/inbox/results/20261120120000-test.json")
        self.assertEqual(res["status"], "done", res)
        self.assertEqual(res.get("notes") or [], [], res)  # done でも、スキップされた行があれば notes に出る

    def read_notice(self, pg, text):
        pg.fill("#glih-fdd", "20261120")
        pg.check("#glih-fany", force=True)
        pg.wait_for_selector("#glih-f-title")
        pg.click("#glih-rpmd [data-m=schedule]")
        pg.fill("#glih-rpnt", text)
        pg.click("#glih-rpntb")


class TestStartup(HelperCase):
    def test_all_tabs_open_without_js_errors(self):
        pg = self.open()
        for tab in ("logs", "setlist", "albums", "songs", "bulk", "check"):
            pg.click(f"#glih [data-tab={tab}]")
            pg.wait_for_timeout(300)
        pg.click("#glih-setbtn")
        self.assertTrue(pg.locator("#glih-srepo").is_visible())
        self.assertEqual(self.errors, [])

    def test_opened_from_viewer_with_log_id(self):
        pg = self.open("?id=abc123abc123#logs")
        pg.wait_for_selector("#glih-f-title")
        self.assertEqual(pg.input_value("#glih-f-title"), "既存の公演")
        self.assertEqual(self.errors, [])

    def test_opened_from_viewer_with_song(self):
        pg = self.open("?artist=Girls%C2%B2&title=%E3%83%86%E3%82%B9%E3%83%88%E6%9B%B2#songs")
        pg.wait_for_timeout(500)
        self.assertEqual(pg.input_value("#glih-st"), "テスト曲")
        self.assertIn("(1)", pg.inner_text("#glih-svtog"))
        self.assertEqual(self.errors, [])


class TestLogs(HelperCase):
    def test_new_log_is_sent_and_registered(self):
        pg = self.open()
        self.new_log(pg, contents="LIVE", title="テスト公演", venue="テスト会場", groups="G2")
        q = self.issue(pg)
        self.assertEqual(q["template"], "add_logs.yml")
        sent = self.send(pg)
        self.assertEqual(sent["auth"], "Bearer dummy-token")
        self.assertEqual(sent["branch"], "main")
        self.assertRegex(sent["url"], r"/repos/test/repo/contents/data/inbox/\d{14}-[a-z0-9]+\.json$")
        self.assertEqual(sent["request"]["template"], "add_logs.yml")
        self.assertIn("done", self.status(pg))
        self.register(sent)
        row = self.read("data/logs/logs.json")[0]
        self.assertEqual((row["date"], row["time"], row["contents"], row["title"], row["venue"]),
                         ("20261201", "1800", "LIVE", "テスト公演", "テスト会場"))
        self.assertEqual(self.errors, [])

    def test_update_sends_only_changed_fields(self):
        pg = self.open("?id=abc123abc123#logs")
        pg.wait_for_selector("#glih-f-title")
        pg.fill("#glih-f-title", "直した公演")
        pg.fill("#glih-f-venue", "")
        q = self.issue(pg)
        self.assertEqual(q["logid"], "abc123abc123")
        self.assertEqual(q["item_title"], "直した公演")
        self.assertEqual(q["venue"], "!clear")
        self.assertNotIn("url", q)
        self.assertNotIn("tags", q)
        sent = self.send(pg)
        self.write("data/logs/logs.json", [LOG])
        self.register(sent)
        row = self.read("data/logs/logs.json")[0]
        self.assertEqual(row["title"], "直した公演")
        self.assertNotIn("venue", {k: v for k, v in row.items() if v})
        self.assertEqual(row["url"], LOG["url"])

    def test_invalid_date_cannot_be_sent(self):
        pg = self.open()
        self.new_log(pg, title="x")
        self.assertIsNotNone(self.issue(pg))
        pg.fill("#glih-fdd", "20261341")
        self.assertIsNone(self.issue(pg))

    def test_send_without_token(self):
        pg = self.open(token=False)
        self.new_log(pg, title="x")
        pg.locator("#glih-go-find + .sendrow button.go").click()
        pg.wait_for_timeout(300)
        self.assertIn("no token", self.status(pg))
        self.assertEqual(self.sent, [])

    def test_server_error_is_shown(self):
        pg = self.open(result={"status": "error", "errors": ["テストのエラー"]})
        self.new_log(pg, title="x")
        self.send(pg)
        self.assertIn("テストのエラー", self.status(pg))

    def test_rejected_token_is_shown(self):
        pg = self.open(put_status=401)
        self.new_log(pg, title="x")
        self.send(pg)
        self.assertIn("401", self.status(pg))


class TestRepeat(HelperCase):
    def test_interval(self):
        pg = self.open()
        self.new_log(pg, contents="RADIO", title="番組 #1")
        pg.click("#glih-rpmd [data-m=interval]")
        pg.fill("#glih-rpc", "3")
        q = self.issue(pg)
        self.assertEqual([x.split()[0] for x in q["repeat"].split("\n")], ["20261201", "20261208", "20261215"])
        self.register(self.send(pg))
        self.assertEqual(sorted(r["title"] for r in self.read("data/logs/logs.json")),
                         ["番組 #1", "番組 #2", "番組 #3"])

    def test_tour(self):
        pg = self.open()
        self.new_log(pg, contents="LIVE", title="架空ツアー")
        pg.click("#glih-rpmd [data-m=tour]")
        pg.locator("#glih-rptr .rpa").first.fill("東京")
        q = self.issue(pg)
        self.assertEqual(q["repeat"], "20261201 1800 | 架空ツアー 東京 | LIVE")
        self.register(self.send(pg))
        self.assertEqual(self.read("data/logs/logs.json")[0]["title"], "架空ツアー 東京")


class TestNotice(HelperCase):
    """schedule の notice 欄: 貼った告知文から日程を読み取る"""

    def test_download_period(self):
        pg = self.open()
        self.read_notice(pg, WALLPAPER)
        url = "https://girls2-fc.jp/page/wallpaper/1252202976852836352"
        q = self.issue(pg)
        self.assertEqual(q["item_title"], "Girls² 11月スペシャル壁紙プレゼントキャンペーン")
        self.assertEqual(q["url"], url)
        self.assertEqual(q["groups_free"], "G2")
        head = "Girls² 11月スペシャル壁紙プレゼントキャンペーン"
        sp = "11月スペシャル壁紙プレゼントCP"
        self.assertEqual(q["repeat"].split("\n"), [
            f"20261125 2000 | {head} 開始 | FANCLUB | {url} | {sp} 開始",
            f"20261128 2000 | {head} 終了 | CLOSE | {url} | {sp} 終了"])
        pg.locator("#glih-rpntt .chip", has_text="Umbrella").click()
        self.assertIn("Umbrella", self.issue(pg)["tags"])
        self.register(self.send(pg))
        self.assertEqual(sorted((r["date"], r["contents"]) for r in self.read("data/logs/logs.json")),
                         [("20261125", "FANCLUB"), ("20261128", "CLOSE")])
        self.assertEqual(self.errors, [])

    def test_lottery_four_rows(self):
        pg = self.open()
        self.read_notice(pg, LOTTERY)
        rows = [x.split(" | ")[:3] for x in self.issue(pg)["repeat"].split("\n")]
        self.assertEqual([(r[0], r[1].split()[-1]) for r in rows], [
            ("20261205 1800", "受付開始"), ("20261213 2359", "受付締切"),
            ("20261218 1500", "当選発表"), ("20261221 2300", "入金期限")])
        self.assertIn("公演日", pg.inner_text("#glih-rpntm"))  # 入れていない日時として表示

    def test_year_goes_over_new_year(self):
        pg = self.open()
        self.read_notice(pg, "架空キャンペーン\n応募期間\n12/28(月)10:00～\n1/5(火)午後8時まで")
        self.assertEqual([x.split(" | ")[0] for x in self.issue(pg)["repeat"].split("\n")],
                         ["20261228 1000", "20270105 2000"])

    def test_close_only_leaves_start_empty(self):
        pg = self.open()
        self.read_notice(pg, "架空の受付\n締切 12/1(火) 24:00まで")
        self.assertEqual(len(self.issue(pg)["repeat"].split("\n")), 1)
        self.assertTrue(self.issue(pg)["repeat"].startswith("20261201 2359"))
        self.assertIn("24:00", pg.inner_text("#glih-rpntm"))

    def test_wrong_weekday_is_warned(self):
        pg = self.open()
        self.read_notice(pg, "架空の受付\n締切 12/1(月) 18:00")
        self.assertIn("曜日が合いません", pg.inner_text("#glih-rpntm"))

    def test_no_date_changes_nothing(self):
        pg = self.open()
        self.read_notice(pg, "こんにちは\n詳細は後日")
        self.assertIn("読み取れませんでした", pg.inner_text("#glih-rpntm"))
        self.assertEqual(pg.input_value("#glih-f-title"), "")


class TestSongs(HelperCase):
    def open_song(self):
        pg = self.open("#songs")
        pg.fill("#glih-sa", "Girls²")
        pg.fill("#glih-st", "テスト曲")
        pg.wait_for_selector("#glih-svtog button:has-text('(1)')")
        return pg

    def test_added_video_keeps_registered_ones(self):
        pg = self.open_song()
        pg.locator("#glih-svch .chip", has_text="Live").first.click()
        pg.locator("#glih-svrows input[placeholder^=https]").fill("https://youtu.be/bbbbbbbbbbb")
        q = self.issue(pg, "#glih-go-songs")
        self.assertEqual(q["videos"], "MV | https://youtu.be/aaaaaaaaaaa | 公式\nLive | https://youtu.be/bbbbbbbbbbb")
        sent = self.send(pg, "#glih-go-songs")
        self.write("data/songs/songs.json", [SONG])
        self.register(sent)
        self.assertEqual([v["url"][-11:] for v in self.read("data/songs/songs.json")[0]["videos"]],
                         ["aaaaaaaaaaa", "bbbbbbbbbbb"])
        self.assertEqual(self.errors, [])

    def test_removing_last_video_sends_clear(self):
        pg = self.open_song()
        pg.click("#glih-svtog button")
        pg.click("#glih-svreg button[aria-label='remove video']")
        self.assertEqual(self.issue(pg, "#glih-go-songs")["videos"], "!clear")

    def test_empty_registered_url_cannot_be_sent(self):
        pg = self.open_song()
        pg.click("#glih-svtog button")
        pg.click("#glih-svreg button[aria-label='edit video']")
        pg.locator("#glih-svreg input[placeholder^=https]").fill("")
        self.assertIsNone(self.issue(pg, "#glih-go-songs"))

    def test_non_youtube_url_cannot_be_sent(self):
        pg = self.open_song()
        pg.locator("#glih-svch .chip", has_text="MV").first.click()
        pg.locator("#glih-svrows input[placeholder^=https]").fill("https://example.com/v")
        self.assertIsNone(self.issue(pg, "#glih-go-songs"))


class TestSetlist(HelperCase):
    OLD = {"setlistid": "202611011800", "title": "既存の公演", "artist": "Girls²",
           "songs": [{"order": 1, "title": "一曲目", "type": "song"}]}

    def test_new_setlist_needs_artist(self):
        pg = self.open("#setlist")
        pg.fill("#glih-fdd", "20261201")
        pg.fill("#glih-fdt", "1800")
        pg.wait_for_selector("#glih-f-songs", state="attached")
        pg.fill("#glih-f-title", "架空公演")
        for blank in ("", "   "):
            pg.fill("#glih-f-artist", blank)
            self.assertIsNone(self.issue(pg))
            self.assertFalse(pg.locator("#glih-go-find + .sendrow").is_visible())
            self.assertIn("bad", pg.get_attribute("#glih-f-artist", "class"))
        pg.fill("#glih-f-artist", "Girls²")
        self.assertEqual(self.issue(pg)["artist_free"], "Girls²")
        self.assertNotIn("bad", pg.get_attribute("#glih-f-artist", "class"))

    def test_existing_setlist_can_be_updated_without_resending_artist(self):
        pg = self.open("?id=202611011800#setlist", setlists=(self.OLD,))
        pg.wait_for_selector("#glih-f-songs", state="attached")
        pg.fill("#glih-f-title", "直した公演")
        q = self.issue(pg)
        self.assertEqual(q["item_title"], "直した公演")
        self.assertNotIn("artist_free", q)

    def test_new_setlist_is_registered(self):
        pg = self.open("#setlist")
        pg.fill("#glih-fdd", "20261201")
        pg.fill("#glih-fdt", "1800")
        pg.wait_for_selector("#glih-f-songs", state="attached")
        pg.fill("#glih-f-title", "架空公演")
        pg.fill("#glih-f-artist", "Girls²")
        pg.evaluate("""() => { const e = document.querySelector('#glih-f-songs'); e.value = '1: 一曲目\\n2: 二曲目';
            e.dispatchEvent(new Event('input', {bubbles: true})); }""")
        self.assertEqual(self.issue(pg)["template"], "add_setlist.yml")
        self.register(self.send(pg))
        row = self.read("data/setlist/setlist.json")[0]
        self.assertEqual(row["setlistid"], "202612011800")
        self.assertEqual([s["title"] for s in row["songs"]], ["一曲目", "二曲目"])
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
