"""scripts/check_repo.py 自体のテスト(検査が本当に問題を見つけられるか)"""
import os
import sys
import unittest

from helpers import Repo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import check_repo as cr  # noqa: E402


class CheckRepo(Repo):
    def test_clean_repo_has_no_problems(self):
        self.assertEqual(cr.check_json(self.dir), [])
        self.assertEqual(cr.check_forms(self.dir), [])
        self.assertEqual(cr.check_workflows(self.dir), [])

    def test_broken_json_found_but_queue_ignored(self):
        self.write("data/logs/logs.json", "{")
        self.write("data/logs/queue/x.json", "{")
        probs = cr.check_json(self.dir)
        self.assertEqual(len(probs), 1)
        self.assertIn("data/logs/logs.json", probs[0])

    def test_non_ascii_in_script_found(self):
        html = "<p>日本語OK</p><script>\nvar a = 1;\nvar b = '日本';\n</script>"
        self.assertEqual(cr.non_ascii_in_scripts(html)[0][0], 3)
        self.assertEqual(cr.non_ascii_in_scripts("<script>var a='\\u65e5';</script><p>日</p>"), [])

    def test_form_label_mismatch_found(self):
        self.edit(".github/ISSUE_TEMPLATE/add_logs.yml", 'label: "venue"', 'label: "venueX"')
        self.assertTrue(any("venueX" in x for x in cr.check_forms(self.dir)))

    def test_clear_option_mismatch_found(self):
        self.edit(".github/ISSUE_TEMPLATE/add_logs.yml", '        - label: "venue"\n', "")
        self.assertTrue(any("値の削除" in x and "venue" in x for x in cr.check_forms(self.dir)))

    def test_schema_problems_found(self):
        import json
        self.assertEqual(cr.check_schema(self.dir), [])
        sch = self.read("scripts/schema.json")
        sch["logs"]["clearable"].append("nofield")
        self.write("scripts/schema.json", sch)
        self.assertTrue(any("nofield" in x for x in cr.check_schema(self.dir)))

    def test_helper_missing_field_found(self):
        self.write("issue_helper_blogger.html", "<script>var DEFS = [{ k: 'date' }];</script>")
        probs = cr.check_schema(self.dir)
        self.assertTrue(any("venue" in x for x in probs))

    def test_duplicate_queue_workflow_found(self):
        self.write(".github/workflows/merge_queue.yml", "steps:\n  - run: python scripts/merge_json.py\n")
        self.write(".github/workflows/process_queue.yml", "steps:\n  - run: python scripts/merge_json.py\n")
        self.write(".github/workflows/rebuild_index.yml", "steps:\n  - run: python scripts/merge_json.py --rebuild-index\n")
        self.write(".github/workflows/update_manifest.yml", "steps:\n  - run: python scripts/merge_json.py --rebuild-manifest\n")
        probs = cr.check_workflows(self.dir)
        self.assertEqual(len(probs), 1)
        self.assertIn("merge_queue.yml", probs[0])


if __name__ == "__main__":
    unittest.main()
