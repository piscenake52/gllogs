# GL log 仕様: 入力補助ページ(helper.html)

2026-11-27 に SPEC.md から分けた。本文の「上の」「下の」「現行仕様」は、分割前の1つのファイルを指す場合がある。見つからないときは [SPEC.md](../SPEC.md) の一覧からたどる。

## 現行仕様(まとめ。食い違うときは、ここが基準)

### helper(helper.html)

- **songsタブ**:
  - `id` 欄(`new` の下): タイトルの一部で `songs.json` を検索し、候補を押す(またはEnterで1件のとき)とその曲を読み込む。同じタイトルが複数あるときだけ、候補にartistを併記する。読み込み後はid欄は空に戻る。`new` で一緒にクリア。
  - artistのチップ: 1段目の右端に「おはガール」を追加(Girls² / Laki / Girls² × iScream / おはガール、2段目 miracle² / magical² / mirage² / lovely²)。artistの候補は、artist欄の直下に出す(チップはそのあと)。
  - `vocal` 欄(artistのチップの下、自由入力のみ): カーソルを置くと、選んだartist(順序・表記ゆれを同じとみなす)の曲で使われているvocalを件数つきで候補表示。入力で絞り込む。読み込んだ曲のvocalは入る。空にして送ると `!clear`。
  - title の候補: artistで絞り、vocalが入っていればvocalでも絞る(部分一致。一致が無ければartistの曲を全部出す)。vocalが空なら従来どおり。
  - `#songs?artist=…&title=…` で開くと、その曲を読み込む(ビューアの楽曲バーの3回タップ)。
- **albumsタブ**: artist欄を date の上に移動(id → artist → date → title → type)。artistのチップにも「おはガール」を追加(songsと同じ並び)。
- **logsタブ**:
  - `copy` と `ANNIVERSARY` は同じ大きさの丸いチップ(大文字表記、`copy` ラベルあり)。copyとrepeat(interval / schedule / tour)の行は、date・timeの下に置く(新規でも既存でも同じ位置・同じ見た目)。repeatのチップの文字は大文字、サイズは3つとも同じ。
  - 日付の左右の矢印ボタンは常に表示。既存データ表示時も date・time・時計アイコンの位置がずれない(2pxにそろえる)。
  - sns: `url` / `tags` のラベルを追加し、入力欄内の表示は削除。tagsの `add` ボタンは入力欄の下に移動(Fancamと同じ大きさ)で、Fancamとの間に線を引く。
  - map: Googleマップの地図URLと埋め込みHTMLのどちらも入れられる(iframeは地図URLに直す)。
  - schedule: 「+ schedule」ボタンで、スケジュール欄を1行ずつ追加できる(×で消す。×は自由入力欄の右端)。追加行は `repeat=` の内容にも入る。
  - ラベル・表示の整理: intervalの `skip` は `skip date`、tourの愛知は `area`、タグ1・タグ2は `tags`、`+` は `+ tour`。display_sp(旧optional、optional_sp)、suffixの入力欄内の表示は削除。
- **setlistタブ**: 曲の詳細の `note` にラベルを付け、入力欄内の表示は削除。既存データ表示時も、紐づくlogsの日付・時刻を読み取り専用で表示する(同じsetlistidのlogsのうち日付が一番古いもの)。copyの位置はtimeの下。
- **曲の編集**: アルバムの収録曲(`alTracks`)とセトリの曲(`addSongsList`)は、同じ編集部品(`edBox` / `edActs`)を使う。
- **setting(右下)**: メインの枠の外側・下の右端に小さな「setting」ボタン。押すと、ボタンの上に設定パネルが開く(もう一度押すと閉じる)。`#setting` で開いた状態にもできる。項目:
  - `repo`(`owner/name`)、`branch`、`token`。リポジトリとブランチは、コード中の固定値の代わりに使う(Issue のリンクにも反映)。
  - **token の保存**: localStorage(`glih_set`)。ENCRYPT をオンにすると、パスフレーズで暗号化して保存する(Web Crypto: PBKDF2-SHA256 250000回 → AES-GCM。ソルト・IV は保存ごとに乱数)。暗号化した token は、ページを開くたびに「unlock」が必要(unlock 後は、メモリ上だけに保持)。暗号化しないと平文で保存される。「clear token」で保存した token を消す(2回押し)。
  - 「test」: リポジトリ・ブランチが見えるか、書き込み権限があるかを確認する。
  - token は Fine-grained token(このリポジトリだけ、Contents の Read and write だけ、期限つき)を想定。`api.github.com` へのリクエスト以外には送らない。
