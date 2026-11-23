"""変換(issue_to_json.py)とマージ(merge_json.py)、helper直送(inbox_to_json.py)の動作テスト。
実行: python -m unittest discover -s tests -v   (リポジトリの直下で)"""
import json
import unittest

from helpers import Repo, body


def logs_body(**over):
    f = {"date": "20261101", "time": "1800", "contents": "LIVE", "title": "テストライブ"}
    f.update(over)
    return body(**f)


class LogsBasics(Repo):
    def test_new_log_with_venue(self):
        self.submit(logs_body(venue="テスト会場", tags="a, b"))
        rows = self.read("data/logs/logs.json")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["date"], r["time"], r["venue"]), ("20261101", "1800", "テスト会場"))
        self.assertEqual(r["tags"], ["a", "b"])  # venue はタグに入れない
        self.assertEqual(list(r).index("venue") < list(r).index("setlistid") if "setlistid" in r else True, True)

    def test_index_contains_venue(self):
        self.submit(logs_body(venue="会場A"))
        idx = self.read("data/logs/logs_index.json")
        self.assertEqual(idx[0].get("venue"), "会場A")

    def test_bad_time_is_reported_and_not_added(self):
        r = self.issue(logs_body(time="18:00"))
        self.assertTrue(self.exists("issue_error.md"))
        self.assertEqual(self.queue_files("logs"), [])

    def test_update_and_clear_venue(self):
        self.submit(logs_body(venue="会場A"))
        logid = self.read("data/logs/logs.json")[0]["logid"]
        self.submit(body(logid=logid, venue="会場B"), 2)
        self.assertEqual(self.read("data/logs/logs.json")[0]["venue"], "会場B")
        self.submit(body(logid=logid, venue="!clear"), 3)
        self.assertNotIn("venue", self.read("data/logs/logs.json")[0])

    def test_delete(self):
        self.submit(logs_body())
        logid = self.read("data/logs/logs.json")[0]["logid"]
        self.submit(body(logid=logid, DELETE="- [X] 削除する"), 2)
        self.assertEqual(self.read("data/logs/logs.json"), [])

    def test_repeat_lines_with_venue_column(self):
        rep = "20261101 1800 | 第1回 | LIVE | | | | | x | 会場A\n20261102 | 第2回"
        self.submit(logs_body(title="ツアー", **{"繰り返し登録 (1行1回)": rep}))
        rows = {r["date"]: r for r in self.read("data/logs/logs.json")}
        self.assertEqual(rows["20261101"].get("venue"), "会場A")
        self.assertIn("x", rows["20261101"].get("tags", []))
        self.assertNotIn("venue", rows["20261102"])

    def test_repeat_display_pc_follows_title(self):
        """繰り返し登録: フォームのdisplay_pcは、行のtitleがフォームのtitleに足した部分を同じように足す(締切・地域名など)。
        行にtitleがなければ #数字 を回ごとに+1。display_spは行の指定を使う。"""
        rep = "20261101 1800 | ツアー #1 | LIVE\n20261102 1800 | ツアー #1 東京 | LIVE | | PC専用なし\n20261103 | | LIVE"
        self.submit(logs_body(title="ツアー #1", display_pc="ツアー PC #1", **{"繰り返し登録 (1行1回)": rep}))
        rows = {r["date"]: r for r in self.read("data/logs/logs.json")}
        self.assertEqual(rows["20261101"]["display_pc"], "ツアー PC #1")
        self.assertEqual(rows["20261102"]["display_pc"], "ツアー PC #1 東京")
        self.assertEqual(rows["20261102"]["display_sp"], "PC専用なし")
        self.assertEqual(rows["20261103"]["display_pc"], "ツアー PC #3")  # 3回目 = #1 + 2

    def test_merge_is_idempotent(self):
        self.submit(logs_body())
        a = self.read("data/manifest.json")
        self.merge_ok()
        self.assertEqual(a, self.read("data/manifest.json"))  # 変化がなければマニフェストも変わらない


