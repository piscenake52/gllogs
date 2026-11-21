"""ビューア(index.html)の自動テスト。Playwright(Chromium)で実際に開いて確認する。

準備:  pip install playwright && playwright install chromium
       npm install axe-core@4   (アクセシビリティ検査用。無ければその1項目だけ飛ばす)
実行:  python -m unittest tests.test_viewer -v
index.html の場所は環境変数 INDEX_HTML で指定(既定: リポジトリ直下の index.html)。
Playwright か index.html が無い環境では全体を skip する(既存の CI を壊さない)。
通信(GitHub API / manifest / logs.json)はすべてモック。日付は 2026-11-20 12:00(JST)に固定する。
"""
import json
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = Path(os.environ.get("INDEX_HTML") or ROOT / "index.html")

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

NOW = "2026-11-20T12:00:00+09:00"
TODAY = "20261120"


def _find_axe():
    for p in [os.environ.get("AXE_JS"), ROOT / "node_modules/axe-core/axe.min.js",
              Path.cwd() / "node_modules/axe-core/axe.min.js", "/tmp/sample/node_modules/axe-core/axe.min.js"]:
        if p and Path(p).exists():
            return Path(p)
    return None


def row(i, time, contents, title, date=TODAY, **kw):
    r = {"logid": "id%03d" % i, "date": date, "time": time, "contents": contents,
         "title": title, "groups": ["G2", "L2"]}
    r.update(kw)
    return r


def bulk(n, date="20261101"):
    return [row(1000 + i, "", "GTUBE", "bulk row %03d" % i, date=date) for i in range(n)]


SETLISTS = [{"setlistid": "S1", "title": "T", "songs": [{"order": 1, "title": "A"}]}]


@unittest.skipIf(sync_playwright is None, "playwright が無いので skip")
@unittest.skipUnless(INDEX.exists(), "index.html が見つからないので skip (INDEX_HTML で指定)")
class ViewerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def open(self, logs, mode="ok", ls=None, viewport=(390, 900), wait=True, route_state=None):
        """index.html を開く。mode: ok / offline / 404 / 403 / 500 / badjson。
        route_state(dict)の 'mode' を後から書き換えると、以降の通信の挙動が変わる(再試行のテスト用)。"""
        ctx = self.browser.new_context(viewport={"width": viewport[0], "height": viewport[1]},
                                       timezone_id="Asia/Tokyo", locale="ja-JP")
        self.addCleanup(ctx.close)
        init = {"gl_log_today_mode": "false"}
        init.update(ls or {})
        ctx.add_init_script("".join("try{localStorage.setItem(%s,%s)}catch(e){};" % (json.dumps(k), json.dumps(v))
                                    for k, v in init.items()))
        pg = ctx.new_page()
        pg.clock.set_fixed_time(NOW)
        self.errors = []
        pg.on("pageerror", lambda e: self.errors.append(str(e)))
        st = route_state if route_state is not None else {}
        st.setdefault("mode", mode)
        payload = json.dumps(logs, ensure_ascii=False)

        def handle(r):
            u = r.request.url
            if not any(x in u for x in ("logs.json", "manifest.json", "api.github.com", "githubusercontent",
                                        "jsdelivr", "setlist", "songs", "albums")):
                return r.continue_()
            m = st["mode"]
            if m == "offline":
                return r.abort()
            if "manifest.json" in u:
                return r.fulfill(status=404, body="")
            if m in ("404", "403", "500") and "api.github.com" not in u:
                return r.fulfill(status=int(m), body="")
            if "api.github.com" in u:
                return r.fulfill(status=200, content_type="application/json", body='[{"sha":"v1"}]')
            if "logs.json" in u:
                body = "{not json" if m == "badjson" else payload
                return r.fulfill(status=200, content_type="application/json", body=body)
            body = json.dumps(SETLISTS) if "setlist" in u else "[]"
            return r.fulfill(status=200, content_type="application/json", body=body)

        pg.route("**/*", handle)
        pg.goto(INDEX.as_uri())
        if wait:
            pg.wait_for_selector(".item", timeout=10000)
            pg.wait_for_timeout(600)
        return pg

    def chips(self, pg):
        return pg.evaluate("""[...document.querySelectorAll('.item')].map(w => [
            (w.querySelector('.item-title') || {}).textContent || '',
            [...w.querySelectorAll('.tag-chip')].map(c => (c.dataset.kind || '') + ':' + c.textContent)])""")


