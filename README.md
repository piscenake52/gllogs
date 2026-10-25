# gllogs

[GL log](https://gl-log.blogspot.com/) のデータ(日程・ログ、セットリスト、楽曲リスト)と、その登録の仕組みをまとめたリポジトリです。

- 閲覧ページ: `index.html`(Blogger のサイトに貼って使う。データは jsDelivr 経由でこのリポジトリのJSONを読む)
- 入力補助ページ(helper): `issue_helper_blogger.html`(Blogger の固定ページ [issuehelper](https://gl-log.blogspot.com/p/issuehelper.html))
- 実装の詳細な仕様: [SPEC.md](SPEC.md)

## データ

| ファイル | 中身 | キー |
|---|---|---|
| `data/logs/logs.json` | 日程・ログ(`date` `time` `contents` `title` `groups` `setlistid` `tags` `sns` ほか) | `logid` |
| `data/setlist/setlist.json` | セットリスト(`artist` `member` `venue` `songs`。曲ごとに歌唱メンバー `member` を持てる) | `setlistid` |
| `data/songs/songs.json` | 楽曲リスト(再生リンク用) | `artist` + `title` |
| `data/albums/albums.json` | アルバム・EP・シングルの収録曲と各種盤(`date` `tracks` `editions`)。データ部の🎶で表示 | `title` + `type` |
| `data/logs/logs_index.json` `data/setlist/setlist_index.json` | helper用の軽量インデックス(自動生成) | |

JSONを直接編集せず、**Issue のフォーム**から登録します(下記)。

## データの登録のしかた

1. [Issues](../../issues/new/choose) で、用途に合ったフォームを選ぶ(logs / setlist / songs ほか)。または、**helper** で入力して、事前入力済みのIssueを開く。
2. Issue を作ると、GitHub Actions が自動で JSON に変換し、データにマージして、コミットします。
3. 入力に問題があれば、Issue にコメントが付きます。**Issueを編集すると再処理**されます(同じIssueは同じログを更新します)。

- 処理されるのは、`data` ラベル付きの Issue で、投稿者がこのリポジトリの OWNER / MEMBER / COLLABORATOR のものだけです。
- 更新のとき、**空欄は「変更しない」**です。消したい項目は、フォームの「値の削除(更新時)」にチェックします。
- 「DELETE」にチェックすると、そのデータを削除します。「COPY」は、コピー元のIDから新規登録します。

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

**sns(logs)**: 1行1件

```
type | url | member
```

- type は URL から自動判定します(X / Instagram / YouTube / TikTok / CL / radiko / GL²family。判定できなければ `etc`)。`threads` / `line` は type を書いて指定します。
- `-URL` で、そのURLだけを削除します。

**繰り返し登録(新規のlogsのみ)**: 1行1回、最大60件

```
YYYYMMDD [時刻] | タイトル | contents | URL | display_sp
```

- 時刻は `HHMM` で、`-` は時刻なし。省略すると、フォームの時刻を使います。
- タイトルの `#数字` は、回ごとに自動で+1されます。

### helper の使い方(関連日程の一括登録)

チケット抽選のように、開始・締切・当選発表・期限をまとめて登録したいとき:

1. helper の logs で、日付・時刻・title・contents・url を入れる。
2. repeat の「repeat entry」をオンにして、mode を `schedule` にする。
3. `start` / `close` / `result` / `due` の各行に、日付(と時刻)を入れる。日付を入れた行だけが登録されます。
   - contents は自由入力で、候補が出ます(`close` は `CLOSE`、`result` は `RESULT`、`due` は `CLOSE` が初期値)。
   - ラベル(`締切`、`当選発表` など)が、タイトルの後ろに付きます(例: `◯◯ 締切`)。
   - `display_sp` に短い名前を入れると、「その名前 + ラベル」が各行の display_sp になります。

## データ部の便利機能(隠し機能)

日付・時刻の部分を、条件付きで操作します(条件は [SPEC.md](SPEC.md) を参照)。

- **ダブルタップ**: logid / setlistid をコピー
- **トリプルタップ**: その行のIDで helper を別タブで開く

## 自動処理(GitHub Actions)

| ワークフロー | 内容 | 実行 |
|---|---|---|
| `auto_merge.yml` | Issue → JSON に変換 → マージ → コミット | Issue の作成・編集時 |
| `rebuild_index.yml` | helper用インデックスの作り直し | 手動(Run workflow) |
| `check_gaps.yml` | logs のタイトルの `#数字` の連番の抜けを調べる | 手動(Run workflow) |

## helper を Blogger に貼るときの注意

Blogger は `<script>` 内の日本語や記号を数値文字参照に変換して文字化けさせます。`issue_helper_blogger.html` の `<script>` は **ASCII のみ**で書き、日本語は `\uXXXX` のエスケープにしてあります。編集するときも、この形を保ってください。
