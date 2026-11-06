"""issue_to_json.py と merge_json.py で共通に使う関数。
Actions では scripts/ に3ファイルを一緒に置く(python scripts/xxx.py で common.py が自動的に読める)。"""
import re


def is_blank(v):
    return v is None or v == "" or v == [] or v == {}


def album_type_ok(t):
    return isinstance(t, str) and bool(re.fullmatch(r"[^\s|][^\n\r|]{0,29}", t)) and t == t.strip().lower()


def map_from_html(v):
    """mapに貼られた Google マップの埋め込みHTML(<iframe src="...">)を、埋め込みURLに直す。URLやそれ以外はそのまま返す"""
    m = re.search(r"""<iframe[^>]*\ssrc\s*=\s*["']([^"']+)["']""", v or "", re.I)
    return m.group(1).replace("&amp;", "&").strip() if m else v
