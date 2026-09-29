import os
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

# フォームのラベルと完全一致させること
# add_logs.yml
LABELS_LOGS = {
    "logid": "logid",
    "date": "date",
    "time": "time",
    "contents": "contents",
    "title": "title",
    "display_pc": "display_pc",
    "display_sp": "display_sp",
    "url": "url",
    "map": "map",
    "setlistid": "setlistid",
    "groups_g2": "groups / Girls²",
    "groups_l2": "groups / Laki",
    "stf": "STF",
    "relations_g2": "relations / Girls²",
    "relations_l2": "relations / Laki",
    "tags": "tags",
}
# add_setlist_songs.yml
LABELS_SS = {
    "setlistid": "setlistid",
    "artist_check": "artist / 選択",
    "artist_free": "artist / 自由入力",
    "title": "title",
    "link": "link",
    "member_g2": "member / Girls²",
    "member_l2": "member / Laki",
    "venue": "venue",
    "songs": "曲目 (songs / setlist用 - 1行1曲)",
}
# 旧フォーム(データの種類ドロップダウンあり)のIssueを誤って処理しないための目印
LEGACY_MARKER = "### データの種類 (Type / logs, setlist, songs)"

CLEAR = "!clear"  # 既存値を消したいときに入力する特別な値
ARTIST_JOIN = " × "  # アーティストを複数選択したときの連結文字（merge_json.py と揃える）

# G2だけ／L2だけにチェックがあるときに補完するメンバー（フォームの並び順）
G2_MEMBERS = ["YZH", "MMK", "MSK", "YOK", "KUR", "MNM", "KIR"]
L2_MEMBERS = ["RIN", "TBK", "HIR", "YUW", "KAN", "RRK", "AKR", "KIK"]

# フォーム(add_logs.yml)のグループ選択肢。並び順をそろえるために使う
G2_OPTIONS = ["G2", "YZH", "MMK", "MSK", "YOK", "KUR", "MNM", "KIR", "TOA", "RAN"]
L2_OPTIONS = ["L2", "RIN", "TBK", "HIR", "YUW", "KAN", "RRK", "AKR", "KIK", "YUR"]

# 入力エラーの内容をIssueにコメントするための一時ファイル（ワークフローが読み取る。コミットはされない）
ERROR_FILE = "issue_error.md"


def is_blank(v):
    return v is None or v == "" or v == [] or v == {}


def extract_field(label, text):
    pattern = rf"^### {re.escape(label)}[ \t]*\n+(.*?)(?=\n+^### |\Z)"
    match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
    if not match:
        return ""
    val = match.group(1).strip()
    # GitHubが自動挿入する "_No response_" や、placeholderに使う "なし" は空扱い
    if val in ("_No response_", "なし"):
        return ""
    return val


def parse_list(raw_str):
    if not raw_str:
        return []
    if raw_str.strip() == CLEAR:
        return [CLEAR]
    if raw_str.startswith("[") and raw_str.endswith("]"):
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass
    items = re.split(r"[,、\n]", raw_str)
    return [item.strip() for item in items if item.strip()]


def parse_checked(raw_str):
    """チェックボックス欄から、チェックされた項目名だけを取り出す（- [x] 名前）"""
    if not raw_str:
        return []
    return [m.group(1).strip()
            for m in re.finditer(r"^\s*-\s*\[[xX]\]\s*(.+?)\s*$", raw_str, re.MULTILINE)]


def parse_selected(raw_str, options):
    """
    グループ/メンバー欄から、選ばれた項目名を取り出す。
    複数選択ドロップダウン（G2, YZH, KUR）とチェックボックス（- [x] G2）の両方に対応し、
    結果はフォームの並び順（options）にそろえる。
    """
    if not raw_str:
        return []
    if re.search(r"^\s*-\s*\[[ xX]\]", raw_str, re.MULTILINE):
        picked = parse_checked(raw_str)
    else:
        picked = [s.strip() for s in re.split(r"[,、\n]", raw_str)
                  if s.strip() and s.strip() not in ("None", "_No response_")]
    picked = list(dict.fromkeys(picked))  # 重複を除く
    return [o for o in options if o in picked] + [p for p in picked if p not in options]