- **send**: 各タブ(logs / setlist、songs、albums、bulk)の Issue ボタンの下に表示。Issue のリンクの値(テンプレートと項目の値)をそのまま読み取って、`data/inbox/<id>.json` に PUT する。ネットワークエラー、409、429、5xx は最大3回再試行する。送信後、`data/inbox/results/<id>.json` を4秒ごと・最大約3分ポーリングして、`done` / `error`(原因・注意)を表示する。`done` でも結果の `skipped` が true のときは `NOT all reflected (check below)` と表示する。`done` のとき、logs・setlist・albums・songs のキャッシュを破棄する。エラーの表示は、401(token の誤り・期限切れ)、403(権限不足・上限)、404(リポジトリ・ブランチが見えない)、422、409 などを具体的に出す。
- **Issue と send の表示条件**: 送れる状態になるまで(初期表示、new 直後、入力が不足のとき)、Issue ボタンと send を隠す(`a.go[aria-disabled="true"]` は非表示)。
- **delete ボタン**: send の横に出す処理は残っているが、画面には出さない(`SHOW_DEL = false`)。削除は Issue のフォームから行う。`true` にすると、logs・setlist(読み込んだ行)、songs(一致した曲)、albums(読み込んだ盤)に delete ボタンが出る(確認ダイアログつき)。
- **venue 欄**(logs): `map` の上。候補は、過去の logs の venue(重複を除き、使用回数が多い順、最大12件。入力すると前方一致を先に、最大8件)。`logs_index.json` に venue がない古いインデックスのときは、最初にカーソルを置いたとき、`logs.json` を一度だけ全部読んで候補を作る。tourモードでは、フォーム上部の venue は隠す。
- **tour の1行**: 並びは「area と venue(1行)」→「map のURL」→「tags」。venue の候補は同じ area の過去の venue(area が空なら全部)。1行の venue は、その回の logs の venue になる。
- **setlist への遷移・新規入力の venue**: logs の行の `venue` だけを引き継ぐ(tags は使わない)。check からの遷移(`openSl`)、logs のフォームからの遷移、setlistid が同じ logs の行からの自動入力、のすべて。元データの logs の行は、`venue` を持つ行を優先して選ぶ。
- **COPY(logs)**: COPY をオンにしたとき、フォームの time 欄の横に「anytime」のチェックを出す。チェックを入れると time が空になり、`time=!clear`(コピー先は時刻なし)。チェックを外すと、元の時刻が戻る(元から時刻がなければ空のまま)。時刻を入力するとチェックは外れる。
- **setlist の曲の入力**: 番号なし(`noOrd`)に対応(上の「曲順が分からない曲」)。
- **setlist のコピー**: `addSlCopyFrom(box, sid)`。選んだ setlist から、同じタイトルのものを先頭に、artist・member・source・songs(titleは空のときだけ)を写す。
- **check タブの追加項目**: setlist・albums・songs のデータが揃っているかの検査を追加(`ckReg`)。logs の setlist が未登録(`nosl`)、albums が未登録(`noalbum`)、setlist の曲が songs に未登録(`slsong`)、albums の曲が songs に未登録(`alsong`)、setlist に曲がない(`slnosong`)、albums に曲がない(`alnotrack`)、盤が未登録(`noedition`)。結果の行から、未登録のデータへ移動するボタン(`it.go`)がある。無視するキーは `CK_IG`。移動先は `jumpSeed` / `gotoAlbum` / `goSong` / `openSl`。
- **フォームの説明文**: Issue フォーム(`add_*.yml`)の日本語の説明文は、簡潔な文に統一した。`add_setlist.yml` に `-:` `?:` `:` と `+?:` `-?:` の書き方を載せた。
- **アニメーション**(2026-11-26): `opacity` と `transform` だけを使い、0.2秒以内。CSS はすべて `prefers-reduced-motion: no-preference` の中に置く(視差効果を減らす設定では動かない)。
  - repeat の中身(`#glih-rpbody` と interval / schedule / tour の欄)、読み込み中・エラーの行(`#glih-fload`)、候補リスト(`.fcand`)は、表示するときに少し上からフェードイン(`glih-in`、0.18秒)。閉じるときの動きはない。
  - send の結果表示(`.sendst`)は、結果の文に置き換わるときに同じフェードイン(`popIn`。クラス `glih-pop` を付け直して再生する)。
  - チップ(`.chip`)は、押している間だけ縮む(`scale(.94)`、0.12秒)。ON / OFF の色の切り替えは動かさない。
