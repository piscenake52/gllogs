# 変更の履歴(CHANGELOG)

`SPEC.md` が現行仕様の置き場。ここには、**変更の経緯**と、**置き換え・廃止された旧仕様**(原文のまま)を置く。

## 変更の履歴(新しい順)

- **2026-11-26(helper songs・送信の条件)** 登録済みの動画の url が空の間は `songs` / `send` ボタンを出さないようにした(以前はその動画が送信内容から外れ、残りがないと `!clear` で全削除になった)。空の url は入力エラー(赤枠・一覧を自動で開く)とし、ボタンの `-n` には数えない。削除は × で指定する。
- **2026-11-26(helper songs・チップの順)** type のチップの並びを動画ポップアップの表示順にそろえた(Performance を Dance Practice の次へ)。
- **2026-11-26(viewer・helper songs)** 動画ポップアップの表示順を変更: Performance を Dance Practice の次(3番目)に入れ、Other・自由入力は Call Lecture の後ろ、Fancam は常に一番下にした(以前は MV → Dance Practice → Lyric → Live → Reaction → Call Lecture で、それ以外は登録順)。helper(songs)の videos の ↑↓ ボタンを削除した(順番を変えるには、削除して追加し直す)。
- **2026-11-26(helper songs)** videos の表示を変更: 登録済みの動画を、一番下の `videos links (件数)` ボタン(logs の sns links と同じ開閉・`+n` / `-n` 表示)の中にまとめた。追加する動画はチップを出さず編集欄だけにし、✕ で削除する。追加分がある状態で曲を選んでも登録済みの動画を読み込み、追加分は後ろに残る。README.md の古い説明(行の ✕ で削除)も直した。通信をモックしたブラウザで確認(実機・Blogger は未確認)。
- **2026-11-26(helper)** アニメーションを追加(`opacity` / `transform` のみ・0.2秒以内・reduced-motion では停止): repeat の中身・読み込み中の行・候補リスト・send の結果のフェードイン、チップを押している間の縮小。通信をモックしたブラウザで確認(実機・Blogger は未確認)。
- **2026-11-26(整理)** `link_check.py` 単体の件数の既定を 400 から 250 にし、ワークフローとそろえた。不要なファイルを削除: `scripts/test_check_repo.py`(`tests/` 版と重複する古い版)、`.github/ISSUE_TEMPLATE/link_check.yml`(紛れ込んだ workflow のコピー)、`.github/ISSUE_TEMPLATE/add_setlist_songs.yml`(setlist / songs が1つだった頃の形のフォーム。setlist と songs は `add_setlist.yml` / `add_songs.yml` を使う)。GitHub Actions の `Tests`(`test` / `viewer`)の成功を確認。SPEC.md と `issue_to_json.py` のコメントを合わせた。
- **2026-11-25(文書の見直し・helper・viewer)** SPEC.md・README.md・CHANGELOG.md を現状に合わせた(テスト件数 28+viewer 37=65、`tests.yml` の `viewer` ジョブ、`check_repo.py` の `--rebuild-manifest` 除外、リンク切れチェックの件数の既定値(workflow 250 / 単体 400)、動画入力の表示)。helper(songs)の videos 入力を、動画ごとの1チップ表示に変更(✎ 編集 / × 取り消し線・↩ 元に戻す / ↗ 開く。新規の動画は × で即削除)。共有のトーストを、下から上がる動き(opacity / transform)に。不要になった `script.js` / `style.css` を削除。見送った案: BIRTHDAY の「誕生日」フォールバック、helper の入力時の空白の正規化、find の軽量インデックス(案B)。
- **2026-11-24(helper)** 繰り返し登録: `display_pc` に対応、`optional` を `display_sp` に改名、schedule・tour にも確認一覧(title / pc / sp)を追加(interval は `pc:` / `sp:` を表示)。title の候補(Instagram Live・TikTok Live・CLキャス・GLRADIO・schedule の行ラベル)、SNS の title 自動入力(groups 選択時のみ)、setlistid 欄を TOUR でも表示。songs の videos の入力画面(url とタグの入れ替え、↗ と ✕ の位置)。id 検索の読み込み: IndexedDB のコピー(10分)の利用と、読み込み中・エラーの表示。
- **2026-11-24(viewer・データ)** 抽出タグのフォールバック(DIARY=日記更新、GTUBE=Gtube、GLRADIO=がるらじ)。ANNIVERSARY の参照行に venue・tags・sns・抽出タグを引き継ぐ。SNS チップの背景を通常タグと同じにした(破線は維持)。viewer のテスト(`tests/test_viewer.py`、`tests.yml` の `viewer` ジョブ)。`check_repo.py` が `--rebuild-manifest` を誤検出する問題を修正。空白の正規化(`space_normalize_20261122.json`、393件)。
- **2026-11-20(文書の見直し)** SPEC.md の詳細メモを、コードと突き合わせて現行に合わせた: メンバーのランプ色、DISPLAYのスイッチ(9つ・`hdr`の保存)、tour 行の venue、ファイル一覧(`process_queue.yml` ほか)、データ取得の流れ(manifest)、display_sp の共通名(`optional`欄)。
- **2026-11-20(追加)** ビューアのタグ表示: 抽出タグ(TODAYのみ・仮の表示)、チップの種類の見分け(tags / venue / snsのタグ / 抽出タグ)、contents別の代わりのタグ(DIARY=日記更新、GTUBE=Gtube、GLRADIO=がるらじ)。SPEC.md の古い記述(snsリンクのtagsは出さない)を、現行に直した。
- **2026-11-20** 保守性の改善: `scripts/schema.json`(項目の定義の集約)、`scripts/check_repo.py`(事前チェック)、`tests/`(自動テスト27件)、`tests.yml` を追加。SPEC.md を「現行仕様(まとめ)」中心に再構成し、旧仕様をこのファイルに移した。
- **2026-11 後半** 自動処理・helper直送: `process_queue.yml` / `update_manifest.yml`、push のリトライ、詳細なエラー報告、helper の setting と send(`data/inbox/`)、manifest、setlist の曲順なし、logs の `venue`(setlistへの同期、ビューアのMAPピン)、動画ポップアップの Fancam アイコン。
- **2026-11** songs の `vocal`、sns の type 補正、`common.py`、map の埋め込みHTML対応、BADGE機能の削除、ヘッダー固定・タップハイライト・括弧の空き、披露実績アイコンの条件、キーボード操作、3回タップ(隠し機能)、helper の songs / albums / logs / setlist の整理。
- それ以前: 機能ごとの追記として SPEC.md の「機能ごとの詳細メモ」に記録している。