class SetlistAndVenueSync(Repo):
    SID = "202611011800"

    def setlist(self, **over):
        f = {"setlistid": self.SID, "artist / 自由入力": "Girls2", "title": "ライブ"}
        f.update(over)
        return body(**f)

    def patch(self, text):
        return body(setlistid=self.SID, **{"artist / 自由入力": "", "曲目の個別変更 (1行1操作)": text})

    def sl(self):
        rows = self.read("data/setlist/setlist.json")
        return next((r for r in rows if r["setlistid"] == self.SID), None)

    def test_unordered_songs_have_no_order_and_sort_last(self):
        self.submit(self.setlist(**{"曲目 (1行1曲)": "A曲\n-: B曲\n1か: 無視"}))
        songs = self.sl()["songs"]
        self.assertEqual([s["title"] for s in songs][:1], ["A曲"])
        self.assertEqual(songs[0]["order"], 1)
        self.assertTrue(all("order" not in s for s in songs[1:]))
        self.assertEqual(songs[1]["title"], "B曲")

    def test_unordered_songs_patch(self):
        self.submit(self.setlist(**{"曲目 (1行1曲)": "A曲\nB曲"}))
        self.submit(self.patch("+?: C曲"), 2)
        songs = self.sl()["songs"]
        self.assertEqual([s["title"] for s in songs], ["A曲", "B曲", "C曲"])
        self.assertNotIn("order", songs[2])
        self.submit(self.patch("-?: C曲"), 3)
        self.assertEqual([s["title"] for s in self.sl()["songs"]], ["A曲", "B曲"])

    def test_logs_venue_overwrites_setlist_venue(self):
        self.submit(self.setlist(venue="古い会場"))
        self.submit(logs_body(venue="新会場", setlistid=self.SID), 2)
        self.assertEqual(self.sl()["venue"], "新会場")
        self.assertEqual(self.read("data/setlist/setlist_index.json")[0]["venue"], "新会場")

    def test_clearing_logs_venue_clears_setlist_venue(self):
        self.submit(self.setlist())
        self.submit(logs_body(venue="会場", setlistid=self.SID), 2)
        logid = self.read("data/logs/logs.json")[0]["logid"]
        self.submit(body(logid=logid, venue="!clear"), 3)
        self.assertNotIn("venue", self.sl())

    def test_new_setlist_inherits_logs_venue(self):
        self.submit(logs_body(venue="会場", setlistid=self.SID))
        self.submit(self.setlist(), 2)
        self.assertEqual(self.sl()["venue"], "会場")

    def test_tags_never_become_venue(self):
        self.submit(self.setlist())
        self.submit(logs_body(tags="タグ会場", setlistid=self.SID), 2)
        self.assertNotIn("venue", self.sl())


class ErrorHandling(Repo):
    def test_broken_json_stays_in_queue_with_detail(self):
        self.write("data/logs/queue/bad.json", '[{"date": "20261101",\n "title": }]')
        r = self.merge()
        self.assertEqual(r.returncode, 1)  # エラー行があれば失敗にする
        self.assertTrue(self.exists("data/logs/queue/bad.json"))  # 読めないファイルは残す
        rep = self.read("queue_report.json")
        err = [x for x in rep if x["level"] == "error"]
        self.assertTrue(err)
        self.assertIn("bad.json", err[0]["file"])
        self.assertIn("2", err[0]["reason"])  # 行番号が入る
        self.assertTrue(self.exists("queue_report.md"))

    def test_good_files_still_processed_when_another_is_broken(self):
        self.write("data/logs/queue/bad.json", "{")
        self.write("data/logs/queue/ok.json", [{"date": "20261101", "time": "1800", "contents": "LIVE", "title": "OK"}])
        r = self.merge()
        self.assertEqual(r.returncode, 1)
        self.assertEqual([x["title"] for x in self.read("data/logs/logs.json")], ["OK"])
        self.assertFalse(self.exists("data/logs/queue/ok.json"))


class Inbox(Repo):
    def request(self, rid, template, params):
        self.write(f"data/inbox/{rid}.json", {"template": template, "params": params, "created": "2026-11-20T00:00:00Z"})

    def run_flow(self):
        r = self.run_script("inbox_to_json.py"); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.merge_ok()
        r = self.run_script("inbox_to_json.py", "--finish"); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_new_log_via_inbox(self):
        self.request("20261120000000-abcd", "add_logs.yml",
                     {"date": "20261101", "time": "1800", "contents": "LIVE", "item_title": "直送", "venue": "会場"})
        self.run_flow()
        rows = self.read("data/logs/logs.json")
        self.assertEqual((rows[0]["title"], rows[0]["venue"]), ("直送", "会場"))
        res = self.read("data/inbox/results/20261120000000-abcd.json")
        self.assertEqual(res["status"], "done")
        self.assertFalse(self.exists("data/inbox/20261120000000-abcd.json"))  # 依頼ファイルは消える

    def test_invalid_input_reports_error(self):
        self.request("20261120000001-efgh", "add_logs.yml", {"date": "20261101", "time": "bad", "contents": "LIVE", "item_title": "x"})
        r = self.run_script("inbox_to_json.py"); self.assertEqual(r.returncode, 0)
        res = self.read("data/inbox/results/20261120000001-efgh.json")
        self.assertEqual(res["status"], "error")
        self.assertTrue(res["errors"])

    def test_unknown_template_rejected(self):
        self.request("20261120000002-ijkl", "../evil.yml", {})
        self.run_script("inbox_to_json.py")
        res = self.read("data/inbox/results/20261120000002-ijkl.json")
        self.assertEqual(res["status"], "error")

    def test_two_requests_same_second_do_not_overwrite(self):
        for rid in ("20261120000003-aaaa", "20261120000003-bbbb"):
            self.request(rid, "add_logs.yml", {"date": "20261101", "time": "1800", "contents": "LIVE", "item_title": rid})
        self.run_flow()
        self.assertEqual(len(self.read("data/logs/logs.json")), 2)


if __name__ == "__main__":
    unittest.main()
