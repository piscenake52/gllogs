import os
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

# フォームのラベルと完全一致させること
# add_logs.yml
# add_logs.yml の contents プルダウンの選択肢（自由入力の判定に使う）
CONTENTS_OPTIONS = {"ANNIVERSARY", "BIRTHDAY", "DEBUT", "FORMATION", "CL", "COLUMN", "COOKING", "DIARY", "ETC", "CAMPAIGN", "CLOSE", "MESSAGE", "PLAYING", "RESULT", "EVENT", "FANMEETING", "RELEASEEVENT", "FANCLUB", "TELEPHONE", "GLRADIO", "GTUBE", "LIVE", "MAGAZINE", "MEDIA", "BOOK", "NEWSPAPER", "MODEL", "MOVIE", "RADIO", "RELEASE", "BD", "CD", "DIGITAL", "DVD", "MUSICCARD", "SALES", "GOODS", "SNS", "STAGE", "STREAMING", "TICKET", "TV", "WEB", "PODCAST", "YOUTUBE", "GARUGARUCH"}

LABELS_LOGS = {
    "logid": "logid",
    "date": "date",
    "time": "time",
    "contents": "contents",
    "contents_free": "contents / 自由入力",
    "title": "title",
    "display_pc": "display_pc",
    "display_sp": "display_sp",
    "url": "url",
    "map": "map",
    "setlistid": "setlistid",
    "groups_g2": "groups / Girls²",
    "groups_l2": "groups / Laki",
    "groups_free": "groups / 自由入力",
    "stf": "STF",
    "relations_g2": "relations / Girls²",
    "relations_l2": "relations / Laki",
    "relations_free": "relations / 自由入力",
    "tags": "tags",
    "sns": "sns",
    "repeat": "繰り返し登録 (1行1回)",
    "delete": "DELETE",
    "clear": "値の削除（更新時）",
    "copy": "COPY",
    "copy_text": "COPY / 文字入力",
    "anniv": "ANNIVERSARY",
    "anniv_text": "ANNIVERSARY / 文字入力",
    "anniv_suffix": "ANNIVERSARY / 付与文言",
}
# add_setlist_songs.yml
LABELS_SS = {
    "setlistid": "setlistid",
    "copy_from": "COPY / コピー元 setlistid",
    "artist_check": "artist / 選択",
    "artist_free": "artist / 自由入力",
    "title": "title",
    "link": "link",
    "member_g2": "member / Girls²",
    "member_l2": "member / Laki",
    "member_free": "member / 自由入力",
    "venue": "venue",
    "source": "source",
    "songs": "曲目 (1行1曲)",
    "songs_patch": "曲目の個別変更 (1行1操作)",
    "delete": "DELETE",
    "clear": "値の削除（更新時）",
}
# 旧フォーム(データの種類ドロップダウンあり)のIssueを誤って処理しないための目印
LEGACY_MARKER = "### データの種類 (Type / logs, setlist, songs)"
LEGACY_SONGS_LABEL = "曲目 (songs / setlist用 - 1行1曲)"  # setlist / songs が1つのフォームだった頃の見出し(再編集されたIssue用)

ANNIV_OPTION = "ANNIVERSARY（記念日を一緒に登録）"
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

# 「値の削除（更新時）」チェックボックスで消せる項目（識別キーは除く。フォームの選択肢名と揃える）
CLEARABLE = {
    "logs": ["time", "contents", "title", "display_pc", "display_sp", "url", "map",
             "groups", "relations", "setlistid", "tags", "sns"],
    "setlist": ["artist", "title", "member", "venue", "source", "songs"],
    "songs": ["link"],
}

# 削除チェックボックスの選択肢名（add_logs.yml / add_setlist_songs.yml と揃える）
DELETE_OPTION = "削除する"
COPY_OPTION = "コピーして新規登録"  # logs: logid のデータをコピーして新規登録


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


def norm_type(v):
    """typeは複数指定できる（カンマ・読点・+・スラッシュ・空白区切り）。"allow, medley" → "allow,medley"（重複は除く）"""
    seen = []
    for t in re.split(r"[,，、+＋/／\s]+", v or ""):
        if t and t not in seen:
            seen.append(t)
    return ",".join(seen)


def split_song_member(title):
    """曲名の直後の {YZH,MMK} を取り出す。戻り値: (曲名, メンバーのリスト or None)。{-} はメンバー指定の消去（空リスト）。波括弧がなければ None"""
    m = re.match(r"^(.*?)\s*[{｛]([^{}｛｝]*)[}｝]\s*$", title or "")
    if not m:
        return title, None
    codes = [c.upper() for c in re.split(r"[,，、\s]+", m.group(2).strip()) if c]
    if codes == ["-"]:
        codes = []
    return m.group(1).strip(), expand_group_codes(list(dict.fromkeys(codes)))  # G2 / L2 だけなら全員に展開、個別メンバーもあれば G2 / L2 は捨てる


