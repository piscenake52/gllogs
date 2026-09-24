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
                print(f"警告: メインファイル {main_file} のJSON形式が不正です。空のリストとして初期化します。")
                main_data = []
    else:
        main_data = []

    # 2. キューフォルダ内のJSONファイルを取得
    json_files = glob.glob(os.path.join(queue_dir, "*.json"))
    if not json_files:
        return False

    processed_count = 0
    valid_files_to_remove = []

    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                new_items = json.load(f)
            
            # 辞書型ならリストに変換
            if isinstance(new_items, dict):
                new_items = [new_items]
            elif not isinstance(new_items, list):
                print(f"スキップ: {file_path} の中身がオブジェクトまたは配列ではありません。")
                continue
            
            for new_item in new_items:
                if not isinstance(new_item, dict):
                    continue
                
                # 既存データの中から同じキーを持つ要素を探す（Upsert処理）
                found = False
                for i, existing_item in enumerate(main_data):
                    if is_same_item(existing_item, new_item):
                        main_data[i] = new_item
                        found = True
                        break
                
                if not found:
                    main_data.append(new_item)
                
                processed_count += 1
            
            # 正常に処理できたファイルは削除リストに追加
            valid_files_to_remove.append(file_path)

        except json.JSONDecodeError as e:
            # ★不正なJSON（構文エラーなど）を弾き落としてログに残す
            print(f"【エラー】不正なJSON形式のためファイルをスキップします: {file_path} -> 詳細: {e}")
        except Exception as e:
            print(f"【エラー】ファイルの処理中に予期せぬエラーが発生しました {file_path} -> 詳細: {e}")

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

    # 5. 正常に処理できた個別ファイルだけを削除（不正なファイルは調査用に残す、または安全に処理）
    for file_path in valid_files_to_remove:
        os.remove(file_path)

    print(f"[{target['name']}] {processed_count}件のデータを統合・更新しました。")
    return True

def main():
    updated = False
    for target in TARGETS:
        if process_target(target):
            updated = True
    
    if not updated:
        print("新規に追加された有効なデータはありませんでした。")

if __name__ == "__main__":
    main()
