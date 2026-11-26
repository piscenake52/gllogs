# GL log 仕様: データ・自動処理

2026-11-27 に SPEC.md から分けた。本文の「上の」「下の」「現行仕様」は、分割前の1つのファイルを指す場合がある。見つからないときは [SPEC.md](../SPEC.md) の一覧からたどる。

## 現行仕様(まとめ。食い違うときは、ここが基準)

### データ・自動処理

#### 処理の流れ(現行)
```
A. Issue(フォーム)      → auto_merge.yml   ─┐
B. helper の send(直接) → data/inbox/*.json → process_queue.yml ─┤→ issue_to_json.py → data/*/queue/*.json
C. queue に JSON を直接 push(手動)         → process_queue.yml ─┘
   → merge_json.py(本体へマージ、queue → processed、manifest・インデックス更新)→ コミット・push
```
- **ワークフロー**: 次の2つが queue を処理する。`auto_merge.yml`(Issue の作成・編集)と `process_queue.yml`(下記の push・手動)。以前あった `merge_queue.yml` と `process-queue.yml`(ハイフン)は削除する。**同じ queue を処理するワークフローを複数置かない**(同時に動いて競合・二重処理になる)。
- **`process_queue.yml`**: `data/{logs,setlist,songs,albums}/queue/*.json` と `data/inbox/*.json` への push、手動(Run workflow)で動く。concurrency は `gllogs-data-merge`(待ち合わせ、キャンセルなし)。PyYAML を入れる。
- **`update_manifest.yml`**: `data/**` の push で `data/manifest.json` を作り直す(`merge_json.py --rebuild-manifest`)。`data/manifest.json`、`data/*/queue/**`、`data/inbox/**` の変更では動かない。
- **push のリトライ**(`process_queue.yml` と `auto_merge.yml`): push に失敗したら、`pull --rebase` はしない(データJSONが競合するため)。`fetch` して `reset --hard origin/<branch>` で最新に合わせ、残っている queue を `merge_json.py` で再処理してから再コミット・再 push(最大5回、待ち時間は 5・10・15… 秒)。`auto_merge.yml` は、Issue から作った queue ファイルが reset で消えるため、処理前に `/tmp/qsnap` へ退避して復元する。別の実行が先に処理済みなら、変更なしで正常終了する。
- **読めない queue ファイル**: `merge_json.py` は終了コード1で終わる(処理できた分は先に保存・コミットされる)。ワークフローは最後に失敗表示にする。読めないファイルは queue に残り、次の実行・手動実行で再試行される。

#### エラーの詳細(`merge_json.py`)
- 標準出力の `【スキップ】` `【警告】` `【エラー】` の行を、どのファイルの何件目かと一緒に記録する(`_Tee` / `REPORT`)。
- JSON の構文エラーは、行・桁・該当行・ヒント(カンマの付け忘れ、余計なカンマ、引用符の閉じ忘れ、`[ ]` で囲む、など)つきで報告する(`explain_json_error`)。UTF-8 で読めないファイル、最上位がオブジェクトでも配列でもないファイル、オブジェクトでない要素、1件の想定外の例外(行番号つき。残りは続行)も報告する。
- 出力: `queue_report.md`(表)と `queue_report.json`(コミットされない)。Actions の Summary にも出す。`auto_merge.yml` は `queue_report.md` を Issue にコメントする。
- 構文エラーなど「読めない」ファイルは queue に残る。中身の一部だけ不正なファイルは、有効な件を適用して processed へ移し、不正な件はレポートにだけ残す。

#### helper からの直接送信(`data/inbox/`)
- helper が `data/inbox/<id>.json` を GitHub の Contents API(PUT)で作る。`<id>` は `YYYYMMDDHHMMSS-xxxx`(日本時間+乱数4文字)。
- 依頼ファイルの形: `{"template": "add_logs.yml", "params": {フォーム項目のid: 値}, "created": "…Z"}`。`params` は、helper が Issue 作成URLに付けていたものと同じ。使えるテンプレートは `add_logs / add_setlist / add_songs / add_albums / add_bulk` の5つ。
- `scripts/inbox_to_json.py`: テンプレートの項目から Issue の本文(`### 見出し` + 値。チェックボックスは `- [X]` / `- [ ]`)を組み立て、`issue_to_json.py` に渡す(Issue と同じ変換)。作られた queue ファイルには、依頼の id を後ろに付ける(同じ秒に複数届いても上書きしない)。
- 結果: `data/inbox/results/<id>.json`(`status` は `queued` → `merge_json.py` のあとの `--finish` で `done` / `error`、`errors`、`notes`、`queue_files`、`skipped`)。`skipped` は、`done` でも反映されなかったものがある(`queue_report.json` の行か `merge_notice.md` がある)ときに true。`merge_notice.md` は同時に処理した全依頼に付く。直近60件だけ残す。依頼ファイル自体は処理後に削除する。
- `.github/ISSUE_TEMPLATE/*.yml` を読むので、リポジトリに置いておく。`scripts/` には `inbox_to_json.py` も置く。
- 削除は、フォームの「DELETE」と同じ(`delete=削除する`)。更新は、Issue と同じく、識別キー(logid など)と変更する項目だけを送る。

#### manifest(`data/manifest.json`)
- 形: `{"files": {"data/logs/logs.json": {"hash": "<sha256の先頭16桁>", "size": バイト数}, …}}`。対象は logs / setlist / songs / albums の本体JSON(インデックスは含まない)。時刻は入れず、内容が同じなら書き換えない(空のコミットが増えない)。`merge_json.py` が毎回(変更がなくても)更新し、`--rebuild-index` でも更新する。
- ビューアは、manifest の hash が前回と同じなら、保存した版をそのまま使う。変わったファイルだけを `raw` から `?v=<hash>` つきで取得し、`size` と一致するか確認する。manifest が取れないときは、これまでどおり API の sha で確認する(フォールバック)。