class TestStartup(ViewerCase):
    def test_renders_without_js_errors(self):
        pg = self.open([row(1, "1000", "LIVE", "Girls2 Live")])
        self.assertEqual(pg.locator(".item").count(), 1)
        self.assertEqual(self.errors, [])
        self.assertFalse(pg.locator("#loadError").is_visible())

    def test_paging_40_per_page(self):
        pg = self.open(bulk(100))
        self.assertEqual(pg.locator(".item").count(), 40)
        pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        pg.wait_for_timeout(800)
        self.assertGreater(pg.locator(".item").count(), 40)

    def test_two_tier_layout_kept(self):
        """日時段+タイトル段の2段表示が崩れていない(タイトルが日時と別の行にある)。"""
        pg = self.open([row(1, "1000", "LIVE", "Girls2 Live 東京公演", venue="東京ガーデンシアター")],
                       viewport=(390, 800))
        box = pg.evaluate("""(() => { const w = document.querySelector('.item');
            const t = w.querySelector('.item-title').getBoundingClientRect();
            const d = w.getBoundingClientRect();
            return {tw: t.width, ww: d.width, h: d.height}; })()""")
        self.assertGreater(box["tw"], 0)
        self.assertLessEqual(box["tw"], box["ww"] + 1)
        self.assertLess(box["h"], 160)


class TestSearch(ViewerCase):
    LOGS = [row(1, "1000", "LIVE", "LIVE TOUR 愛知公演", date="20261101"),
            row(2, "1100", "LIVE", "LIVE TOUR 東京公演", date="20261102"),
            row(3, "1200", "EVENT", "お見送り会 愛知", date="20261103")]

    def titles(self, pg):
        return pg.evaluate("[...document.querySelectorAll('.item .item-title')].map(e => e.textContent)")

    def test_whitespace_split_is_and(self):
        pg = self.open(self.LOGS)
        pg.fill("#searchInput", "LIVE 愛知")
        pg.wait_for_timeout(800)
        t = self.titles(pg)
        self.assertEqual(len(t), 1)
        self.assertIn("愛知", t[0])

    def test_case_insensitive(self):
        pg = self.open(self.LOGS)
        pg.fill("#searchInput", "live tour")
        pg.wait_for_timeout(800)
        self.assertEqual(len(self.titles(pg)), 2)

    def test_tag_chip_click_searches_tag(self):
        pg = self.open([row(1, "1000", "EVENT", "お見送り会 in 名古屋", date="20261101", tags=["お見送り会"]),
                        row(2, "1100", "EVENT", "別の予定", date="20261102")],
                       ls={"gl_log_tag_mode": "true"})
        pg.click(".tag-chip")
        pg.wait_for_timeout(800)
        self.assertEqual(pg.input_value("#searchInput"), "お見送り会")
        self.assertEqual(len(self.titles(pg)), 1)


