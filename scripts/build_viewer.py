"""index.html を、GitHub Pages で公開する形に分ける。

使い方: python scripts/build_viewer.py index.html 出力フォルダ --url 公開先URL [--preview]

出力:
  viewer.js   <style> と本文の HTML を書き出してから、本体のスクリプトを実行する
  loader.txt  Blogger に貼る内容(<head> の検索用の情報・先読みのスクリプト + viewer.js の読み込み)
  index.html  loader.txt を単独で開けるページにしたもの(テスト用の確認ページ。--preview のときだけ)

<head> の <style> 以外は loader.txt に入る。そこを変えたときは Blogger の貼り直しが必要。
"""
import argparse
import json
import os
import re
import sys

SCRIPT = re.compile(r"<script(?P<attr>[^>]*)>(?P<code>.*?)</script>", re.S)

# 読み込めなかったときの表示。Blogger に貼っても化けないように、日本語は文字参照にする
ERROR_HTML = (
    '<div id="glvLoadFail" hidden style="padding:24px 16px;text-align:center">'
    "&#12506;&#12540;&#12472;&#12434;&#35501;&#12415;&#36796;&#12417;&#12414;&#12379;&#12435;&#12391;&#12375;&#12383;&#12290;<br>"
    '<button type="button" onclick="location.reload()" style="margin-top:12px;padding:8px 20px">'
    "&#20877;&#35501;&#12415;&#36796;&#12415;</button></div>"
)


class BuildError(Exception):
    pass


def split(html):
    """index.html を (head の style 以外, style 要素, 本文の HTML, 本文のスクリプトのリスト) に分ける。"""
    m = re.search(r"<head>(.*?)\n</head>\s*<body>(.*)</body>\s*</html>\s*$", html, re.S)
    if not m:
        raise BuildError("<head> ... </head> <body> ... </body> </html> の形になっていません")
    head, body = m.group(1), m.group(2)
    # <style> は行の先頭にあるものを対象にする(スクリプト内の文字列は対象にしない)
    styles = list(re.finditer(r"(?m)^<style[^>]*>.*?^</style>[ \t]*\n?", head, re.S))
    if len(styles) != 1:
        raise BuildError("<head> の <style> は1つにしてください(現在 %d)" % len(styles))
    s = styles[0]
    head_rest = (head[: s.start()] + head[s.end():]).strip("\n")
    first = SCRIPT.search(body)
    if not first:
        raise BuildError("<body> にスクリプトがありません")
    markup, tail = body[: first.start()], body[first.start():]
    scripts = []
    for sm in SCRIPT.finditer(tail):
        if "src=" in sm.group("attr"):
            raise BuildError("<body> の外部スクリプト(src)には対応していません")
        scripts.append(sm.group("code"))
    rest = re.sub(r"<!--.*?-->", "", SCRIPT.sub("", tail), flags=re.S).strip()
    if rest:
        raise BuildError("<body> のスクリプトより後ろに HTML があります: " + rest[:80])
    return head_rest, s.group(0), markup.strip("\n"), scripts


def viewer_js(style, markup, scripts):
    # 自分の <script> の直前に書き出す(読み込みは途中で止まって待つので、元の index.html と同じ順になる)
    first = ("/* index.html から scripts/build_viewer.py が作成。直接編集しない */\n"
             "document.currentScript.insertAdjacentHTML('beforebegin', %s);\n" % json.dumps(style + "\n" + markup))
    return first + "".join(";\n" + s.strip("\n") + "\n" for s in scripts)


def loader(head_rest, url):
    origin = re.match(r"(https?://[^/]+)", url)
    src = (url.rstrip("/") + "/" if url else "") + "viewer.js"
    lines = ["<!-- GL log loader: scripts/build_viewer.py -->", head_rest]
    if origin:
        lines.append('<link rel="preconnect" href="%s">' % origin.group(1))
    lines.append(ERROR_HTML)
    lines.append('<script charset="utf-8" src="%s" '
                 "onerror=\"document.getElementById('glvLoadFail').hidden=false\"></script>" % src)
    return "\n".join(lines) + "\n"


def preview_page(head_rest, url):
    # 確認用のページは検索に出さない
    return ('<!DOCTYPE html>\n<html lang="ja">\n<head>\n<meta charset="UTF-8">\n'
            '<meta name="robots" content="noindex, nofollow">\n<title>GL log (preview)</title>\n</head>\n<body>\n'
            + loader(head_rest, url) + "</body>\n</html>\n")


def build(src, out, url="", preview=False):
    with open(src, encoding="utf-8") as f:
        head_rest, style, markup, scripts = split(f.read())
    os.makedirs(out, exist_ok=True)
    files = {"viewer.js": viewer_js(style, markup, scripts), "loader.txt": loader(head_rest, url)}
    if preview:
        files["index.html"] = preview_page(head_rest, url)
    for name, text in files.items():
        with open(os.path.join(out, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return sorted(files)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--url", default="", help="viewer.js を置く場所(省略すると相対パス)")
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args(argv)
    try:
        names = build(a.src, a.out, a.url, a.preview)
    except BuildError as e:
        print("build_viewer: " + str(e), file=sys.stderr)
        return 1
    print("%s: %s" % (a.out, ", ".join(names)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