#### setlist の曲順が分からない曲(順番なし)
- 曲の `order` を持たない曲を登録できる。形式: `-: 曲名`、`?: 曲名`、`: 曲名`(番号を空にする)。1行でも番号なし(`-` / `?` / 空)を書くと、それ以降の番号なしの行は同じ扱いになる(`unordered` の持ち越し)。番号ありの曲のあとに、番号なしの曲を並べて保存する(安定ソート)。
- 更新のパッチ: `+?: 曲名` または `-?: 曲名` で、順番なしの曲を末尾に追加する。タイトルで曲を消す。`?:` での更新は不可(エラー)。
- ビューアのセトリのポップアップ: 番号なしの曲は、番号の代わりに `－` を出し、最後に並べる。すべて番号なしのセトリは、「曲順不明」のチップを出す。
- helper(setlist): 曲の欄の番号を空にできる(`noOrd`)。解析・整形・値の比較も番号なしに対応。

#### logs の `venue`(会場名)
- logs に任意の項目 `venue` を追加(`url` と `map` の間)。専用の項目で、tags には入れない。フォーム `add_logs.yml` に `venue` 欄(値の削除の選択肢にも追加)。`issue_to_json.py`(`LABELS_LOGS` / `CLEARABLE` / `build_logs`)と `merge_json.py`(項目の並び)に追加。更新・`!clear`・COPY の扱いは他の項目と同じ。
- 軽量インデックス `logs_index.json` にも `venue` を入れる(helperの候補用。`tags` と同じ行の条件)。
- 繰り返し登録のtourの行: 1行の書式は `日付 時刻 | タイトル | contents | URL | display_sp | map | setlistid | tags | venue`(末尾に venue の列を追加。以前の書式のまま使える)。最大列数は8。
- **setlist への反映**(`merge_json.py` の `sync_venue`。すべての target の処理が終わったあとに実行):
  - logs の行(ref の行は除く)の `venue` または `setlistid` が処理の前後で変わり、`setlistid` があるとき、同じ `setlistid` の setlist の `venue` を**常に上書き**する(複数の logs が同じ setlist を指すときは、新しい日付の行を優先)。
  - logs の `venue` を空にした(消した)ときは、setlist の `venue` も消す。
  - setlist を新規登録したとき(その `setlistid` が処理の前にはなかった)、setlist 側に `venue` がなければ、結びついた logs の `venue` を初期値にする。同じ処理の中で setlist の `venue` を入力した場合は、logs の変更があればそちらが優先。
  - 反映は venue から venue だけ。tags からは引き継がない。setlist の検索用インデックスも更新する。失敗しても、ほかの処理結果は残し、原因をレポートに出す。

#### データの項目・入力

- **songs.json に `vocal`(任意・自由入力)**: 歌唱メンバー・ユニット名など。キーは従来どおり `artist` + `title`(vocalはキーではない)。例: artistは `Girls²`、vocalは `○○`。
  - Issueフォーム `add_songs.yml`: `vocal` 欄(artistの下)と、「値の削除(更新時)」の `vocal` を追加。
  - `issue_to_json.py`: ラベル `vocal` を読み、songsのレコードに入れる(`CLEARABLE` の songs に `vocal`)。`merge_json.py`: songs の項目の並びは `artist, vocal, title, link, lyrics, videos`。
  - 更新: 入力した項目だけ上書き(空欄は変更しない)。消すときは「値の削除」または `!clear`。`videos` は入力すると丸ごと置き換わる。曲の削除は `DELETE`。
  - helper(songs)のvideos入力: 上から、追加する動画の編集欄 → typeのチップ → `videos links (登録件数)` ボタン → 登録済みの動画。送る書式は `type | url | tags` のまま。
    - typeのチップの並び: MV / Dance Practice / Performance / Lyric / Live / Reaction / Call Lecture / Etc / Fancam(動画ポップアップの表示順と同じ。Etcはtypeが空)。
    - 追加した動画: チップ(✎ × ↗)は出さず、編集欄だけ(1行目に type・tags、2行目に url。url が http(s) のときは欄の中の ↗ で開く)。url欄の右の ✕ で削除する。
    - 登録済みの動画: `videos links` ボタンで開閉する(曲を読み込んだ直後は閉じる)。1動画1チップで、本体か✎で編集行を開閉 / ×で取り消し線(↩で元に戻す) / ↗で新しいタブで開く。YouTube以外のURLか、空のurl(削除指定していないもの)があるときは自動で開く。
    - ボタンの件数は登録済みの数。追加は `+n`、削除指定(取り消し線)は `-n` を付ける。
    - 送る順は 登録済み → 追加分(画面での並べ替えはない。↑↓ボタンは2026-11-26に削除)。別の曲に変えると登録済み側は読み直し(未送信の編集は破棄)、追加分は残る。id欄の候補を選ぶか `new` で追加分も消える。残る動画がないときは `!clear`(全削除)。追加した動画でurlが空の行は送らない。登録済みの動画のurlを空(空白だけを含む)にしたときは、削除ではなく入力エラーとして、url欄とチップを赤枠にし、`songs` と `send` の両方のボタンを出さない(他の項目の変更も送れない)。×で削除指定した動画は、urlが空でも送れる。YouTube以外のURLがあるときも送信できない。
  - 同じ曲かどうかは `artist` と `title` の完全一致で決まる。artist / title を変えると別の曲(新規)になり、元の曲は残る(名前の変更は旧データを `DELETE` して登録し直す)。
- **snsの type 自動補正**(`issue_to_json.py`): `type | url` で type を明示しても、それが `site` か `etc` で、URLのドメインが X / Instagram / YouTube / TikTok / CL / radiko / GL²family と判定できるときは、その種類にする。type 自体を省略したときの自動判定は従来どおり(判定できなければ `etc`)。
- **共通部品 `common.py`**: `is_blank` / `album_type_ok` / `map_from_html`(`<iframe src>` の埋め込みHTMLを地図URLに直す。`&amp;`→`&`)。`issue_to_json.py` と `merge_json.py` が `from common import ...` で使うため、Actionsでは **`common.py` と `schema.json` を、スクリプトと同じ場所(`scripts/`)に置く**(`schema.json` は項目の定義。「保守のための仕組み」を参照)。
- **map の入力**: Googleマップの地図URL・埋め込みHTML(`<iframe ...>`)のどちらも入れられる(logsのmap、繰り返し登録のtourの行のmap)。保存時は地図URLにそろえる。ビューア側も埋め込みURLとiframeの両方を受け付ける。