- **公開**: GitHub Pages(`https://piscenake52.github.io/gllogs/`)。Blogger には貼らない。ファイルは UTF-8・改行は LF。
- **setlist の必須項目**(2026-11-26): 新規とコピーは `artist` と `title` が必須(空白だけも不可)。空の欄は入力エラーの表示にし、`Check: …` を出して Issue と send を隠す。登録済みの更新は変更した項目だけを送る。
- **告知文の読み取り**(2026-11-26): repeat の schedule の一番上に `notice` 欄と `read`。`parseNotice(text, today)` がルールで日程を読む(外部サービスは使わず、送信もしない)。
  - 日付は `M/D`・`M月D日`(年・曜日・時刻は省略可)。年がない日付は、約4か月前〜約1年先から、曜日が合って近いもの(合わなければ警告)。`24:00` は `2359`。
  - 行の振り分け: 入金・支払 → `due`、当落・当選・結果発表 → `result`、期間・受付・応募・販売など → `start` / `close`。同じ行にキーワードがなければ直前の見出しで判定する。判断できない日時や2つめの期間は「入れていない日時」に出す。
  - `read` は title・url・display_sp と4つの行を上書きする(読めた日程がないときは何も変えない)。start の日付がなければ start 行は空。groups は空のときだけ(Girls² → `G2`、Laki → `L2`)。
  - ラベルは期間の種類で変える(開始/終了、受付開始/受付締切、応募受付開始/応募受付締切、抽選受付開始/抽選受付締切、販売開始/販売終了)。`result` は当選発表(当選連絡)、`due` は入金期限(支払期限)。
  - start の contents は、URL が `girls2-fc.jp/page/wallpaper/` なら `FANCLUB`、「キャンペーン」を含めば `CAMPAIGN`。display_sp は先頭の「Girls² 」を省き「キャンペーン」→「CP」。
  - タグは、登録済みの logs のタグが行の先頭か『』「」の中にあれば候補チップ(最大6件)。押すと tags に入る。

## 機能ごとの詳細メモ

### TOURモード(helper・繰り返し登録のmode: tour)
- **使い方**: 繰り返し登録をONにして`tour`を選ぶ。1公演=1行(date / time / area / map)。`+`で行を増やし、`×`で行を消す。最初の行は、上のdate・timeを編集するまで追従する。登録済みの公演を開いて`next`の`tour`を押すと、公演名の元(最後のスペース以降を除いたもの)・contents・url・groupsを引き継いだ新規入力になり、追加公演を足せる
- **共通**: title(公演名)・contents・url・groups・relations・snsは、フォーム上部の値を全行に使う。`suffix`(自由入力+チップ「公演」。空ならなし)と`display_sp`欄(旧名`optional`。コード上は`#glih-rpop`)と`display_pc`欄(display_spの上に、少し間をあけて並べる。`display_sp`欄と同じく全行共通)も全行共通
- **行ごと**: 日付・時刻・area(過去のLIVEのtitleから候補を出す)・venue(会場名。候補は過去のvenue。areaが空のときは全venue)・map・tags(上のtagsには足さず、行のtagsだけ)。入力欄の並びは、area+venue / map / tags。tourモード中は上部のvenue / map / setlistid / tagsは非表示で送らない。titleは`公演名`+半角スペース+`area`+`suffix`(areaが空なら公演名のまま)。display_pc・display_spは、それぞれの共通欄+同じ付け方。setlistidはcontentsがLIVE等(上の5つ)で時刻があればdate+timeが自動で入る
- **登録の中身**: 繰り返し登録の行`日付 時刻 | title | contents | url | display_sp | map | setlistid | tags`として送る(後ろの空欄は省く。tagsはカンマ区切りで、フォームのtagsに足す)(display_pcは行に載せず、フォームの`display_pc`として送る。mergeが回ごとに行の部分を足す／`#数字`を+1する)
- **intervalの確認一覧**: 各行に `タイトル / pc: display_pc / sp: display_sp` を並べる(それぞれ`#数字`を回ごとに+1した値)。schedule・tourには確認一覧は出ない。
- **候補表示(自動入力はしない)**: 行のareaが入っているときに、その行のmapまたはtagsの入力欄に入る(またはタイプする)と、同じareaの過去データのmap / tagsを新しい順に候補表示する。押すと入力される。対象のcontentsはLIVE・RELEASEEVENT・FANMEETING。areaは、過去データのtitleの最後の語(末尾の「公演」は除く)と一致するもの。候補の元は`logs_index.json`(この3つのcontentsだけ`map`・`tags`・`groups`を持つ)
- **ANNIVERSARY**: tourモードでは使える(上部の「anniv.」)。チェックすると全行に参照型のANNIVERSARYを作る。付与文言は入力したまま(全行共通)

### helper: schedule モード(関連日程の一括登録)

新規のlogsで「repeat entry」をオンにし、modeを`schedule`にすると、1件の案件の関連日程(開始・締切・当選発表・期限)をまとめて登録できる(チケットの抽選受付など)。modeは`interval`(N日/週/月ごとの間隔)と`schedule`の2つ。

行は`start / close / result / due`の4つ。1行が繰り返し登録の1行(`日付 時刻 | タイトル | contents | URL | display_sp`)になる。