## 置き換え・廃止された旧仕様(原文のまま)

次の節は、現行仕様と食い違うため SPEC.md から移した。現行の仕様は SPEC.md の「現行仕様(まとめ)」を見ること。

#### L2626(旧仕様: ダブルタップでのlogidコピーは廃止。現行は「現行仕様」の3回タップ)
【隠し機能】年・月・日・曜日・時刻の表示と、📍・📋️の表示がすべてONの間だけ有効。 データ行の日付/時刻部分をダブルタップ(ダブルクリック)すると、その行のlogidをクリップボードにコピーし、 画面下に表示する(Issueフォームで既存ログを更新するときにlogidを調べる用)。

#### logid / setlistid コピー機能(廃止: 「helper遷移の条件変更」(SPEC.md)を参照)

日付・時刻のダブルクリック/ダブルタップでクリップボードにコピーしトースト表示する(2回目のタップでコピー)。

- 発動条件: 年月日曜時+📍+📋️がすべてON
- 🔗が**ON**(全部ON): `logid`をコピー(無ければ「この行にはlogidがありません」)
- 🔗が**OFF**: `setlistid`をコピー(無ければ何も起きない。logidと違いトーストも出さない)
- **helperを開ける状態(後述「helperへの遷移」)のときは、ダブルタップでもコピーしない**(3回タップに備えるため)。コピーする元の条件は上のとおり変えていない

#### helperへの遷移(隠し機能)(条件を変更: 「helper遷移の条件変更」(SPEC.md)が現行)