#### 保守のための仕組み(テスト・事前チェック・項目定義)

- **`scripts/schema.json`**: 項目の定義を集めたファイル。`logs` `setlist` `songs` `albums` それぞれの `order`(保存時の項目の並び)・`key_fields`(識別キー)・`index_fields`(インデックスに入れる項目)・`clearable`(更新時に「値の削除」で消せる項目)と、フォームの項目名 `labels_logs` / `labels_ss`。`common.py` が読み込み(`SCHEMA`)、`issue_to_json.py` と `merge_json.py` はそこから値を取る(コード中の直書きをやめた。値は従来と同じ)。
- **`scripts/check_repo.py`**(事前チェック): ①data のJSONが読めるか(queue・inbox は除く) ②`add_logs.yml` `add_setlist.yml` `add_songs.yml` の項目名が `LABELS_*` と一致するか、「値の削除」の選択肢が `clearable` と一致するか ③`schema.json` の整合(識別キー・消せる項目・インデックス項目が `order` に含まれる、重複がない)と、helper の `DEFS` に logs / setlist の編集できる全項目があるか ④`merge_json.py`(`--rebuild-index` `--rebuild-manifest` なし)を実行するワークフローが `auto_merge.yml` と `process_queue.yml` だけか。問題があれば終了コード1。
- **`tests/`**(`unittest`。`python -m unittest discover -s tests -v`): `helpers.py`(一時フォルダにリポジトリと同じ並びを作り、本物のスクリプトを実行する)、`test_pipeline.py`(logs の新規・更新・削除・繰り返し・インデックス・マニフェストの安定、setlist の曲順なし・個別変更、venue の同期4種(上書き・消去・新規setlistへの引き継ぎ・タグからは引き継がない)、読めないJSONのエラー報告と他ファイルの処理継続、inbox の登録・入力エラー・不正テンプレート・同時刻の依頼・`skipped` の判定)、`test_check_repo.py`(事前チェックが問題を見つけられるか)。計30件。`tests/test_viewer.py`(ビューアをブラウザ(Playwright + Chromium)で開き、通信はモック・日付は固定で確認する。axe-core によるアクセシビリティ検査を含む。37件)と、`tests/test_helper.py`(helper を同じ方法で開き、send の内容を本物の `inbox_to_json.py` → `merge_json.py` に通して登録結果まで確認する。起動、logs、repeat、告知文の読み取り、songs の videos、setlist。albums・bulk・check・token の暗号化・find の候補は対象外。27件)があり、合計94件。
- **`.github/workflows/tests.yml`**: scripts・tests・.github・helper・index.html の変更、PR、手動で動く。`test` ジョブ(事前チェックと unittest)、`viewer` ジョブ(`tests.test_viewer`。Playwright・axe-core を入れて実行)、`helper` ジョブ(`tests.test_helper`)の3つ。data の更新では動かない。権限は contents: read のみ。
- **`.github/workflows/pages.yml`**: helper・`tests/test_helper.py`・`pages.yml` の main への push と手動で動く。`test` ジョブ(事前チェックと helper のテスト)が通ったときだけ、`deploy` ジョブが helper にページの外枠(doctype・charset・viewport・noindex)を付けて GitHub Pages に公開する。失敗したら公開中のページはそのまま。公開するのは helper のページだけ。
- **項目を足す手順**は README の「テストと事前チェック」にある。
- 検証状況: ローカルで95件(1件 skip)、GitHub Actions の `Tests` と `Publish helper` の成功を確認した(2026-11-26、`fb76b8d`)。2026-11-27 に ASCII の検査とそのテスト1件を削除した。

## 機能ごとの詳細メモ

## 追記3: データ登録の仕組み(Issue → JSON → サイト)と helper

### 全体の流れ

```
GitHub Issue(フォーム) → Actions(auto_merge.yml)
  → scripts/issue_to_json.py(フォームの本文をキュー用JSONに変換)
  → scripts/merge_json.py(本体のJSONにマージ。処理済みはprocessedへ)
  → data/ をコミット → index.html が読む(`data/manifest.json` で変わったファイルを判定し、jsDelivr(コミット固定)/ raw.githubusercontent.com から取得。manifest が使えないときは、GitHub API でコミットSHAを確認する)
```

※これはIssue経由の基本の流れ。helperの直送・queueへの直接pushを含む現行の流れと、manifest の仕様は、冒頭「現行仕様」の「処理の流れ(現行)」「manifest」を参照。

| ファイル | 役割 |
|---|---|
| `.github/ISSUE_TEMPLATE/add_logs.yml` | logs(日程・ログ)の登録・更新・削除フォーム |
| `add_setlist.yml` | setlist(セットリスト)のフォーム |
| `add_songs.yml` | songs(楽曲リスト。再生リンク用)のフォーム |
| `add_albums.yml` / `add_bulk.yml` | albums(アルバム)のフォーム / 一括更新(tag add など)のフォーム。helperの直送で使えるテンプレートは、add_logs / add_setlist / add_songs / add_albums / add_bulk |
| `.github/workflows/auto_merge.yml` | Issueが`opened`/`edited`されたら変換とマージを実行 |
| `process_queue.yml` | `data/*/queue/*.json` と `data/inbox/*.json`(helperの直送)への push、手動で、変換・マージ・コミットを実行(「現行仕様」を参照) |
| `update_manifest.yml` | データの手動編集の push で `data/manifest.json` を作り直す |
| `tests.yml` | scripts・tests・.github・helper の変更、PR、手動で、自動テストと事前チェックを実行 |
| `rebuild_index.yml` | 手動実行。helper用の軽量インデックス(`logs_index.json`/`setlist_index.json`)を作り直す |
| `check_gaps.yml` / `check_gaps.py` | 毎週月曜 03:30(JST)と手動。logsのタイトルの`#数字`の連番の抜けを調べ、Issueに報告する(2回目以降はIssueの本文を上書き) |
| `pages.yml` | helper のテストが通ったら GitHub Pages に公開する(「現行仕様」を参照) |
| `helper.html` | 入力補助ページ(GitHub Pages で公開) |

