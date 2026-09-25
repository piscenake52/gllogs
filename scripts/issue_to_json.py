import os
import json
import re

def extract_field(label, text):
    pattern = rf"### {label}\s*\n+\s*(.*?)(?=\n+###|\Z)"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        val = match.group(1).strip()
        # GitHubが自動挿入する "_No response_" や設定した "なし" は空文字に変換する
        if val == "_No response_" or val == "なし":
            return ""
        return val
    return ""

def parse_list(raw_str):
    if not raw_str:
        return []
    if raw_str.startswith("[") and raw_str.endswith("]"):
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, list):
                return parsed
        except:
            pass
    items = re.split(r"[,\n]", raw_str)
    return [item.strip() for item in items if item.strip()]

def main():
    body = os.environ.get("ISSUE_BODY", "")
    
    target_type = extract_field(r"データの種類 \(Type / logs, setlist, songs\)", body)
    date = extract_field(r"日付 \(date\)", body)
    time = extract_field(r"時間 \(time\)", body)
    contents = extract_field(r"コンテンツ種別 \(contents\)", body)
    title = extract_field(r"タイトル \(title\)", body)
    display_pc = extract_field(r"display_pc", body)
    display_sp = extract_field(r"display_sp", body)
    url = extract_field(r"URL \(url\)", body)
    map_val = extract_field(r"マップ情報 \(map\)", body)
    setlistid = extract_field(r"セットリストID \(setlistid\)", body)
    groups_raw = extract_field(r"グループ/メンバー \(groups - カンマ区切りまたは改行区切り\)", body)
    relations_raw = extract_field(r"関連情報 \(relations - JSON配列またはカンマ区切り\)", body)
    tags_raw = extract_field(r"タグ \(tags - カンマ区切り\)", body)

    if not target_type or not date:
        print("必須項目が見つかりませんでした。処理をスキップします。")
        return

    groups = parse_list(groups_raw)
    relations = parse_list(relations_raw)
    tags = parse_list(tags_raw)

    data = {
        "date": date,
        "time": time if time else "0000",
        "contents": contents,
        "title": title,
        "display_pc": display_pc,
        "display_sp": display_sp,
        "url": url,
        "map": map_val,
        "groups": groups,
        "relations": relations,
        "setlistid": setlistid,
        "tags": tags
    }

    queue_dir = f"data/{target_type}/queue"
    os.makedirs(queue_dir, exist_ok=True)

    safe_title = re.sub(r'[\\/*?:"<>|]', "", title) if title else "notitle"
    filename = f"{date}_{time}_{safe_title[:10]}.json"
    file_path = os.path.join(queue_dir, filename)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"JSONファイルを生成しました: {file_path}")

if __name__ == "__main__":
    main()