| 行 | 日付・時刻 | contents(自由入力。候補を表示) | ラベル(タイトルに足す語) |
|---|---|---|---|
| start | 画面上部の日付・時刻を使う(チェックを外すと登録しない=開始なし) | 初期値は空。空のときは上のcontentsを使う | 初期値は空。空のときは上のtitleをそのまま使う |
| close | 入力した日付・時刻(時刻が空=時刻なし) | 初期値`CLOSE` | 初期値`締切` |
| result | 同上 | 初期値`RESULT` | 初期値`当選発表` |
| due | 同上 | 初期値`CLOSE` | 初期値`入金期限` |

- **日付を入れた行だけ**が登録される(start以外の日付が空の行は登録しない)。「開始がなくて終了のみ」「当選発表や期限がない」場合に対応する
- 登録されるタイトルは **「上のtitle + ラベル」**(例: `Concert ticket lottery 締切`)。startは、ラベルが空なら上のtitleのまま
- contentsは**自由入力で、文字を入れると候補が出る**(これまでにlogsで使われたcontentsが先、続いて選択肢の一覧)。選択肢にない文字を入れると欄が赤くなり、その行は登録されない
- ラベルの欄の下に、言い換えの候補(チップ)を並べる。押すとラベルに入り、もう一度押すと消える。手入力もできる

| 行 | ラベルの候補(この並び) |
|---|---|
| start | 開始、受付開始、抽選受付開始、販売開始 |
| close | 締切、終了、受付締切、抽選受付締切、販売終了 |
| result | 当選発表 |
| due | 入金期限 |

- **same url**: オンにすると、上のURLを全件に入れる(オフなら入れない)
- **display_sp**: スマホ表示用の**短い名前**を1つ入れる欄。入れると、各行のdisplay_spが「この名前 + ラベル」になる(startはラベルが空ならこの名前だけ)。例: 名前`Ticket`、ラベル`締切` → `Ticket 締切`。空欄ならdisplay_spは付けない(titleがそのまま使われる)
- 例(10/16開始、10/20締切、10/23当選発表、10/25入金期限): 4件が、それぞれ 開始=上のcontents / 締切=CLOSE / 当選発表=RESULT / 入金期限=CLOSE で登録され、URLは全件に入る

#### 画面から削除した説明文(仕様としての意味)

画面を簡潔にするため、次の説明文は表示しないことにした。意味はここに残す。

1. 「start = the date / time / title / contents above. Other rows: fill the date to register it (time empty = none; title = the title above + the label).」
   → startは、画面上部の日付・時刻・title・contentsをそのまま使う。ほかの行は、日付を入れるとその行が登録される(時刻が空なら時刻なし。titleは「上のtitle + ラベル」)。
2. 「Short name used as display_sp of every entry: this + the label (start: this only). Empty = display_sp is not set.」
   → 全件のdisplay_spに使う短い名前。「この名前 + ラベル」が各行のdisplay_spになる(startはこの名前だけ)。空欄ならdisplay_spは付けない。
3. 「N entries will be registered (the url above is added to each / no url; map / sns / display are not copied).」(scheduleモード)
   → 登録される件数。フォームのurl・sns・display_pc・display_spは全件に引き継ぐ(display系は行のラベルを足す。空にした項目は付けない)。mapは引き継がない。
4. scheduleモードの警告「A date / time / contents of a row is not valid (the row is skipped).」
   → 日付・時刻・contentsが正しくない行は、登録しない(その行を飛ばす)。欄が赤くなる。日付が未入力のとき(`Set the date above first.`)は、画面上部の日付を先に入れる必要がある。
5. intervalモードの「including the first date (max 60); empty = auto from until」(countの説明)
   → countは、最初の日付を含む件数(最大60件)。空欄のときは、untilの日付までの件数を自動で数える(untilを入れてcountを入力していなければ自動)。
