# gllogs

[GL log](https://gl-log.blogspot.com/) のデータ(日程・ログ、セットリスト、楽曲リスト)と、その登録の仕組みをまとめたリポジトリです。

- 閲覧ページ: `index.html`(Blogger のサイトに貼って使う。データは jsDelivr 経由でこのリポジトリのJSONを読む)
- 入力補助ページ(helper): `issue_helper_blogger.html`(Blogger の固定ページ [issuehelper](https://gl-log.blogspot.com/p/issuehelper.html))
- 実装の詳細な仕様: [SPEC.md](SPEC.md)(最初の「現行仕様(まとめ)」が基準)
- 変更の履歴・置き換え済みの旧仕様: [CHANGELOG.md](CHANGELOG.md)

## データ

| ファイル | 中身 | キー |
|---|---|---|
| `data/logs/logs.json` | 日程・ログ(`date` `time` `contents` `title` `groups` `venue` `setlistid` `tags` `sns` ほか) | `logid` |
| `data/setlist/setlist.json` | セットリスト(`artist` `member` `venue` `songs`。曲ごとに歌唱メンバー `member` を持てる) | `setlistid` |
| `data/songs/songs.json` | 楽曲リスト(`link` `lyrics` `videos`、歌唱メンバーなどの自由入力 `vocal`)。ビューアの楽曲バー・披露実績・動画で使う | `artist` + `title` |
| `data/albums/albums.json` | アルバム・EP・シングルの収録曲と各種盤(`date` `tracks` `editions`)。データ部の🎶で表示 | `title` + `type` |
| `data/logs/logs_index.json` `data/setlist/setlist_index.json` | helper用の軽量インデックス(自動生成) | |
| `data/manifest.json` | 各データファイルの hash と size。ビューアが、変わったファイルだけを読むために使う(自動生成) | |
| `data/inbox/` | helper から直接送られた依頼(処理後に削除)と、その結果 `results/<id>.json`(直近60件) | |

JSONを直接編集せず、**Issue のフォーム**から登録します(下記)。

## データの登録のしかた

登録のしかたは3つあります。どれも同じ変換処理を通ります。

**A. Issue から**
1. [Issues](../../issues/new/choose) で、用途に合ったフォームを選ぶ(logs / setlist / songs ほか)。または、**helper** で入力して、事前入力済みのIssueを開く。
2. Issue を作ると、GitHub Actions が自動で JSON に変換し、データにマージして、コミットします。
3. 入力に問題があれば、Issue にコメントが付きます。**Issueを編集すると再処理**されます(同じIssueは同じログを更新します)。

**B. helper から直接送る(Issue なし)**
1. helper の右下にある **setting** で、`repo` / `branch` / `token` を設定して保存する(token は ENCRYPT をオンにすると、パスフレーズで暗号化して保存されます)。
2. 各タブの **send** を押すと、入力内容が `data/inbox/` に書き込まれ、Actions が処理します。結果(反映できたか、エラーの原因)は、helper に表示されます。
3. 削除は Issue のフォームから行います(helper の delete ボタンは非表示です)。

**C. queue に JSON を置く**
`data/{logs,setlist,songs,albums}/queue/` に JSON ファイルを push すると、`process_queue.yml` が処理します(Actions の Run workflow でも実行できます)。

- 読めないファイルがあると、Actions は失敗表示になり、原因(ファイル・何件目・何行目・理由)が Summary に出ます。そのファイルは queue に残り、直して置き直すか、再実行すると再処理されます。
- push が競合したときは、最新に合わせ直して自動で再処理します(最大5回)。

- 処理されるのは、`data` ラベル付きの Issue で、投稿者がこのリポジトリの OWNER / MEMBER / COLLABORATOR のものだけです。
- 更新のとき、**空欄は「変更しない」**です。消したい項目は、フォームの「値の削除(更新時)」にチェックします。
- 「DELETE」にチェックすると、そのデータを削除します。「COPY」は、コピー元のIDから新規登録します(logs では、COPY 時の時刻欄に「anytime」を出せます)。
- logs の `venue`(会場名)は、タグではなく専用の項目です。ビューアではタグ行の一番左に出て、`map` にリンクがなければ、📍が会場名で Google マップを検索します。logs の `venue` を登録・変更すると、同じ `setlistid` の setlist の `venue` にも反映されます(venue から venue だけ。タグからは引き継ぎません)。空にすると setlist のほうも消えます。

### ANNIVERSARY(記念日)の連動

LIVEなどを登録するときに「ANNIVERSARY」にチェックすると、元データを参照する記念日が一緒に作られます。url・groups・relations・tags・snsは元データを参照して表示されるので、元データだけ更新すれば記念日にも反映されます。タイトルは元のタイトルに「 記念日」が付きます。繰り返し登録やBIRTHDAY / ANNIVERSARYの元データには使えません。

### グループ・メンバーの入力

- **G2 / L2 だけ**を選ぶと、そのグループの全員に展開されます(setlistのmember、sns、relations、曲ごとのメンバー)。
- **個別メンバーも選ぶ**と、選んだメンバーだけが登録されます(`G2,MSK` → `MSK` だけ)。
- logs の `groups` だけは、グループのコード(`G2` / `L2`)そのものもデータに持ちます(自由入力では展開しません)。

詳しい表は [SPEC.md](SPEC.md) の「グループ・メンバーの登録仕様」を見てください。

### 書式のメモ

**曲目(setlist)**: 1行1曲

```
1: 曲名 {YZH,MMK} | type | original | notes
```

- 曲名の直後の `{メンバー}` が歌唱メンバー。`{-}` で指定を消す。省略すると全員扱い。
- 個別変更は `N: ...`(更新)、`+N: ...`(挿入)、`-N: ...`(削除)、`N>M: 曲名`(移動)。
- 曲順が分からない曲は、番号を `-` `?` か空にします(`-: 曲名` `?: 曲名` `: 曲名`)。順番なしの曲は最後に並び、ビューアでは `－` と表示されます(全曲が順番なしなら「曲順不明」のチップ)。更新では `+?: 曲名` で追加、`-?: 曲名` でタイトル指定の削除です。

**sns(logs)**: 1行1件

```
type | url | member
```

- type は URL から自動判定します(X / Instagram / YouTube / TikTok / CL / radiko / GL²family。判定できなければ `etc`)。`threads` / `line` は type を書いて指定します。
- type を `site` や `etc` にしても、URL が X などと判定できるときは、その種類に直して登録します(ビューアでも、すでに `site` で入っているものを URL から判定して表示します)。
- Fancam(tags に `Fancam` を付けたリンク)は、ポップアップで SNS の種類ごとにまとめて表示されます。
- `-URL` で、そのURLだけを削除します。

**繰り返し登録(新規のlogsのみ)**: 1行1回、最大60件

```
YYYYMMDD [時刻] | タイトル | contents | URL | display_sp
```

tour(helper の mode: tour)の1行は、末尾まで書くと `日付 時刻 | タイトル | contents | URL | display_sp | map | setlistid | tags | venue` です。

- 時刻は `HHMM` で、`-` は時刻なし。省略すると、フォームの時刻を使います。
- タイトルの `#数字` は、回ごとに自動で+1されます。

### helper の songs タブ

- `id` 欄にタイトルの一部を入れると、`songs.json` から候補が出ます。選ぶと、その曲の artist・vocal・title・link・lyrics・動画が読み込まれます(同じタイトルが複数あるときは artist も表示)。
- `vocal` は自由入力です(例: artist は `Girls²`、vocal は歌唱メンバー)。artist を選んで `vocal` 欄にカーソルを置くと、その artist の曲で使われている vocal が候補に出ます。title の候補も、artist と vocal で絞り込まれます。
- 曲を特定するのは `artist` と `title` の組み合わせです。どちらかを変えると別の曲になります(名前を直すときは、新しい名前で登録して、旧データを `DELETE` してください)。
- ビューアの楽曲バーの3回タップから、`#songs` で開くこともできます。

### helper の使い方(関連日程の一括登録)

チケット抽選のように、開始・締切・当選発表・期限をまとめて登録したいとき:

1. helper の logs で、日付・時刻・title・contents・url を入れる。
2. repeat の「repeat entry」をオンにして、mode を `schedule` にする。
3. `start` / `close` / `result` / `due` の各行に、日付(と時刻)を入れる。日付を入れた行だけが登録されます。
   - contents は自由入力で、候補が出ます(`close` は `CLOSE`、`result` は `RESULT`、`due` は `CLOSE` が初期値)。
   - ラベル(`締切`、`当選発表` など)が、タイトルの後ろに付きます(例: `◯◯ 締切`)。
   - `display_sp` に短い名前を入れると、「その名前 + ラベル」が各行の display_sp になります。

## データ部の便利機能(隠し機能)

年・月・日・曜日・時刻のボタン、📍、📋、💞、🏷️、💽、🔗が**すべてON**のときだけ有効です(♪は条件に含めません。詳細は [SPEC.md](SPEC.md))。PC は Ctrl / Shift / Cmd を押しながらクリックで、1回で動きます。

- **日付・時刻を3回タップ**: その行を helper で別タブに開きます。📋セトリ検索が OFF なら `logid` で `#logs`、ON なら `setlistid` で `#setlist`。ID のない行は何も起きません。
- **楽曲バー(♪が ON)の曲名を3回タップ**: その曲を helper の songs タブで開きます(`?artist=…&title=…#songs`)。
- ダブルタップで ID をコピーする機能は廃止しました。

### キーボード・スマホの操作

- TODAY モード: PC は `←` で前日、`→` で翌日(押しっぱなしで連続して送れます)。スマホは左右のフリック。
- 入力欄・スライダーの操作中や、ポップアップ・カレンダーを開いている間は、`←` `→` は反応しません。

## 自動処理(GitHub Actions)

| ワークフロー | 内容 | 実行 |
|---|---|---|
| `auto_merge.yml` | Issue → JSON に変換 → マージ → コミット | Issue の作成・編集時 |
| `process_queue.yml` | queue の JSON と helper の依頼(`data/inbox/`)を処理 → マージ → コミット | queue・inbox への push、手動 |
| `tests.yml` | 自動テストと事前チェック | scripts・tests・.github・helper の変更、PR、手動 |
| `update_manifest.yml` | `data/manifest.json` の作り直し | データの手動編集の push(queue・inbox は除く)、手動 |
| `rebuild_index.yml` | helper用インデックスの作り直し | 手動(Run workflow) |
| `check_gaps.yml` | logs のタイトルの `#数字` の連番の抜けを調べる | 手動(Run workflow) |
| `link_check.yml` | logs の `url` / `map` のリンク切れを少しずつ確認(結果は `data/logs/link_state.json`) | 毎日 03:00(JST)・手動 |

`scripts/` には、`issue_to_json.py`、`merge_json.py`、`inbox_to_json.py`、**`common.py`**、**`schema.json`**(項目の定義)、`check_repo.py`(事前チェック)を一緒に置きます(`common.py` と `schema.json` が欠けると動きません)。`inbox_to_json.py` は `.github/ISSUE_TEMPLATE/*.yml` を読むため、フォームのファイルも置いたままにしてください。

**注意**: 同じ queue を処理するワークフローは、`auto_merge.yml` と `process_queue.yml` の2つだけにします。同じ処理をするファイルが他にあると、同時に動いて競合・二重処理になります。

## テストと事前チェック(保守のために)

スクリプトやフォームを直したときは、リポジトリの直下で次を実行します(push すると `tests.yml` が自動で実行します)。PyYAML が必要です(`pip install pyyaml`)。

```
python scripts/check_repo.py                 # 事前チェック
python -m unittest discover -s tests -v      # 自動テスト
```

- **事前チェック**(`scripts/check_repo.py`): data の JSON が読めるか / フォーム(`add_*.yml`)と `issue_to_json.py` の項目名が一致しているか / 「値の削除」の選択肢が合っているか / helper の `<script>` が ASCII だけか / `schema.json` と helper の項目が合っているか / キューを処理するワークフローが2つ(`auto_merge.yml` `process_queue.yml`)だけか。
- **自動テスト**(`tests/`): 本物のスクリプトを一時フォルダで動かし、logs の登録・更新・削除、繰り返し登録、setlist の曲順なし、venue の同期、読めない JSON のエラー報告、helper 直送(inbox)を確かめます。直した所以外が壊れていないかの確認に使います。

### 項目を足すとき(例: logs に `foo` を足す)
1. `scripts/schema.json` … `logs.order`(並び順)に足す。更新時に消せる項目なら `logs.clearable` にも足す。フォームの項目名は `labels_logs` に足す。
2. `.github/ISSUE_TEMPLATE/add_logs.yml` … 入力欄と、「値の削除」の選択肢を足す。
3. `scripts/issue_to_json.py` … `build_logs` で値を読む。
4. helper の `DEFS` と、`index.html` の表示を直す。
5. 事前チェックを実行する。1〜4 の食い違いは、ここで見つかります。

## helper を Blogger に貼るときの注意

helper の token は、このリポジトリだけを対象にして Contents の Read and write だけを許可し、期限を付けた Fine-grained token にしてください。

Blogger は `<script>` 内の日本語や記号を数値文字参照に変換して文字化けさせます。`issue_helper_blogger.html` の `<script>` は **ASCII のみ**で書き、日本語は `\uXXXX` のエスケープにしてあります。編集するときも、この形を保ってください。