データ部の日付・時刻を**3回連続タップ**(PCは Ctrl / Shift / Cmd + クリック)すると、その行のIDでhelperを別タブで開く(`https://gl-log.blogspot.com/p/issuehelper.html?id=<ID>#logs` または `#setlist`)。

**helperを開ける状態**(`helperModeOn`)は、次のすべてを満たすとき:

- 年月日曜時+📍+📋️がON(「logid / setlistid コピー機能」と同じ発動条件)
- ♪(`songMode`)と💞(`heartModeOn`)がON
- 次のどちらか
  - 🔗がOFF、かつ📋セトリ検索がON → `setlistid`で`#setlist`を開く
  - 🔗がON、かつ📋セトリ検索がOFF → `logid`で`#logs`を開く

IDが無い行は何もしない。この状態では、**ダブルタップのIDコピーは行わない**(3回タップの途中でコピーのトーストが出ないようにするため)。helperを開ける状態でないときは、ダブルタップのコピーは従来どおり。

| ♪💞 | 📋 | 🔗 | ダブルタップ | トリプルタップ |
|---|---|---|---|---|
| どちらかOFF | - | - | 🔗ONならlogid、OFFならsetlistidをコピー | なし |
| ON | ON | OFF | コピーしない | helper(setlist) |
| ON | OFF | ON | コピーしない | helper(logs) |
| ON | ON | ON | 従来どおりコピー(logid) | なし |
| ON | OFF | OFF | 従来どおりコピー(setlistid) | なし |

#### 下書き自動保存(廃止)
- 入力途中の内容を保存して復元・破棄を確認する機能(`glih_drafts`、`restore` / `discard` のバナー)は廃止した。helperを開いたときに、以前の保存分(localStorage の `glih_drafts`)は消す。

### helper遷移の条件変更(logid / setlistid コピーの廃止)(現行: 「現行仕様」の3回タップ)
- 日付・時刻のダブルタップ/ダブルクリックでlogid・setlistidをコピーする機能は廃止(トーストも無し)。
- 3回連続タップ(PCは Ctrl / Shift / Cmd + クリック)でhelperを別タブで開く機能だけが残る。
- 発動条件: 年・月・日・曜・時のボタン、📍、📋、💞、🏷️、💽、🔗がすべてON。♪のON/OFFは条件に含めない。
  - 📋セトリ検索がOFF: その行のlogidで `#logs` を開く。
  - 📋セトリ検索がON: その行のsetlistidで `#setlist` を開く。
- 条件を満たさないときは何も起きない。IDが無い行(logidが無い、または📋セトリ検索ONでsetlistidが無い)も何もしない。
- 発動条件が揃っている間だけ、日付/時刻の文字選択(ダブルタップの単語選択とコピーメニュー)を止める。

### 年フィルターの折りたたみ(YEARボタン)(置き換え: 「フィルターの折りたたみ(上の帯)」(SPEC.md)が現行)
- 年フィルターの行の左端に折りたたみボタンを置く。開いている間は「‹」だけ。畳んだあと(行が縮む動きに合わせて)「YEAR ›」と文字が出る(将来、他のフィルターも横並びにするため)。
- 押すと、年のボタンが左のYEARボタンへ滑りながら小さくなって吸い込まれる(ボタンに近い順に21msずつ遅れて、0.42秒)。吸い込みの終わり際(約7割)から、行そのものが42pxから22pxに縮み、下の行が上へ詰まる。YEARボタンは22pxの小さなつまみとして残り、矢印が反転する。もう一度押すと、先に行が広がり、YEARボタンの位置から年のボタンが右へ広がって戻る。
- 畳んでいる間も、選択した年の絞り込みは有効のまま(チェックの状態は変えない)。
- 状態は `gl_year_fold`(true / false)に保存し、次回も同じ状態で開く(起動時はアニメなし)。
- （廃止）選択中の年の数のバッジ。BADGE機能の削除に伴い、現在は出さない。
- `prefers-reduced-motion` ではアニメなしで切り替わる。畳んでいる間は年のボタン(`#yearChecks`)を `display:none` にする。
