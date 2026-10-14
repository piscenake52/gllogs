import os
import re
import json
import glob
import shutil
import uuid
import copy
import sys

MAX_PROCESSED_FILES = 30
CLEAR = "!clear"  # 既存値を消したいときにIssueへ入力する特別な値
ARTIST_JOIN = " × "  # 複数アーティストの連結文字（issue_to_json.py と揃える）
LOGID_LENGTH = 12  # logid の桁数（UUIDの先頭から取る16進数）
NOTICE_FILE = "merge_notice.md"  # 削除対象が見つからなかった等をIssueにコメントするための一時ファイル（コミットされない）
NOTICES = []
REPEAT_LIMIT = 60  # 繰り返し登録の最大件数
ISSUE_MAP_FILE = "data/issue_map.json"  # {Issue番号: logid}  Issue再編集時に同じログを更新するための対応表

# 新規追加で groups / member が何も入力されなかったときの既定値
DEFAULT_GROUPS = ["G2", "L2"]
DEFAULT_MEMBERS = {  # setlist: artist ごとの既定値
    "Girls²": ["G2"],
    "Laki": ["L2"],
}

# フォームのグループ選択肢（issue_to_json.py と揃える。groups の並び順にも使う）
G2_OPTIONS = ["G2", "YZH", "MMK", "MSK", "YOK", "KUR", "MNM", "KIR", "TOA", "RAN"]
L2_OPTIONS = ["L2", "RIN", "TBK", "HIR", "YUW", "KAN", "RRK", "AKR", "KIK", "YUR"]

