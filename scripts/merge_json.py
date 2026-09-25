import os
import json
import glob
import shutil

TARGETS = [
    {
        "name": "logs",
        "queue_dir": "data/logs/queue/",
        "processed_dir": "data/logs/processed/",
        "main_file": "data/logs/logs.json"
    },
    {
        "name": "setlist",
        "queue_dir": "data/setlist/queue/",
        "processed_dir": "data/setlist/processed/",
        "main_file": "data/setlist/setlist.json"
    },
    {
        "name": "songs",
        "queue_dir": "data/songs/queue/",
        "processed_dir": "data/songs/processed/",
        "main_file": "data/songs/songs.json"
    },
]

# ★ date, time, contents, title の4つを一致判定のキーに戻す
UNIQUE_KEYS = ["date", "time", "contents", "title"]
MAX_PROCESSED_FILES = 30

def is_same_item(item1, item2):
    """指定された4つのキーの値がすべて一致するか判定する"""
    for key in UNIQUE_KEYS:
        if item1.get(key) != item2.get(key):
            return False
    return True

def cleanup_processed_dir(processed_dir):
    """processed フォルダ内のファイルを新しい順に並べ、30個を超える古いものを削除する"""
    if not os.path.exists(processed_dir):
        return

    files = glob.glob(os.path.join(processed_dir, "*.json"))
    if len(files) <= MAX_PROCESSED_FILES:
        return

    files.sort(key=lambda x: os.path.getmtime(x))
    excess_files = files[:-MAX_PROCESSED_FILES]

    for file_path in excess_files:
        try:
            os.remove(file_path)
            print(f"古い処理済みファイルを削除しました: {file_path}")
        except Exception as e:
            print(f"ファイルの削除に失敗しました {file_path}: {e}")

def process_target(target):
    queue_dir = target["queue_dir"]
    processed_dir = target["processed_dir"]
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
    successfully_processed_files = []

    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                new_items = json.load(f)
            
            if isinstance(new_items, dict):
                new_items = [new_items]
            elif not isinstance(new_items, list):
                print(f"スキップ: {file_path} の中身がオブジェクトまたは配列ではありません。")
                continue
            
            for new_item in new_items:
                if not isinstance(new_item, dict):
                    continue
                
                # ★ メインデータの中から同じ4つのキーを持つ要素をすべて探す
                matching_indices = []
                for i, existing_item in enumerate(main_data):
                    if is_same_item(existing_item, new_item):
                        matching_indices.append(i)
                
                if len(matching_indices) == 1:
                    # 1つだけ見つかった場合：安全に部分更新（Upsert）する
                    idx = matching_indices[0]
                    main_data[idx].update(new_item)
                    processed_count += 1
                elif len(matching_indices) > 1:
                    # 2つ以上見つかった場合：重複エラーとして安全にスキップ
                    print(f"【警告】date, time, contents, titleが完全に一致するデータがメインファイルに複数存在するため、競合を避けてスキップします: {new_item.get('date')}, {new_item.get('time')}, {new_item.get('contents')}, {new_item.get('title')}")
                else:
                    # 見つからなかった場合：新規追加
                    main_data.append(new_item)
                    processed_count += 1
            
            successfully_processed_files.append(file_path)

        except json.JSONDecodeError as e:
            print(f"【エラー】不正なJSON形式のためファイルをスキップします: {file_path} -> 詳細: {e}")
        except Exception as e:
            print(f"【エラー】ファイルの処理中に予期せぬエラーが発生しました {file_path} -> 詳細: {e}")

    if processed_count == 0:
        return False

    # 3. ソート処理
    try:
        main_data.sort(key=lambda x: (x.get("date", ""), x.get("time", "")), reverse=True)
    except Exception:
        pass

    # 4. メインファイルを更新
    os.makedirs(os.path.dirname(main_file), exist_ok=True)
    with open(main_file, "w", encoding="utf-8") as f:
        json.dump(main_data, f, ensure_ascii=False, indent=2)

    # 5. 処理済みファイルを processed フォルダへ移動
    os.makedirs(processed_dir, exist_ok=True)
    for file_path in successfully_processed_files:
        file_name = os.path.basename(file_path)
        dest_path = os.path.join(processed_dir, file_name)
        
        if os.path.exists(dest_path):
            os.remove(dest_path)
            
        shutil.move(file_path, dest_path)

    # 6. processed フォルダの保持数制限（最大30個）
    cleanup_processed_dir(processed_dir)

    print(f"[{target['name']}] {processed_count}件のデータを統合・更新し、ファイルを processed フォルダへ移動しました。")
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
