import os
import json
import re
from datetime import datetime, timedelta, timezone

# フォームのラベルと完全一致させること
# add_logs.yml
LABELS_LOGS = {
    "logid": "ログID (logid)",
    "date": "日付 (date)",
    "time": "時間 (time)",
    "contents": "コンテンツ種別 (contents)",
    "title": "タイトル (title)",
    "display_pc": "display_pc",
    "display_sp": "display_sp",
    "url": "URL (url)",
    "map": "マップ情報 (map)",
    "setlistid": "セットリストID (setlistid)",
    "groups_g2": "グループ/メンバー Girls² (groups)",
    "groups_l2": "グループ/メンバー Laki (groups)",
    "relations": "関連情報 (relations - JSON配列またはカンマ区切り)",
    "tags": "タグ (tags - カンマ区切り)",
}
# add_setlist_songs.yml
LABELS_SS = {
    "setlistid": "セットリストID (setlistid / setlist用)",
    "artist": "アーティスト (artist)",
    "title": "タイトル (title / setlist名 または 曲名)",
    "link": "楽曲リンク (link / songs用)",
    "member": "出演メンバー (member / setlist用 - カンマ区切り)",
    "venue": "会場 (venue / setlist用)",
    "songs": "曲目 (songs / setlist用 - 1行1曲)",
}
# 旧フォーム(データの種類ドロップダウンあり)のIssueを誤って処理しないための目印
LEGACY_MARKER = "### データの種類 (Type / logs, setlist, songs)"

CLEAR = "!clear"  # 既存値を消したいときに入力する特別な値


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


def build_logs(f):
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
        "groups": parse_checked(f["groups_g2"]) + parse_checked(f["groups_l2"]),
        "relations": parse_list(f["relations"]),
        "setlistid": f["setlistid"],
        "tags": parse_list(f["tags"]),
    }
    return data


def build_setlist(f):
    return {
        "setlistid": f["setlistid"],
        "artist": f["artist"],
        "member": parse_list(f["member"]),
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
    if f"### {LABELS_SS['artist']}" in body:
        f = {key: extract_field(label, body) for key, label in LABELS_SS.items()}
        target_type = "setlist" if f["setlistid"] else "songs"
    else:
        f = {key: extract_field(label, body) for key, label in LABELS_LOGS.items()}
        target_type = "logs"

    if target_type == "logs":
        # 未選択のドロップダウンは "None" として届くことがあるため空扱いにする
        if f["contents"] == "None":
            f["contents"] = ""
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