TARGETS = [
    {
        "name": "logs",
        "queue_dir": "data/logs/queue/",
        "processed_dir": "data/logs/processed/",
        "main_file": "data/logs/logs.json",
        "key_fields": ["logid"],
        "order": ["logid", "date", "time", "contents", "title", "display_pc", "display_sp",
                  "url", "map", "groups", "relations", "setlistid", "tags", "sns"],
        "clear_to_empty_list": [],
        "append_lists": ["tags", "sns"],  # 更新時は上書きせず、既存の値に新しいものだけ追記する
        "sort_key": lambda x: (x.get("date") or "", x.get("time") or ""),
        "sort_reverse": True,
        "index_file": "data/logs/logs_index.json",  # 検索・候補用の軽量版（helperが先に読む）
        "index_fields": ["logid", "date", "time", "contents", "title", "setlistid"],
    },
    {
        "name": "setlist",
        "queue_dir": "data/setlist/queue/",
        "processed_dir": "data/setlist/processed/",
        "main_file": "data/setlist/setlist.json",
        "key_fields": ["setlistid"],
        "order": ["setlistid", "artist", "member", "title", "venue", "songs"],
        "clear_to_empty_list": [],
        "sort_key": lambda x: x.get("setlistid") or "",
        "sort_reverse": True,
        "index_file": "data/setlist/setlist_index.json",
        "index_fields": ["setlistid", "artist", "title", "venue"],
        "index_song_titles": True,  # songs は曲名の配列だけを入れる
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
    """12桁の短いUUID(16進数)を発行。既存のlogidと重複したら振り直す"""
    existing = {e.get("logid") for e in main_data}
    while True:
        new_id = uuid.uuid4().hex[:LOGID_LENGTH]
        if new_id not in existing:
            return new_id


# ---------- 更新・新規追加 ----------

def autofill_setlistid(record, explicit_clear=False):
    """contents が LIVE で setlistid が未設定なら、date + time(12桁)を setlistid にする。
    time が空・桁数不正のときは何もしない。setlistid を明示的に消す指定(!clear)のときも補完しない"""
    if explicit_clear or record.get("contents") != "LIVE" or record.get("setlistid"):
        return
    date, time = record.get("date") or "", record.get("time") or ""
    if re.fullmatch(r"\d{8}", date) and re.fullmatch(r"\d{4}", time):
        record["setlistid"] = date + time


def _sns_urls(e):
    """snsの1要素から urls を [{"url","member"}] にそろえて返す（旧形式の文字列urlや {"type","url"} も読める）"""
    raw = e.get("urls") or ([e["url"]] if e.get("url") else [])
    out = []
    for u in raw:
        if isinstance(u, str):
            out.append({"url": u, "member": []})
        elif isinstance(u, dict) and u.get("url"):
            mem = u.get("member") or []
            out.append({"url": u["url"], "member": [mem] if isinstance(mem, str) else list(mem)})  # 文字列1件の旧形式も配列にそろえる
    return out


def merge_sns(current, incoming):
    """sns: typeごとに urls をまとめる。同じtypeがあれば urls に追記、無ければ新しい要素を追加する。
    同じURLがあれば重ねず、新しい入力にmember（配列）があれば上書きする（空なら既存のmemberを残す）"""
    merged = []
    for e in (current if isinstance(current, list) else []):
        if isinstance(e, dict) and e.get("type"):
            merged.append({"type": e["type"], "urls": _sns_urls(e)})
    for e in incoming:
        if not (isinstance(e, dict) and e.get("type")):
            continue
        tgt = next((m for m in merged if m["type"] == e["type"]), None)
        if tgt is None:
            tgt = {"type": e["type"], "urls": []}
            merged.append(tgt)
        for u in _sns_urls(e):
            same = next((x for x in tgt["urls"] if x["url"] == u["url"]), None)
            if same is None:
                tgt["urls"].append(u)
            elif u["member"]:
                same["member"] = u["member"]
    return merged


def split_removals(key, v):
    """tags / sns の入力を (追加分, 個別削除の指定) に分ける。
    tags: `-タグ名` が削除指定。sns: {"_remove": URL} が削除指定（issue_to_json.py が `-URL` から作る）"""
    if key == "tags":
        adds = [t for t in v if not (isinstance(t, str) and t.startswith("-") and t[1:].strip())]
        removes = [t[1:].strip() for t in v if isinstance(t, str) and t.startswith("-") and t[1:].strip()]
    else:
        adds = [e for e in v if not (isinstance(e, dict) and "_remove" in e)]
        removes = [e["_remove"] for e in v if isinstance(e, dict) and e.get("_remove")]
    return adds, removes


def apply_removals(record, key, removes):
    """個別削除を適用する。空になったら属性ごと取り除く。戻り値: 見つからなかった指定のリスト"""
    cur = record.get(key)
    missing = []
    if key == "tags":
        have = cur if isinstance(cur, list) else []
        missing = [r for r in removes if r not in have]
        left = [t for t in have if t not in removes]
    else:
        left, found = [], set()
        for e in (cur if isinstance(cur, list) else []):
            if not (isinstance(e, dict) and e.get("type")):
                continue
            urls = []
            for u in _sns_urls(e):
                if u["url"] in removes:
                    found.add(u["url"])
                else:
                    urls.append(u)
            if urls:  # URLが空になったtypeは取り除く
                left.append({"type": e["type"], "urls": urls})
        missing = [r for r in removes if r not in found]
    if left:
        record[key] = left
    else:
        record.pop(key, None)
    for r in missing:
        print(f"【注意】{key} の削除指定が既存の値にありませんでした: {r}")
    return missing


def sns_members(sns):
    """snsの全URLに書かれたmemberのコード（重複なし・出てきた順）"""
    out = []
    for e in (sns if isinstance(sns, list) else []):
        if isinstance(e, dict):
            for u in _sns_urls(e):
                for m in u["member"]:
                    if m not in out:
                        out.append(m)
    return out


def order_groups(items):
    """G2 / L2 のメンバーが入っていればグループのコード(G2 / L2)を足し、フォームの並び順にそろえる（それ以外は後ろ。STFなど）"""
    has = set(items)
    if any(m in has for m in G2_OPTIONS[1:]):
        has.add("G2")
    if any(m in has for m in L2_OPTIONS[1:]):
        has.add("L2")
    ordered = [o for o in G2_OPTIONS if o in has] + [o for o in L2_OPTIONS if o in has]
    return ordered + [x for x in dict.fromkeys(items) if x not in ordered]


def add_member_groups(groups, members):
    """groups に、まだ入っていない member（とそのグループのコード）を足す"""
    return order_groups(list(groups or []) + [m for m in members if m not in (groups or [])])


def apply_songs_patch(existing, ops, label=""):
    """曲目の個別変更。ops は {"op": update/insert/delete, "order": N, title/type/original/notes} のリスト（書いた順に適用）。
    update: 指定した項目だけ書き換える / insert: N番に挿入しN番以降を+1 / delete: N番を削除しN番以降を-1。
    再編集で同じ操作がもう一度流れても二重にならないよう、insert は同じ曲名がすでにN番にあれば何もせず、delete は曲名が一致したときだけ削除する"""
    songs = [dict(x) for x in (existing.get("songs") or []) if isinstance(x, dict)]
    def find(n):
        return next((i for i, x in enumerate(songs) if x.get("order") == n), None)
    for op in ops:
        n, kind = op.get("order"), op.get("op")
        i = find(n)
        where = f"{label} の {n}番"
        if kind == "update":
            if i is None:
                NOTICES.append(f"- **setlist**: {where} の曲がないため更新できませんでした")
                continue
            for k in ("title", "type", "original", "notes"):
                if k in op:
                    songs[i][k] = op[k]
            if "member" in op:  # [] は消去
                if op["member"]:
                    songs[i]["member"] = op["member"]
                else:
                    songs[i].pop("member", None)
        elif kind == "insert":
            if i is not None and songs[i].get("title") == op.get("title"):
                continue  # 反映済み（同じIssueの再編集）
            for x in songs:
                if isinstance(x.get("order"), int) and x["order"] >= n:
                    x["order"] += 1
            songs.append({"order": n, "title": op.get("title", ""), "type": op.get("type", "song"),
                          "original": op.get("original", ""), "notes": op.get("notes", "")})
            if op.get("member"):
                songs[-1]["member"] = op["member"]
        elif kind == "move":
            to = op.get("to")
            if i is None:
                NOTICES.append(f"- **setlist**: {where} の曲がないため移動できませんでした")
                continue
            if op.get("title") and songs[i].get("title") != op["title"]:
                NOTICES.append(f"- **setlist**: {where} は `{songs[i].get('title')}` で、指定の曲名 `{op['title']}` と違うため移動しませんでした")
                continue
            x = songs.pop(i)
            for y in songs:
                if isinstance(y.get("order"), int) and y["order"] > n:
                    y["order"] -= 1
            for y in songs:
                if isinstance(y.get("order"), int) and y["order"] >= to:
                    y["order"] += 1
            x["order"] = to
            songs.append(x)
        elif kind == "delete":
            if i is None:
                NOTICES.append(f"- **setlist**: {where} の曲がないため削除できませんでした")
                continue
            if op.get("title") and songs[i].get("title") != op["title"]:
                NOTICES.append(f"- **setlist**: {where} は `{songs[i].get('title')}` で、指定の曲名 `{op['title']}` と違うため削除しませんでした")
                continue
            del songs[i]
            for x in songs:
                if isinstance(x.get("order"), int) and x["order"] > n:
                    x["order"] -= 1
    songs.sort(key=lambda x: x["order"] if isinstance(x.get("order"), int) else 10**9)
    if songs:
        existing["songs"] = songs
    else:
        existing.pop("songs", None)


def apply_update(target, existing, new_item):
    """空の項目は既存値を残す。値が !clear の項目だけ消す。append_lists の項目は既存値に追記する。
    tags / sns は個別削除（`-タグ名` / `-URL`）も受け付ける（追記のあとに適用する）"""
    removals = {}
    new_item = dict(new_item)
    patch = new_item.pop("songs_patch", None) if target["name"] == "setlist" else None
    for k in ("tags", "sns"):
        if isinstance(new_item.get(k), list) and not is_clear(new_item[k]):
            new_item[k], removals[k] = split_removals(k, new_item[k])
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
        if k == "sns" and isinstance(v, list):
            existing[k] = merge_sns(existing.get(k), v)
            continue
        if k in target.get("append_lists", []) and isinstance(v, list):
            merged = existing[k] if isinstance(existing.get(k), list) else []
            merged = list(merged)
            for t in v:
                if t not in merged:  # 既にあるものは重ねない（Issueの再編集でも増えない）
                    merged.append(t)
            existing[k] = merged
            continue
        existing[k] = v
    for k, rem in removals.items():
        if rem:
            apply_removals(existing, k, rem)
    if target["name"] == "logs" and "sns" in new_item:
        sync_groups_with_sns(existing, new_item)
    if isinstance(patch, list) and patch:
        apply_songs_patch(existing, patch, existing.get("setlistid", ""))  # 曲目全体の置き換えがあれば、そのあとに適用する


def sync_groups_with_sns(existing, new_item):
    """このIssueで追加・変更したsnsのmemberを、groups に無ければ足す（そのグループのコード G2 / L2 も）。
    groups を消す指定と同時でも足す。snsからmemberが外れても、groups からは外さない（足すだけ）"""
    sns_in = new_item.get("sns")
    incoming = sns_members(sns_in) if isinstance(sns_in, list) and not is_clear(sns_in) else []
    if not incoming:
        return
    groups = existing.get("groups") if isinstance(existing.get("groups"), list) else []
    new_groups = add_member_groups(groups, incoming)
    if new_groups != groups:
        existing["groups"] = new_groups


def finalize_new(target, item, main_data):
    """新規レコードの検証と既定値の補完。不正なら None"""
    name = target["name"]

    if name == "logs":
        date = item.get("date", "")
        contents = item.get("contents", "") or "ETC"  # 未選択ならETC
        time = item.get("time", "")
        if not re.fullmatch(r"\d{8}", date):
            print(f"【スキップ】logsの新規追加には8桁のdateが必要です: {item}")
            return None
        item["contents"] = contents
        if time and not re.fullmatch(r"\d{4}", time):
            print(f"【スキップ】timeは4桁の数字で指定してください: {item}")
            return None
        item["time"] = time  # 空欄ならそのまま空で登録する(0000には補完しない)
        autofill_setlistid(item)  # LIVE で setlistid 未入力なら date+time を登録
        members = sns_members(item.get("sns"))
        if item.get("groups"):
            if members:
                item["groups"] = add_member_groups(item["groups"], members)  # 入力された groups に、snsのmemberも足す
        elif members:
            item["groups"] = add_member_groups([], members)  # groups 未入力でsnsにmemberがあれば、既定の G2, L2 ではなくmemberのグループにする
        else:
            item["groups"] = list(DEFAULT_GROUPS)
        if not item.get("logid"):
            item["logid"] = generate_logid(item, main_data)

    elif name == "setlist":
        if not re.fullmatch(r"\d{12}", item.get("setlistid", "")):
            print(f"【スキップ】setlistidは12桁の数字で指定してください: {item}")
            return None
        if not item.get("artist") or not item.get("title"):
            print(f"【スキップ】setlistの新規追加にはartistとtitleが必要です: {item}")
            return None
        # member は artist が Girls² / Laki のときだけ既定値を補完（それ以外は属性を作らない）
        # 「Girls² × Laki」のように複数の場合は、該当分を合わせる（G2, L2）
        if "member" not in item:
            default_member = []
            for a in item["artist"].split(ARTIST_JOIN):
                default_member += DEFAULT_MEMBERS.get(a.strip(), [])
            if default_member:
                item["member"] = default_member
        # venue / songs は空なら属性を作らない

    return reorder(target, item)


def clean_new(item):
    """新規用: 空値・!clear・内部用キー(_始まり)・曲目の個別変更を取り除く"""
    out = {}
    for k, v in item.items():
        if k.startswith("_") or k == "songs_patch" or is_blank(v) or is_clear(v):
            continue
        if k in ("tags", "sns") and isinstance(v, list):
            v = split_removals(k, v)[0]  # 新規では個別削除の指定は無視する
            if not v:
                continue
        out[k] = v
    return out


def apply_delete(target, main_data, item, issue_map):
    """識別キーが一致するレコードを削除する。戻り値: deleted / notfound / conflict / invalid"""
    key = key_of(target, item)
    label = "+".join(target["key_fields"])
    if key is None:
        print(f"【スキップ】削除には識別キー({label})が必要です: {item}")
        return "invalid"
    shown = " / ".join(str(v) for v in key)
    matches = [i for i, e in enumerate(main_data) if key_of(target, e) == key]
    if len(matches) > 1:
        print(f"【警告】{key} がメインファイルに複数存在するため競合を避けて削除をスキップします")
        NOTICES.append(f"- **{target['name']}**: `{shown}` が複数存在するため削除できませんでした")
        return "conflict"
    if not matches:
        print(f"【スキップ】削除対象が見つかりません({label}: {shown})")
        NOTICES.append(f"- **{target['name']}**: 削除対象が見つかりませんでした（{label}: `{shown}`）")
        return "notfound"
    del main_data[matches[0]]
    if target["name"] in ("logs", "setlist"):
        # 削除したlogid / setlistid を指すIssue対応を消す（残すと、元Issueの再編集で存在しないlogidの更新扱いになるため）
        for iss in [k for k, v in issue_map.items() if v == key[0]]:
            del issue_map[iss]
    print(f"【削除】{target['name']}: {shown}")
    return "deleted"


def apply_copy(target, main_data, src_id, item, issue, issue_map):
    """logid(src_id)のレコードをコピーして新規登録する。入力された項目だけ上書きし、!clear の項目はコピーしない。
    戻り値: added / notfound / conflict / invalid"""
    src = [e for e in main_data if e.get("logid") == src_id]
    if not src:
        print(f"【スキップ】コピー元のlogidが見つかりません: {src_id}")
        NOTICES.append(f"- **logs**: コピー元が見つかりませんでした（logid: `{src_id}`）")
        return "notfound"
    if len(src) > 1:
        print(f"【警告】コピー元 {src_id} が複数存在するためスキップします")
        NOTICES.append(f"- **logs**: コピー元 `{src_id}` が複数存在するためコピーできませんでした")
        return "conflict"

    new = copy.deepcopy(src[0])
    new.pop("logid", None)  # 新しいlogidを発行する
    overrides = {k: v for k, v in item.items() if not k.startswith("_") and k != "logid"}
    for k, v in overrides.items():
        if is_clear(v):
            new.pop(k, None)
        elif not is_blank(v):
            if k in ("tags", "sns") and isinstance(v, list):
                adds, rems = split_removals(k, v)
                if adds:
                    new[k] = adds  # tags / groups なども、コピーでは追記ではなく入力値で置き換える
                if rems:
                    apply_removals(new, k, rems)  # 個別削除はコピーした値から取り除く
            else:
                new[k] = v  # tags / groups なども、コピーでは追記ではなく入力値で置き換える
    # LIVE: date / time を変えたときは、コピー元の setlistid は引き継がず date+time で振り直す（setlistid 入力時はそれを優先）
    if new.get("contents") == "LIVE" and "setlistid" not in overrides and ("date" in overrides or "time" in overrides):
        new.pop("setlistid", None)

    new_item = finalize_new(target, new, main_data)
    if new_item is None:
        return "invalid"
    if is_clear(overrides.get("setlistid")):
        new_item.pop("setlistid", None)  # 明示的に消す指定のときは自動補完もしない
    if issue:
        issue_map[issue] = new_item["logid"]
    main_data.append(new_item)
    print(f"【コピー】logs: {src_id} -> {new_item['logid']}")
    return "added"


def apply_copy_setlist(target, main_data, src_id, item, issue, issue_map):
    """setlistid(src_id)のレコードを、新しいsetlistid(item["setlistid"])へコピーして新規登録する。
    入力された項目だけ上書きし、空の項目（曲目・memberなど）はコピー元を引き継ぐ。!clear の項目はコピーしない。
    新しいIDがすでに存在するときは、上書きせずに止める（Issueにコメント）。
    同じIssueの再編集では、前回のコピー先を取り除いて作り直す。戻り値: added / notfound / conflict / invalid"""
    new_id = item.get("setlistid", "")
    if not re.fullmatch(r"\d{12}", new_id):
        print(f"【スキップ】コピー先のsetlistidは12桁の数字で指定してください: {item}")
        return "invalid"
    src = [e for e in main_data if e.get("setlistid") == src_id]
    if not src:
        print(f"【スキップ】コピー元のsetlistidが見つかりません: {src_id}")
        NOTICES.append(f"- **setlist**: コピー元が見つかりませんでした（setlistid: `{src_id}`）")
        return "notfound"
    if len(src) > 1:
        print(f"【警告】コピー元 {src_id} が複数存在するためスキップします")
        NOTICES.append(f"- **setlist**: コピー元 `{src_id}` が複数存在するためコピーできませんでした")
        return "conflict"
    prev = issue_map.get(issue) if issue else None  # 同じIssueが前回作ったコピー先
    clash = [e for e in main_data if e.get("setlistid") == new_id and new_id != prev]
    if clash:
        print(f"【スキップ】コピー先の setlistid {new_id} はすでに存在します")
        NOTICES.append(f"- **setlist**: コピー先の setlistid `{new_id}` はすでに存在するため、コピーしませんでした（上書きしません）")
        return "conflict"

    new = copy.deepcopy(src[0])
    patch = item.get("songs_patch")
    overrides = {k: v for k, v in item.items() if not k.startswith("_") and k not in ("setlistid", "songs_patch")}
    for k, v in overrides.items():
        if is_clear(v):
            new.pop(k, None)
        elif not is_blank(v):
            new[k] = v  # songs / member なども、コピーでは入力値で置き換える
    new["setlistid"] = new_id
    if isinstance(patch, list) and patch:
        apply_songs_patch(new, patch, new_id)  # コピーした曲目に個別変更を適用する
    new_item = finalize_new(target, new, main_data)
    if new_item is None:
        return "invalid"
    if prev:
        main_data[:] = [e for e in main_data if e.get("setlistid") != prev]  # 前回のコピー先を取り除いて作り直す
    if issue:
        issue_map[issue] = new_id
    main_data.append(new_item)
    print(f"【コピー】setlist: {src_id} -> {new_id}")
    return "added"


REPEAT_DROP = ("date", "title", "logid", "setlistid", "url", "map", "sns", "display_pc", "display_sp")  # 繰り返し登録では引き継がない項目


def bump_number(title, i):
    """title の最後の `#数字` を +i する（0詰めの桁数は保つ）。`#数字` がなければそのまま"""
    ms = list(re.finditer(r"#(\d+)", title or ""))
    if not ms or i == 0:
        return title
    m = ms[-1]
    num = str(int(m.group(1)) + i).zfill(len(m.group(1)))
    return title[:m.start(1)] + num + title[m.end(1):]


def apply_repeat(target, main_data, item, repeat, issue, issue_map):
    """繰り返し登録: repeat（1行1回の {"date", "title"?}）ごとに logs を登録する。
    title は最初の回の title の `#数字` を回ごとに +1（行に title があればそれを優先）。url / map / sns / display は引き継がない。
    同じIssueの再編集は、前回の登録分を同じ順番で更新し、増えた回は追加、減った回は削除する（logid は変わらない）。
    すでに同じ date + time + contents + title の行があるときは、その回は登録しない。戻り値: added / updated / invalid"""
    base = {k: v for k, v in item.items() if not k.startswith("_") and k not in REPEAT_DROP}
    dropped = [k for k in ("url", "map", "sns", "display_pc", "display_sp") if not is_blank(item.get(k))]
    if dropped:
        NOTICES.append(f"- **logs**: 繰り返し登録では {' / '.join(dropped)} は引き継ぎません")
    title0 = item.get("title", "")
    prev = issue_map.get(issue) if issue else None
    prev = list(prev) if isinstance(prev, list) else []
    ids, added, updated = [], 0, 0
    for i, occ in enumerate(repeat[:REPEAT_LIMIT]):
        rec = dict(base)
        rec["date"] = occ.get("date", "")
        rec["title"] = occ.get("title") or bump_number(title0, i)
        row = None
        if i < len(prev) and prev[i]:
            row = next((e for e in main_data if e.get("logid") == prev[i]), None)
        if row is not None:
            apply_update(target, row, dict(rec))
            autofill_setlistid(row)
            main_data[main_data.index(row)] = reorder(target, row)
            ids.append(prev[i])
            updated += 1
            continue
        dup = [e for e in main_data if e.get("date") == rec["date"] and (e.get("time") or "") == (rec.get("time") or "")
               and e.get("contents") == (rec.get("contents") or "ETC") and e.get("title") == rec["title"]]
        if dup:
            NOTICES.append(f"- **logs**: {rec['date']} `{rec['title']}` はすでにあるため登録しませんでした")
            ids.append("")
            continue
        new_item = finalize_new(target, clean_new(rec), main_data)
        if new_item is None:
            ids.append("")
            continue
        main_data.append(new_item)
        ids.append(new_item["logid"])
        added += 1
    for old in prev[len(repeat[:REPEAT_LIMIT]):]:  # 減った回を取り除く
        if old:
            main_data[:] = [e for e in main_data if e.get("logid") != old]
    if len(repeat) > REPEAT_LIMIT:
        NOTICES.append(f"- **logs**: 繰り返し登録は{REPEAT_LIMIT}件までです。{len(repeat) - REPEAT_LIMIT}件は登録しませんでした")
    if issue:
        issue_map[issue] = ids
    print(f"【繰り返し】logs: 追加 {added} 件 / 更新 {updated} 件")
    return "added" if added else "updated" if updated else "invalid"


def apply_item(target, main_data, raw, issue_map):
    """戻り値: added / updated / deleted / notfound / conflict / invalid"""
    name = target["name"]
    item = dict(raw)
    issue = str(item.pop("_issue", "") or "")

    if item.pop("_delete", False):
        return apply_delete(target, main_data, item, issue_map)

    repeat = item.pop("_repeat", None) if name == "logs" else None
    if isinstance(repeat, list) and repeat and not item.get("_copy_from"):
        return apply_repeat(target, main_data, item, repeat, issue, issue_map)

    if name == "setlist" and item.get("_copy_from"):
        src_id = item.pop("_copy_from")
        return apply_copy_setlist(target, main_data, src_id, item, issue, issue_map)

    # コピー指定: 初回はコピー元から新規登録。同じIssueの再編集は、発行済みの複製を更新する
    copy_from = item.pop("_copy_from", "") if name == "logs" else ""
    if copy_from:
        if not (issue and issue in issue_map):
            return apply_copy(target, main_data, copy_from, item, issue, issue_map)
        item["logid"] = issue_map[issue]

    # 同じIssueの再編集は、発行済みlogidの更新として扱う
    if name == "logs" and not item.get("logid") and issue and isinstance(issue_map.get(issue), str):
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
            if name == "logs":
                autofill_setlistid(main_data[matches[0]], explicit_clear=is_clear(item.get("setlistid")))
            # 更新で属性が追加された場合も、決まった並び順の位置に入るよう整える
            main_data[matches[0]] = reorder(target, main_data[matches[0]])
            return "updated"

    new_item = finalize_new(target, clean_new(item), main_data)
    if new_item is None:
        return "invalid"
    if name == "logs" and issue:
        issue_map[issue] = new_item["logid"]
    main_data.append(new_item)
    return "added"


# ---------- ファイル操作 ----------

def write_index(target, main_data):
    """検索・候補用の軽量インデックスを書き出す（index_file が設定されたものだけ）。
    必要な項目だけを残し、空の項目は省く。メインファイルと同じ並びで、空白なしのJSONにする"""
    path = target.get("index_file")
    if not path:
        return
    out = []
    for e in main_data:
        row = {k: e[k] for k in target["index_fields"] if not is_blank(e.get(k))}
        if target.get("index_song_titles"):
            titles = [x.get("title") for x in (e.get("songs") or []) if isinstance(x, dict) and x.get("title")]
            if titles:
                row["songs"] = titles
        out.append(row)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))


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

    stats = {"added": 0, "updated": 0, "deleted": 0, "notfound": 0, "conflict": 0, "invalid": 0}
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

    changed = stats["added"] + stats["updated"] + stats["deleted"]

    if changed:
        if target["sort_key"]:
            main_data.sort(key=target["sort_key"], reverse=target["sort_reverse"])
        os.makedirs(os.path.dirname(main_file), exist_ok=True)
        with open(main_file, "w", encoding="utf-8") as f:
            json.dump(main_data, f, ensure_ascii=False, indent=2)
        write_index(target, main_data)

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
          f"削除{stats['deleted']}件 / 削除対象なし{stats['notfound']}件 / "
          f"競合スキップ{stats['conflict']}件 / 不正スキップ{stats['invalid']}件")
    return changed > 0


def rebuild_indexes():
    """メインファイルから軽量インデックスだけを作り直す（初回の作成用: python merge_json.py --rebuild-index）"""
    for target in TARGETS:
        if target.get("index_file"):
            data = load_json_list(target["main_file"], "メインファイル")
            write_index(target, data)
            print(f"[{target['name']}] インデックスを作成しました: {target['index_file']} ({len(data)}件)")


def main():
    if "--rebuild-index" in sys.argv:
        rebuild_indexes()
        return
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

    if NOTICES:
        with open(NOTICE_FILE, "w", encoding="utf-8") as f:
            f.write("⚠️ 一部の処理を実行できませんでした。\n\n" + "\n".join(NOTICES)
                    + "\n\nIDを確認して、Issueを編集すると再処理されます。\n")

    if not updated:
        print("新規に追加・更新された有効なデータはありませんでした。")


if __name__ == "__main__":
    main()