class TestTagChips(ViewerCase):
    TAG = {"gl_log_tag_mode": "true"}
    TODAY_ON = {"gl_log_tag_mode": "true", "gl_log_today_mode": "true"}

    def kinds(self, pg):
        return {t[:12]: c for t, c in self.chips(pg)}

    def test_kinds_are_distinguishable(self):
        logs = [
            row(1, "0900", "LIVE", "Girls2 Live", venue="東京ガーデンシアター", date="20261101"),
            row(2, "1000", "EVENT", "お見送り会", tags=["お見送り会"], date="20261102"),
            row(3, "1100", "GTUBE", "SNS付き", date="20261103",
                sns=[{"type": "x", "urls": [{"url": "https://x.com/a/status/1", "tags": ["挨拶"]}]}]),
        ]
        pg = self.open(logs, ls=self.TAG)
        got = {t: c for t, c in self.chips(pg)}
        self.assertTrue(any(x.startswith("venue:") for x in got["Girls2 Live"]), got)
        self.assertTrue(any(x.startswith("tag:") for x in got["お見送り会"]), got)
        self.assertTrue(any(x.startswith("sns:") for x in got["SNS付き"]), got)

    def test_chip_css_differs_by_kind(self):
        logs = [row(1, "0900", "LIVE", "Girls2 Live", venue="東京ガーデンシアター", date="20261101"),
                row(2, "1000", "EVENT", "お見送り会", tags=["お見送り会"], date="20261102")]
        pg = self.open(logs, ls=self.TAG)
        style = pg.evaluate("""(() => { const g = k => { const c = document.querySelector('.tag-chip[data-kind=' + k + ']');
            if (!c) return null; const s = getComputedStyle(c); return s.backgroundColor + '|' + s.borderStyle; };
            return [g('tag'), g('venue')]; })()""")
        self.assertIsNotNone(style[0])
        self.assertIsNotNone(style[1])
        self.assertNotEqual(style[0], style[1])

    def auto(self, title, contents="GTUBE", **kw):
        """TODAY ON で、1行だけの当日データを開き、その行の抽出タグ(auto)を返す。"""
        logs = [row(1, "1000", contents, title, **kw),
                row(2, "1100", "EVENT", "辞書用", tags=["お見送り会", "KAZ", "ラキラキLOVE!", "tiktok更新",
                                                       "Seven Blooms Beyond", "Beyond", "Halloween",
                                                       "Girls²", "Lucky²", "ab", "がるらじ"])]
        # 辞書用の行は TODAY ON でも当日に出るが、tags があるので抽出対象外。対象行だけを見る
        pg = self.open(logs, ls=self.TODAY_ON)
        for t, c in self.chips(pg):
            if t.startswith(title[:10]):
                return [x.split(":", 1)[1] for x in c if x.startswith("auto:")]
        self.fail("対象行が見つからない: " + title)

    def test_auto_extracts_existing_tag_from_title(self):
        self.assertEqual(self.auto("お見送り会 in 名古屋"), ["お見送り会"])

    def test_auto_prefers_longer_tag(self):
        self.assertEqual(self.auto("Seven Blooms Beyond 先行受付 Beyond"), ["Seven Blooms Beyond"])

    def test_auto_ascii_needs_word_boundary(self):
        self.assertEqual(self.auto("okazaki で食事", "DIARY"), ["日記更新"])  # KAZ は語の途中 -> 補完のみ
        self.assertEqual(self.auto("今日は KAZ と散歩", "DIARY"), ["KAZ"])
        self.assertEqual(self.auto("HappyHalloween 回", "EVENT"), [])  # Halloween は語の途中 -> 出ない

    def test_auto_skips_group_hidden_and_short_tags(self):
        self.assertEqual(self.auto("Girls² バラエティ出演", "EVENT"), [])
        self.assertEqual(self.auto("tiktok更新 のお知らせ", "EVENT"), [])
        self.assertEqual(self.auto("ab テスト", "EVENT"), [])

    def test_auto_fullwidth_not_matched(self):
        self.assertEqual(self.auto("ラキラキLOVE！リリース", "DIARY"), ["日記更新"])  # 全角！は一致しない

    def test_auto_fallback_by_contents(self):
        self.assertEqual(self.auto("ただの日記", "DIARY"), ["日記更新"])
        self.assertEqual(self.auto("ただの動画", "GTUBE"), ["Gtube"])
        self.assertEqual(self.auto("ただの放送", "GLRADIO"), ["がるらじ"])

    def test_auto_only_in_today_mode(self):
        logs = [row(1, "1000", "GTUBE", "お見送り会 in 名古屋", date="20261101"),
                row(2, "1100", "EVENT", "辞書用", tags=["お見送り会"], date="20261102")]
        pg = self.open(logs, ls=self.TAG)  # TODAY OFF
        self.assertFalse(any(x.startswith("auto:") for _, c in self.chips(pg) for x in c))

    def test_auto_skipped_when_row_has_tags_or_venue(self):
        logs = [row(1, "1000", "LIVE", "お見送り会 Live", venue="東京ガーデンシアター"),
                row(2, "1100", "EVENT", "お見送り会 別", tags=["お見送り会"])]
        pg = self.open(logs, ls=self.TODAY_ON)
        self.assertFalse(any(x.startswith("auto:") for _, c in self.chips(pg) for x in c))

    def test_auto_chip_click_searches(self):
        logs = [row(1, "1000", "GTUBE", "お見送り会 in 名古屋"),
                row(2, "1100", "EVENT", "辞書用", tags=["お見送り会"], date="20261119")]
        pg = self.open(logs, ls=self.TODAY_ON)
        pg.click(".tag-chip[data-kind=auto]")
        pg.wait_for_timeout(800)
        self.assertEqual(pg.input_value("#searchInput"), "お見送り会")


