"""issue_to_json.py と merge_json.py で共通に使う関数。
Actions では scripts/ に、これらのファイルと schema.json を一緒に置く(python scripts/xxx.py で common.py が自動的に読める)。"""
import json
import os
import re


def load_schema():
    """scripts/schema.json(項目の定義)を読む"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


SCHEMA = load_schema()


def is_blank(v):
    return v is None or v == "" or v == [] or v == {}


def album_type_ok(t):
    return isinstance(t, str) and bool(re.fullmatch(r"[^\s|][^\n\r|]{0,29}", t)) and t == t.strip().lower()


def map_from_html(v):
    """mapに貼られた Google マップの埋め込みHTML(<iframe src="...">)を、埋め込みURLに直す。URLやそれ以外はそのまま返す"""
    m = re.search(r"""<iframe[^>]*\ssrc\s*=\s*["']([^"']+)["']""", v or "", re.I)
    return m.group(1).replace("&amp;", "&").strip() if m else v
