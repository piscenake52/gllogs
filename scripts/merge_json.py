import os
import json
import glob

TARGETS = [
    {
        "name": "logs",
        "queue_dir": "data/logs/queue/",
        "main_file": "data/logs/logs.json"
    },
    {
        "name": "setlist",
        "queue_dir": "data/setlist/queue/",
        "main_file": "data/setlist/setlist.json"
    },
    {
        "name": "songs",
        "queue_dir": "data/songs/queue/",
        "main_file": "data/songs/songs.json"
    },
]

def process_target(target):
    queue_dir = target["queue_dir"]
    main_file = target["main_file"]

    if os.path.exists(main_file):
        with open(main_file, "r", encoding="utf-8") as f:
            try:
                main_data = json.load(f)
                if not isinstance(main_data, list):
                    main_data = []
            except json.JSONDecodeError:
                main_data = []
    else:
        main_data = []

    json_files = glob.glob(os.path.join(queue_dir, "*.json"))
    if not json_files:
        return False

    added_count = 0
    for file_path in json_files:
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                item = json.load(f)
                if isinstance(item, dict):
                    main_data.append(item)
                    added_count += 1
                elif isinstance(item, list):
                    main_data.extend(item)
                    added_count += len(item)
            except Exception as e:
                print(f"ファイルの読み込みに失敗しました {file_path}: {e}")

    if added_count == 0:
        return False

    try:
        main_data.sort(key=lambda x: (x.get("date", ""), x.get("time", "")), reverse=True)
    except Exception:
        pass

    os.makedirs(os.path.dirname(main_file), exist_ok=True)
    with open(main_file, "w", encoding="utf-8") as f:
        json.dump(main_data, f, ensure_ascii=False, indent=2)

    for file_path in json_files:
        os.remove(file_path)

    print(f"[{target['name']}] {added_count}件のデータを {main_file} に統合しました。")
    return True

def main():
    updated = False
    for target in TARGETS:
        if process_target(target):
            updated = True

    if not updated:
        print("新規に追加されたデータはありませんでした。")

if __name__ == "__main__":
    main()