class TestRefRows(ViewerCase):
    """ANNIVERSARY の参照行(ref)は、参照元のvenue・tags・sns・抽出タグを同じ種別のチップで出す。"""
    TODAY_ON = {"gl_log_tag_mode": "true", "gl_log_today_mode": "true"}

    def ref_chips(self, srcs, ref_extra=None, ls=None):
        logs = list(srcs) + [row(900, "", "ANNIVERSARY", None, date="20251120", ref=srcs[0]["logid"], **(ref_extra or {}))]
        logs[-1].pop("title", None)
        logs += [row(901, "1100", "EVENT", "辞書用", tags=["お見送り会"], date="20261119")]
        pg = self.open(logs, ls=ls or self.TODAY_ON)
        res = pg.evaluate("""[...document.querySelectorAll('.item')].map(w => [w.querySelector('.item-title').textContent,
            [...w.querySelectorAll('.tag-chip')].map(c => c.dataset.kind + ':' + c.textContent)])""")
        return [c for t, c in res if "記念日" in t], pg

    def src(self, title, contents="LIVE", **kw):
        kw.setdefault("date", "20250101")
        return row(800, "1000", contents, title, **kw)

    def test_venue_inherited_as_venue_chip(self):
        got, _ = self.ref_chips([self.src("Girls2 Live", venue="東京ガーデンシアター")])
        self.assertEqual(got, [["venue:東京ガーデンシアター"]])

    def test_tags_inherited(self):
        got, _ = self.ref_chips([self.src("Girls2 Live", tags=["お見送り会"])])
        self.assertEqual(got, [["tag:お見送り会"]])

    def test_sns_tags_inherited(self):
        sns = [{"type": "x", "urls": [{"url": "https://x.com/a/status/1", "tags": ["挨拶"]}]}]
        got, _ = self.ref_chips([self.src("Girls2 Live", sns=sns)])
        self.assertEqual(got, [["sns:挨拶"]])

    def test_auto_tag_from_source_title(self):
        got, _ = self.ref_chips([self.src("お見送り会 in 名古屋", "EVENT")])
        self.assertEqual(got, [["auto:お見送り会"]])

    def test_auto_tag_fallback_uses_source_contents(self):
        got, _ = self.ref_chips([self.src("ただの日記", "DIARY")])
        self.assertEqual(got, [["auto:日記更新"]])

    def test_no_chip_when_source_has_nothing(self):
        got, _ = self.ref_chips([self.src("ただの予定", "EVENT")])
        self.assertEqual(got, [[]])

    def test_own_venue_wins_and_map_not_inherited(self):
        got, pg = self.ref_chips([self.src("Girls2 Live", venue="東京ガーデンシアター")],
                                 ref_extra={"venue": "横浜アリーナ"})
        self.assertEqual(got, [["venue:横浜アリーナ"]])
        _, pg = self.ref_chips([self.src("Girls2 Live", venue="東京ガーデンシアター")],
                               ls=dict(self.TODAY_ON, gl_log_map_mode="true"))
        # 参照元にmapが無くvenueだけの場合、参照行に地図ピンは出さない(venueそのものは引き継がない)
        self.assertEqual(pg.evaluate("[...document.querySelectorAll('.item')].filter(w => w.textContent.includes('記念日')).map(w => w.querySelectorAll('a.map-pin').length)"), [0])

    def test_venue_chip_click_searches_venue(self):
        """会場チップを押すと会場名で検索され、参照元の行が見つかる(ANNIVERSARYの登録年の行は検索結果に出さない仕様)。"""
        _, pg = self.ref_chips([self.src("Girls2 Live", venue="東京ガーデンシアター")])
        pg.click(".tag-chip[data-kind=venue]")
        pg.wait_for_timeout(800)
        self.assertEqual(pg.input_value("#searchInput"), "東京ガーデンシアター")
        self.assertIn("Girls2 Live", pg.inner_text("#daySlideArea"))


