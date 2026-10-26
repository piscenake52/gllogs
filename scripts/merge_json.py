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
        "order": ["logid", "date", "time", "contents", "ref", "suffix", "title", "display_pc", "display_sp",
                  "url", "map", "groups", "relations", "setlistid", "albumid", "tags", "sns"],
        "clear_to_empty_list": [],
        "append_lists": ["tags", "sns"],  # 更新時は上書きせず、既存の値に新しいものだけ追記する
        "sort_key": lambda x: (x.get("date") or "", x.get("time") or ""),
        "sort_reverse": True,
        "index_file": "data/logs/logs_index.json",  # 検索・候補用の軽量版（helperが先に読む）
        "index_fields": ["logid", "date", "time", "contents", "ref", "suffix", "title", "setlistid", "albumid"],
    },
    {
        "name": "setlist",
        "queue_dir": "data/setlist/queue/",
        "processed_dir": "data/setlist/processed/",
        "main_file": "data/setlist/setlist.json",
        "key_fields": ["setlistid"],
        "order": ["setlistid", "artist", "member", "title", "venue", "source", "songs"],
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
    {
        "name": "albums",
        "queue_dir": "data/albums/queue/",
        "processed_dir": "data/albums/processed/",
        "main_file": "data/albums/albums.json",
        "key_fields": ["title", "type"],
        "order": ["id", "title", "type", "date", "tracks", "editions"],
        "clear_to_empty_list": [],
        "sort_key": lambda x: (x.get("date") or "", x.get("title") or ""),
        "sort_reverse": True,
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


# ---------- ANNIVERSARY（参照型）----------

ANNIV_BLOCKED = ("ANNIVERSARY", "BIRTHDAY")


def linked_annivs(main_data, logid):
    """logid を ref で参照している ANNIVERSARY レコード"""
    return [e for e in main_data if e.get("ref") == logid]


def ensure_anniversary(main_data, logid, suffix=""):
    """参照型の ANNIVERSARY（logid, date, contents, ref だけ）を作る。既にあれば何もしない"""
    src = next((e for e in main_data if e.get("logid") == logid), None)
    if src is None:
        return
    if src.get("ref") or src.get("contents") in ANNIV_BLOCKED:
        NOTICES.append(f"- **ANNIVERSARY**: `{logid}` は contents が ANNIVERSARY / BIRTHDAY（または参照型）のため、記念日は作りませんでした")
        return
    suffix = (suffix or "").strip()
    old = linked_annivs(main_data, logid)
    if old:
        if suffix:  # 重複しては作らない。付与文言が指定されていれば、参照している記念日の文言だけ更新する
            for e in old:
                e["suffix"] = suffix
        return
    rec = {"logid": generate_logid({}, main_data), "date": src.get("date", ""), "contents": "ANNIVERSARY", "ref": logid}
    if suffix:
        rec["suffix"] = suffix
    main_data.append(reorder(TARGETS[0], rec))
    print(f"【追加】ANNIVERSARY（参照）: {rec['logid']} -> {logid}")


def sync_anniv_dates(main_data, logid):
    """元データの date が変わったら、参照している ANNIVERSARY の date も合わせる"""
    src = next((e for e in main_data if e.get("logid") == logid), None)
    if src is None:
        return
    for e in linked_annivs(main_data, logid):
        e["date"] = src.get("date", e.get("date", ""))


def ref_title(main_data):
    """index 用: 参照元の title を使って「 記念日」を付けた title を返す関数を作る"""
    by_id = {e.get("logid"): e for e in main_data}
    def f(e):
        src = by_id.get(e.get("ref"))
        if src and src.get("title"):
            return src["title"] + " " + (e.get("suffix") or "記念日")
        return ""
    return f


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
            ent = {"url": u["url"], "member": [mem] if isinstance(mem, str) else list(mem)}  # 文字列1件の旧形式も配列にそろえる
            if "with" in u:  # 空配列も残す（更新時の「同写りを消す」指定。保存するときは merge_sns が取り除く）
                ent["with"] = [u["with"]] if isinstance(u["with"], str) else list(u["with"] or [])
            if "tags" in u:  # 空配列も残す（更新時の「tagsを消す」指定。保存するときは merge_sns が取り除く）
                ent["tags"] = [u["tags"]] if isinstance(u["tags"], str) else list(u["tags"] or [])
            out.append(ent)
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
                if not u.get("with"):
                    u.pop("with", None)  # 空の with は保存しない
                if not u.get("tags"):
                    u.pop("tags", None)  # 空の tags も保存しない
                tgt["urls"].append(u)
            else:
                if u["member"]:
                    same["member"] = u["member"]
                if "with" in u:
                    if u["with"]:
                        same["with"] = u["with"]  # 同写りも、新しい入力があれば置き換える
                    else:
                        same.pop("with", None)  # `+-`（空配列）は既存の同写りを消す。指定がなければ既存を残す
                if "tags" in u:
                    if u["tags"]:
                        same["tags"] = u["tags"]  # リンクのtagsは、新しい入力があれば置き換える
                    else:
                        same.pop("tags", None)  # `-`（空配列）は既存のtagsを消す。指定がなければ既存を残す
    return merged


TAGS_REPLACE = "="  # tagsの先頭にこれがあれば、既存tagsを「入力順そのまま」で置き換える（helperが並べ替え・入れ替えのときに付ける）


def split_removals(key, v):
    """tags / sns の入力を (追加分, 個別削除の指定) に分ける。
    tags: `-タグ名` が削除指定。sns: {"_remove": URL} が削除指定（issue_to_json.py が `-URL` から作る）"""
    if key == "tags":
        adds = [t for t in v if not (isinstance(t, str) and (t == TAGS_REPLACE or (t.startswith("-") and t[1:].strip())))]
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
    """snsの全URLに書かれたmember(投稿者)とwith(同写り)のコード（重複なし・出てきた順。groupsに足す対象）"""
    out = []
    for e in (sns if isinstance(sns, list) else []):
        if isinstance(e, dict):
            for u in _sns_urls(e):
                for m in list(u["member"]) + list(u.get("with") or []):
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
    replace_tags = isinstance(new_item.get("tags"), list) and TAGS_REPLACE in new_item["tags"]
    for k in ("tags", "sns"):
        if isinstance(new_item.get(k), list) and not is_clear(new_item[k]):
            new_item[k], removals[k] = split_removals(k, new_item[k])
    if replace_tags:
        removals.pop("tags", None)  # 置き換えでは個別削除は使わない（入力にないタグは消える）
        ordered = list(dict.fromkeys(t for t in new_item.pop("tags") if isinstance(t, str) and t.strip()))
        if ordered:
            existing["tags"] = ordered  # 入力順のまま登録（表示もこの順）
        else:
            existing.pop("tags", None)
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
        elif not item.get("ref"):
            item["groups"] = list(DEFAULT_GROUPS)  # 参照型(ref)は groups を持たず、参照元の値を使う
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

    elif name == "albums":
        if item.get("type") not in ("album", "ep", "single", "musiccard"):
            print(f"【スキップ】albumsのtypeは album / ep / single / musiccard のどれかにしてください: {item}")
            return None
        if item.get("date") and not re.fullmatch(r"\d{8}", str(item["date"])):
            print(f"【スキップ】albumsのdateは8桁の数字で指定してください: {item}")
            return None

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
    if target["name"] == "logs":
        for e in linked_annivs(main_data, key[0]):
            main_data.remove(e)
            print(f"【削除】ANNIVERSARY（参照）: {e.get('logid')}")
            NOTICES.append(f"- **logs**: `{shown}` を参照していた ANNIVERSARY `{e.get('logid')}` も一緒に削除しました")
        matches = [i for i, e in enumerate(main_data) if key_of(target, e) == key]
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


REPEAT_DROP = ("date", "title", "logid", "setlistid", "map")  # 繰り返し登録で、フォームの値をそのまま引き継がない項目(url / sns / display_pc / display_sp は引き継ぐ。display_pc / display_sp は回ごとに title と同じ規則で変える)


def bump_number(title, i):
    """title の最後の `#数字` を +i する（0詰めの桁数は保つ）。`#数字` がなければそのまま"""
    ms = list(re.finditer(r"#(\d+)", title or ""))
    if not ms or i == 0:
        return title
    m = ms[-1]
    num = str(int(m.group(1)) + i).zfill(len(m.group(1)))
    return title[:m.start(1)] + num + title[m.end(1):]


def apply_repeat(target, main_data, item, repeat, issue, issue_map, anniv=False, anniv_sx=""):
    """繰り返し登録: repeat（1行1回の {"date", "time"?, "title"?, "contents"?, "url"?, "display_sp"?}）ごとに logs を登録する。
    title は最初の回の title の `#数字` を回ごとに +1（行に title があればそれを優先）。time / contents / url / display_sp は行に指定があればそれを使う。
    フォームの url / sns は全回に引き継ぐ。display_pc / display_sp は、行に title があればその title の「フォームの title より後ろの部分」を足し、なければ `#数字` を回ごとに +1 する（フォームで空にした項目は付けない）。map は引き継がない(通知もしない)。
    同じIssueの再編集は、前回の登録分を同じ順番で更新し、増えた回は追加、減った回は削除する（logid は変わらない）。
    すでに同じ date + time + contents + title の行があるときは、その回は登録しない。戻り値: added / updated / invalid"""
    base = {k: v for k, v in item.items() if not k.startswith("_") and k not in REPEAT_DROP}
    title0 = item.get("title", "")
    prev = issue_map.get(issue) if issue else None
    prev = list(prev) if isinstance(prev, list) else []
    ids, added, updated = [], 0, 0
    for i, occ in enumerate(repeat[:REPEAT_LIMIT]):
        rec = copy.deepcopy(base)  # sns など入れ子の値を回ごとに別物にする
        rec["date"] = occ.get("date", "")
        rec["title"] = occ.get("title") or bump_number(title0, i)
        for k in ("display_pc", "display_sp"):  # フォームの値を引き継ぐ。空(または !clear)にした項目は付けない
            v0 = item.get(k)
            if is_blank(v0) or is_clear(v0) or not isinstance(v0, str):
                rec.pop(k, None)
            elif occ.get("title") and title0 and occ["title"].startswith(title0):
                rec[k] = v0 + occ["title"][len(title0):]  # 行の title がフォームの title の後ろに足した部分(締切・地域名など)を同じように足す
            elif occ.get("title"):
                rec[k] = v0
            else:
                rec[k] = bump_number(v0, i)  # title と同じく #数字 を回ごとに +1
        if "time" in occ:
            rec["time"] = occ["time"]  # 行ごとの時刻（空文字 = 時刻なし）
        for k in ("contents", "url", "display_sp", "map", "setlistid"):
            if occ.get(k):
                rec[k] = occ[k]  # 行ごとの contents / URL / map / setlistid
        if occ.get("tags"):
            rec["tags"] = list(dict.fromkeys(list(rec.get("tags") or []) + list(occ["tags"])))  # 行ごとのtagsはフォームのtagsに足す
        row = None
        if i < len(prev) and prev[i]:
            row = next((e for e in main_data if e.get("logid") == prev[i]), None)
        if row is not None:
            apply_update(target, row, dict(rec))
            autofill_setlistid(row)
            main_data[main_data.index(row)] = reorder(target, row)
            ids.append(prev[i])
            updated += 1
            sync_anniv_dates(main_data, prev[i])
            if anniv:
                ensure_anniversary(main_data, prev[i], anniv_sx)
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
        if anniv:
            ensure_anniversary(main_data, new_item["logid"], anniv_sx)
    for old in prev[len(repeat[:REPEAT_LIMIT]):]:  # 減った回を取り除く（参照している記念日も一緒に）
        if old:
            main_data[:] = [e for e in main_data if e.get("logid") != old and e.get("ref") != old]
    if len(repeat) > REPEAT_LIMIT:
        NOTICES.append(f"- **logs**: 繰り返し登録は{REPEAT_LIMIT}件までです。{len(repeat) - REPEAT_LIMIT}件は登録しませんでした")
    if issue:
        issue_map[issue] = ids
    print(f"【繰り返し】logs: 追加 {added} 件 / 更新 {updated} 件")
    return "added" if added else "updated" if updated else "invalid"


# albums の処理で logs.json の albumid も書き換えるため、albums の処理中だけ logs を読み込んで持つ
LOGS_CTX = {"data": None, "changed": False}
ALBUM_TYPES_OK = ("album", "ep", "single", "musiccard")
ALBUM_ID_RE = re.compile(r"[0-9a-f]{12}")


def apply_album(target, main_data, raw):
    """albums 1件の登録 / 更新 / 削除。識別は id 優先(なければ title + type)。
    _logids(紐づけるlogsのlogid)があれば、その行の albumid を設定し、リストにない行の albumid は外す。
    戻り値: added / updated / deleted / notfound / conflict / invalid"""
    item = dict(raw)
    delete = bool(item.pop("_delete", False))
    logids = item.pop("_logids", None)
    item.pop("_issue", None)
    aid = str(item.get("id") or "").strip().lower()
    key = key_of(target, item)
    if aid and not ALBUM_ID_RE.fullmatch(aid):
        print(f"【スキップ】albumsのidは12桁の英数字(0-9 a-f)で指定してください: {item}")
        return "invalid"
    by_id = [e for e in main_data if aid and e.get("id") == aid]
    by_key = [e for e in main_data if key is not None and key_of(target, e) == key]
    if len(by_id) > 1 or (not by_id and len(by_key) > 1):
        print(f"【警告】albums が複数一致するため競合を避けてスキップします: {aid or key}")
        return "conflict"
    existing = by_id[0] if by_id else (by_key[0] if len(by_key) == 1 else None)
    if existing is not None and aid and existing.get("id") and existing["id"] != aid:
        print(f"【スキップ】同じtitle+typeの盤が別のidで存在します: {key}")
        NOTICES.append(f"- **albums**: `{' / '.join(str(v) for v in key or ())}` はすでに別のidで登録されています")
        return "conflict"
    logs = LOGS_CTX["data"]

    def unlink(album_id, keep=()):
        n = 0
        for r in logs:
            if r.get("albumid") == album_id and r.get("logid") not in keep:
                r.pop("albumid", None)
                n += 1
        if n:
            LOGS_CTX["changed"] = True

    if delete:
        if existing is None:
            print(f"【スキップ】削除対象のalbumsが見つかりません: {aid or key}")
            NOTICES.append(f"- **albums**: 削除対象が見つかりませんでした（{aid or ' / '.join(str(v) for v in key or ())}）")
            return "notfound"
        if existing.get("id"):
            unlink(existing["id"])
        main_data.remove(existing)
        print(f"【削除】albums: {existing.get('title')}")
        return "deleted"

    if existing is None:
        if key is None:
            print(f"【スキップ】albumsには title と type が必要です: {item}")
            return "invalid"
        new_item = finalize_new(target, clean_new(item), main_data)
        if new_item is None:
            return "invalid"
        ids = {e.get("id") for e in main_data}
        if not new_item.get("id"):
            while True:
                nid = uuid.uuid4().hex[:LOGID_LENGTH]
                if nid not in ids:
                    break
            new_item["id"] = nid
        new_item = reorder(target, new_item)
        main_data.append(new_item)
        existing, res = new_item, "added"
    else:
        # title / type の変更も許す(id一致のとき)。変更先が別の盤と重なる場合は何もしない
        nk = key_of(target, item)
        if nk is not None and nk != key_of(target, existing) and any(e is not existing and key_of(target, e) == nk for e in main_data):
            print(f"【スキップ】変更後のtitle+typeが別の盤と重なります: {nk}")
            NOTICES.append(f"- **albums**: 変更後の `{' / '.join(str(v) for v in nk)}` はすでに別の盤として存在します")
            return "conflict"
        for k in ("title", "type"):
            if item.get(k):
                existing[k] = item[k]
        if existing.get("type") not in ALBUM_TYPES_OK:
            print(f"【スキップ】albumsのtypeが不正です: {existing.get('type')}")
            return "invalid"
        upd = {k: v for k, v in item.items() if k not in ("id", "title", "type")}
        apply_update(target, existing, upd)
        if not existing.get("id"):
            existing["id"] = aid or uuid.uuid4().hex[:LOGID_LENGTH]
        existing_pos = main_data.index(existing)
        main_data[existing_pos] = reorder(target, existing)
        existing = main_data[existing_pos]
        res = "updated"
    if isinstance(logids, list) and logs is not None:
        album_id = existing["id"]
        for lid in logids:
            rows = [r for r in logs if r.get("logid") == lid]
            if not rows:
                NOTICES.append(f"- **albums**: logid `{lid}` が見つかりません（紐づけできませんでした）")
                continue
            if rows[0].get("albumid") != album_id:
                rows[0]["albumid"] = album_id
                LOGS_CTX["changed"] = True
        unlink(album_id, keep=set(logids))
    return res


def apply_item(target, main_data, raw, issue_map):
    """戻り値: added / updated / deleted / notfound / conflict / invalid"""
    name = target["name"]
    if name == "albums":
        return apply_album(target, main_data, raw)
    item = dict(raw)
    issue = str(item.pop("_issue", "") or "")
    anniv = bool(item.pop("_anniversary", False)) if name == "logs" else False
    anniv_sx = item.pop("_anniv_suffix", "") if name == "logs" else ""

    if item.pop("_delete", False):
        return apply_delete(target, main_data, item, issue_map)

    repeat = item.pop("_repeat", None) if name == "logs" else None
    if isinstance(repeat, list) and repeat and not item.get("_copy_from"):
        return apply_repeat(target, main_data, item, repeat, issue, issue_map, anniv, anniv_sx)

    if name == "setlist" and item.get("_copy_from"):
        src_id = item.pop("_copy_from")
        return apply_copy_setlist(target, main_data, src_id, item, issue, issue_map)

    # コピー指定: 初回はコピー元から新規登録。同じIssueの再編集は、発行済みの複製を更新する
    copy_from = item.pop("_copy_from", "") if name == "logs" else ""
    if copy_from:
        if not (issue and issue in issue_map):
            res = apply_copy(target, main_data, copy_from, item, issue, issue_map)
            if anniv and res == "added" and isinstance(issue_map.get(issue), str):
                ensure_anniversary(main_data, issue_map[issue], anniv_sx)
            return res
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
            if name == "logs" and item.get("contents") in ANNIV_BLOCKED and linked_annivs(main_data, key[0]):
                print(f"【スキップ】ANNIVERSARYが参照しているため contents を変更できません: {key[0]}")
                NOTICES.append(f"- **logs**: `{key[0]}` は ANNIVERSARY から参照されているため、contents を ANNIVERSARY / BIRTHDAY には変更できません")
                return "invalid"
            apply_update(target, main_data[matches[0]], item)
            if name == "logs":
                sync_anniv_dates(main_data, key[0])
                if anniv:
                    ensure_anniversary(main_data, key[0], anniv_sx)
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
    if anniv and name == "logs":
        ensure_anniversary(main_data, new_item["logid"], anniv_sx)
    return "added"


def apply_bulk(target, main_data, bulk):
    """bulk変更(logsのみ): tags の置換 / 追加 / 削除、contents の変更。戻り値: 実際に変わった行数。
    すでに同じ状態の行（同じタグがある・無い、同じ contents）は黙って飛ばす。見つからない logid は通知する"""
    if target["name"] != "logs" or not isinstance(bulk, dict):
        return 0
    op, ids = bulk.get("op"), bulk.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > 100:
        print("【スキップ】bulk: 対象が不正です（1〜100件）")
        return 0
    by_id = {}
    for r in main_data:
        if isinstance(r, dict) and r.get("logid"):
            by_id.setdefault(r["logid"], []).append(r)
    changed, missing, blocked = 0, [], []
    for lid in ids:
        rows = by_id.get(lid, [])
        if len(rows) != 1:
            missing.append(lid)
            continue
        row = rows[0]
        tags = row.get("tags") if isinstance(row.get("tags"), list) else []
        if op == "replace":
            old, new = bulk.get("from"), bulk.get("to")
            if old not in tags:
                continue
            out = list(dict.fromkeys(new if t == old else t for t in tags))
            row["tags"] = out
        elif op == "add":
            v = bulk.get("value")
            if not v or v in tags:
                continue
            row["tags"] = tags + [v]
        elif op == "remove":
            v = bulk.get("value")
            if v not in tags:
                continue
            out = [t for t in tags if t != v]
            if out:
                row["tags"] = out
            else:
                row.pop("tags", None)
        elif op == "contents":
            v = bulk.get("value")
            if not v or row.get("contents") == v:
                continue
            if v in ANNIV_BLOCKED:
                continue
            if row.get("contents") in ANNIV_BLOCKED and linked_annivs(main_data, lid):
                blocked.append(lid)
                continue
            row["contents"] = v
        else:
            return 0
        main_data[main_data.index(row)] = reorder(target, row)
        changed += 1
    if missing:
        NOTICES.append("- **logs bulk**: 見つからない logid があります（" + ", ".join("`" + m + "`" for m in missing[:10]) + (" ..." if len(missing) > 10 else "") + "）")
    if blocked:
        NOTICES.append("- **logs bulk**: ANNIVERSARY から参照されているため contents を変えなかった行があります（" + ", ".join("`" + b + "`" for b in blocked[:10]) + "）")
    return changed


# ---------- ファイル操作 ----------


INDEX_MAP_CONTENTS = ("LIVE", "RELEASEEVENT", "FANMEETING")


def write_index(target, main_data):
    """検索・候補用の軽量インデックスを書き出す（index_file が設定されたものだけ）。
    必要な項目だけを残し、空の項目は省く。メインファイルと同じ並びで、空白なしのJSONにする"""
    path = target.get("index_file")
    if not path:
        return
    out = []
    rt = ref_title(main_data) if target["name"] == "logs" else None
    for e in main_data:
        row = {k: e[k] for k in target["index_fields"] if not is_blank(e.get(k))}
        if target["name"] == "logs" and e.get("contents") in INDEX_MAP_CONTENTS:
            for k in ("map", "tags", "groups"):  # helperのtourモード(areaに紐づくmap / tags候補)とsetlistの引き継ぎ(groups)のため、LIVE / RELEASEEVENT / FANMEETING だけ入れる
                if not is_blank(e.get(k)):
                    row[k] = e[k]
        if target["name"] == "logs":
            # helperのタグ候補用: タグは全行に入れる(全体のlogs.jsonを読まなくても候補が作れる)。stags = snsリンクごとのタグを並べたもの(出現数の集計用)
            if not is_blank(e.get("tags")):
                row["tags"] = e["tags"]
            stags = [t for s in (e.get("sns") or []) if isinstance(s, dict)
                     for u in (s.get("urls") or []) if isinstance(u, dict)
                     for t in (u.get("tags") or []) if isinstance(t, str) and t.strip()]
            if stags:
                row["stags"] = stags
        if target["name"] == "logs" and e.get("ref") and "title" not in row:
            t = rt(e)
            if t:
                row["title"] = t
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
    if target["name"] == "albums":
        LOGS_CTX["data"] = load_json_list(TARGETS[0]["main_file"], "メインファイル")
        LOGS_CTX["changed"] = False

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
            if "_bulk" in raw:
                stats["updated"] += apply_bulk(target, main_data, raw["_bulk"])
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
    if target["name"] == "albums" and LOGS_CTX["changed"]:
        logs_target = TARGETS[0]
        with open(logs_target["main_file"], "w", encoding="utf-8") as f:
            json.dump(LOGS_CTX["data"], f, ensure_ascii=False, indent=2)
        write_index(logs_target, LOGS_CTX["data"])
        changed = changed or 1

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
