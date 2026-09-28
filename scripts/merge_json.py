import os
import re
import json
import glob
import shutil

MAX_PROCESSED_FILES = 30
CLEAR = "!clear"  # 既存値を消したいときにIssueへ入力する特別な値
ISSUE_MAP_FILE = "data/issue_map.json"  # {Issue番号: logid}  Issue再編集時に同じログを更新するための対応表

DEFAULT_GROUPS = [
    "G2", "YZH", "MMK", "MSK", "YOK", "KUR", "MNM", "KIR",
    "L2", "RIN", "TBK", "HIR", "YUW", "KAN", "RRK", "AKR", "KIK",
]
DEFAULT_MEMBERS = {
    "Girls²": ["YZH", "MMK", "MSK", "YOK", "KUR", "MNM", "KIR"],
    "Laki": ["RIN", "TBK", "HIR", "YUW", "KAN", "RRK", "AKR", "KIK"],
}

TARGETS = [
    {
        "name": "logs",
        "queue_dir": "data/logs/queue/",
        "processed_dir": "data/logs/processed/",
        "main_file": "data/logs/logs.json",
        "key_fields": ["logid"],
        "order": ["logid", "date", "time", "contents", "title", "display_pc", "display_sp",
                  "url", "map", "groups", "relations", "setlistid", "tags"],
        "clear_to_empty_list": [],
        "sort_key": lambda x: (x.get("date") or "", x.get("time") or ""),
        "sort_reverse": True,
    },
    {
        "name": "setlist",
        "queue_dir": "data/setlist/queue/",
        "processed_dir": "data/setlist/processed/",
        "main_file": "data/setlist/setlist.json",
        "key_fields": ["setlistid"],
        "order": ["setlistid", "artist", "member", "title", "venue", "songs"],
        "clear_to_empty_list": ["member", "songs"],
        "sort_key": lambda x: x.get("setlistid") or "",
        "sort_reverse": True,
    },
    {
        "name": "songs",
        "queue_dir": "data/songs/queue/",
        "processed_dir": "data/songs/processed/",
        "main_file": "data/songs/songs.json",
        "key_fields": ["artist", "title"],
        "order": ["artist", "title", "link"],
        "clear_to_empty_list": [],
        "sort_key": None,  # 追加順のまま
        "sort_reverse": False,
    },
]


# ---------- 共通ヘルパー ----------

def is_blank(v):
    return v is None or v == "" or v == [] or v == {}


def is_clear(v):
    return v == CLEAR or v == [CLEAR]


def key_of(target, item):
    """識別キー。必要な項目が欠けていれば None"""
    vals = tuple(item.get(f) for f in target["key_fields"])
    if any(is_blank(v) for v in vals):
        return None
    return vals


def reorder(target, item):
    ordered = {k: item[k] for k in target["order"] if k in item}
    for k, v in item.items():
        if k not in ordered:
            ordered[k] = v
    return ordered


def generate_logid(item, main_data):
    """既存の命名規則 {date}_{time}_{contents} で発行。衝突時は _02, _03 ... を付ける"""
    base = f"{item['date']}_{item['time']}_{item['contents']}"
    existing = {e.get("logid") for e in main_data}
    if base not in existing:
        return base
    n = 2
    while f"{base}_{n:02d}" in existing:
        n += 1
    return f"{base}_{n:02d}"


# ---------- 更新・新規追加 ----------

def apply_update(target, existing, new_item):
    """空の項目は既存値を残す。値が !clear の項目だけ消す"""
    for k, v in new_item.items():
        if k in target["key_fields"]:
            continue
        if is_clear(v):
            if k in target["clear_to_empty_list"]:
                existing[k] = []
            else:
                existing.pop(k, None)
            continue
        if is_blank(v):
            continue
        existing[k] = v


def finalize_new(target, item, main_data):
    """新規レコードの検証と既定値の補完。不正なら None"""
    name = target["name"]

    if name == "logs":
        date = item.get("date", "")
        contents = item.get("contents", "")
        time = item.get("time", "") or "0000"
        if not re.fullmatch(r"\d{8}", date) or not contents:
            print(f"【スキップ】logsの新規追加には8桁のdateとcontentsが必要です: {item}")
            return None
        if not re.fullmatch(r"\d{4}", time):
            print(f"【スキップ】timeは4桁の数字で指定してください: {item}")
            return None
        item["time"] = time
        item.setdefault("groups", list(DEFAULT_GROUPS))
        if not item.get("logid"):
            item["logid"] = generate_logid(item, main_data)

    elif name == "setlist":
        if not re.fullmatch(r"\d{12}", item.get("setlistid", "")):
            print(f"【スキップ】setlistidは12桁の数字で指定してください: {item}")
            return None
        if not item.get("artist") or not item.get("title"):
            print(f"【スキップ】setlistの新規追加にはartistとtitleが必要です: {item}")
            return None
        item.setdefault("member", list(DEFAULT_MEMBERS.get(item["artist"], [])))
        item.setdefault("venue", "")
        item.setdefault("songs", [])

    elif name == "songs":
        item.setdefault("link", "")

    return reorder(target, item)


def clean_new(item):
    """新規用: 空値・!clear・内部用キー(_始まり)を取り除く"""
    return {k: v for k, v in item.items()
            if not k.startswith("_") and not is_blank(v) and not is_clear(v)}