class TestLoadFailure(ViewerCase):
    LOGS = [row(1, "1000", "LIVE", "Girls2 Live", date="20261101")]

    def fail_msg(self, mode):
        pg = self.open(self.LOGS, mode=mode, wait=False)
        pg.wait_for_selector("#loadError", state="visible", timeout=15000)
        return pg, pg.inner_text("#loadErrorMsg").strip()

    def test_each_failure_shows_a_distinct_message(self):
        msgs = {}
        for mode in ("offline", "404", "403", "500", "badjson"):
            pg, msg = self.fail_msg(mode)
            self.assertTrue(msg, mode + " の原因表示が空")
            self.assertTrue(pg.locator("#retryBtn").is_visible(), mode)
            msgs[mode] = msg
            pg.context.close()
        self.assertEqual(len(set(msgs.values())), len(msgs), msgs)  # 原因ごとに文言が違う

    def test_no_technical_code_shown(self):
        _, msg = self.fail_msg("500")
        self.assertNotRegex(msg, r"\b(HTTP|Error|500|TypeError|SyntaxError)\b")

    def test_manual_retry_recovers(self):
        st = {}
        pg = self.open(self.LOGS, mode="offline", wait=False, route_state=st)
        pg.wait_for_selector("#loadError", state="visible", timeout=15000)
        st["mode"] = "ok"
        pg.click("#retryBtn")
        pg.wait_for_selector(".item", timeout=15000)
        self.assertFalse(pg.locator("#loadError").is_visible())

    def test_auto_retry_recovers(self):
        st = {}
        pg = self.open(self.LOGS, mode="offline", wait=False, route_state=st)
        pg.wait_for_selector("#loadError", state="visible", timeout=15000)
        st["mode"] = "ok"
        pg.wait_for_selector(".item", timeout=10000)  # 最初の自動再試行は3秒後
        self.assertFalse(pg.locator("#loadError").is_visible())

    def test_online_event_retries_after_giving_up(self):
        st = {}
        pg = self.open(self.LOGS, mode="offline", wait=False, route_state=st)
        pg.wait_for_selector("#loadError", state="visible", timeout=15000)
        pg.wait_for_timeout(33000)  # 3+8+20秒=3回の自動再試行を使い切る
        st["mode"] = "ok"
        pg.evaluate("window.dispatchEvent(new Event('online'))")
        pg.wait_for_selector(".item", timeout=10000)

    def test_stale_notice_when_cache_exists(self):
        st = {}
        pg = self.open(self.LOGS, mode="ok", route_state=st)
        self.assertFalse(pg.locator("#staleNotice").is_visible())
        st["mode"] = "offline"
        pg.evaluate("localStorage.setItem('gl_log_checked_at','0')")
        pg.reload()
        pg.wait_for_selector(".item", timeout=10000)
        pg.wait_for_selector("#staleNotice", state="visible", timeout=15000)  # 保存済みデータで表示+通知
        self.assertFalse(pg.locator("#loadError").is_visible())
        st["mode"] = "ok"
        pg.click("#staleRetryBtn")
        pg.wait_for_selector("#staleNotice", state="hidden", timeout=15000)


