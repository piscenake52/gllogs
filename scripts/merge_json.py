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

# 一致判定に使うキーのリスト
UNIQUE_KEYS = ["date", "time", "contents", "title"]

def is_same_item(item1, item2):
    """指定されたキーの値がすべて一致するか判定する"""
    for key in UNIQUE_KEYS:
        if item1.get(key) != item2.get(key):
            return False
    return True

def process_target(target):
    queue_dir = target["queue_dir"]
    main_file = target["main_file"]

    # 1. メインデータの読み込み
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

    # 2. キューフォルダ内のJSONファイルを取得
    json_files = glob.glob(os.path.join(queue_dir, "*.json"))
    if not json_files:
        return False

    processed_count = 0
    for file_path in json_files:
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                new_items = json.load(f)
                if isinstance(new_items, dict):
                    new_items = [new_items]
                elif not isinstance(new_items, list):
                    continue
                
                for new_item in new_items:
                    # 既存データの中から同じキーを持つ要素を探す
                    found = False
                    for i, existing_item in enumerate(main_data):
                        if is_same_item(existing_item, new_item):
                            # 一致する場合は新しい内容で更新（上書き）
                            main_data[i] = new_item
                            found = True
                            break
                    
                    # 見つからなかった場合は新規追加
                    if not found:
                        main_data.append(new_item)
                    
                    processed_count += 1

            except Exception as e:
                print(f"ファイルの読み込みに失敗しました {file_path}: {e}")

    if processed_count == 0:
        return False

    # 3. 日付や時間などのキーがあればソート
    try:
        main_data.sort(key=lambda x: (x.get("date", ""), x.get("time", "")), reverse=True)
    except Exception:
        pass

    # 4. メインファイルを更新
    os.makedirs(os.path.dirname(main_file), exist_ok=True)
    with open(main_file, "w", encoding="utf-8") as f:
        json.dump(main_data, f, ensure_ascii=False, indent=2)

    # 5. 処理済みの個別ファイルを削除
    for file_path in json_files:
        os.remove(file_path)

    print(f"[{target['name']}] {processed_count}件のデータを統合・更新しました。")
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