def parse_songs(raw_str):
    """
    1行1曲。書式: [順番:] 曲名 | type | original | notes
      - 曲名の直後に {YZH,MMK} と書くと、その曲の歌唱メンバーになる（省略＝全員扱い）
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
        title, members = split_song_member(parts[0] if parts else "")
        if not title:
            continue
        type_ = parts[1] if len(parts) > 1 else ""
        if type_ == "":
            type_ = "song"
        elif type_ == "-":
            type_ = ""
        else:
            type_ = norm_type(type_) or "song"
        original = parts[2] if len(parts) > 2 else ""
        notes = " | ".join(parts[3:]) if len(parts) > 3 else ""
        song = {
            "order": order,
            "title": title,
            "type": type_,
            "original": original,
            "notes": notes,
        }
        if members:
            song["member"] = members  # 指定があるときだけ持つ（ない曲は全員扱い）
        songs.append(song)
    return songs


def resolve_artist(f):
    """自由入力を優先。空なら選択したものを ARTIST_JOIN でつなぐ（複数選択可）"""
    if f["artist_free"]:
        return f["artist_free"]
    return ARTIST_JOIN.join(parse_checked(f["artist_check"]))


# URLだけが書かれたときの種別の判定（ドメイン → type）。サブドメインも同じtypeにする（www. / m. / vt.tiktok.com / vm.tiktok.com など）
SNS_HOSTS = {
    "x.com": "x", "twitter.com": "x",
    "instagram.com": "instagram",
    "youtube.com": "youtube", "youtu.be": "youtube",
    "tiktok.com": "tiktok",
    "cl-live.com": "cl",  # CL (www.cl-live.com など)
    "radiko.jp": "radiko",
    "girls2-fc.jp": "gl2family",  # ファンクラブ GL²family (SNSではないが、SNSリンクとして扱う)
}


def detect_sns_type(url):
    """URLのドメインから type を判定する。登録ドメインそのもの、またはそのサブドメインなら一致。
    (instagram.com.example.com のような偽装や、ユーザー情報付きの x.com@example.com は一致させない)"""
    host = re.sub(r"^https?://([^/?#]+).*$", r"\1", url).lower().split("@")[-1].split(":")[0]
    for domain, type_ in SNS_HOSTS.items():
        if host == domain or host.endswith("." + domain):
            return type_
    return ""


SNS_MEMBER_CODES = set(G2_OPTIONS + L2_OPTIONS)  # urlごとのmemberに使えるコード（groupsと同じ）


def expand_group_codes(codes):
    """コードの並びの G2 / L2 を、そのグループの全員に置き換える（重複なし）。
    ただし、そのグループの個別メンバー（TOA / RAN / YUR も含む）も一緒に書かれているとき（G2,MSK など）は、G2 / L2 は捨てて個別メンバーだけにする"""
    out = []
    for m in codes:
        if m in ("G2", "L2"):
            group = G2_MEMBERS if m == "G2" else L2_MEMBERS
            if any(c in (G2_OPTIONS if m == "G2" else L2_OPTIONS)[1:] for c in codes):
                continue  # 個別メンバーがいる → グループ名はUI上の印なので登録しない
            members = group
        else:
            members = [m]
        for x in members:
            if x not in out:
                out.append(x)
    return out


def parse_sns(raw):
    """sns欄（1行1件）を [{"type","urls":[{"url","member"}]}] にする（同じtypeは1つにまとめて urls に入れる）。
    先頭が `-` の行は個別削除（`-URL`。戻り値の要素は {"_remove": URL}）。
    書式: `type | url | member | tags`（tagsはそのリンクだけの検索用タグ。カンマ区切り。省略可。`-` だけを書くと既存のtagsを消す。`url | member | tags` も可）。memberは省略可（groupsと同じコード。複数人はカンマ区切り: `YZH,MMK`。G2 / L2 だけを入力するとそのグループ全員。G2,MSK のように個別メンバーもあれば、そのメンバーだけ）。member欄の `+` のあとは with（投稿者と一緒に写っている人。書式はmemberと同じ）: `YZH+MMK,KUR`（投稿者YZH、同写りMMKとKUR）、`+MMK`（投稿者なし、同写りのみ）、`YZH+-`（既存の同写りを消す）。`type | url`、`url | member`、URLだけでも可（x / instagram / youtube / tiktok / girls2-fc.jp は自動判定）。
    出力の member は配列（なしは []）。with は同写りがあるときだけ配列で持つ。同じURLが複数あれば、後に書いたmemberで上書きする。戻り値: (値, エラーのリスト)。!clear のときは [CLEAR]"""
    if not raw:
        return [], []
    if raw.strip() == CLEAR:
        return [CLEAR], []
    items, errors = [], []
    for line in raw.split("\n"):
        line = unicodedata.normalize("NFKC", line).strip()
        if not line or line.startswith("#"):
            continue
        shown = line.replace("`", "'")
        if line.startswith("-"):
            # 個別削除: `-URL`（URLだけで、どのtypeにあっても消す）
            m = re.search(r"https?://\S+", line)
            if not m:
                errors.append(f"- **sns**: 削除するときは `-URL` の形で入力してください（入力値: `{shown}`）")
            else:
                items.append({"_remove": m.group(0)})
            continue
        parts = [x.strip() for x in line.split("|")]
        type_, url, member, tag_raw = "", "", "", ""
        if len(parts) == 1:
            url = parts[0]
        elif len(parts) == 2:
            if re.match(r"https?://", parts[0], re.I):
                url, member = parts          # url | member
            else:
                type_, url = parts           # type | url
        elif len(parts) == 3:
            if re.match(r"https?://", parts[0], re.I):
                url, member, tag_raw = parts  # url | member | tags
            else:
                type_, url, member = parts    # type | url | member
        elif len(parts) == 4:
            type_, url, member, tag_raw = parts  # type | url | member | tags
        else:
            errors.append(f"- **sns**: `|` が多すぎます。`type | url | member | tags` の形で入力してください（入力値: `{shown}`）")
            continue
        link_tags = []
        clear_tags = tag_raw.strip() == "-"  # tags欄が `-` だけ = 既存リンクのtagsを消す指定
        for t in re.split(r"[,、]", "" if clear_tags else tag_raw):
            t = t.strip()
            if t and t not in link_tags:
                link_tags.append(t)
        type_ = type_.lower()
        member_part, _, with_part = member.partition("+")  # `+` の左が投稿者(member)、右が同写り(with)
        clear_with = with_part.strip() == "-"  # `+-` は既存の同写りを消す指定
        if clear_with:
            with_part = ""
        members, withs = [], []
        for m in re.split(r"[,、\s]+", member_part.upper()):
            if m and m not in members:
                members.append(m)
        for m in re.split(r"[,、\s+]+", with_part.upper()):
            if m and m not in withs:
                withs.append(m)
        if not re.fullmatch(r"https?://\S+", url):
            errors.append(f"- **sns**: URLはhttp(s)://から始めてください（入力値: `{shown}`）")
            continue
        bad = [m for m in members + withs if m not in SNS_MEMBER_CODES]
        if bad:
            errors.append(f"- **sns**: memberはgroupsと同じコードで入力してください（複数はカンマ区切り）。不明: `{'`, `'.join(bad)}`（入力値: `{shown}`）")
            continue
        members = expand_group_codes(members)
        withs = expand_group_codes(withs)
        if not type_:
            type_ = detect_sns_type(url) or "etc"  # 判定できないURLはすべてetc
        if not re.fullmatch(r"[a-z0-9_-]+", type_):
            errors.append(f"- **sns**: typeは半角英数字・ハイフン・アンダーバーで入力してください（入力値: `{shown}`）")
            continue
        # 同じtypeは1つの要素にまとめ、urlsに追加する。同じURLは重ねず、memberを新しい値で上書きする
        grouped = next((g for g in items if g.get("type") == type_), None)
        if grouped is None:
            grouped = {"type": type_, "urls": []}
            items.append(grouped)
        same = next((u for u in grouped["urls"] if u["url"] == url), None)
        if same is None:
            ent = {"url": url, "member": members}
            if withs or clear_with:
                ent["with"] = withs  # [] は「既存の同写りを消す」（merge側で取り除く）
            if link_tags or clear_tags:
                ent["tags"] = link_tags  # [] は「既存のtagsを消す」（merge側で取り除く）
            grouped["urls"].append(ent)
        else:
            if members:
                same["member"] = members
            if withs or clear_with:
                same["with"] = withs
            if link_tags or clear_tags:
                same["tags"] = link_tags
    return items, errors


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


REPEAT_MAX = 60  # 繰り返し登録の最大件数


def parse_repeat(raw_str):
    """繰り返し登録（1行1回）。書式: `YYYYMMDD [時刻] [| タイトル [| contents [| URL [| display_sp]]]]`
      - 日付は YYYY/MM/DD・YYYY-MM-DD でもよい。時刻は `HHMM` / `HH:MM`、`-`（時刻なし）。時刻を省略すると、フォームの時刻をそのまま使う
      - `|` が1つだけのときは、その後ろ全部がタイトル（従来どおり）。`|` が2つ以上のときは、タイトル | contents | URL | display_sp の順（どれも空欄でフォームの値を使う。display_sp は空欄なら付けない）
    戻り値: ([{"date", "time"?, "title"?, "contents"?, "url"?, "display_sp"?}, ...], エラーのリスト)"""
    import datetime
    ops, errors = [], []
    for line in (raw_str or "").split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        shown = line.replace(chr(96), chr(39))
        parts = [x.strip() for x in re.split(r"[|｜]", line)]
        tokens = to_halfwidth(parts[0]).split()
        time_tok = None
        if len(tokens) >= 2 and re.fullmatch(r"\d{1,2}:\d{2}|\d{3,4}|-|--:--", tokens[-1]) and len(re.sub(r"[^0-9]", "", "".join(tokens[:-1]))) == 8:
            time_tok = tokens.pop()
        d = re.sub(r"[^0-9]", "", "".join(tokens))
        ok = False
        if len(d) == 8:
            try:
                datetime.date(int(d[:4]), int(d[4:6]), int(d[6:]))
                ok = True
            except ValueError:
                pass
        if not ok:
            errors.append(f"- **繰り返し登録**: 日付を読み取れない行です（`{shown}`）。`YYYYMMDD` または `YYYYMMDD | タイトル` で入力してください")
            continue
        op = {"date": d}
        if time_tok is not None:
            if time_tok in ("-", "--:--"):
                op["time"] = ""
            else:
                t = re.sub(r"[^0-9]", "", time_tok).zfill(4)
                if not (int(t[:2]) <= 23 and int(t[2:]) <= 59):
                    errors.append(f"- **繰り返し登録**: 時刻は 0000〜2359 で入力してください（`{shown}`）")
                    continue
                op["time"] = t
        rest = parts[1:]
        if len(rest) == 1:
            if rest[0]:
                op["title"] = rest[0]
        elif len(rest) >= 2:
            if len(rest) > 7:
                errors.append(f"- **繰り返し登録**: `|` が多すぎます。`日付 時刻 | タイトル | contents | URL | display_sp | map | setlistid | tags` の形で入力してください（`{shown}`）")
                continue
            title, cont = rest[0], rest[1].upper()
            url = rest[2] if len(rest) > 2 else ""
            sp = rest[3] if len(rest) > 3 else ""
            map_ = rest[4] if len(rest) > 4 else ""
            sid = to_halfwidth(rest[5]) if len(rest) > 5 else ""
            row_tags = []
            for t in re.split(r"[,、]", rest[6]) if len(rest) > 6 else []:
                t = t.strip()
                if t and t not in row_tags:
                    row_tags.append(t)
            if map_ and not re.fullmatch(r"https?://\S+", map_):
                errors.append(f"- **繰り返し登録**: mapはhttp(s)://から始めてください（`{shown}`）")
                continue
            if sid and not re.fullmatch(r"\d{12}", sid):
                errors.append(f"- **繰り返し登録**: setlistidは12桁の数字で入力してください（`{shown}`）")
                continue
            if cont and cont not in CONTENTS_OPTIONS:
                errors.append(f"- **繰り返し登録**: contents が選択肢にありません: `{cont}`（`{shown}`）")
                continue
            if url and not re.fullmatch(r"https?://\S+", url):
                errors.append(f"- **繰り返し登録**: URLはhttp(s)://から始めてください（`{shown}`）")
                continue
            if title:
                op["title"] = title
            if cont:
                op["contents"] = cont
            if url:
                op["url"] = url
            if sp:
                op["display_sp"] = sp
            if map_:
                op["map"] = map_
            if sid:
                op["setlistid"] = sid
            if row_tags:
                op["tags"] = row_tags  # その回だけのtags（フォームのtagsに足す）
        ops.append(op)
    if len(ops) > REPEAT_MAX:
        errors.append(f"- **繰り返し登録**: 一度に登録できるのは{REPEAT_MAX}件までです（{len(ops)}件）")
    return ops, errors


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

    # relations の自由入力: メンバーのコード(G2 / L2 はそのグループ全員)。!clear は削除
    free_rel = parse_list(f.get("relations_free", ""))
    if free_rel != [CLEAR]:
        ok_codes = set(G2_OPTIONS + L2_OPTIONS)
        bad = [x for x in free_rel if x.upper() not in ok_codes]
        if bad:
            errors.append(f"- **relations**: メンバーのコード(YZH, MMK, ... / G2 / L2)で入力してください。不明: `{'`, `'.join(bad)}`")

    sns, sns_errors = parse_sns(f.get("sns", ""))
    f["_sns"] = sns
    errors += sns_errors
    return errors


def is_delete_requested(f):
    """「削除」チェックボックスにチェックがあるか"""
    return DELETE_OPTION in parse_checked(f.get("delete", ""))


def apply_clear_checks(target_type, f, data):
    """「値の削除（更新時）」でチェックされた項目を !clear にする（入力値があってもチェックを優先）"""
    for name in parse_checked(f.get("clear", "")):
        if name in CLEARABLE[target_type]:
            data[name] = CLEAR


def build_delete(target_type, f):
    """削除指示（識別キー + _delete）を作る。戻り値: (データ, エラー内容のリスト)"""
    if target_type == "logs":
        logid = to_halfwidth(f["logid"]).lower()
        if not logid or logid == CLEAR:
            return None, ["- **ログID (logid)**: 削除するときはlogidを入力してください"]
        data = {"logid": logid}
    elif target_type == "setlist":
        sid = to_halfwidth(f["setlistid"])
        if not re.fullmatch(r"[0-9]{12}", sid):
            shown = sid.replace("`", "'")
            return None, [f"- **セットリストID (setlistid)**: 12桁の半角数字で入力してください（入力値: `{shown}`）"]
        data = {"setlistid": sid}
    else:
        if not f["artist"] or not f["title"]:
            return None, ["- **artist / title**: songsを削除するときは、artistとtitleを入力してください"]
        data = {"artist": f["artist"], "title": f["title"]}
    data["_delete"] = True  # mergeで削除として扱い、取り除く
    return data, []


def write_error(errors):
    body = ("⚠️ 入力内容に問題があるため、このIssueは処理されませんでした。\n\n"
            + "\n".join(errors)
            + "\n\n入力を修正してIssueを編集すると、自動で再処理されます。\n")
    with open(ERROR_FILE, "w", encoding="utf-8") as fp:
        fp.write(body)


def ensure_group_codes(items):
    """G2 / L2 のメンバーが1人でも入っていれば、グループのコード(G2 / L2)を自動で足す。
    並びはフォームの並び順(G2 とそのメンバー → L2 とそのメンバー → それ以外)にそろえる。!clear のときは何もしない"""
    if items == [CLEAR]:
        return items
    has = set(items)
    if any(m in has for m in G2_OPTIONS[1:]):
        has.add("G2")
    if any(m in has for m in L2_OPTIONS[1:]):
        has.add("L2")
    ordered = [o for o in G2_OPTIONS if o in has] + [o for o in L2_OPTIONS if o in has]
    return ordered + [x for x in items if x not in ordered]


def build_relations(f):
    """relations: プルダウンを優先。未選択のときだけ自由入力を使う(G2 / L2 はそのグループ全員に展開、重複なし)"""
    picked = (parse_selected(f["relations_g2"], G2_OPTIONS[1:])
              + parse_selected(f["relations_l2"], L2_OPTIONS[1:]))
    if picked:
        return picked
    free = parse_list(f.get("relations_free", ""))
    if free == [CLEAR]:
        return free
    return expand_group_codes([x.upper() for x in free])  # G2,MSK のように個別メンバーもあるときは、そのメンバーだけ


def build_logs(f):
    is_stf = "STF" in parse_checked(f["stf"])
    g2_picked = parse_selected(f["groups_g2"], G2_OPTIONS)
    l2_picked = parse_selected(f["groups_l2"], L2_OPTIONS)
    free = parse_list(f["groups_free"])
    if not g2_picked and not l2_picked and free:
        # プルダウンが未選択のときだけ自由入力を使う（G2/L2のメンバー展開はしない。メンバーがいれば G2/L2 のコードは自動で足す）
        free = ensure_group_codes(free)
        groups = free if (free == [CLEAR] or not is_stf) else free + ["STF"]
    elif is_stf:
        # STFはスタッフ目線のログ等を示す印。G2/L2を選んでいてもメンバーへは自動展開せず、
        # 選んだ内容(通常はグループ名のみ)に "STF" を加えるだけにする
        groups = ensure_group_codes(g2_picked + l2_picked) + ["STF"]
    else:
        # G2 / L2 だけを選んだときは全メンバーに展開する。メンバーを選んだときは、選んだメンバーに G2 / L2 のコードを足す
        groups = ensure_group_codes(expand_groups(g2_picked, "G2", G2_MEMBERS) + expand_groups(l2_picked, "L2", L2_MEMBERS))
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
        "relations": build_relations(f),
        "setlistid": f["setlistid"],
        "tags": parse_list(f["tags"]),
        "sns": f.get("_sns", []),
    }
    return data


def parse_source(raw):
    """setlistのsource欄: OFFICIAL(公式の情報) / UNOFFICIAL(ファンメイド) → "official" / "unofficial"。空は ""(変更なし・不明)。!clear は消去。
    戻り値: (値, エラー文 or None)"""
    v = unicodedata.normalize("NFKC", raw or "").strip()
    if not v:
        return "", None
    if v == CLEAR:
        return CLEAR, None
    key = re.sub(r"[\s_\-]+", "", v).upper()
    if key == "OFFICIAL":
        return "official", None
    if key == "UNOFFICIAL":
        return "unofficial", None
    shown = v.replace("`", "'")
    return "", f"- **source**: OFFICIAL か UNOFFICIAL で入力してください（空は不明）。入力値: `{shown}`"


def build_setlist(f):
    member = (expand_members(parse_selected(f["member_g2"], G2_OPTIONS), "G2", G2_MEMBERS)
              + expand_members(parse_selected(f["member_l2"], L2_OPTIONS), "L2", L2_MEMBERS))
    if not member:
        # プルダウンが未選択のときだけ自由入力を使う（そのままの値）
        member = parse_list(f["member_free"])
    return {
        "setlistid": f["setlistid"],
        "artist": f["artist"],
        "member": member,
        "title": f["title"],
        "venue": f["venue"],
        "songs": parse_songs(f["songs"]),
    }


def parse_songs_patch(raw_str):
    """曲目の個別変更。1行1操作。書式:
         N: 曲名 {メンバー} | type | original | notes   … N番の曲を部分更新（空欄・省略した項目は今のまま、- は空にする。メンバーは {YZH,MMK}、{-} で指定を消す）
        +N: 曲名 | type | original | notes   … N番に曲を挿入（N番以降は1つ後ろへ。typeを省略すると song）
        -N: 曲名                              … N番の曲を削除（N番以降は1つ前へ。曲名を書くと一致したときだけ削除）
        N>M: 曲名                             … N番の曲をM番へ移動（間の曲は1つずつずれる。曲名を書くと一致したときだけ移動）
    戻り値: (操作のリスト, エラーのリスト)"""
    ops, errors = [], []
    for line in (raw_str or "").split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        mv = re.match(r"^(\d+)\s*[>＞]\s*(\d+)\s*(?:[:：]\s*(.*))?$", line)
        if mv:
            if mv.group(1) == mv.group(2):
                errors.append(f"- **曲目の個別変更**: 移動元と移動先が同じです（`{line.replace(chr(96), chr(39))}`）")
                continue
            op = {"op": "move", "order": int(mv.group(1)), "to": int(mv.group(2))}
            mt = re.split(r"[|｜]", mv.group(3) or "")[0].strip()
            if mt:
                op["title"] = mt
            ops.append(op)
            continue
        m = re.match(r"^([+\-＋－]?)\s*(\d+)\s*(?:[:：]\s*(.*))?$", line)
        if not m:
            errors.append(f"- **曲目の個別変更**: 読み取れない行です（`{line.replace(chr(96), chr(39))}`）。`N: 曲名 | type`、`+N: 曲名`、`-N` の形式で入力してください")
            continue
        sign = {"＋": "+", "－": "-"}.get(m.group(1), m.group(1))
        op = {"op": {"+": "insert", "-": "delete", "": "update"}[sign], "order": int(m.group(2))}
        parts = [p.strip() for p in re.split(r"[|｜]", m.group(3) or "")]
        title, members = split_song_member(parts[0] if parts else "")
        if members is not None and op["op"] != "delete":
            op["member"] = members  # [] は消去（{-}）
        if op["op"] == "insert" and not title:
            errors.append(f"- **曲目の個別変更**: 挿入には曲名が必要です（`{line.replace(chr(96), chr(39))}`）")
            continue
        if op["op"] == "update" and not title and not any(parts[1:]) and "member" not in op:
            errors.append(f"- **曲目の個別変更**: 更新する項目がありません（`{line.replace(chr(96), chr(39))}`）")
            continue
        if title:
            op["title"] = title
        if op["op"] != "delete":
            for i, key in ((1, "type"), (2, "original"), (3, "notes")):
                v = " | ".join(parts[3:]) if key == "notes" else (parts[i] if len(parts) > i else "")
                if v == "-":
                    op[key] = ""          # - は空にする
                elif v:
                    op[key] = (norm_type(v) or "song") if key == "type" else v
            if op["op"] == "insert" and "type" not in op:
                op["type"] = "song"
        ops.append(op)
    return ops, errors


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


BULK_MAX = 100
BULK_OPS = ("replace", "add", "remove", "contents")


def build_bulk(body):
    """bulk フォーム(add_bulk.yml)のIssueを検証し、キュー用の辞書を返す。戻り値: (data, errors)"""
    ids_raw = extract_field("bulk ids", body)
    op = extract_field("bulk op", body).strip().lower()
    v_from = extract_field("bulk from", body).strip()
    v_to = extract_field("bulk to", body).strip()
    errors = []
    ids = []
    for x in re.split(r"[\s,]+", ids_raw or ""):
        x = x.strip().lower()
        if x and x not in ("none", "_no", "response_") and x not in ids:
            ids.append(x)
    bad = [x for x in ids if not re.fullmatch(r"[0-9a-f]{12}", x)]
    if not ids:
        errors.append("- **bulk ids**: 対象の logid を入力してください")
    if bad:
        errors.append("- **bulk ids**: 12桁の logid で入力してください（" + ", ".join("`" + b.replace(chr(96), chr(39)) + "`" for b in bad[:5]) + "）")
    if len(ids) > BULK_MAX:
        errors.append(f"- **bulk ids**: {BULK_MAX}件を超えているため処理しません（{len(ids)}件）")
    if op not in BULK_OPS:
        errors.append("- **bulk op**: replace / add / remove / contents のどれかを入力してください")
    value = ""
    if op == "replace":
        if not v_from or not v_to:
            errors.append("- **bulk from / to**: replace では from と to の両方が必要です")
        elif v_from == v_to:
            errors.append("- **bulk from / to**: from と to が同じです")
    elif op in ("add", "contents"):
        value = v_to or v_from
        if not value:
            errors.append("- **bulk to**: 値を入力してください")
    elif op == "remove":
        value = v_from or v_to
        if not value:
            errors.append("- **bulk from**: 削除するタグを入力してください")
    if op == "contents" and value:
        value = to_halfwidth(value).upper()
        if value not in CONTENTS_OPTIONS or value in ("ANNIVERSARY", "BIRTHDAY"):
            errors.append("- **bulk to**: contents の選択肢にある値を入力してください（ANNIVERSARY / BIRTHDAY は指定できません）")
    if errors:
        return None, errors
    bulk = {"op": op, "ids": ids}
    if op == "replace":
        bulk["from"], bulk["to"] = v_from, v_to
    else:
        bulk["value"] = value
    return {"_bulk": bulk}, []


def main():
    body = os.environ.get("ISSUE_BODY", "").replace("\r\n", "\n")
    issue_number = os.environ.get("ISSUE_NUMBER", "").strip()

    if LEGACY_MARKER in body:
        print("旧フォームのIssueは処理しません。新しいフォームから作成し直してください。")
        return

    # bulk フォーム(add_bulk.yml): logs の複数行をまとめて変更する
    if "### bulk ids" in body:
        data, errors = build_bulk(body)
        if errors:
            write_error(errors)
            print("入力エラーのため処理を中止しました:\n" + "\n".join(errors))
            return
        os.makedirs("data/logs/queue", exist_ok=True)
        file_path = os.path.join("data/logs/queue", f"{creation_stamp()}.json")
        with open(file_path, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        print(f"JSONファイルを生成しました: {file_path}")
        return

    # フォームの種類は、本文に含まれる見出しで判別する
    if f"### {LABELS_SS['artist_free']}" in body:
        f = {key: extract_field(label, body) for key, label in LABELS_SS.items()}
        f["artist"] = resolve_artist(f)
        if not f["songs"]:
            f["songs"] = extract_field(LEGACY_SONGS_LABEL, body)
        # setlist / songs は別々のフォーム。setlistだけにある項目(venue / 曲目)かsongsだけにある項目(link)の見出しで判別する。
        # 両方ある(旧・統合フォームのIssue)ときは、従来どおり setlistid の有無で判別する
        has_setlist_form = any(f"### {x}" in body for x in (LABELS_SS["venue"], LABELS_SS["songs"], LEGACY_SONGS_LABEL))
        has_songs_form = f"### {LABELS_SS['link']}" in body
        if has_setlist_form and not has_songs_form:
            target_type = "setlist"
        elif has_songs_form and not has_setlist_form:
            target_type = "songs"
        else:
            target_type = "setlist" if f["setlistid"] else "songs"
        if has_setlist_form != has_songs_form:
            # 専用フォームでは、識別キーが無いままだと黙って無視されてしまうので、Issueにコメントして知らせる
            errors = []
            if target_type == "setlist" and not f["setlistid"]:
                errors.append("- **setlistid**: setlistを登録・更新・削除するときは、setlistidを入力してください")
            if target_type == "songs" and not (f["artist"] and f["title"]):
                errors.append("- **artist / title**: songsを登録・更新・削除するときは、artistとtitleを入力してください")
            if errors:
                write_error(errors)
                print("入力エラーのため処理を中止しました:\n" + "\n".join(errors))
                return
    else:
        f = {key: extract_field(label, body) for key, label in LABELS_LOGS.items()}
        target_type = "logs"

    # コピー指定: COPYチェックがON、または文字入力欄が copy（前後の空白・大文字小文字は無視。それ以外の文字は無視する）
    copy_req = target_type == "logs" and (
        COPY_OPTION in parse_checked(f.get("copy", ""))
        or f.get("copy_text", "").strip().lower() == "copy"
    )
    if target_type == "setlist" and f.get("copy_from", "").strip() and is_delete_requested(f):
        errors = ["- **削除 / コピー**: 「削除する」と「コピー」は同時に指定できません"]
        write_error(errors)
        print("入力エラーのため処理を中止しました:\n" + "\n".join(errors))
        return
    if copy_req and is_delete_requested(f):
        errors = ["- **削除 / コピー**: 「削除する」と「コピーして新規登録」は同時に指定できません"]
        write_error(errors)
        print("入力エラーのため処理を中止しました:\n" + "\n".join(errors))
        return

    if is_delete_requested(f):
        # 削除チェックあり: 識別キーだけの削除指示を出力する（他の入力項目は使わない）
        data, errors = build_delete(target_type, f)
        if errors:
            write_error(errors)
            print("入力エラーのため処理を中止しました:\n" + "\n".join(errors))
            return
        must = True
    elif target_type == "logs":
        # 未選択のドロップダウンは "None" として届くことがあるため空扱いにする
        if f["contents"] == "None":
            f["contents"] = ""
        # プルダウンが未選択のときは自由入力を使う（プルダウン優先）
        if not f["contents"] and f.get("contents_free") and f["contents_free"] not in ("None", "_No response_"):
            free = f["contents_free"].strip()
            # 自由入力が contents の選択肢に一致すればその値、一致しなければ ETC で登録する(!clear はそのまま渡して値を消す)
            f["contents"] = CLEAR if free == CLEAR else (free.upper() if free.upper() in CONTENTS_OPTIONS else "ETC")
        # 数値項目を半角にそろえ、桁数などを検証する（問題があればIssueにコメントして終了）
        repeat_ops, repeat_errors = parse_repeat(f.get("repeat", ""))
        if repeat_ops and not f["date"]:
            f["date"] = repeat_ops[0]["date"]  # date が空なら最初の回の日付を使う
        errors = normalize_and_validate_logs(f) + repeat_errors
        if repeat_ops and (f["logid"] or copy_req):
            errors.append("- **繰り返し登録**: 新規登録のときだけ使えます（logid の入力・コピーとは一緒に使えません）")
        anniv_req = (ANNIV_OPTION in parse_checked(f.get("anniv", ""))
                     or f.get("anniv_text", "").strip().lower() == "anniversary")
        if anniv_req:
            if f["contents"] in ("ANNIVERSARY", "BIRTHDAY"):
                errors.append("- **ANNIVERSARY**: contents が ANNIVERSARY / BIRTHDAY のデータには使えません")
        if errors:
            write_error(errors)
            print("入力エラーのため処理を中止しました:\n" + "\n".join(errors))
            return
        data = build_logs(f)
        if anniv_req:
            data["_anniversary"] = True  # mergeで、参照型のANNIVERSARYを一緒に作る（mergeで取り除く）
            sx = f.get("anniv_suffix", "").strip()
            data["_anniv_suffix"] = "" if sx in ("", "None", "_No response_") else sx  # タイトルの後ろに「半角スペース+この文言」を付けて表示する（空なら 記念日）
        if repeat_ops:
            data["_repeat"] = repeat_ops
        if copy_req:
            # コピー: logid は「コピー元」。入力された項目だけを上書きし、それ以外はコピー元の値を引き継ぐ（新しいlogidはmergeで発行）
            if not f["logid"]:
                errors = ["- **ログID (logid)**: コピーするときは、コピー元のlogidを入力してください"]
                write_error(errors)
                print("入力エラーのため処理を中止しました:\n" + "\n".join(errors))
                return
            data["_copy_from"] = data.pop("logid")
        if issue_number:
            # 同じIssueの再編集を、同じレコードの更新として扱うための目印（mergeで取り除く）
            data["_issue"] = issue_number
        must = bool(f["logid"] or f["date"])
    elif target_type == "setlist":
        # コピー: setlistid が新しいID、copy_from がコピー元。入力した項目だけ上書きし、空の項目はコピー元を引き継ぐ（mergeで処理）
        f["setlistid"] = to_halfwidth(f["setlistid"])
        copy_src = to_halfwidth(f.get("copy_from", ""))
        data = build_setlist(f)
        src, src_err = parse_source(f.get("source", ""))
        if src_err:
            write_error([src_err])
            print("入力エラーのため処理を中止しました:\n" + src_err)
            return
        data["source"] = src
        patch_ops, patch_errors = parse_songs_patch(f.get("songs_patch", ""))
        if patch_errors:
            write_error(patch_errors)
            print("入力エラーのため処理を中止しました:\n" + "\n".join(patch_errors))
            return
        if patch_ops:
            data["songs_patch"] = patch_ops
        if copy_src:
            errors = []
            if not re.fullmatch(r"[0-9]{12}", copy_src):
                errors.append(f"- **コピー元 setlistid**: 12桁の半角数字で入力してください（入力値: `{copy_src.replace(chr(96), chr(39))}`）")
            if not re.fullmatch(r"[0-9]{12}", f["setlistid"]):
                errors.append("- **setlistid**: コピーするときは、新しい setlistid（日付+開演時刻 12桁）を入力してください")
            elif f["setlistid"] == copy_src:
                errors.append("- **setlistid**: コピー元と同じIDです。新しい日付・開演時刻のIDを入力してください")
            if errors:
                write_error(errors)
                print("入力エラーのため処理を中止しました:\n" + "\n".join(errors))
                return
            data["_copy_from"] = copy_src
            if issue_number:
                data["_issue"] = issue_number  # 同じIssueの再編集で、コピー先を作り直すための目印（mergeで取り除く）
        must = bool(f["setlistid"])
    else:
        data = build_songs(f)
        must = bool(f["artist"] and f["title"])

    if not must:
        print(f"[{target_type}] 必須項目が見つかりませんでした。処理をスキップします。")
        return

    if not is_delete_requested(f):
        apply_clear_checks(target_type, f, data)

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