class TestPasteSafety(unittest.TestCase):
    """Blogger に貼るときの文字化け・構文エラー対策(静的チェック。ブラウザ不要)。"""

    @classmethod
    def setUpClass(cls):
        if not INDEX.exists():
            raise unittest.SkipTest("index.html が見つからない")
        cls.src = INDEX.read_text(encoding="utf-8")

    def test_script_syntax_via_node(self):
        import shutil
        import subprocess
        import tempfile
        node = shutil.which("node")
        if not node:
            self.skipTest("node が無い")
        scripts = re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*ld\+json)[^>]*>(.*?)</script>", self.src, re.S)
        self.assertTrue(scripts)
        for i, s in enumerate(scripts):
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
                f.write(s)
            r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
            os.unlink(f.name)
            self.assertEqual(r.returncode, 0, "script %d: %s" % (i, r.stderr[:300]))

    def test_html_body_raw_non_ascii_does_not_grow(self):
        """HTML本文(<script>/<style>/コメント以外)の生の日本語・記号は、ヘルプ欄など既存分だけ許容し、増えたことを検知する。
        新しい表示文言は &#NNN; で書く(Blogger への貼り付けで化けない)。"""
        body = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", self.src, flags=re.S)
        lines = {ln.strip() for ln in body.splitlines() if re.search(r"[^\x00-\x7f]", ln)}
        self.assertLessEqual(len(lines), BASELINE_RAW_NONASCII_HTML_LINES,
                             "HTML本文の生の非ASCII行が増えている: %d行 (基準 %d)" % (len(lines), BASELINE_RAW_NONASCII_HTML_LINES))

    def test_js_string_literals_have_no_raw_japanese_ui_text(self):
        """JS内のユーザー向け文字列は \\uXXXX で書く(貼り付け時の文字化け対策)。
        ここでは、ひらがな・カタカナ・漢字が JS の文字列リテラルに直書きされていないことを見る。"""
        scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", self.src, re.S)
        offenders = []
        jp = re.compile(r"[぀-ヿ一-鿿]")
        for s in scripts:
            for n, line in enumerate(s.splitlines(), 1):
                code = re.sub(r"//.*$|/\*.*?\*/", "", line)  # コメントは除く
                if jp.search(code):
                    offenders.append((n, line.strip()[:80]))
        # 既存の直書き(歴史的経緯)は許容し、増えたことだけを検知する。基準値は BASELINE_RAW_JP_LINES
        self.assertLessEqual(len(offenders), BASELINE_RAW_JP_LINES,
                             "JS内の日本語直書きが増えている: %d行 (基準 %d)\n%s"
                             % (len(offenders), BASELINE_RAW_JP_LINES, offenders[BASELINE_RAW_JP_LINES:][:5]))


BASELINE_RAW_NONASCII_HTML_LINES = 36  # 現状(ヘルプ欄など)。増えたときだけ検知する
BASELINE_RAW_JP_LINES = 23  # 現状の直書き(メンバー名の辞書など、データ)。増えたときだけ検知する


@unittest.skipIf(sync_playwright is None, "playwright が無いので skip")
@unittest.skipUnless(INDEX.exists(), "index.html が見つからない")
class TestAccessibility(ViewerCase):
    KNOWN = {"color-contrast", "scrollable-region-focusable"}  # 意図的に残している2種

    def test_axe_only_known_violations(self):
        axe = _find_axe()
        if not axe:
            self.skipTest("axe-core が無い (npm install axe-core@4)")
        pg = self.open([row(1, "1000", "LIVE", "Girls2 Live", venue="東京", date="20261101",
                            sns=[{"type": "x", "urls": [{"url": "https://x.com/a/status/1", "tags": ["挨拶"]}]}])],
                       ls={"gl_log_tag_mode": "true", "gl_log_map_mode": "true"})
        pg.evaluate(axe.read_text(encoding="utf-8"))
        ids = pg.evaluate("axe.run(document, {resultTypes: ['violations']}).then(r => r.violations.map(v => v.id))")
        self.assertEqual(set(ids) - self.KNOWN, set(), "新しいアクセシビリティ違反: %s" % ids)

    def test_landmarks_and_viewport(self):
        pg = self.open([row(1, "1000", "LIVE", "Girls2 Live", date="20261101")])
        self.assertEqual(pg.locator("[role=banner]").count(), 1)
        self.assertEqual(pg.locator("[role=main]").count(), 1)
        vp = pg.evaluate("document.querySelector('meta[name=viewport]').content")
        self.assertNotIn("user-scalable=no", vp)
        self.assertNotIn("maximum-scale", vp)

    def test_icon_buttons_have_labels(self):
        pg = self.open([row(1, "1000", "LIVE", "Girls2 Live", date="20261101")])
        for i in ("mapToggleBtn", "setlistIconToggleBtn", "linkToggleBtn", "songToggleBtn"):
            self.assertTrue(pg.get_attribute("#" + i, "aria-label"), i)


if __name__ == "__main__":
    unittest.main()