- **処理対象のIssue**: `data`ラベル付き(または旧形式のタイトル`[DATA]`)で、投稿者がリポジトリの OWNER / MEMBER / COLLABORATOR のものだけ。
- **同時実行**: データ更新・インデックス再作成は同じconcurrencyグループ(`gllogs-data-merge`)で直列に実行し、コミットの衝突を防ぐ。
- **入力エラー**: `issue_to_json.py`が`issue_error.md`を出し、Issueにコメントして処理を中止する。編集すると再処理される。
- **通知**: 削除対象が見つからなかった等は`merge_notice.md`としてIssueにコメントする。
- **Issueの再編集**: `data/issue_map.json`(Issue番号→logid)で、同じIssueを編集したときは同じログを更新する(新規にならない)。
- **値の削除**: 更新時、空欄は「変更しない」。消したい項目はフォームの「値の削除(更新時)」にチェックする(内部では`!clear`)。
- **DELETE**: 「削除する」にチェックするとそのデータを削除する。
- **COPY**: コピー元のIDを指定して新規登録する。入力した項目だけ上書きし、空の項目はコピー元を引き継ぐ。

### ANNIVERSARY(参照型・logsのみ)
- **登録**: フォームの「ANNIVERSARY」にチェック(または「ANNIVERSARY / 文字入力」に`ANNIVERSARY`)すると、元データの登録・更新と同時に、参照型のANNIVERSARYを1件作る。作られるのは`logid / date / contents=ANNIVERSARY / ref=元のlogid`だけ(timeは空)。すでに参照しているものがあれば作らない(重複しない)。
- **付与文言(suffix)**: タイトルの後ろに「半角スペース+文言」を付けて表示する。フォーム「ANNIVERSARY / 付与文言」(空なら`記念日`)で、ANNIVERSARYの`suffix`に保存する。helperでは「anniv.」の行にチェックと文言の入力欄(初期値`記念日`、チップ: 記念日 / 出演記念日 / 放送記念日)が出る。すでに参照している元データでは、文言を変えて送るとANNIVERSARY側の`suffix`だけ更新する。
- **使えない場合**: 元データのcontentsがANNIVERSARY / BIRTHDAYのとき、繰り返し登録のときはエラー(helperではチェックが無効になる)。
- **表示(index.html)**: 読み込み時に`ref`を解決する。自分の値があればそちらを優先。`title / display_pc / display_sp`は元の値+半角スペース+`suffix`(無ければ「記念日」)(元に値があるときだけ)。`url / groups / relations / tags / sns`は元の値を使う。`map / setlistid`は参照しない。参照元が無いデータは表示しない。
- **連動**: 元データのdateを変えるとANNIVERSARYのdateも合わせる。元データを削除すると参照しているANNIVERSARYも一緒に削除し、Issueに通知する。参照されている元データのcontentsをANNIVERSARY / BIRTHDAYに変えることはできない。
- **index**: `logs_index.json`に`ref`を持つ。参照型のtitleは元のtitle+「 記念日」に解決して入れる。
- **helper**: 「ANNIVERSARY」チェック。すでに参照されている元データではON固定(送らない)。
- **groups**: 参照型には既定の`G2, L2`を入れない(元の値を使う)。

### logs / setlist のデータ形式(抜粋)

logs(1件): `logid, date, time, contents, title, display_pc, display_sp, url, map, groups, relations, setlistid, tags, sns`

```json
{ "logid": "a1b2c3d4e5f6", "date": "20261016", "time": "1200", "contents": "TICKET",
  "title": "...", "groups": ["G2","YZH","L2"], "setlistid": "202610161200",
  "tags": ["..."], "sns": [{ "type": "x", "urls": [{ "url": "https://x.com/...", "member": ["YZH","MMK"] }] }] }
```

setlist(1件): `setlistid, artist, member, title, venue, songs`

```json
{ "setlistid": "202610161830", "artist": "Girls² × Laki", "member": ["G2","L2"], "venue": "...",
  "songs": [{ "order": 1, "title": "曲名", "type": "song", "original": "", "notes": "", "member": ["YZH","MMK"] }] }
```

- `time`は4桁(`HHMM`)。**空欄は「時刻なし」**(`0000`には補完しない)。
- `setlistid`は12桁(`YYYYMMDDHHMM`)。logsの`contents`が`LIVE`/`TOUR`/`ANNIVERSARYLIVE`/`RELEASEEVENT`/`FANMEETING`で`setlistid`が未入力なら、`date`+`time`で自動入力する。
- `songs[].member`は曲ごとの歌唱メンバー(省略=全員)。

### グループ・メンバーの登録仕様(すべての入力箇所)

**基本の考え方**: 「G2」「L2」は、グループだけを選んだとき=そのグループの全員、個別メンバーも選んだとき=選んだメンバーだけ(グループ名は登録しない)。ただし logs の groups は、グループのコード(G2/L2)そのものもデータに持つ。

G2のメンバー: `YZH, MMK, MSK, YOK, KUR, MNM, KIR`(展開されるのはこの7人)。選択肢にはほかに`TOA, RAN`があり、これは**個別メンバー扱い**(G2と一緒に選んでも、7人には展開しない)。L2のメンバー: `RIN, TBK, HIR, YUW, KAN, RRK, AKR, KIK`(展開される8人)、ほかに選択肢`YUR`(個別メンバー扱い)。

