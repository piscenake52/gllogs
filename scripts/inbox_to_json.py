"""helper から直接送られた依頼 data/inbox/*.json を、Issueフォームと同じ処理(issue_to_json.py)でキューのJSONに変換する。

依頼ファイルの形式:  {"template": "add_logs.yml", "params": {"フォーム項目のid": "値", ...}, "created": "2026-10-19T12:34:56Z"}
  params は、helper が Issue 作成URLに付けていたものと同じ(= フォーム項目のid → 値)。
使い方:
  python scripts/inbox_to_json.py            依頼 → data/*/queue/*.json  と  data/inbox/results/<id>.json(結果)
  python scripts/inbox_to_json.py --finish   merge_json.py のあとに実行。結果ファイルに、反映できたか・スキップの理由を書き足す
"""
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

INBOX = "data/inbox"
RESULTS = os.path.join(INBOX, "results")
TEMPLATE_DIR = ".github/ISSUE_TEMPLATE"
ALLOWED = ("add_logs.yml", "add_setlist.yml", "add_songs.yml", "add_albums.yml", "add_bulk.yml")
QUEUE_DIRS = ("data/logs/queue", "data/setlist/queue", "data/songs/queue", "data/albums/queue")
KEEP_RESULTS = 60
HERE = os.path.dirname(os.path.abspath(__file__))
JST = timezone(timedelta(hours=9))


def now_iso():
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")


def load_template(name):
    import yaml
    with open(os.path.join(TEMPLATE_DIR, name), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_body(tpl, params):
    """Issueフォームが作る本文(### 見出し + 値)を再現する。チェックボックスは - [x] / - [ ] の形"""
    parts = []
    used = set()
    for el in tpl.get("body", []):
        t, i = el.get("type"), el.get("id")
        if t == "markdown" or not i:
            continue
        attrs = el.get("attributes", {})
        label = attrs.get("label", i)
        val = params.get(i)
        used.add(i)
        val = "" if val is None else str(val)
        if t == "checkboxes":
            picked = {x.strip() for x in re.split(r"[,\n]", val) if x.strip()}
            lines = [f"- [{'X' if o.get('label') in picked else ' '}] {o.get('label')}" for o in attrs.get("options", [])]
            parts.append(f"### {label}\n\n" + "\n".join(lines))
        else:
            parts.append(f"### {label}\n\n" + (val.strip() if val.strip() else "_No response_"))
    unknown = [k for k in params if k not in used]
    return "\n\n".join(parts) + "\n", unknown


def queue_snapshot():
    snap = set()
    for d in QUEUE_DIRS:
        snap.update(glob.glob(os.path.join(d, "*.json")))
    return snap


def write_result(rid, data):
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, rid + ".json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def convert_one(path):
    rid = os.path.splitext(os.path.basename(path))[0]
    res = {"id": rid, "status": "error", "time": now_iso(), "template": "", "queue_files": [], "errors": [], "notes": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            req = json.load(f)
        tplname = str(req.get("template", ""))
        params = req.get("params")
        if tplname not in ALLOWED:
            raise ValueError(f"template が不正です: {tplname!r}（使えるもの: {', '.join(ALLOWED)}）")
        if not isinstance(params, dict):
            raise ValueError("params がオブジェクトではありません")
        res["template"] = tplname
        body, unknown = build_body(load_template(tplname), params)
        if unknown:
            res["notes"].append("無視した項目: " + ", ".join(unknown))
    except Exception as e:
        res["errors"].append(f"依頼ファイルを読めません: {type(e).__name__}: {e}")
        return res

    before = queue_snapshot()
    if os.path.exists("issue_error.md"):
        os.remove("issue_error.md")
    env = dict(os.environ, ISSUE_BODY=body, ISSUE_NUMBER="", ISSUE_CREATED_AT=str(req.get("created", "")))
    r = subprocess.run([sys.executable, os.path.join(HERE, "issue_to_json.py")], env=env, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    if os.path.exists("issue_error.md"):
        with open("issue_error.md", "r", encoding="utf-8") as f:
            res["errors"].append(f.read().strip().replace("このIssueは", "この依頼は").replace("Issueを編集すると、自動で再処理されます", "直して送り直してください"))
        os.remove("issue_error.md")
    if r.returncode != 0:
        res["errors"].append("変換中に想定外のエラー: " + out.strip()[-600:])
    new = sorted(queue_snapshot() - before)
    for n in new:  # 同じ秒に複数届いても上書きしないよう、依頼のidを付ける
        base, ext = os.path.splitext(n)
        dest = f"{base}_{rid}{ext}"
        os.replace(n, dest)
        res["queue_files"].append(dest)
    if res["queue_files"]:
        res["status"] = "queued"
    elif not res["errors"]:
        res["errors"].append("反映する内容がありませんでした（変更なし、または対象を判別できません）。" + (" / " + out.strip()[-300:] if out.strip() else ""))
    return res


def convert_all():
    files = sorted(glob.glob(os.path.join(INBOX, "*.json")))
    for p in files:
        res = convert_one(p)
        write_result(res["id"], res)
        print(f"[inbox] {res['id']}: {res['status']}" + (" / " + " ".join(res["errors"])[:200] if res["errors"] else ""))
        os.remove(p)
    cleanup_results()


def finish():
    rows = []
    if os.path.exists("queue_report.json"):
        with open("queue_report.json", "r", encoding="utf-8") as f:
            rows = json.load(f)
    notice = ""
    if os.path.exists("merge_notice.md"):
        with open("merge_notice.md", "r", encoding="utf-8") as f:
            notice = f.read().strip()
    for rp in glob.glob(os.path.join(RESULTS, "*.json")):
        with open(rp, "r", encoding="utf-8") as f:
            res = json.load(f)
        if res.get("status") != "queued":
            continue
        remain = [q for q in res.get("queue_files", []) if os.path.exists(q)]
        mine = [r for r in rows if os.path.basename(r.get("file", "")) in {os.path.basename(q) for q in res.get("queue_files", [])}]
        for r in mine:
            idx = "" if r.get("index") is None else f"{r['index'] + 1}件目: "
            (res["errors"] if r.get("level") == "error" else res["notes"]).append(idx + str(r.get("reason")))
        if notice:
            res["notes"].append(notice)
        res["status"] = "error" if remain else "done"
        res["time"] = now_iso()
        write_result(res["id"], res)
        print(f"[inbox] {res['id']}: {res['status']}")


def cleanup_results():
    files = sorted(glob.glob(os.path.join(RESULTS, "*.json")))  # idは日時で始まるので名前順 = 古い順
    for p in files[:-KEEP_RESULTS]:
        os.remove(p)


if __name__ == "__main__":
    if "--finish" in sys.argv:
        finish()
    else:
        convert_all()