def parse_songs(raw_str):
    """
    1行1曲。書式: [順番:] 曲名 | type | original | notes
      - 順番を省略すると前の曲+1（先頭は1）
      - type を省略すると song。空にしたいときは - を書く
      - # で始まる行と空行は無視
    """
    if not raw_str:
        return []
    if raw_str.strip() == CLEAR:
        return CLEAR
    songs = []
    order = 0
    for line in raw_str.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\d+)\s*[:：]\s*(.*)$", line)
        if m:
            order = int(m.group(1))
            line = m.group(2)
        else:
            order += 1
        parts = [p.strip() for p in re.split(r"[|｜]", line)]
        title = parts[0] if parts else ""
        if not title:
            continue
        type_ = parts[1] if len(parts) > 1 else ""
        if type_ == "":
            type_ = "song"
        elif type_ == "-":
            type_ = ""
        original = parts[2] if len(parts) > 2 else ""
        notes = " | ".join(parts[3:]) if len(parts) > 3 else ""
        songs.append({
            "order": order,
            "title": title,
            "type": type_,
            "original": original,
            "notes": notes,
        })
    return songs


def resolve_artist(f):
    """自由入力を優先。空なら選択したものを ARTIST_JOIN でつなぐ（複数選択可）"""
    if f["artist_free"]:
        return f["artist_free"]
    return ARTIST_JOIN.join(parse_checked(f["artist_check"]))


def to_halfwidth(s):
    """全角の英数字・記号を半角にそろえ、前後の空白を取り除く（例: ２０２６０９２８ → 20260928）"""
    return unicodedata.normalize("NFKC", s or "").strip()


def expand_groups(picked, group, members):
    """グループ名(G2/L2)だけを選んだドロップダウンは、そのグループの全メンバーを補完する。個別に選んだときは選んだものだけ"""
    if picked == [group]:
        return [group] + members
    return picked


def expand_members(picked, group, members):
    """setlist用: グループ名(G2/L2)は配列に入れない。グループ名だけを選んだときはそのグループの全メンバーに置き換え、
    個別メンバーも選んだときは、選んだメンバーだけにする"""
    rest = [p for p in picked if p != group]
    if not rest and group in picked:
        return list(members)
    return rest


def normalize_and_validate_logs(f):
    """logsフォームの数値項目を半角にそろえて検証する。戻り値: エラー内容のリスト（空なら問題なし）"""
    for key in ("logid", "date", "time", "setlistid"):
        f[key] = to_halfwidth(f[key])
    f["logid"] = f["logid"].lower()  # logid は小文字の16進数（大文字で入力されても一致するように）

    # (項目, 表示名, 正規表現, 説明, !clear を許可するか)
    rules = [
        ("date", "日付 (date)", r"[0-9]{8}", "8桁の半角数字（例: 20260928）", False),
        ("time", "時間 (time)", r"[0-9]{4}", "4桁の半角数字（例: 1200）", True),
        ("setlistid", "セットリストID (setlistid)", r"[0-9]{12}", "12桁の半角数字（例: 202609221830）", True),
    ]
    errors = []
    for key, label, pattern, hint, allow_clear in rules:
        v = f[key]
        if not v or (allow_clear and v == CLEAR):
            continue
        if not re.fullmatch(pattern, v):
            shown = v.replace("`", "'")
            errors.append(f"- **{label}**: {hint}で入力してください（入力値: `{shown}`）")

    if not f["logid"] and not f["date"]:
        errors.append("- **ログID (logid) または 日付 (date)**: 更新するときはlogid、新規追加のときは日付を入力してください")
    return errors


def write_error(errors):
    body = ("⚠️ 入力内容に問題があるため、このIssueは処理されませんでした。\n\n"
            + "\n".join(errors)
            + "\n\n入力を修正してIssueを編集すると、自動で再処理されます。\n")
    with open(ERROR_FILE, "w", encoding="utf-8") as fp:
        fp.write(body)