| 入力箇所 | 入力方法 | 登録される内容 |
|---|---|---|
| **logs の groups** | ドロップダウン | G2またはL2だけ選ぶとそのグループの全員に展開(`G2`+7人)。個別メンバーも選ぶと選んだものだけ(メンバーがいれば`G2`/`L2`のコードを自動で足す) |
| | 自由入力(helperのチップもここ) | 入力した値のまま。展開しない(`G2`だけなら`["G2"]`)。メンバーがいれば`G2`/`L2`のコードを自動で足す |
| | STFにチェック | 選んだ内容に`STF`を足すだけ。展開しない |
| | 何も入力しない(新規のみ) | snsにmemberがあればそのメンバーのグループ、なければ`G2, L2` |
| **logs の relations** | ドロップダウン | 選んだメンバーだけ(選択肢にG2/L2はない) |
| | 自由入力 | `G2`/`L2`だけなら全員に展開。同じグループの個別メンバーも書けばそのメンバーだけ |
| **logs の sns の member** | `type \| url \| member` の`member`(helperのチップもここ) | `G2`/`L2`だけなら全員に展開。個別メンバーもあればそのメンバーだけ。`G2`/`L2`の文字は保存しない。登録後、snsのmemberは`groups`に足される(外れても`groups`からは外さない) |
| **setlist の member** | ドロップダウン | G2/L2だけなら全員に展開。個別メンバーも選べばそのメンバーだけ。`G2`/`L2`の文字は入らない |
| | 自由入力(helperのチップもここ) | 入力した値のまま |
| | 何も入力しない(新規のみ) | artistが`Girls²`なら`["G2"]`、`Laki`なら`["L2"]`、`Girls² × Laki`なら両方。それ以外のartistはmemberを作らない |
| **曲ごとの歌唱メンバー** | 曲名の直後の `{YZH,MMK}`(helperのチップもここ) | `G2`/`L2`だけなら全員に展開、個別メンバーもあればそのメンバーだけ。`{-}`は指定を消す。省略=全員扱い(ハートを出さない) |

共通ルール(`expand_group_codes`): グループ名と同じグループの個別メンバー(`TOA/RAN/YUR`を含む)が一緒に書かれたら、グループ名は捨てて個別メンバーだけにする。ドロップダウンと自由入力があるときは**ドロップダウンが優先**(ドロップダウンが空のときだけ自由入力を使う)。

### setlistのsource(OFFICIAL / UNOFFICIAL)
- **データ**: `setlist.json`の`source`。`"official"`(公式の情報)/`"unofficial"`(ファンメイド)。分からないときは**項目なし**(初期値は空)。
- **入力(Issue)**: `source`欄に`OFFICIAL`か`UNOFFICIAL`(保存値は`official` / `unofficial`。それ以外の表記はエラー)。空は「変更なし・不明」。消すときは`!clear`、または「値の削除」で`source`。それ以外の値はエラー。
- **helper(setlistタブ)**: venueの下に`OFFICIAL` / `UNOFFICIAL`の2つのチップ(どちらか一方。押すと選択、もう一度押すと解除。初期値は両方オフ)。登録済みのsetlistは現在の値で点灯する。点灯中のチップを消すと、`!clear`が送られる。新規・コピーでも同じ。
- **index.html(セトリポップアップ)**: 曲リストの上に、OFFICIAL(青)またはUNOFFICIAL(グレー)のチップを出す。`source`が無いときは何も出さない。

### 曲目の書式(setlist)

1行1曲: `[順番:] 曲名 {メンバー} | type | original | notes`

- 順番を省略すると前の曲+1(先頭は1)。typeを省略すると`song`。空にしたいときは`-`
- `type`はカンマ区切りで複数指定できる(例: `allow,medley`)。`song`はバッジに出さない。使えるtype: `arrange` / `medley` / `mc` / `dt` / `dj` / `towel` / `encore` / `allow` / `cover`(helperのチップも同じ。ポップアップのバッジは大文字、allowは「撮影可能」)
- 曲名の直後の`{YZH,MMK}`が歌唱メンバー(上の表)
- 個別変更(1行1操作): `N: 曲名 {メンバー} | type | original | notes`(N番を部分更新。空欄・省略は今のまま、`-`は空にする。`{-}`でメンバー指定を消す)、`+N: 曲名 | ...`(N番に挿入。N番以降は1つ後ろへ)、`-N: 曲名`(N番を削除。曲名を書くと一致したときだけ)、`N>M: 曲名`(N番をM番へ移動。間の曲は1つずつずれる)。メンバーだけの変更もできる

### sns の書式

1行1件: `type | url | member`。`type | url`、`url | member`、URLだけでもよい。`-URL`でそのURLだけを削除する。同じtypeは1つにまとめ、同じURLは重ねずmemberを新しい値で上書きする。更新時は上書きせず、既存の値に新しいものだけ追記する。

- **typeの自動判定**(`SNS_HOSTS`): `x.com`/`twitter.com`=x、`instagram.com`、`youtube.com`/`youtu.be`、`tiktok.com`、`cl-live.com`=cl、`radiko.jp`=radiko、`girls2-fc.jp`=gl2family。サブドメインも一致する。判定できないURLは`etc`。偽装(`instagram.com.example.com`、`x.com@example.com`)は一致させない
- `threads`/`line`は自動判定の対象外。使うときはテキスト欄に`threads | https://...`のようにtypeを直接書く
- **helperのsns入力補助**: URL欄+メンバーチップ+`add`ボタン。**typeのプルダウンは無い**(typeはサーバー側の自動判定。すでにある行を置き換えるときは、その行のtypeを残す)。G2/L2チップはメンバー行の表示切替で、G2/L2だけをONにして`add`すると`url | G2`の行になり全員に展開される。個別メンバーも選ぶとメンバーだけが書かれる。`add`すると、チップも含めて入力はリセットされる

