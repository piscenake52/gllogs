import json
import os
import re
import sys

LOGS = "data/logs/logs.json"
IGNORE_FILE = "data/logs/gap_ignore.txt"  # 抜けを無視したいシリーズ（1行1件。レポートに出るシリーズ名をそのまま書く）
REPORT_FILE = "gap_report.md"            # ワークフローが読み取る（コミットはされない）
MAX_LINES = 150                          # レポートの最大行数（Issue本文の上限対策）


def split_title(title):
    """タイトルの最後の `#数字` を '#' に置き換えたシリーズ名と、その番号を返す。なければ None"""
    ms = list(re.finditer(r"#(\d+)", title or ""))
    if not ms:
        return None
    m = ms[-1]
    return title[:m.start(1)] + title[m.end(1):], int(m.group(1))


def find_gaps(rows, ignore=()):
    """シリーズ(contents + タイトルの#以外の部分)ごとに、番号の欠け・重複を探す。
    戻り値: [{"series","contents","gaps":[番号...],"dups":[番号...],"count"}]"""
    series = {}
    for r in rows:
        sp = split_title(r.get("title"))
        if not sp:
            continue
        name, n = sp
        series.setdefault((r.get("contents") or "", name), []).append((n, r.get("date") or ""))
    out = []
    for (contents, name), items in series.items():
        label = name.replace("\n", " ")
        if label in ignore or f"{contents} {label}" in ignore:
            continue
        nums = sorted(n for n, _ in items)
        if len(set(nums)) < 3:  # 2件以下は連番かどうか判断できない
            continue
        have = set(nums)
        lo, hi = nums[0], nums[-1]
        if hi - lo > 400:
            continue
        gaps = [n for n in range(lo, hi + 1) if n not in have]
        dups = sorted({n for n in nums if nums.count(n) > 1})
        # 年号のような大きい数字(#2026 など)や、ほぼ抜けだらけのものは連番ではないので除く
        if not gaps and not dups:
            continue
        if len(gaps) > max(10, len(have)):
            continue
        out.append({"series": label, "contents": contents, "gaps": gaps, "dups": dups, "count": len(have), "range": (lo, hi)})
    out.sort(key=lambda x: (x["contents"], x["series"]))
    return out


def fmt_nums(nums, limit=30):
    s = ", ".join(f"#{n}" for n in nums[:limit])
    return s + (f" ... (+{len(nums) - limit})" if len(nums) > limit else "")


def build_report(found):
    lines = [f"`#数字` つきのタイトルのうち、番号が抜けている・重複しているシリーズです（{len(found)}件）。",
             "意図した欠番なら `data/logs/gap_ignore.txt` に `contents シリーズ名` を1行で書くと、次回から出ません。", ""]
    for f in found:
        head = f"- **{f['contents'] or '-'}** `{f['series']}` (#{f['range'][0]}–#{f['range'][1]}, {f['count']}件)"
        lines.append(head)
        if f["gaps"]:
            lines.append(f"  - 抜け: {fmt_nums(f['gaps'])}")
        if f["dups"]:
            lines.append(f"  - 重複: {fmt_nums(f['dups'])}")
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES] + ["", "…（長いため途中までです）"]
    return "\n".join(lines) + "\n"


def main():
    with open(LOGS, encoding="utf-8") as fp:
        rows = json.load(fp)
    ignore = set()
    if os.path.exists(IGNORE_FILE):
        with open(IGNORE_FILE, encoding="utf-8") as fp:
            ignore = {l.strip() for l in fp if l.strip() and not l.startswith("#")}
    found = find_gaps(rows, ignore)
    if os.path.exists(REPORT_FILE):
        os.remove(REPORT_FILE)
    if found:
        with open(REPORT_FILE, "w", encoding="utf-8") as fp:
            fp.write(build_report(found))
    print(f"シリーズの抜け・重複: {len(found)}件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
