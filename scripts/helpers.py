"""テスト用の道具。一時フォルダにリポジトリと同じ並び(scripts/, .github/ISSUE_TEMPLATE/, data/)を作り、本物のスクリプトを実行する。"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # リポジトリの直下
SCRIPTS = os.path.join(ROOT, "scripts")
TEMPLATES = os.path.join(ROOT, ".github", "ISSUE_TEMPLATE")
TARGETS = ("logs", "setlist", "songs", "albums")


def body(**fields):
    """Issueフォームの本文(### 見出し + 値)を作る。fields は {見出し: 値}。空の値は '_No response_' にする(GitHubと同じ)"""
    out = []
    for label, val in fields.items():
        out.append(f"### {label}\n\n{val if val != '' else '_No response_'}\n")
    return "\n".join(out)


class Repo(unittest.TestCase):
    """1テストごとに空のデータを持つ作業フォルダを作る"""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="gllogs_test_")
        shutil.copytree(SCRIPTS, os.path.join(self.dir, "scripts"), ignore=shutil.ignore_patterns("__pycache__"))
        if os.path.isdir(TEMPLATES):
            shutil.copytree(TEMPLATES, os.path.join(self.dir, ".github", "ISSUE_TEMPLATE"))
        for t in TARGETS:
            os.makedirs(os.path.join(self.dir, "data", t, "queue"))
            self.write(f"data/{t}/{t}.json", [])
        os.makedirs(os.path.join(self.dir, "data", "inbox"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    # --- ファイル ---
    def path(self, rel):
        return os.path.join(self.dir, rel)

    def write(self, rel, data):
        p = self.path(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            if isinstance(data, str):
                f.write(data)
            else:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def read(self, rel):
        with open(self.path(rel), "r", encoding="utf-8") as f:
            return json.load(f)

    def edit(self, rel, old, new):
        """ファイル内の文字列を1か所だけ置き換える(置き換え対象がなければテストの書き間違いなので失敗にする)"""
        with open(self.path(rel), "r", encoding="utf-8") as f:
            s = f.read()
        self.assertIn(old, s)
        with open(self.path(rel), "w", encoding="utf-8") as f:
            f.write(s.replace(old, new, 1))

    def exists(self, rel):
        return os.path.exists(self.path(rel))

    def queue_files(self, target):
        return sorted(glob.glob(self.path(f"data/{target}/queue/*.json")))

    # --- スクリプト実行 ---
    def run_script(self, name, *args, env=None):
        e = dict(os.environ)
        e.update(env or {})
        return subprocess.run([sys.executable, os.path.join(self.dir, "scripts", name), *args],
                              cwd=self.dir, env=e, capture_output=True, text=True)

    def issue(self, text, number="1"):
        """Issue本文を issue_to_json.py に渡す(Actionsの auto_merge.yml と同じ)"""
        r = self.run_script("issue_to_json.py", env={"ISSUE_BODY": text, "ISSUE_NUMBER": str(number)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def merge(self):
        return self.run_script("merge_json.py")

    def merge_ok(self):
        r = self.merge()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def submit(self, text, number="1"):
        """Issue → キュー → マージ。成功するまでを1回で行う"""
        self.issue(text, number)
        self.merge_ok()