def build_logs(f):
    is_stf = "STF" in parse_checked(f["stf"])
    g2_picked = parse_selected(f["groups_g2"], G2_OPTIONS)
    l2_picked = parse_selected(f["groups_l2"], L2_OPTIONS)
    if is_stf:
        # STFはスタッフ目線のログ等を示す印。G2/L2を選んでいてもメンバーへは自動展開せず、
        # 選んだ内容(通常はグループ名のみ)に "STF" を加えるだけにする
        groups = g2_picked + l2_picked + ["STF"]
    else:
        groups = expand_groups(g2_picked, "G2", G2_MEMBERS) + expand_groups(l2_picked, "L2", L2_MEMBERS)
    data = {
        "logid": f["logid"],
        "date": f["date"],
        "time": f["time"],
        "contents": f["contents"],
        "title": f["title"],
        "display_pc": f["display_pc"],
        "display_sp": f["display_sp"],
        "url": f["url"],
        "map": f["map"],
        "groups": groups,
        "relations": parse_selected(f["relations_g2"], G2_OPTIONS[1:])
                     + parse_selected(f["relations_l2"], L2_OPTIONS[1:]),
        "setlistid": f["setlistid"],
        "tags": parse_list(f["tags"]),
    }
    return data


def build_setlist(f):
    return {
        "setlistid": f["setlistid"],
        "artist": f["artist"],
        "member": expand_members(parse_selected(f["member_g2"], G2_OPTIONS), "G2", G2_MEMBERS)
                  + expand_members(parse_selected(f["member_l2"], L2_OPTIONS), "L2", L2_MEMBERS),
        "title": f["title"],
        "venue": f["venue"],
        "songs": parse_songs(f["songs"]),
    }


def build_songs(f):
    return {
        "artist": f["artist"],
        "title": f["title"],
        "link": f["link"],
    }


JST = timezone(timedelta(hours=9))


def creation_stamp():
    """Issue作成時刻(JST)を YYYYMMDDHHMMSS で返す。取得できなければ現在時刻"""
    raw = os.environ.get("ISSUE_CREATED_AT", "").strip()  # 例: 2026-09-28T12:34:56Z
    try:
        dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        dt = datetime.now(timezone.utc)
    return dt.astimezone(JST).strftime("%Y%m%d%H%M%S")


def main():
    body = os.environ.get("ISSUE_BODY", "").replace("\r\n", "\n")
    issue_number = os.environ.get("ISSUE_NUMBER", "").strip()

    if LEGACY_MARKER in body:
        print("旧フォームのIssueは処理しません。新しいフォームから作成し直してください。")
        return

    # フォームの種類は、本文に含まれる見出しで判別する
    if f"### {LABELS_SS['artist_free']}" in body:
        f = {key: extract_field(label, body) for key, label in LABELS_SS.items()}
        f["artist"] = resolve_artist(f)
        target_type = "setlist" if f["setlistid"] else "songs"
    else:
        f = {key: extract_field(label, body) for key, label in LABELS_LOGS.items()}
        target_type = "logs"

    if target_type == "logs":
        # 未選択のドロップダウンは "None" として届くことがあるため空扱いにする
        if f["contents"] == "None":
            f["contents"] = ""
        # 数値項目を半角にそろえ、桁数などを検証する（問題があればIssueにコメントして終了）
        errors = normalize_and_validate_logs(f)
        if errors:
            write_error(errors)
            print("入力エラーのため処理を中止しました:\n" + "\n".join(errors))
            return
        data = build_logs(f)
        if issue_number:
            # 同じIssueの再編集を、同じレコードの更新として扱うための目印（mergeで取り除く）
            data["_issue"] = issue_number
        must = bool(f["logid"] or f["date"])
    elif target_type == "setlist":
        data = build_setlist(f)
        must = bool(f["setlistid"])
    else:
        data = build_songs(f)
        must = bool(f["artist"] and f["title"])

    if not must:
        print(f"[{target_type}] 必須項目が見つかりませんでした。処理をスキップします。")
        return

    # 空の項目は出力しない（既存値を残す方針。mergeは空値を無視する）
    data = {k: v for k, v in data.items() if not is_blank(v)}

    queue_dir = f"data/{target_type}/queue"
    os.makedirs(queue_dir, exist_ok=True)

    # ファイル名は Issue の作成日時（JST）。同じIssueを編集しても同じ名前になる
    file_path = os.path.join(queue_dir, f"{creation_stamp()}.json")

    with open(file_path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

    print(f"JSONファイルを生成しました: {file_path}")


if __name__ == "__main__":
    main()