### snsのwith(同写り)と、ALL / POST表示
- **データ**: `sns[].urls[]`に`with`(配列。無くてもよい)を持てる。`member`=投稿者、`with`=投稿者と一緒に写っている人。`{"url":"…","member":["YZH"],"with":["MMK","KUR"],"tags":[…]}`。既存データ(`member`のみ)は、そのまま「投稿者のみ」として読める(移行不要)。投稿者がメンバーでない(公式アカウントなど)リンクは、`member`を空にして`with`だけを持てる。
- **書式**: sns欄のmember欄の`+`の左が投稿者、右が同写り。`YZH+MMK,KUR`(投稿者YZH、同写りMMKとKUR)、`+MMK`(投稿者なし、同写りのみ)、`YZH+-`(既存の同写りを消す)。`+`が無ければ、これまでどおり投稿者のみ。G2 / L2だけを書くとそのグループ全員(memberと同じ展開)。
- **groups**: with のメンバーも member と同様に、その行の`groups`に足される(G2 / L2コードの自動追加も同じ)。
- **helper**: sns入力補助と、リンクごとの✎編集欄で、memberのチップとwithのチップを分けて入力する。テキスト欄には`member+with`の形で書き込まれる(双方向に同期)。
- **index.html(SNSポップアップ)**: ランプは従来どおり右上基準の並び。member(投稿者)の丸が先、with(同写り)の四角(丸と同じ大きさ)がそれに続く。列数は、表示するランプの合計で決める(1個=1列、9個以上=3列、それ以外=2列)。メンバーフィルターは、memberとwithのどちらかが一致したリンクを残す。ホバー表示(title)は出さない。
- **ALL / POSTスイッチ**: ポップアップの左下。ALL=丸と四角の両方、POST=丸(member)のみ(四角を消し、丸の個数で並びを組み直す)。ラベルも切り替わる。状態は`localStorage`(`snsScopeMode`)に保存し、初期値はALL。右下のTAGスイッチとは独立。

### snsのリンクごとのtags
- **データ**: `sns[].urls[]`に`tags`(配列。無くてもよい)を持てる。`{"url":"…","member":["YZH"],"tags":["挨拶","ライブ配信"]}`
- **入力**: `type | url | member | tags`(tagsはカンマ区切り。memberを飛ばすときは`x | https://… | | 挨拶`)。`url | member | tags`も可。同じURLを入れ直すと、tagsは新しい入力があれば置き換え、空なら既存を残す
- **検索(index.html)**: 検索の対象に各リンクのtagsを加える。リンクのtagsに当たったデータもヒットする
- **🔗ポップアップ**: 検索語(タグ・キーワード)ではリンクを絞らず、常に全リンクを出す(以前はリンクのtagsに当たったリンクだけにしていたが廃止)。メンバーフィルターだけは、選んだメンバーを**どれか**持つリンクだけを出す(どのリンクも当たらなければ全リンク)。番号は元のまま、メンバーのランプもそのまま出す。ポップアップ内のタグチップ(`.tag-chip`)を押すと、データ部のチップと同じく今の絞り込みを外してそのタグで検索し、ポップアップは閉じる
- **tagsを消す**: tags欄に`-`だけを書くと、既存リンクのtagsをすべて消す(`x | https://… | YZH | -`)。新しいtagsを書けば置き換え。何も書かなければ既存を残す。保存時、空のtagsは持たない
- **helper**: snsの入力欄に`tags`欄(入力した文字から、過去に使われたtagsを候補表示)。リンクごとの✎編集欄でも同じ。各リンクの下に、そのリンクのtagsを**チップ**で出し(`tag ×`)、押すとそのtagだけを外す(最後の1つを外すと`-`が書かれる)。登録済みリンクのボタンには`#tag`を出す

### 繰り返し登録(新規のlogsのみ)

1行1回、最大60件(`REPEAT_LIMIT`)。書式:

```
YYYYMMDD [時刻] [| タイトル [| contents [| URL [| display_sp]]]]
```

- 日付は`YYYY/MM/DD`・`YYYY-MM-DD`でもよい。時刻は`HHMM`/`HH:MM`、`-`(時刻なし)。時刻を省略するとフォームの時刻を使う
- `|`が1つだけのときは、その後ろ全部がタイトル(従来どおり)。`|`が2つ以上のときは「タイトル | contents | URL | display_sp」の順で、どれも空欄ならフォームの値を使う(display_spは空欄なら付けない)
- 行にタイトルがなければ、最初の回のタイトルの`#数字`を回ごとに+1する(ゼロ埋めは保つ)
- フォームの`url`/`sns`は全回に引き継ぐ。`display_pc`/`display_sp`は、行にtitleがあればフォームのtitleより後ろの部分(締切・地域名など)を足し、なければtitleと同じく`#数字`を回ごとに+1する。行に`url`/`display_sp`の指定があればそれを優先する。フォームで空にした項目は付けない。`map`は引き継がない(通知はしない)
- 同じIssueの再編集は、前回の登録分を同じ順番で更新し、増えた回は追加、減った回は削除する。すでに同じ`date+time+contents+title`の行があるときは、その回は登録しない
- groups / relations / tags などの、ほかの項目はフォームの値を全件に使う

## リンク切れチェック(link_check.py / link_check.yml)

- GitHub Actions が毎日 03:00(JST)に、logs.json の `url` / `map` を少しずつ確認する(手動実行も可。件数は `limit` で変えられる)。結果は `data/logs/link_state.json`(全URLの状態)と `data/logs/link_report.json`(切れだけ)に保存され、helper の check タブ `link broken` が読む。
- 通常の閲覧・運営に影響しないための制限: 1回 250 件(ワークフローと `link_check.py` 単体で共通の既定)・25 分まで / 確認の間隔 1 秒(ブラウザ) 0.5 秒(それ以外) / ブラウザでは画像・動画・フォント・CSS を読み込まない / 毎日の夜間のみ。確認が古い順に回るので、全件が一巡するまで数十日かかる。`url` を直した行は未確認として優先して確認される。
- 判定方法: 
  - girls2-fc.jp/page/...: 画面なしの Chromium で開き、最大 8 秒待つ。記事のタイトルが出れば ok、サイト共通のタイトル(`Girls²(ガールズガールズ)...`)のまま、またはトップへ遷移したら NG。
  - YouTube(watch / youtu.be / shorts / live): oEmbed で 404 なら NG(401/403 は判定不能)。
  - Google マップ短縮(maps.app.goo.gl): 転送先が Google なら ok、404 なら NG。
  - その他のサイト: 404 / 410 / ドメインなしなら NG、200〜399 は ok、それ以外は判定不能。
  - 対象外: Instagram / TikTok / X / cl-live.com / Facebook / LINE と、girls2-fc.jp の /page/ 以外。
