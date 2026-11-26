"""リポジトリの事前チェック。push / PR のたびに Actions(tests.yml)から実行する。1つでも問題があれば終了コード1。
  python scripts/check_repo.py
チェック内容:
  1. data/ 以下のJSONが読めるか(queue と inbox は除く。そちらは処理側がエラー報告する)
  2. Issueフォーム(.github/ISSUE_TEMPLATE/add_*.yml)と issue_to_json.py の項目名(LABELS_*)・「値の削除」の選択肢が一致しているか
  3. scripts/schema.json の中身が整合しているか(消せる項目が並び順に含まれる、など)と、helper(DEFS)に logs / setlist の全項目があるか
  4. 同じキューを処理するワークフローが増えていないか(auto_merge.yml と process_queue.yml 以外で merge_json.py を実行していないか)
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

QUEUE_WORKFLOWS = {"auto_merge.yml", "process_queue.yml"}  # キューを処理してよいワークフロー(同時に動かないよう、この2つだけ)
# フォームごとに「yml にあるラベルは、必ずコード側の LABELS に載っている」ことを確かめる。add_bulk / add_albums は独自の読み取りなので対象外
FORMS = {"add_logs.yml": ("LABELS_LOGS", "logs"), "add_setlist.yml": ("LABELS_SS", "setlist"), "add_songs.yml": ("LABELS_SS", "songs")}


def rel(p):
    return os.path.relpath(p, ROOT)


def check_json(root=ROOT):
    bad = []
    for p in glob.glob(os.path.join(root, "data", "**", "*.json"), recursive=True):
        r = os.path.relpath(p, root).replace(os.sep, "/")
        if "/queue/" in r or r.startswith("data/inbox/"):
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            bad.append(f"{r}: JSONを読めません ({type(e).__name__}: {e})")
    return bad


def check_forms(root=ROOT):
    problems = []
    try:
        import yaml
        import issue_to_json as m
    except Exception as e:
        return [f"フォームの確認に必要なモジュールを読めません: {e}"]
    for name, (label_var, target) in FORMS.items():
        p = os.path.join(root, ".github", "ISSUE_TEMPLATE", name)
        if not os.path.exists(p):
            problems.append(f"{name}: フォームがありません")
            continue
        with open(p, "r", encoding="utf-8") as f:
            tpl = yaml.safe_load(f)
        els = [e for e in tpl.get("body", []) if e.get("id")]
        labels = {e["attributes"]["label"] for e in els}
        known = set(getattr(m, label_var).values())
        for x in sorted(labels - known):
            problems.append(f"{name}: フォームの項目「{x}」が issue_to_json.py の {label_var} にありません(読み取られません)")
        if target == "logs":  # logs フォームは、LABELS_LOGS の全項目を持つ
            for x in sorted(known - labels):
                problems.append(f"{name}: issue_to_json.py の {label_var} の項目「{x}」が、フォームにありません")
        clear = next((e for e in els if e["id"] == "clear"), None)
        opts = [o["label"] for o in clear["attributes"]["options"]] if clear else []
        want = m.CLEARABLE[target]
        for x in want:
            if x not in opts:
                problems.append(f"{name}: 「値の削除」に「{x}」の選択肢がありません(CLEARABLE にはあります)")
        for x in opts:
            if x not in want:
                problems.append(f"{name}: 「値の削除」の「{x}」は、CLEARABLE にありません(選んでも消えません)")
    return problems


def check_schema(root=ROOT):
    problems = []
    try:
        with open(os.path.join(root, "scripts", "schema.json"), "r", encoding="utf-8") as f:
            sch = json.load(f)
    except Exception as e:
        return [f"scripts/schema.json を読めません: {e}"]
    for t in ("logs", "setlist", "songs", "albums"):
        d = sch.get(t) or {}
        order = d.get("order", [])
        for key in ("key_fields", "clearable", "index_fields"):
            for x in d.get(key, []):
                if x not in order and not (key == "clearable" and x in ("groups", "relations")):
                    problems.append(f"schema.json: {t}.{key} の「{x}」が {t}.order にありません")
        if len(order) != len(set(order)):
            problems.append(f"schema.json: {t}.order に重複があります")
    # helper(helper.html)の DEFS に、logs / setlist の編集できる項目があるか
    for p in glob.glob(os.path.join(root, "helper.html")):
        with open(p, "r", encoding="utf-8") as f:
            keys = set(re.findall(r"\bk:\s*'([a-z_0-9]+)'", f.read()))
        for t in ("logs", "setlist"):
            for x in (sch.get(t) or {}).get("clearable", []):
                if x not in keys:
                    problems.append(f"{os.path.relpath(p, root)}: {t} の項目「{x}」が、helper の DEFS にありません(schema.json にはあります)")
    return problems


def check_workflows(root=ROOT):
    problems = []
    for p in glob.glob(os.path.join(root, ".github", "workflows", "*.y*ml")):
        name = os.path.basename(p)
        with open(p, "r", encoding="utf-8") as f:
            s = f.read()
        runs = [ln for ln in s.split("\n") if "merge_json.py" in ln and not ln.lstrip().startswith("#") and "--rebuild-index" not in ln and "--rebuild-manifest" not in ln]  # キューを処理しない(マニフェスト/インデックスの作り直しだけ)
        if runs and name not in QUEUE_WORKFLOWS:
            problems.append(f".github/workflows/{name}: キューを処理する merge_json.py を実行しています。同時に動くと競合するため、{' と '.join(sorted(QUEUE_WORKFLOWS))} 以外では実行しないでください")
    return problems


def main():
    sections = [("JSON", check_json), ("フォームとコードの項目", check_forms), ("schema.json と helper の項目", check_schema), ("ワークフロー", check_workflows)]
    total = 0
    for title, fn in sections:
        probs = fn()
        total += len(probs)
        print(f"[{'NG' if probs else 'OK'}] {title}")
        for x in probs:
            print("   - " + x)
    if total:
        print(f"\n{total} 件の問題があります")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write("## 事前チェックの問題\n\n見つかった問題は、ログを見てください(" + str(total) + " 件)\n")
        sys.exit(1)
    print("\n問題なし")


if __name__ == "__main__":
    main()