def apply_item(target, main_data, raw, issue_map):
    """戻り値: added / updated / conflict / invalid"""
    name = target["name"]
    item = dict(raw)
    issue = str(item.pop("_issue", "") or "")

    # 同じIssueの再編集は、発行済みlogidの更新として扱う
    if name == "logs" and not item.get("logid") and issue and issue in issue_map:
        item["logid"] = issue_map[issue]

    key = key_of(target, item)
    can_generate = name == "logs" and not item.get("logid")
    if key is None and not can_generate:
        print(f"【スキップ】識別キー({'+'.join(target['key_fields'])})がありません: {item}")
        return "invalid"

    if key is not None:
        matches = [i for i, e in enumerate(main_data) if key_of(target, e) == key]
        if len(matches) > 1:
            print(f"【警告】{key} がメインファイルに複数存在するため競合を避けてスキップします")
            return "conflict"
        if len(matches) == 1:
            apply_update(target, main_data[matches[0]], item)
            return "updated"

    new_item = finalize_new(target, clean_new(item), main_data)
    if new_item is None:
        return "invalid"
    if name == "logs" and issue:
        issue_map[issue] = new_item["logid"]
    main_data.append(new_item)
    return "added"


# ---------- ファイル操作 ----------

def cleanup_processed_dir(processed_dir):
    """processed フォルダ内のファイルを新しい順に並べ、30個を超える古いものを削除する"""
    if not os.path.exists(processed_dir):
        return
    files = glob.glob(os.path.join(processed_dir, "*.json"))
    if len(files) <= MAX_PROCESSED_FILES:
        return
    files.sort(key=lambda x: os.path.getmtime(x))
    for file_path in files[:-MAX_PROCESSED_FILES]:
        try:
            os.remove(file_path)
            print(f"古い処理済みファイルを削除しました: {file_path}")
        except Exception as e:
            print(f"ファイルの削除に失敗しました {file_path}: {e}")


def load_json_list(path, label):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"警告: {label} {path} のJSON形式が不正です。空として初期化します。")
            return []
    return data if isinstance(data, list) else []


def process_target(target, issue_map):
    queue_dir = target["queue_dir"]
    processed_dir = target["processed_dir"]
    main_file = target["main_file"]

    json_files = glob.glob(os.path.join(queue_dir, "*.json"))
    if not json_files:
        return False
    json_files.sort(key=lambda p: (os.path.getmtime(p), p))  # 古い投稿から順に適用

    main_data = load_json_list(main_file, "メインファイル")

    stats = {"added": 0, "updated": 0, "conflict": 0, "invalid": 0}
    parsed_files = []

    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                new_items = json.load(f)
        except json.JSONDecodeError as e:
            print(f"【エラー】不正なJSON形式のためファイルをスキップします: {file_path} -> {e}")
            continue
        except Exception as e:
            print(f"【エラー】ファイルの処理中に予期せぬエラーが発生しました {file_path} -> {e}")
            continue

        if isinstance(new_items, dict):
            new_items = [new_items]
        elif not isinstance(new_items, list):
            print(f"スキップ: {file_path} の中身がオブジェクトまたは配列ではありません。")
            continue

        for raw in new_items:
            if not isinstance(raw, dict):
                continue
            stats[apply_item(target, main_data, raw, issue_map)] += 1
        parsed_files.append(file_path)

    changed = stats["added"] + stats["updated"]

    if changed:
        if target["sort_key"]:
            main_data.sort(key=target["sort_key"], reverse=target["sort_reverse"])
        os.makedirs(os.path.dirname(main_file), exist_ok=True)
        with open(main_file, "w", encoding="utf-8") as f:
            json.dump(main_data, f, ensure_ascii=False, indent=2)

    # 読み込めたファイルは、スキップ分も含めて processed へ移動する（同じ警告を毎回出さないため）
    if parsed_files:
        os.makedirs(processed_dir, exist_ok=True)
        for file_path in parsed_files:
            dest_path = os.path.join(processed_dir, os.path.basename(file_path))
            if os.path.exists(dest_path):
                os.remove(dest_path)
            shutil.move(file_path, dest_path)
        cleanup_processed_dir(processed_dir)

    print(f"[{target['name']}] 追加{stats['added']}件 / 更新{stats['updated']}件 / "
          f"競合スキップ{stats['conflict']}件 / 不正スキップ{stats['invalid']}件")
    return changed > 0


def main():
    issue_map_raw = {}
    if os.path.exists(ISSUE_MAP_FILE):
        try:
            with open(ISSUE_MAP_FILE, "r", encoding="utf-8") as f:
                issue_map_raw = json.load(f)
        except json.JSONDecodeError:
            print(f"警告: {ISSUE_MAP_FILE} が不正なため空として扱います。")
    issue_map = dict(issue_map_raw) if isinstance(issue_map_raw, dict) else {}

    updated = False
    for target in TARGETS:
        if process_target(target, issue_map):
            updated = True

    if issue_map != issue_map_raw:
        os.makedirs(os.path.dirname(ISSUE_MAP_FILE), exist_ok=True)
        with open(ISSUE_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(issue_map, f, ensure_ascii=False, indent=2)

    if not updated:
        print("新規に追加・更新された有効なデータはありませんでした。")


if __name__ == "__main__":
    main()