- 最初に NG だったものは、同じ実行の最後(60 秒後)にもう一度確認し、続けて NG のときだけ「切れ」にする。
- 一覧の `ignore` はこの端末の記憶のみ。url を直すと、次回の確認で一覧から消える。
- 事前調査用の `link_probe.py` / `link_probe_browser.py`(と各 yml)は、本番のチェックができたので不要。

## albums(収録曲・各種盤) 💽
- データ: `data/albums/albums.json`(配列)。1件=1リリース。キーは `title` + `type`(`album` / `ep` / `single` / `musiccard`。表示は MUSIC CARD)。
  `{ "title", "type", "date": "YYYYMMDD", "tracks": [{"no": 1, "title": "曲名"}], "editions": [{ "name", "format", "price", "note", "extra": [{"no": "DVD1", "title": "曲名"}], "tracks": [...] }] }`
  - `tracks` は共通の収録曲。盤の `extra` はその盤だけの追加曲(`no` は自由なラベル)。盤に `tracks` があるときは、共通の収録曲の代わりにそれを使う。
- 登録: helper の albums タブ → `add_albums.yml`([DATA] albums) → `issue_to_json.py`(`build_albums`) → `merge_json.py`(target `albums`)。削除は同じフォームで「削除する」にチェック(titleとtypeだけ入力)。空にした date / tracks / editions は `!clear` で消える。
- データ部の💽: contents が CD・DVD・BD・MUSICCARD・RELEASE・EP(EPはRELEASEのグループに加えた)の行で、🔗の左に出す。常に表示(ダブルタップの条件なし)。
  - 名前: 行のタイトルの「」(なければ『』)内(半角の｢｣や全角英数字は、NFKCで全角の「」・半角英数字にそろえて見る)。種別: タグ(完全一致)かデータ文の独立した語(ALBUM/AL=album, EP=ep, SINGLE/SG=single, MUSICCARD・MUSIC CARD=musiccard)。見つかった種別と一致するものだけ。種別が無い行は、名前が一致するものすべて(複数なら ポップアップ上部の種別チップで切り替え)。albums.json が無い・一致が無い行は出さない。
- ポップアップ: 種別チップ / リリース名・種別・発売日 / 盤チップ(ALL・各盤)と盤の情報(形態・価格・メモ) / 収録曲(曲順、盤の追加曲は水色のラベル、披露回数)。曲を押すと📊の披露実績。閉じると収録曲に戻る。
- helper(albums): find(既存を選んで編集) / title / type / date / tracks(1曲1行、候補は押して選ぶ、Enterは候補が出ていないときだけ次の行、↑↓=up/down、undo、貼り付け replace/append) / copy(他のリリースの収録曲をコピー) / editions(盤名・形態・価格・メモ・追加曲・own tracklist)。songs.json に無い曲名は赤+候補。URLが7500字を超えると送信不可(盤を分ける)。

### albums の id と logs の albumid
- albums の各盤は12桁の英数字(0-9 a-f)の `id` を持つ。logs の行は `albumid`(1行に1つ)でその盤を指す。両方に持たせて紐づける
- id は helper が新規入力時に採番する(空なら merge_json.py が採番。id の無い既存の盤は、次の更新で自動採番)
- albums フォーム(add_albums.yml)に `album id` と `logids`(紐づける logid、1行に1つ)を追加。1つのIssueで albums.json の登録 / 更新と、logs.json の albumid の書き込みを同時に行う(merge_json.py)
  - `logids` に載せた行に albumid を設定し、載っていない行の albumid は外す。`logids` が空なら紐づけをすべて外す
  - 盤の削除では、その albumid を持つ全 logs 行の albumid も消す
  - 更新は id 優先。id が一致すれば title / type を変えても同じ盤を更新する。変更後の title+type が別の盤と重なる場合は何もしない。id が無いIssueは従来どおり title+type で判定する
- logs の index(logs_index.json)に albumid を含める。merge_json.py を差し替えたら `--rebuild-index` で作り直すこと
- helper(albums タブ): id 表示、紐づける logs を1行ずつ表示(追加は logid か title の候補、x で外す)。find 欄に logid を入れると、その行の盤を開く(未紐づけならその行から新規入力)
- helper(logs の行): contents が CD / DVD / BD / MUSICCARD / RELEASE / EP / DIGITAL の行に albums ボタン。albumid があればその盤を開く(なければ従来の「」内の名前での紐づけ)
- index.html の💽: albumid を持つ行はその id の盤を開く(contents は問わない)。albumid が無い行は従来の名前での紐づけ(albumid の運用確認後に廃止予定)

### albums: artist / format / extra disc / ALL廃止、helper: sns折りたたみ
- albums.json の盤に `artist`(任意の文字列。Girls² と Laki の両方は「Girls² × Laki」)を追加。helper の albums タブに入力欄とチップ。logs 行から新規入力を開くときは groups(G2のみ / L2のみ / 両方)から推定。viewer の収録曲ポップアップは artist / type / 日付を並べて表示
- 盤の `format`: 自由入力とチップ(CD / DVD / BD の複数選択、CD+DVD の形、並びは CD・DVD・BD の固定)
- extra(追加ディスク): helper ではディスクごとの枠(ディスク名 + 曲目)。保存する番号は「ディスク名 + 順番」(DVD1, DVD2 ...)で、データの形は従来のまま
- viewer: 盤のチップの先頭の「ALL」を廃止。盤があるときは先頭の盤が初期表示。盤が無いときは共通の曲目を表示(データの構造は変更なし)
- helper の logs: sns の自由入力欄と表示チップは初期表示で折りたたみ(「sns links (件数)」ボタンで開閉)。自由入力欄の初期の高さは従来の半分

### setlistid の自動付与

- date+time が揃っている行で setlistid が未設定のとき、contents が LIVE / TOUR / ANNIVERSARYLIVE / RELEASEEVENT / FANMEETING なら date+time(12桁)を自動で付ける(merge_json.py の SETLISTID_CONTENTS)。登録できる contents に EP を追加(RELEASE 扱い)。