6. intervalモードの「N of M dates will be registered (the same time / contents / groups / relations / tags; url / map / sns / display are not copied; the #number counts up).」
   → チェックを入れたM件のうちN件が登録される。時刻・contents・groups・relations・tagsは、元と同じものを全件に使う。url・snsは全件に引き継ぎ、display_pc・display_spもtitleと同じく`#数字`が回ごとに+1される(空にした項目は付けない)。mapは引き継がない。

### helper(`helper.html`)

GitHub Pages(`https://piscenake52.github.io/gllogs/`)で公開する入力補助ページ。入力内容から、Issueフォームの**事前入力付きURL**(`/issues/new?template=...&項目=値`)を作る。変更した項目(青枠)だけを事前入力する。tags/snsは更新時に追記、空欄にした値の削除はフォームの「値の削除」で行う。relationsは事前入力できない(JSONで確認)。

- **タブ**: logs / setlist / songs。logsとsetlistは同じ「探す・編集」パネルを共有する(`found`、`renderFound`、`doFind`)
- **新規モード**: 上部の日付・時刻(または「anytime」=時刻なし)を入れると空のフォームができる。**編集モード**: IDで探して読み込む(上部の日付・時刻は隠れる)
- **URLパラメータ**: `?id=<12桁のID>#logs` / `#setlist` でそのIDを自動で探す(データ部からの遷移に使う)
- **logsからsetlistへの遷移**: setlistidのデータが無いときは、setlistidから日付(前8桁)と時刻(後4桁)を自動入力し、logsの行から title→title、groups→artist(`Girls²`/`Laki`、両方なら`Girls² × Laki`)、groupsのメンバー→member、logsの`venue`→venue を引き継ぐ(tagsからは引き継がない。現行は末尾「2026-11 後半の変更のまとめ」)
- **グループ・メンバーのチップ**: G2とL2のチップは常に表示し、ONにするとそのグループのメンバー行が表示される(メンバーが選ばれている間は、G2/L2の見た目はONのまま)。G2/L2をOFFにするとそのメンバーもOFFになる。logsのgroups(データに入る)と、メンバーだけの欄(setlistのmember・曲ごとのメンバー・snsのmember。G2/L2は**表示切替のみ**で値には入らない)で扱いが違う
- **日付入力**: ブラウザ標準ではなく自前のカレンダー(`CAL`)。時刻は標準のピッカー
- **曲目の補助**: 1曲ずつ追加・挿入・更新・削除・移動。type・メンバーのチップ付き
- **snsの補助**: テキストエリアの**上**に、URL欄・メンバーチップ・`add`ボタン。登録済みのリンクは、ボタンの中に**2段**(1段目=リンク、2段目=メンバー)で左寄せに並び、押すとそのリンクを消す/戻す(取り消し線)、右端の↗で開く

#### `<script>` の文字

ASCII のみの制約は 2026-11-27 に廃止した(Blogger に貼らなくなったため)。ファイルは UTF-8 で、日本語をそのまま書ける。既存の `\uXXXX` の表記はそのまま。

### helperの自動入力まとめ(logs / setlist)
- **logsのSNS**: **groupsが選ばれている状態で、contentsにSNSを選んだとき**にだけ、titleが空(またはhelperが自分で入れた値のまま)なら自動入力する。groupsがG2のみで`SNS　Girls²`(上付きの2)、L2のみで`SNS　Laki`、両方で`SNS　`(全角スペース)。**groupsが未選択でcontentsをSNSにした場合、そのあとでgroupsを選んでも自動入力しない**(titleの候補だけ出す。候補はcontentsとgroupsから作る)。自動入力のあとにgroupsを変えても、titleは追従しない。手で書き換えたtitleと、読み込んだデータのtitleは触らない。contentsがSNS以外になり、titleがhelperの入れた値のままなら空に戻す。
- **logsのtitle候補(helper)**: titleの入力で出る候補。(1)固定の候補: contentsがSNSなら `Instagram Live` / `TikTok Live`、CLなら `CLキャス`。後ろに全角スペース+メンバー名(groupsで選ばれたメンバー1〜5人、複数は`・`で結合)を付ける。メンバーが選ばれていなければ、G2だけならグループ名(Girls²)、L2だけならLakiを付ける(それ以外は付けない)。候補は先頭に出し、自動入力はしない。(2)contentsがGLRADIOのとき、選ばれたメンバー名を`＆`で結んだ名前+`のがるらじ`を候補に出す(前編・後編は付けない)。(3)POSTの候補はGirls²とLakiのみ。(4)繰り返し登録のscheduleの行ラベル(row label)に、チップにない語の候補を出す。
- **setlistの新規入力**: idを入れる(日付+時刻を入れた場合も同じ)と、そのidをsetlistidに持つlogsの行から、title←title、artist←groups(G2→Girls²、L2→Laki)、member←groupsのメンバーコード、venue←logsの`venue`だけを引き継ぐ(tagsは使わない)。logsの矢印から遷移した場合は、遷移元の入力値を使う。logsが複数ある場合は、`venue`を持つ行、次にtagsを持つ行を優先して選ぶ(venueへ入れるのはvenueだけ)。元データは`logs_index.json`(LIVE・RELEASEEVENT・FANMEETINGは`groups`・`tags`・`map`・`venue`を持つ)。それ以外のcontentsの行や古いindexのときだけ`logs.json`本体を読む。
- **既存のid**: 編集モード(findで読み込み)。自動入力はしない。
- **tourのmap / tags**: areaと、入力したmap(tags)で過去データが1組に絞れたら、空のもう一方(または自動入力した値)を入れる。

### helper: check タブ(データ点検)

- helperの右端タブ`check`(`#check`)。GitHub上の最新`logs.json`を読み込み、端末内で点検する(読み取り専用。修正はlogsタブで行う)。
- 要修正: date/time形式・実在しない日付、logid重複、refの参照切れ、groupsの未知コード/空(STFは正常。ref行は除外)。
- 要確認: 同日・同時刻・同題名・同種類の重複候補、urlがhttp(s)でない、tags(空配列/空文字/前後空白/重複)。
- 参考: 1回しか使われていないタグ、urlが無い行(titleのある行のみ)。
- 重複候補だけ`ignore`できる(キー=logidを並べ替えて連結、localStorage `glih_ck_ignore`。端末ごと)。`open N`はlogidをid欄に入れてlogsタブで検索する。

### helperのnext(repeat/tour/weekly/monthly/yearly)で引き継ぐ項目

- contents / groups / relations / tags / time / url / display_pc / display_sp / sns を新規入力欄へ入れる。dateは各モードの規則で進める。
- title・display_pc・display_spは末尾の`#数字`を+1する。tourだけは、最後の空白より後ろ(地域名)を除いた部分にする。
- 引き継いだ値を入力欄で消すと、その項目はIssueに送られず、登録されない(新規登録のとき)。

### helper: 半角英数字だけの項目の入力補助

- 対象: id(fid)、contents、groups、relations、member、url、map、setlistid、songsタブのlink。
- ブラウザは日本語入力(IME)のオン・オフを強制できないため、①スマホのキーボード種別を`inputmode`で指定(url/map/link=url、setlistid=numeric、ほか=text。`autocapitalize=off`など)、②入力時に全角の英数字・記号を半角へ自動変換(変換中は行わず、確定後に変換)、③groups/relations/memberは全角・読点のカンマも`,`にする。
- title・display・tags・sns・曲名など日本語を入れる項目は対象外。

## helper: 重複警告 / タグ表記ゆれ警告 / setlist 貼り付け変換

### 重複警告(logs 新規・単発のみ)
- 日付 + 時刻 + title + contents(空は ETC) + groups(順不同の集合)が **すべて一致** する既存行があると、Issue ボタン上に警告を出す(`open` = その行を読み込む、`json` = 読み込んで JSON 欄を開く)。groups が違う行は重複とみなさない。
- 繰り返し登録(repeat)がONの間は判定しない。Issue ボタンは警告中も押せる。
- 判定には logs.json 全件を使う(初回のみ遅延読み込み)。

### タグ表記ゆれ警告(logs の tags)
- 入力したタグが既存タグと完全一致しないが、全角半角・大文字小文字・空白・記号・長音・ひらがな/カタカナ違いを無視すると既存タグと一致する場合に警告。`use existing`(既存表記に置換) / `keep mine`(そのまま、この画面の間は再警告しない)。
- 編集で元から入っていたタグは対象外。編集距離による判定はしない(誤検出が多いため)。

### setlist 貼り付け変換
- setlist の songs 欄の下の `setlist paste` で開く。`1.` `1)` `①` `M1` 形式の番号を解釈、`EN1` / `アンコール` は連番で notes に `encore`。`※` / `MC` 行・見出し行は無視。末尾の `( )` と `★` 以降は notes。
- songs.json に無い曲名は赤表示+候補(最大3件)。自動では直さず、候補を押すと置換。`apply to songs`(空なら置換、入力済みなら追記) / `undo`。

## bulk(まとめて変更・logs のみ)

- helper の `bulk` タブ(check の左)。①絞り込み(tag / 日付範囲 / contents / groups / 文字列) → ②操作 → ③変更前後の一覧(チェックで対象を外せる) → Issue。
- 操作: `tag replace`(from→to。タグの並び順は保つ) / `tag add` / `tag remove` / `contents`(ANNIVERSARY・BIRTHDAY には変更不可)。すでにその状態の行(同じタグが入っている・無い、同じ contents)はエラーにせず黙って飛ばす。
- 上限は 100 件。チェックされた「変更のある行」が 100 件を超える、または絞り込み結果が 300 件を超える間は Issue ボタンを無効にする(超過分を勝手に切り捨てない)。元に戻すための Issue は作らない。
- Issue フォーム `add_bulk.yml`(`bulk ids` = logid を1行ずつ / `bulk op` = replace・add・remove・contents / `bulk from` / `bulk to`)。`issue_to_json.py` が検証して `{"_bulk": {...}}` をキューに出し、`merge_json.py` の `apply_bulk` が反映する。logid が12桁でない・100件超・値の不足は Issue コメントでエラー。見つからない logid は通知コメント。
- 同じ Issue を編集して再実行しても、同じ状態になるだけ(冪等)。

## check タブの追加項目(# の抜け / 開始・終了の対応)

- `# numbers: gaps / duplicates`(要確認): タイトル末尾の `#数字` をシリーズ(contents + `#`以外のタイトル)ごとに見て、番号の抜け・重複を出す。`check_gaps.py` と同じ判定(3種類以上の番号、範囲400以内、抜けが多すぎるものは除外)。カードには抜けの前後の行を表示。
- `start without end / deadline`(要確認): タイトルの `開始` に対して、同じ文字列の `終了` / `締切` が無いもの。過去の日付だけ対象(未来は終了が未発表のことがあるため)。`発券` `有効期間` `日時未定` `配送申請` `ダウンロード` を含むタイトルは対象外。
- `end / deadline without start`(情報): 逆に、終了・締切だけがあるもの。
- 組みの判定: `受付 / 発売 / 販売 / 先行 / 抽選 ...` などの種類語を除いた前後の文字列で対応づける。
- 上の3項目と duplicate は `ignore`(この端末の記憶のみ)で候補から外せる。`show ignored` / `clear ignored` も共通。

## helperの時間入力の補完
- 時間の入力欄(上部のtime、一括の各行のtimeなど)で、3桁(600・930)は先頭に0を足して4桁(0600・0930)にする。1〜2桁は補完しない(時と分の区別がつかないため)。
- 補完のタイミング: 入力欄から離れたとき(blur)と、ボタンを押す直前・Enterを押したとき。補完後が0000〜2359に収まらない値(960→0960)は、これまでどおりエラー。

## helperの通信の最適化
- logs.json(約5MB)と logs_index.json は、IndexedDB に「そのファイルの最新コミットのsha」と一緒に保存する。次に開いたとき、shaが同じなら保存した版を使う(大きなダウンロードなし)。shaが取れないとき(APIの回数制限・オフライン)は、これまでどおり最新を取り直す。check の「run」も、shaを確認してから取得する。
- 同じファイルの取得が重なったときは、1回のダウンロードを共有する(二重ダウンロードをしない)。
- タグの候補(logsのtags・snsリンクのtags)は、logs_index.json から作る。index は全行の `tags` と、snsリンクのタグを並べた `stags` を持つ(`merge_json.py` の `write_index`)。`stags` が無い古いindexのときだけ、全体の logs.json を取る。

### helper: 相互リンク(logs → albums → songs)
- logs行(contents が CD / DVD / BD / MUSICCARD / RELEASE / EP、ref行は除く)を開くと、ref / ref by と同じ欄に albums ボタンを表示する。名前は title の「」『』内、type は tags・display_pc・display_sp・title の ALBUM/AL, EP, SINGLE/SG, MUSICCARD/MUSIC CARD から判定
- albums.json に同名があれば albums タブでその盤を編集用に読み込む(複数あれば1件ずつボタン)。なければ albums の新規入力に title / type(推定) / date を入れて開く
- albums の全トラック行に songs ボタン。songs.json に曲があれば songs タブでその曲を読み込み、なければ title を入れた新規入力(artist は元の logs 行の groups が G2 のみ=Girls², L2 のみ=Laki、両方・不明は空欄)
- あわせて songs タブの link 自動入力が、link の空の曲で無限再帰する不具合を修正

### albums タブ(helper)追記

- type は album / ep / single / musiccard / digital / dvd / blu-ray の7種(issue_to_json.py・merge_json.py も対応)。
- 先頭の `id` 欄に文字入力すると albums 候補が出る(logs の id 候補と同じ表示: 日付+type / title)。12桁hexは album id、それ以外は title・logid として検索。
- `find` 欄は廃止。artist チップは Girls² / Laki のどちらか一方のみ選択(再クリックで解除)。
- editions の format チップに MUSICCARD を追加(CD / DVD / BD / MUSICCARD)。
- type チップの `musiccard` は表示を `mu-ca` に(値は musiccard のまま)。format チップは CD / DVD / BD / DIGITAL / mu-ca(自由入力なので値は `mu-ca`)。

### check タブ追記

- 「LIVE / EVENT / RELEASE without ANNIVERSARY」(to check): ref が自分の logid の ANNIVERSARY 行が無い、contents が LIVE・TOUR・EVENT(RELEASEEVENT / FANMEETING 含む)・RELEASE(CD / DVD / BD / DIGITAL / MUSICCARD / EP 含む)の行を一覧。ignore 可(ブラウザ内保存)。

## helper: sns未addのIssue
- findタブ(logs)のsns入力欄にURLを入力したままaddせずに下のIssueボタンを押すと、そのURLを自動でaddしてからIssueを開く。URLの形式が不正な場合はIssueを開かず、入力欄を赤枠にする。

## helper: songs未addのIssue
- findタブ(setlist)の songs 入力欄(title / # / original / notes / typeチップ)に入力があって add を押していない状態で Issue を押すと、先に add してから Issue が開く(snsと同じ)。
- 止める場合(赤枠): titleが空のまま他の欄だけ入力されている / titleに `|` を含む / # が既存の番号(insert・update・deleteを手で選ぶ必要があるため、# 欄を赤枠にする)。
- setlistのpasteボックスは自動適用しない(songs.jsonに無い曲名の候補を手で選ぶ設計のため)。

## helper: setlistとalbumsの曲の入力の見た目・操作を統一

- 貼り付け: 開閉ボタンの表示を両方「paste」に。貼り付けの操作を両方「replace / append / undo」に統一。setlistは従来の「apply to songs」を「append」に改称し、songsの欄を丸ごと置き換える「replace」と「undo」を追加(読み込み済みのsetlistの編集中は、番号指定のinsert / update / deleteで直すため replace は使えない)。albumsにも「undo」を追加(replace / append の直前の状態へ戻す)。
- 曲名の確認: setlistの1曲入力(#・title)にも、albumsと同じ「OK / not in songs.json + 候補」の表示と、songsタブを開く「→」を追加。
- データの形・番号の付け方(setlistは番号を入力、albumsは自動)・差分編集は従来のまま。

- helperの日付入力欄の幅を150pxから138pxに。空のときは右の余白を詰めて、プレースホルダ(YYYY/MM/DD)が切れないようにする(入力後は曜日と✕の分を空ける)。

- helper: 入力欄のサンプル表示(placeholder。YYYY/MM/DD・HH:MM・https://・title・notes・tags・type・各貼り付け欄の書き方の例など)をすべて削除。残したのは、既存の曲を編集するときに現在の値を薄く見せる表示(title / original / notes)と、次の曲の番号の自動表示(#)、日付・時刻欄の内部用の空白1文字(空のとき✕と曜日を隠すため)。

## helper: setlist の曲の入力(一覧形式)

- setlistの songs は albums の曲目と同じ一覧(1曲1行)。曲名の入力欄の右(スマホは下)に → ↑ ↓ ✕(削除) と ⋯(詳細)を同じ大きさで並べる。add / insert / update と、番号を指定する patch 欄は廃止(一覧の編集と ↑ ↓ ✕ で足りるため。送る内容は一覧全体)。songsのテキスト欄は隠し、値は保持する。
- ⋯ を開くと type チップ、original / notes(ラベル付きで1行)、メンバーを編集。original は type に cover を選んでいるときだけ表示(値は保持)。
- paste(replace / append / undo)で一覧を入れ替え・追加できるので、テキスト欄での自由入力は不要。paste の入力欄は枠なしで、他の入力欄と同じ幅(albumsの paste も同様)。

## helper(logs): id / groups / display / repeat の整理

- id: 「find」ボタンを廃止(候補の表示と選択、またはEnterで読み込む)。
- groups: チップのみ(テキスト欄は隠し、値は保持)。
- display_pc / display_sp: 1行の入力欄(複数行ではない)。
- repeat: 新規作成では、repeat(チェックと設定の枠)を contents の上(groups の下)へ移動。repeat が schedule のときは、title の上の contents 欄を隠す(各行が自分の contents を持つ。start の行は最初に、隠した contents の値が入る)。

- helper(songs): artist のチップに miracle / magical / mirage / lovely を追加(Girls² / Laki の次。押すとその名前が入り、もう一度押すと外れる)。lyrics の「search」ボタン(uta-netの検索)は廃止。

## helper: artist と member を1つの欄に統合(setlist・albums)

- artist の欄の下に、artist チップ(Girls² / Laki)と member のチップ(G2 / L2 と各メンバー)を続けて表示。member のテキスト欄は隠し(値の保持用)、member の行は出さない。artist のテキスト欄は、Girls² / Laki 以外の名前の自由入力用として残す。
- artist のチップを押すと member が自動で入る(従来どおり。手で直した member は上書きしない)。
- 逆に、member のチップを選ぶと artist のチップが自動で付く(G2 のメンバーがいれば Girls²、L2 のメンバーがいれば Laki、両方なら「Girls² × Laki」。artist に手で入れた他の名前は残す)。member が空のときは artist を変えない。
- 送るデータの形(artist / member)は従来のまま。

- helper(setlist / albums): artist と member を1つの「artist」欄に統合。artist の入力欄(Girls² / Laki 以外の名前も自由入力できる)と Girls² / Laki のチップの下に、member のチップ(G2 / L2 と各メンバー)を並べる。member のテキスト欄は隠し、値だけ保持する。メンバーを選ぶと artist のチップも連動する(G2のメンバー = Girls²、L2のメンバー = Laki。artist 欄に手で入れた他の名前は残す)。