### albums の type(自由入力)

- helper の type は自由入力欄+チップ(album / ep / single / mu-ca / digital / dvd / blu-ray)。入力は小文字・前後の空白なしに正規化する(入力欄に候補は出さない)。
- パイプライン(issue_to_json.py / merge_json.py)は 1〜30文字(改行と | は不可)の小文字なら受け付ける。上の7種は候補であって制限ではない。

### songs の歌詞リンク(📜)

- songs.json の各曲に任意項目 `lyrics`(uta-net の曲ページURL。`https://www.uta-net.com/` から始まるものだけ)。Issueフォーム(add_songs.yml / add_setlist_songs.yml)に `lyrics` 入力と「値の削除」の選択肢を追加。issue_to_json.py は uta-net 以外のURLをエラーにする。merge_json.py の songs の項目順は artist / title / link / lyrics。
- ビューア(index.html): 📜 を曲紹介バー(♪)・アルバムポップアップ・セトリポップアップの各曲に表示(披露実績📊の左、常に表示。セトリの mc / dt / dj / towel の行は空き)。押すと新しいタブで開く。`lyrics` があればその曲のページ、なければ曲名で uta-net を検索するページ(`https://www.uta-net.com/search/?Aselect=2&Bselect=4&Keyword=曲名`)。
- helper(songs): `lyrics` 欄(入力・開く・✕)と「search」ボタン(曲名で uta-net の検索を新しいタブで開く)。uta-net 以外のURLは赤枠でIssueリンクが無効。曲を選ぶと既存の `lyrics` が入る。
- helper(check): 「songs without a lyrics link」(info・ignore可): `lyrics` が無い曲の一覧。各行に「search」(uta-net検索)と「open」(songsタブで開く)。
- 検索URLのパラメータ(Aselect=2: 曲名、Bselect=4: 部分一致)は記憶に基づく値で、未確認。
- ポップアップのスイッチ(index): セトリ・アルバムのポップアップの右上(×の左)に📜・📊のスイッチ。📊はヘッダーの📊ボタンと同じ状態(どちらで切り替えても連動。ポップアップのスイッチは、ヘッダー側の「他のボタンがすべてON」の条件を問わず切り替えられる)。📜はこの端末に記憶(`gl_lyrics_mode`、初期はON)。OFFの間は各曲の行の📜がなめらかに消える。曲紹介バー(♪)の📜は常に表示(📊はこれまでどおりヘッダー連動)。

## 追加ディスク内の区分(見出し)

- 1枚のディスクにMVとライブ映像など複数の内容が入っているとき、区分(見出し)で区切り、区分ごとに番号を1から振り直す。区分名は自由入力(LIVE TOUR 2025 など)。区分が無い場合は従来どおり。
- データ: editions[].extra の配列に `{"section":"LIVE TOUR 2025"}` の行を挟む(曲ではない。曲の行は従来どおり `{"no":"BD1","title":...}`)。番号は「ディスク名 + 区分内の順番」(BD1, BD2 ... 区分が変わると BD1 に戻る)。
- helper(albums): 追加ディスクの曲目に「+ section」ボタン。貼り付けでは `[LIVE TOUR 2025]` だけの行が区分の見出しになる。読み込み時も区分を復元する。
- issue_to_json.py: 追加ディスク(extra)だけ section 行を受け付ける(通常の曲目 tracks では無視)。
- viewer: アルバムポップアップの追加ディスクで、区分の見出しを小さな太字の行として表示(曲の行ではないので番号・ボタン無し)。
- 表示例: `BD1 MVタイトル / BD2 MVドキュメンタリー / LIVE TOUR 2025 / BD1 タイトル / BD2 タイトル ...`

- SNSポップアップ: 1行目の右端の番号のランプが右上の✕ボタンに重なっていたため、本文(sns-modal-body)を10px下げて、ランプが✕の下に収まるようにした。

- 記念日(ANNIVERSARY)の行にも、参照元(ref)にsetlistidがあれば📋アイコンを出し、押すと参照元のセトリのポップアップを開く(`_refSetlistid`)。アイコン専用で、セトリ検索・メンバー判定・helperへ開くIDには使わない(従来どおり記念日の行自身のsetlistidのみ)。

- 区分(section)は改行できる(helperは複数行の入力欄、Enterで改行。viewerも改行どおりに表示)。helperの区分欄は「sec」ラベルを外して左端まで伸ばす。
- helper(albumsの曲目): track / section とも、→ ↑ ↓ ✕ のボタンは入力欄の下に1行で並べ、縦幅の小さい同じ幅のボタンにする。sectionには → が無いので、その位置は空けて ↑ ↓ ✕ の位置をtrackとそろえる。曲の番号の表示は区分の後で1に戻る。

- helper(albums): editionの行も同様に、↑ ↓ ✕ を名前欄の下に1行で並べ、縦幅の小さい同じ幅のボタンにした。

- helper(albums の曲目): ボタンの行は入力欄と同じ幅に収め、曲番号の列にかぶらない。曲名の候補は、ボタンの上にかぶさるように表示する。

## albums の type に mini album を追加

- type の候補に `mini album`(album の次)。helperのtypeチップ、issue_to_json.py / merge_json.py の候補、add_albums.yml の説明に追加。viewerでは「MINI ALBUM」と大文字で表示。
- logs行から盤を引くとき(💽・helper)は、タイトル/タグの「MINI ALBUM」を album とは別の type として扱う(album の盤を引かない)。

- helperのalbums type チップの並びを2行(4個ずつ)に変更: `single / ep / album / mini album` と `digital / mu-ca / dvd / blu-ray`。

- helperの幅: 画面幅800px以上(PC)では最大760px(スマホ・狭い画面は従来どおり最大520px)。

- helperのalbums type チップの2行表示はスマホ幅のみ。画面幅800px以上(PC)では8個を1行に並べる。

- helper(albums の曲目・edition): 画面幅800px以上(PC)では、ボタン(→ ↑ ↓ ✕)を入力欄の右に1行で表示(スマホは入力欄の下)。
