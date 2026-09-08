(() => {
  // localStorageが使えない/制限された環境(プライベートモードや一部のAndroid設定等でSecurityErrorになる場合)
  // でも、アプリ全体が読み込みエラーで止まってしまわないよう、必ずこの安全なラッパー経由でアクセスする。
  // 失敗時はキャッシュ・設定の保存/復元を諦めるだけで、致命的なエラーにはしない。
  const lsGet = key => { try { return localStorage.getItem(key); } catch (e) { return null; } };
  const lsSet = (key, value) => { try { localStorage.setItem(key, value); } catch (e) {} };

  // 特定の配信元(ホスト名+パス)からのアクセスかどうかをハッシュ比較で判定する(URL文字列はソースに直接書かない)。
  // headの早期リダイレクト用スクリプトと同じアルゴリズム・同じハッシュ値を使用している。
  const isForcedFreshSource = () => {
    const simpleHash = s => {
      let h = 0;
      for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
      return h;
    };
    return simpleHash(location.hostname) === -1626720631 && simpleHash(location.pathname) === 982197929;
  };
  let logs = [], filtered = [], rendered = 0, updating = false;
  let desc = true, defaultText = '', timer = null, renderTimer = null;
  let setlistData = []; // setlist.json(公演ごとのセットリスト)のキャッシュ
  let songsData = []; // songs.json(artist/title/link)のキャッシュ。SETLISTポップアップの再生ボタンにも使う
  let setlistMode = false; // SETLISTボタンでON/OFFする「セトリ検索モード」
  const pageSize = 40, isTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  const $ = id => document.getElementById(id);
  // G2: 小田柚葉:YZH、隅谷百花:MMK、鶴屋美咲:MSK、小川桜花:YOK、増田來亜:KUR、菱田未渚美:MNM、山口綺羅:KIR、原田都愛:TOA、石井蘭:RAN
  // L2: 山口莉愛:RIN、杉浦優來:YUR、永山椿:TBK、深澤日彩:HIR、比嘉優和:YUW、佐藤栞奈:KAN、上村梨々香:RRK、森朱里:AKR、佐藤妃希:KIK
  const g2 = [
    {v:'G2',t:'Girls\u00B2'},{v:'YZH',n:'YUZUHA',c:'\uD83E\uDE75'},{v:'MMK',n:'MOMOKA',c:'\uD83D\uDC99'},{v:'MSK',n:'MISAKI',c:'\uD83E\uDDE1'},
    {v:'YOK',n:'YOKA',c:'\uD83D\uDC9C'},{v:'KUR',n:'KUREA',c:'\uD83E\uDD0D'},{v:'MNM',n:'MINAMI',c:'\uD83E\uDE77'},{v:'KIR',n:'KIRA',c:'\uD83D\uDC9B'},
    'sep',{v:'RAN',n:'RAN',c:'\u2764\uFE0F'},{v:'TOA',n:'TOA',c:'\uD83D\uDC9A'}
  ];
  const l2 = [
    {v:'L2',t:'Laki'},{v:'RIN',n:'RINA',c:'\uD83D\uDC9C'},{v:'TBK',n:'TSUBAKI',c:'\uD83E\uDDE1'},{v:'HIR',n:'HIIRO',c:'\uD83E\uDE75'},
    {v:'YUW',n:'YUWA',c:'\u2764\uFE0F'},{v:'KAN',n:'KANNA',c:'\uD83D\uDC99'},{v:'RRK',n:'RIRIKA',c:'\uD83E\uDE77'},{v:'AKR',n:'AKARI',c:'\uD83D\uDC9A'},
    {v:'KIK',n:'KIKI',c:'\uD83D\uDC9B'},'sep',{v:'YUR',n:'YURA',c:'\uD83E\uDD0D'}
  ];
  const others = ['FANCLUB','DIARY','GLRADIO','GTUBE','YOUTUBE','CL','SNS','RELEASE','LIVE','EVENT','MODEL','MOVIE','MEDIA','WEB','TICKET','SALES','ANNIVERSARY','BIRTHDAY','ETC'];

  const symbols = {
    'FANCLUB': '\uD83D\uDCE3',
    'DIARY': '\uD83D\uDCDD', 'GLRADIO': '\uD83D\uDD0A', 'GTUBE': '\u25B6\uFE0F', 'YOUTUBE': '\uD83C\uDF9E\uFE0F', 
    'CL': '\uD83C\uDD91', 'RELEASE': '\uD83C\uDFA7', 'LIVE': '\uD83C\uDF99\uFE0F', 
    'EVENT': '\uD83D\uDCAC', 'MEDIA': '\uD83D\uDCE1', 'WEB': '\uD83C\uDF10', 'SNS': '\uD83D\uDCF1', 'SALES': '\uD83D\uDED2', 'ANNIVERSARY': '\uD83D\uDD16', 'BIRTHDAY': '\uD83C\uDF82',
    'MODEL': '\uD83D\uDC60', 'MOVIE': '\uD83C\uDFAC\uFE0F', 'TICKET': '\uD83C\uDFAB',
    'CLOSE': '\u2705', 'RESULT': '\uD83C\uDFAF', 'CAMPAIGN': '\uD83D\uDCE8', 'PLAYING': '\uD83C\uDFB6', // フィルターボタンには表示せず、ETC選択時のみ該当させる
    'ETC': '\uD83D\uDCCC',
    // 以下4種類はcontentsフィルターボタンには表示しないが、フィルター判定上は"RELEASE"として扱う(normalizeContType参照)。
    // データ部のアイコン表示ではそれぞれ専用のアイコン+コンテンツ名を表示する。
    'CD': '\uD83D\uDCBF\uFE0F', 'DVD': '\uD83D\uDCC0\uFE0F', 'BD': '\uD83D\uDCC0\uFE0F', 'DIGITAL': '\uD83C\uDFA7',
    // 以下5種類はフィルターボタンには表示せず、フィルター判定上は"MEDIA"として扱う(normalizeContType参照)
    'TV': '\uD83D\uDCFA\uFE0F', 'RADIO': '\uD83D\uDCFB\uFE0F', 'MAGAZINE': '\uD83D\uDCD6', 'BOOK': '\uD83D\uDCDA', 'NEWSPAPER': '\uD83D\uDCF0',
    // 以下2種類はフィルターボタンには表示せず、フィルター判定上は"WEB"として扱う(normalizeContType参照)
    'STREAMING': '\uD83D\uDCF6', 'PODCAST': '\uD83C\uDFA4',
    // COLUMNはフィルターボタンには表示せず、フィルター判定上は"WEB"として扱う(normalizeContType参照)
    'COLUMN': '\uD83C\uDF10',
    // GOODSはフィルターボタンには表示せず、フィルター判定上は"SALES"として扱う(normalizeContType参照)
    'GOODS': '\uD83D\uDED2',
    // 以下2種類はフィルターボタンには表示せず、フィルター判定上は"EVENT"として扱う(normalizeContType参照)
    'STAGE': '\uD83C\uDFAD', 'COOKING': '\uD83C\uDF7D\uFE0F'
  };

  // 内部値(contents値・フィルター値)と実際の表示名が異なるものだけここに登録する(それ以外は値そのものを表示名として使う)
  const contentDisplayNames = { 'GLRADIO': 'GL\u00B2RADIO' };
  const displayNameFor = v => contentDisplayNames[v] || v;

  const dayNames = ['日', '月', '火', '水', '木', '金', '土'];

  // 項目左端の日付表示:年/月/日/曜日/時分をそれぞれ個別に表示on/offできる(次回訪問時も記憶)
  const DATE_PARTS_KEY = 'gl_log_date_parts';
  let dateParts = { year: true, month: true, day: true, weekday: true, time: false };
  try {
    const savedParts = JSON.parse(lsGet(DATE_PARTS_KEY) || 'null');
    if (savedParts && typeof savedParts === 'object') dateParts = Object.assign(dateParts, savedParts);
  } catch (e) { /* 壊れていたら既定値のまま使う */ }

  const formatTimeStr = timeStr => {
    if (!timeStr || timeStr.length !== 4) return '';
    return timeStr.slice(0, 2) + ':' + timeStr.slice(2, 4);
  };

  // dateは「20260908」のような8桁(年4桁+月2桁+日2桁)の文字列を想定
  const formatDisplayDate = item => {
    const dateStr = item.date;
    if (!dateStr) return '';
    if (!/^\d{8}$/.test(dateStr)) return dateStr; // 想定外フォーマットはそのまま表示
    const y = dateStr.slice(0, 4), m = dateStr.slice(4, 6), d = dateStr.slice(6, 8);
    const dateObj = new Date(parseInt(y, 10), parseInt(m, 10) - 1, parseInt(d, 10));
    const dayStr = isNaN(dateObj.getTime()) ? '' : dayNames[dateObj.getDay()];

    // 画面表示は従来通り「年.月.日」のドット区切りにする(データ格納形式とは切り離す)
    const ymd = [];
    if (dateParts.year) ymd.push(y);
    if (dateParts.month) ymd.push(m);
    if (dateParts.day) ymd.push(d);
    let out = ymd.join('.');
    if (dateParts.weekday && dayStr) out += (out ? ' ' : '') + `[${dayStr}]`;
    return out;
  };

  // 8桁のYYYYMMDD形式は既にゼロ埋め済みなので、そのまま文字列比較でソート可能
  const normalizeDateForSort = dateStr => dateStr || '';

  // ソート専用のキー:date(正規化)とtime(HHMM、未設定時は"0000"扱い)を組み合わせる。
  // timeは検索対象には含めない(検索用テキストの生成には使わない)。
  const sortKeyFor = item => normalizeDateForSort(item.date) + '_' + (item.time || '0000');

  const createLabel = item => {
    if (item === 'sep') {
      const s = document.createElement('span');
      s.className = 'sep';
      s.textContent = '/';
      return s;
    }
    const l = document.createElement('label');
    l.tabIndex = 0;
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.tabIndex = -1;
    cb.value = item.v || item;
    const sp = document.createElement('span');
    sp.className = 'label-text';
    if (item.n) {
      sp.title = item.n;
      sp.textContent = item.c;
      l.title = item.n; // ホバー範囲をアイコンだけでなくボタン全体に拡張
    } else if (typeof item === 'string' && symbols[item] !== undefined) {
      // コンテンツ種類ボタン:通常はテキスト、ICONモードON時はアイコンのみ表示に切り替える
      const iconPart = document.createElement('span');
      iconPart.className = 'label-icon-part';
      iconPart.textContent = symbols[item];
      const textPart = document.createElement('span');
      textPart.className = 'label-text-part';
      textPart.textContent = displayNameFor(item);
      sp.append(iconPart, textPart);
      l.dataset.tooltipName = displayNameFor(item); // ICONモード時のみtitleとして反映する(updateContentTooltipsで制御)
    } else {
      sp.textContent = item.t || item;
    }
    if (item.v && item.t) l.className = 'btn-group';
    const badge = document.createElement('span');
    badge.className = 'count-badge';
    badge.style.display = 'none';
    l.append(cb, sp, badge);
    return l;
  };

  g2.forEach(i => $('memberChecks1').appendChild(createLabel(i)));
  l2.forEach(i => $('memberChecks2').appendChild(createLabel(i)));
  const applySavedContentOrder = arr => {
    try {
      const saved = JSON.parse(lsGet('gl_log_content_order') || 'null');
      if (!Array.isArray(saved)) return arr;
      const savedValid = saved.filter(v => arr.includes(v));
      const rest = arr.filter(v => !savedValid.includes(v));
      return [...savedValid, ...rest];
    } catch (e) {
      return arr;
    }
  };

  others.splice(0, others.length, ...applySavedContentOrder(others));
  others.forEach(o => $('otherChecks').appendChild(createLabel(o)));

  // コンテンツ種類ボタンのみ、ドラッグ&ドロップで並び替え可能にする(並びはlocalStorageに記憶)
  (() => {
    const row = $('otherChecks');
    let draggedEl = null;

    const saveOrder = () => {
      const order = Array.from(row.querySelectorAll('label')).map(l => l.querySelector('input')?.value).filter(Boolean);
      lsSet('gl_log_content_order', JSON.stringify(order));
    };

    Array.from(row.querySelectorAll('label')).forEach(label => {
      label.draggable = true;

      label.addEventListener('dragstart', e => {
        draggedEl = label;
        label.classList.add('is-dragging-reorder');
        e.dataTransfer.effectAllowed = 'move';
      });

      label.addEventListener('dragend', () => {
        draggedEl = null;
        label.classList.remove('is-dragging-reorder');
        saveOrder();
      });

      label.addEventListener('dragover', e => {
        e.preventDefault();
        if (!draggedEl || draggedEl === label) return;
        const rect = label.getBoundingClientRect();
        const before = (e.clientX - rect.left) < rect.width / 2;
        row.insertBefore(draggedEl, before ? label : label.nextSibling);
      });
    });
  })();


  const enableHorizontalScroll = el => {
    el.addEventListener('wheel', e => {
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
      if (el.scrollWidth <= el.clientWidth) return;
      e.preventDefault();
      el.scrollLeft += e.deltaY;
    }, { passive: false });

    let isDragging = false, dragStartX = 0, dragStartScrollLeft = 0, hasDragged = false;
    el.addEventListener('mousedown', e => {
      isDragging = true; hasDragged = false;
      dragStartX = e.pageX; dragStartScrollLeft = el.scrollLeft;
      el.style.cursor = 'grabbing';
    });
    window.addEventListener('mousemove', e => {
      if (!isDragging) return;
      const dx = e.pageX - dragStartX;
      if (Math.abs(dx) > 3) hasDragged = true;
      el.scrollLeft = dragStartScrollLeft - dx;
    });
    window.addEventListener('mouseup', () => {
      if (!isDragging) return;
      isDragging = false;
      el.style.cursor = '';
    });
    el.addEventListener('click', e => {
      if (hasDragged) { e.preventDefault(); e.stopPropagation(); hasDragged = false; }
    }, true);
  };
  document.querySelectorAll('.checks-row-years, .checks-row-other, .header-btn-group').forEach(enableHorizontalScroll);

  let checkboxes = document.querySelectorAll('.checks input[type="checkbox"]');
  let labels = document.querySelectorAll('.checks label:has(input)');
  const g2Vals = ['YZH','MMK','MSK','YOK','KUR','MNM','KIR','TOA','RAN'];
  const l2Vals = ['RIN','YUR','TBK','HIR','YUW','KAN','RRK','AKR','KIK'];
  const allGroupVals = [...g2Vals, ...l2Vals];

  // groupsからGirls\u00b2(G2)/Laki(L2)どちらの予定かを判定する。
  // 1) groupsに'G2'/'L2'のリテラルタグがあればそれを優先。
  // 2) どちらのリテラルタグも無ければ、メンバーコードの内容からG2/L2を判定する。
  // 3) 両方に該当する場合は'both'を返す(斜め半々アイコン用)。
  const getTeamClass = item => {
    const g = item.groups || [];
    let hasG2 = g.includes('G2');
    let hasL2 = g.includes('L2');
    if (!hasG2 && !hasL2) {
      hasG2 = g.some(v => g2Vals.includes(v));
      hasL2 = g.some(v => l2Vals.includes(v));
    }
    if (hasG2 && hasL2) return 'both';
    if (hasG2) return 'g2';
    if (hasL2) return 'l2';
    return null;
  };

  // ソート用:日付+時刻が同じ場合のタイブレーク優先順位(G2とL2両方 > G2のみ > L2のみ > STF含む > それ以外)
  // STFが含まれる場合は、たとえgroupsにG2/L2のリテラルタグが同時にあっても常に「STF含む」枠になる
  const groupSortRank = item => {
    const g = item.groups || [];
    if (g.includes('STF')) return 3;
    const tc = getTeamClass(item);
    if (tc === 'both') return 0;
    if (tc === 'g2') return 1;
    if (tc === 'l2') return 2;
    return 4;
  };
  // ソート用:日付+時刻+グループも同じ場合のタイブレーク。メンバーフィルターボタンの実際の表示順
  // (g2→l2、それぞれボタンの並び順どおり)でランク付けする。複数メンバーが該当する場合は
  // 最も並び順が早いメンバーを代表値として使う。該当メンバーが無ければ末尾扱い。
  const memberOrder = [...g2, ...l2]
    .filter(i => typeof i === 'object' && i.n !== undefined)
    .map(i => i.v);
  const memberSortRank = item => {
    const g = item.groups || [];
    let best = memberOrder.length;
    g.forEach(v => {
      const idx = memberOrder.indexOf(v);
      if (idx !== -1 && idx < best) best = idx;
    });
    return best;
  };

  // データ部のG2/L2アイコンをクリックした際に表示する、メンバーコード→(名前,ハート絵文字)の対応表
  const memberInfoByCode = {};
  [...g2, ...l2].forEach(i => {
    if (typeof i === 'object' && i.n !== undefined) memberInfoByCode[i.v] = { n: i.n, c: i.c };
  });

  // 💞ボタン(ハートモード):データ部のハート表示を一括で展開/縮小する。
  // 個別のG2/L2アイコンでの開閉とも連動し、ひとつでも展開されていればON、ひとつも展開されていなければOFFとする。
  // フィルター変更や追加読み込みで行が再描画された場合も、ON中は新しく表示される行のハートを自動的に展開状態で生成する。
  let heartModeOn = false;
  const refreshHeartModeState = () => {
    heartModeOn = !!$('items').querySelector('.team-hearts.is-open');
    $('heartToggleBtn').classList.toggle('is-active', heartModeOn);
  };

  // team-both(G2/L2両方)の行でハートを一括表示する際、どちらのグループのメンバーかを判定するための集合
  const g2MemberCodes = new Set(g2.filter(i => typeof i === 'object' && i.n !== undefined).map(i => i.v));
  const l2MemberCodes = new Set(l2.filter(i => typeof i === 'object' && i.n !== undefined).map(i => i.v));

  const primaryConts = ['FANCLUB','DIARY','GLRADIO','GTUBE','YOUTUBE','CL','SNS','RELEASE','LIVE','EVENT','MEDIA','WEB','SALES','ANNIVERSARY','BIRTHDAY','MODEL','MOVIE','TICKET'];
  const allConts = [...primaryConts, 'ETC'];
  const cats = [{meta:'G2',values:g2Vals},{meta:'L2',values:l2Vals}];

  // CD/DVD/BD/DIGITALはコンテンツフィルターボタンには表示しないが、フィルター判定(年/コンテンツ種類/自動on-off/
  // 件数プレビュー/ソート等)上は"RELEASE"の一部として扱う。データ部の表示(アイコン・コンテンツ名)には影響しない。
  const releaseAliasConts = ['CD', 'DVD', 'BD', 'DIGITAL'];
  const mediaAliasConts = ['TV', 'RADIO', 'MAGAZINE', 'BOOK', 'NEWSPAPER'];
  const webAliasConts = ['STREAMING', 'PODCAST', 'COLUMN'];
  const salesAliasConts = ['GOODS'];
  const eventAliasConts = ['STAGE', 'COOKING'];
  const normalizeContType = c =>
    releaseAliasConts.includes(c) ? 'RELEASE' :
    mediaAliasConts.includes(c) ? 'MEDIA' :
    webAliasConts.includes(c) ? 'WEB' :
    salesAliasConts.includes(c) ? 'SALES' :
    eventAliasConts.includes(c) ? 'EVENT' : c;

  // ソート用:日付+時刻+グループも同じ場合の最終タイブレーク。othersはコンテンツフィルターボタンの
  // 現在の並び順(ドラッグでの並び替え結果を含む)を反映しているため、そのインデックスをそのまま使う。
  const contentSortRank = item => {
    const idx = others.indexOf(normalizeContType(item.contents));
    return idx === -1 ? others.length : idx;
  };

  const updateThemeButtonStyle = isDark => {
    const btn = $('themeToggleBtn');
    // ボタンの色は「押すと切り替わる先」の色を示す:ライト時は黒丸(押すとダークに)、ダーク時は白丸(押すとライトに)
    btn.classList.toggle('mode-to-dark', !isDark);
    btn.classList.toggle('mode-to-light', isDark);
    btn.setAttribute('aria-label', isDark ? '\u30E9\u30A4\u30C8\u30E2\u30FC\u30C9\u306B\u5207\u308A\u66FF\u3048' : '\u30C0\u30FC\u30AF\u30E2\u30FC\u30C9\u306B\u5207\u308A\u66FF\u3048');
  };

  // ダークモードのクラス付与はhead内の同期スクリプトで既に完了している(初期表示のチラつき防止のため)。
  // ここではボタンの見た目を現在の状態に合わせて初期化するだけ
  updateThemeButtonStyle(document.documentElement.classList.contains('dark-mode'));

  $('themeToggleBtn').onclick = () => {
    const isDark = document.documentElement.classList.toggle('dark-mode');
    updateThemeButtonStyle(isDark);
    lsSet('gl_log_theme', isDark ? 'dark' : 'light');
  };

  if (lsGet('gl_log_collapsed') === 'true') {
    $('stickyHeader').classList.add('collapsed');
    $('toggleBtn').textContent = '\u25BC';
  }
  requestAnimationFrame(() => $('stickyHeader').classList.remove('is-initializing'));

  $('toggleBtn').onclick = () => {
    const c = $('stickyHeader').classList.toggle('collapsed');
    $('toggleBtn').textContent = c ? '\u25BC' : '\u25B2';
    lsSet('gl_log_collapsed', c);
  };

  // 錠前ボタン:既定はOFF(画面固定しない、通常スクロール)。ONにするとヘッダーが画面上部に固定される。
  const setHeaderLocked = (locked, persist) => {
    $('stickyHeader').classList.toggle('unlocked', !locked);
    $('lockToggleBtn').classList.toggle('is-active', locked);
    $('lockToggleBtn').textContent = locked ? '\uD83D\uDD12' : '\uD83D\uDD13';
    $('lockToggleBtn').setAttribute('aria-label', locked ? '\u30D8\u30C3\u30C0\u30FC\u56FA\u5B9A\u5207\u66FF(\u73FE\u5728ON)' : '\u30D8\u30C3\u30C0\u30FC\u56FA\u5B9A\u5207\u66FF(\u73FE\u5728OFF)');
    if (persist) lsSet('gl_log_header_locked', locked);
  };

  setHeaderLocked(lsGet('gl_log_header_locked') === 'true', false);

  $('lockToggleBtn').onclick = () => {
    setHeaderLocked(!$('lockToggleBtn').classList.contains('is-active'), true);
  };

  $('sortBtn').onclick = () => {
    desc = !desc;
    $('sortBtn').textContent = desc ? '\u2193' : '\u2191';
    updateDisplay(true);
  };

  const searchInput = $('searchInput');
  const searchClearBtn = $('searchClearBtn');
  const searchBoxWrap = searchInput.parentElement;
  const searchSuggestions = $('searchSuggestions');

  const updateSearchClearState = () => {
    if (searchInput.value.length > 0) {
      searchBoxWrap.classList.add('has-text');
    } else {
      searchBoxWrap.classList.remove('has-text');
    }
  };

  // セトリ検索モード中は検索窓のプレースホルダーの「keywoooooooord」部分を「soooooooong」に切り替える
  const SEARCH_PLACEHOLDER_NORMAL = 'search keywoooooooord \u0d26\u0d4d\u0d26\u0d3f(\uff65\u1d17|';
  const SEARCH_PLACEHOLDER_SETLIST = 'search soooooooong \u0d26\u0d4d\u0d26\u0d3f(\uff65\u1d17|';
  const updateSearchPlaceholder = () => {
    searchInput.placeholder = setlistMode ? SEARCH_PLACEHOLDER_SETLIST : SEARCH_PLACEHOLDER_NORMAL;
  };

  // 検索窓:直近使った検索ワードを最大5件まで記憶し、フォーカス時に候補として表示する
  // セトリ検索モード中に入力された検索ワードは、通常検索とは別のキーで保存する(要件により分離)
  const RECENT_SEARCH_KEY = 'gl_log_recent_searches';
  const SETLIST_RECENT_SEARCH_KEY = 'gl_log_recent_setlist_searches';
  const MAX_RECENT_SEARCHES = 5;
  let highlightedSuggestionIndex = -1;
  const getRecentSearchKey = () => setlistMode ? SETLIST_RECENT_SEARCH_KEY : RECENT_SEARCH_KEY;
  const getRecentSearches = () => {
    try {
      const arr = JSON.parse(lsGet(getRecentSearchKey()) || '[]');
      return Array.isArray(arr) ? arr : [];
    } catch {
      return [];
    }
  };
  const saveRecentSearch = kw => {
    const trimmed = kw.trim();
    if (!trimmed) return;
    const key = getRecentSearchKey();
    const list = getRecentSearches().filter(v => v !== trimmed);
    list.unshift(trimmed);
    lsSet(key, JSON.stringify(list.slice(0, MAX_RECENT_SEARCHES)));
  };
  const removeRecentSearch = kw => {
    const key = getRecentSearchKey();
    const list = getRecentSearches().filter(v => v !== kw);
    lsSet(key, JSON.stringify(list));
  };
  const getSuggestionButtons = () => Array.from(searchSuggestions.querySelectorAll('button'));
  const highlightSuggestion = index => {
    const btns = getSuggestionButtons();
    highlightedSuggestionIndex = index;
    btns.forEach(b => b.classList.remove('is-highlighted'));
    if (index >= 0 && index < btns.length) {
      btns[index].classList.add('is-highlighted');
      try { btns[index].scrollIntoView({ block: 'nearest' }); } catch {}
    }
  };
  const applySuggestion = term => {
    searchInput.value = term;
    updateSearchClearState();
    saveRecentSearch(term);
    searchSuggestions.classList.remove('is-open');
    syncTodayModeFromSearch(); // 年月日8桁の候補が選ばれた場合もTODAYモードに反映する
    if (setlistMode) {
      autoUpdateContentTypeFilters();
      updateManualIndicators();
    }
    updateDisplay(true);
  };
  const renderSearchSuggestions = () => {
    const list = getRecentSearches();
    searchSuggestions.textContent = '';
    highlightedSuggestionIndex = -1;
    if (!list.length) {
      searchSuggestions.classList.remove('is-open');
      return;
    }
    list.forEach(term => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = term;
      // mousedownで反応させる(inputのblurより先に発火させ、候補クリックが確実に効くようにするため)
      btn.onmousedown = e => {
        e.preventDefault();
        applySuggestion(term);
      };
      searchSuggestions.appendChild(btn);
    });
    searchSuggestions.classList.add('is-open');
  };
  searchInput.addEventListener('focus', () => {
    if (!searchInput.value) renderSearchSuggestions();
  });
  searchInput.addEventListener('blur', () => {
    searchSuggestions.classList.remove('is-open');
    if (searchInput.value.trim()) saveRecentSearch(searchInput.value);
  });

  searchInput.oninput = () => {
    updateSearchClearState();
    searchSuggestions.classList.remove('is-open'); // 入力し始めたら候補は引っ込める(ライブ検索と競合しないように)
    syncTodayModeFromSearch(); // 年月日8桁の入力/削除に応じてTODAYモードをON/OFFする
    clearTimeout(timer);
    timer = setTimeout(() => {
      // セトリ検索モード中は、検索ワードの変化に応じてコンテンツ種類フィルターも自動on/offする
      if (setlistMode) {
        autoUpdateContentTypeFilters();
        updateManualIndicators();
      }
      updateDisplay(true);
    }, 180);
  };
  searchInput.addEventListener('keydown', e => {
    const isOpen = searchSuggestions.classList.contains('is-open');
    const btns = getSuggestionButtons();

    if (isOpen && btns.length && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault();
      const next = e.key === 'ArrowDown'
        ? (highlightedSuggestionIndex < btns.length - 1 ? highlightedSuggestionIndex + 1 : 0)
        : (highlightedSuggestionIndex > 0 ? highlightedSuggestionIndex - 1 : btns.length - 1);
      highlightSuggestion(next);
      return;
    }

    if (isOpen && highlightedSuggestionIndex >= 0 && btns[highlightedSuggestionIndex]) {
      // ハイライト中の候補をDeleteキーで削除する
      if (e.key === 'Delete') {
        e.preventDefault();
        const targetIndex = highlightedSuggestionIndex;
        removeRecentSearch(btns[targetIndex].textContent);
        renderSearchSuggestions();
        const newBtns = getSuggestionButtons();
        if (newBtns.length) highlightSuggestion(Math.min(targetIndex, newBtns.length - 1));
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        applySuggestion(btns[highlightedSuggestionIndex].textContent);
        return;
      }
    }

    if (e.key === 'Escape' && isOpen) {
      searchSuggestions.classList.remove('is-open');
      return;
    }

    if (e.key === 'Enter' && searchInput.value.trim()) {
      saveRecentSearch(searchInput.value);
    }
  });

  searchClearBtn.onclick = () => {
    searchInput.value = '';
    updateSearchClearState();
    syncTodayModeFromSearch(); // クリアで日付ではなくなるのでTODAYモードもOFFに戻す
    if (setlistMode) {
      autoUpdateContentTypeFilters();
      updateManualIndicators();
    }
    updateDisplay(true);
    searchInput.focus();
  };

  window.onkeydown = e => {
    if ((e.key === '/' || (e.ctrlKey && e.key.toLowerCase() === 'k')) && document.activeElement !== searchInput) {
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
    }
  };

  window.onscroll = () => $('toTopBtn').classList.toggle('is-visible', window.scrollY > 300);
  $('toTopBtn').onclick = () => window.scrollTo({ top: 0, behavior: 'smooth' });

  let isMobileState = window.innerWidth <= 600;
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      const nowMobile = window.innerWidth <= 600;
      if (nowMobile !== isMobileState) {
        isMobileState = nowMobile;
        updateDisplay(false);
      }
      if ($('songBar').classList.contains('is-open')) updateSongTickerScroll();
    }, 200);
  });

  const createItemNode = item => {
    const w = document.createElement('div');
    w.className = 'item';
    const sc = document.createElement('div');
    sc.className = 'item-scroll-container';
    
    const d = document.createElement('span');
    d.className = 'item-date';
    d.textContent = formatDisplayDate(item);

    // 時刻は日付と別要素にして、未設定の行でも"00:00"と同じ幅を確保したまま見た目だけブランクにする
    // (幅を確保しないと、後ろのコンテンツ種類アイコン等が左にずれて見えるため)
    let tm = null;
    if (dateParts.time) {
      const t = formatTimeStr(item.time);
      tm = document.createElement('span');
      tm.className = 'item-time';
      tm.textContent = t || '00:00';
      if (!t) tm.classList.add('is-blank');
    }
    
    const ct = document.createElement('span');
    ct.className = 'item-contents';
    if (item.contents) {
      // スマホ版・ICONモードONはアイコンのみ、それ以外(PC版・ICONモードOFF)は「アイコン + コンテンツ名」で出し分け
      const contentsName = displayNameFor(item.contents);
      ct.textContent = (isMobileState || iconMode) ? (symbols[item.contents] || contentsName) : ((symbols[item.contents] ? symbols[item.contents] + ' ' : '') + contentsName);
    } else {
      ct.textContent = '';
    }

    // http(s)始まりのURLのみリンク化する(javascript:等の危険なスキームを弾く簡易バリデーション)
    const hasUrl = !!(item.url && /^https?:\/\//i.test(item.url.trim()));
    const t = document.createElement(hasUrl ? 'a' : 'span');
    t.className = 'item-title';
    t.tabIndex = -1; // データ部の文章はTab移動の対象にしない(クリック/タップでは従来通り操作可能)
    if (hasUrl) {
      t.href = item.url;
      t.target = '_blank';
      t.rel = 'noopener noreferrer';
    } else {
      t.classList.add('no-url');
    }
    t.textContent = ((isMobileState ? item.display_sm : item.display_pc) || item.title || '').trim();

    const teamClass = getTeamClass(item);
    // MAPモードON時のみ、mapに有効なhttp(s)リンクがある場合に📍アイコンをリンク化して表示する(値が無ければ何も表示しない)
    let mp = null;
    if (mapMode) {
      const hasMap = !!(item.map && /^https?:\/\//i.test(item.map.trim()));
      mp = document.createElement(hasMap ? 'a' : 'span');
      mp.className = 'map-pin';
      mp.tabIndex = -1; // データ部のアイコンはTab移動の対象にしない
      mp.textContent = '\uD83D\uDCCD'; // map値の有無にかかわらず同じ幅を確保するため、常にアイコン文字を入れておく
      if (hasMap) {
        mp.href = item.map;
        mp.target = '_blank';
        mp.rel = 'noopener noreferrer';
      }
    }

    // セトリ検索モード中、setlistidを持つ行にのみ📍の右にSETLISTアイコンを表示する。押すとセットリストをポップアップ表示する
    let sl = null;
    if (setlistMode && item.setlistid) {
      sl = document.createElement('span');
      sl.className = 'setlist-icon';
      sl.tabIndex = -1; // データ部のアイコンはTab移動の対象にしない
      sl.textContent = '\uD83D\uDCCB\uFE0F';
      sl.setAttribute('role', 'button');
      sl.setAttribute('aria-label', 'Setlist');
      sl.onclick = e => {
        e.stopPropagation();
        openSetlistModal(item.setlistid);
      };
    }

    const dateChildren = tm ? [d, tm] : [d];
    const children = [...dateChildren, ...(mp ? [mp] : []), ...(sl ? [sl] : []), ct];
    if (teamClass) {
      const ti = document.createElement('span');
      ti.className = 'team-icon team-' + teamClass;

      // groups内のメンバーコードのうち、名前が判明しているものだけを表示順(g2→l2)で抽出する
      const memberCodes = memberOrder.filter(v => (item.groups || []).includes(v));
      if (memberCodes.length) {
        const hearts = document.createElement('span');
        hearts.className = 'team-hearts';
        // 四角(マーカー)はteam-both(G2/L2混在)の行のみ、G2/L2それぞれの最初のハートに直接クラスを付けて
        // CSSでバッジのように重ねて表示する(独立した別枠にすると、四角の有無でハートの位置がずれてしまうため)
        let g2MarkerAdded = false, l2MarkerAdded = false;
        memberCodes.forEach(code => {
          const info = memberInfoByCode[code];
          if (!info) return;
          const h = document.createElement('span');
          h.className = 'team-heart';
          if (teamClass === 'both') {
            if (!g2MarkerAdded && g2MemberCodes.has(code)) {
              h.classList.add('group-start-g2');
              g2MarkerAdded = true;
            } else if (!l2MarkerAdded && l2MemberCodes.has(code)) {
              h.classList.add('group-start-l2');
              l2MarkerAdded = true;
            }
          }
          h.textContent = info.c;
          hearts.appendChild(h);
        });

        ti.classList.add('is-clickable');
        ti.tabIndex = -1; // データ部のアイコンはTab移動の対象にしない(クリック/タップでは従来通り開閉可能)
        ti.setAttribute('role', 'button');
        ti.setAttribute('aria-expanded', 'false');
        if (heartModeOn) {
          hearts.classList.add('is-open');
          ti.setAttribute('aria-expanded', 'true');
        }
        const toggleHearts = () => {
          const isOpen = hearts.classList.toggle('is-open');
          ti.setAttribute('aria-expanded', String(isOpen));
          refreshHeartModeState();
        };
        ti.addEventListener('click', toggleHearts);
        ti.addEventListener('keydown', e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggleHearts();
          }
        });

        children.push(ti, hearts);
      } else {
        children.push(ti);
      }
    }
    children.push(t);

    sc.append(...children);
    w.append(sc);
    return w;
  };

  const renderBatch = () => {
    if (rendered >= filtered.length) return;
    requestAnimationFrame(() => {
      const frag = document.createDocumentFragment();
      const next = Math.min(rendered + pageSize, filtered.length);
      for (let i = rendered; i < next; i++) {
        frag.appendChild(createItemNode(filtered[i]));
      }
      $('items').appendChild(frag);
      rendered = next;
    });
  };

  new IntersectionObserver(entries => {
    entries.forEach(en => en.isIntersecting && renderBatch());
  }, { rootMargin: '300px' }).observe($('scrollSentinel'));

  // PC(マウス操作)でも、省略されているタイトルをドラッグで水平スクロールして見られるようにする
  (() => {
    let dragEl = null, startX = 0, scrollStart = 0, dragged = false;
    const DRAG_THRESHOLD = 5;

    $('items').addEventListener('mousedown', e => {
      const target = e.target.closest('.item-title');
      if (!target) return;
      dragEl = target;
      startX = e.pageX;
      scrollStart = target.scrollLeft;
      dragged = false;
    });

    window.addEventListener('mousemove', e => {
      if (!dragEl) return;
      const dx = e.pageX - startX;
      if (Math.abs(dx) > DRAG_THRESHOLD) {
        if (!dragged) dragEl.classList.add('is-dragging');
        dragged = true;
      }
      if (dragged) {
        dragEl.scrollLeft = scrollStart - dx;
        e.preventDefault();
      }
    });

    window.addEventListener('mouseup', () => {
      if (dragEl) dragEl.classList.remove('is-dragging');
      dragEl = null;
    });

    // ドラッグ操作の後にリンク遷移してしまわないよう抑制する
    $('items').addEventListener('click', e => {
      const target = e.target.closest('.item-title');
      if (target && dragged) {
        e.preventDefault();
        dragged = false;
      }
    }, true);
  })();

  const renderActiveBadges = (checked, kw) => {
    $('activeFiltersRow').textContent = '';
    const frag = document.createDocumentFragment();

    const makeBadge = (text, onClick, squareColor) => {
      const badge = document.createElement('div');
      badge.className = 'filter-badge';
      if (squareColor) {
        const sq = document.createElement('span');
        sq.className = 'badge-square';
        sq.style.backgroundColor = squareColor;
        badge.appendChild(sq);
      }
      const label = document.createElement('span');
      label.textContent = text;
      const x = document.createElement('span');
      x.className = 'badge-x';
      x.textContent = '\u00D7';
      badge.append(label, x);
      badge.onclick = onClick;
      return badge;
    };

    if (kw) {
      const badgeLabel = (setlistMode ? 'Setlist: "' : 'Keyword: "') + kw + '"';
      frag.appendChild(makeBadge(badgeLabel, () => {
        searchInput.value = '';
        updateSearchClearState();
        syncTodayModeFromSearch(); // 検索ワード削除でTODAYモードもOFFに戻す
        if (setlistMode) {
          autoUpdateContentTypeFilters();
          updateManualIndicators();
        }
        updateDisplay(true);
      }));
    }

    checked.forEach(cb => {
      const l = cb.closest('label');
      const titleSpan = l.querySelector('span[title]');
      let name;
      if (titleSpan) {
        name = titleSpan.textContent.trim() + ' ' + titleSpan.getAttribute('title');
      } else if (symbols[cb.value]) {
        name = symbols[cb.value] + ' ' + displayNameFor(cb.value);
      } else {
        name = l.querySelector('.label-text').textContent.trim() || cb.value;
      }
      const squareColor = cb.value === 'G2' ? '#f472b6' : cb.value === 'L2' ? '#facc15' : null;
      frag.appendChild(makeBadge(name, () => {
        cb.checked = false;
        if (allConts.includes(cb.value)) {
          manuallyTouchedConts.add(cb.value);
        }
        updateDisplay(true);
      }, squareColor));
    });

    $('activeFiltersRow').appendChild(frag);
  };

  const parseDateQuery = rawKw => {
    let isDateQuery = false;
    let targetMonthDay = null;
    let targetMonthDayRange = null;
    let startDate = null, endDate = null;

    const isValidMD = s => {
      if (!s || s.length !== 4) return false;
      const m = parseInt(s.slice(0, 2), 10), d = parseInt(s.slice(2, 4), 10);
      return m >= 1 && m <= 12 && d >= 1 && d <= 31;
    };

    const rangeMatch = rawKw.match(/^(\d{4,8})?-(\d{4,8})?$/);
    if (rangeMatch && (rangeMatch[1] || rangeMatch[2])) {
      isDateQuery = true;
      const p1 = rangeMatch[1], p2 = rangeMatch[2];

      const p1IsMD = !!(p1 && isValidMD(p1));
      const p2IsMD = !!(p2 && isValidMD(p2));

      if ((p1IsMD || !p1) && (p2IsMD || !p2) && (p1IsMD || p2IsMD)) {
        targetMonthDayRange = [p1IsMD ? p1 : '0101', p2IsMD ? p2 : '1231'];
      } else {
        if (p1) {
          if (p1.length === 4) startDate = p1 + '0101';
          else if (p1.length === 6) startDate = p1 + '01';
          else startDate = p1;
        }
        if (p2) {
          if (p2.length === 4) endDate = p2 + '1231';
          else if (p2.length === 6) {
            const y = parseInt(p2.slice(0, 4), 10);
            const m = parseInt(p2.slice(4, 6), 10);
            const lastDay = new Date(y, m, 0).getDate();
            endDate = p2 + String(lastDay).padStart(2, '0');
          } else endDate = p2;
        }
      }
    } else if (/^\d{4}$/.test(rawKw)) {
      const m = parseInt(rawKw.slice(0, 2), 10);
      const d = parseInt(rawKw.slice(2, 4), 10);
      const isValidMD2 = m >= 1 && m <= 12 && d >= 1 && d <= 31;

      if (isValidMD2) {
        isDateQuery = true;
        targetMonthDay = rawKw;
      } else {
        isDateQuery = true;
        startDate = rawKw + '0101';
        endDate = rawKw + '1231';
      }
    } else if (/^\d{6}$/.test(rawKw)) {
      isDateQuery = true;
      startDate = rawKw + '01';
      const y = parseInt(rawKw.slice(0, 4), 10);
      const m = parseInt(rawKw.slice(4, 6), 10);
      const lastDay = new Date(y, m, 0).getDate();
      endDate = rawKw + String(lastDay).padStart(2, '0');
    } else if (/^\d{8}$/.test(rawKw)) {
      isDateQuery = true;
      startDate = rawKw;
      endDate = rawKw;
    }

    return { isDateQuery, targetMonthDay, targetMonthDayRange, startDate, endDate };
  };

  // セトリ検索モード:setlist.jsonのsongs[].titleをkwで部分一致検索し、該当する公演のsetlistidの集合を返す
  const getMatchedSetlistIds = kw => {
    const result = new Set();
    setlistData.forEach(entry => {
      const hit = (Array.isArray(entry.songs) ? entry.songs : []).some(s => (s.title || '').toLowerCase().includes(kw));
      if (hit) result.add(entry.setlistid);
    });
    return result;
  };

  // セトリ検索モード中のアイテム判定:setlistidを持つデータのみが対象。
  // キーワード未入力時は「setlistidを持つデータすべて」、入力時は該当曲を含む公演のみに絞り込む
  const isSetlistOk = (item, kw, setlistIds) => {
    if (!item.setlistid) return false;
    if (!kw) return true;
    return setlistIds.has(item.setlistid);
  };

  // SETLISTアイコン押下時のポップアップ:setlistidに紐づくsetlist.jsonのデータを整形して表示する
  const escapeHtml = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // songsのtype値と実際の表示文言が異なるものだけここに登録する(それ以外はtype値そのものを表示する)
  const setlistTypeDisplayNames = {
    'allow': '\u64AE\u5F71\u53EF\u80FD',
    'mc': 'MC',
    'encore': '\u30A2\u30F3\u30B3\u30FC\u30EB',
    'cover': '\u30AB\u30D0\u30FC',
    'dt': '\u30C0\u30F3\u30B9\u30C8\u30E9\u30C3\u30AF',
    'medley': '\u30E1\u30C9\u30EC\u30FC'
  };
  const displayNameForSetlistType = t => setlistTypeDisplayNames[t] || t;
  // setlistidは"YYYYMMDDHHMM"(公演の開演日時)形式。データ部と同じ表示形式(年.月.日 [曜]、時:分)に分解する
  const formatSetlistDateTime = setlistid => {
    if (!/^\d{12}$/.test(setlistid || '')) return { dateStr: '', timeStr: '' };
    const y = setlistid.slice(0, 4), m = setlistid.slice(4, 6), d = setlistid.slice(6, 8);
    const hh = setlistid.slice(8, 10), mm = setlistid.slice(10, 12);
    const dateObj = new Date(parseInt(y, 10), parseInt(m, 10) - 1, parseInt(d, 10));
    const dayStr = isNaN(dateObj.getTime()) ? '' : dayNames[dateObj.getDay()];
    const dateStr = `${y}.${m}.${d}` + (dayStr ? ` [${dayStr}]` : '');
    const timeStr = `${hh}:${mm}`;
    return { dateStr, timeStr };
  };
  // type:songの曲名でsongs.jsonを完全一致検索し(前後空白・大小文字は無視)、Youtube等へのlinkを取得する
  const findSongLinkByTitle = title => {
    const norm = t => (t || '').trim().toLowerCase();
    const target = norm(title);
    if (!target) return null;
    const found = songsData.find(s => norm(s.title) === target);
    return found && found.link ? found.link : null;
  };
  const setlistModalOverlay = $('setlistModalOverlay');
  const setlistModalBody = $('setlistModalBody');
  // ポップアップ内はinnerHTMLで再生成するため、再生ボタンのクリックはイベント委譲で拾う
  setlistModalBody.addEventListener('click', e => {
    const btn = e.target.closest('.setlist-song-play-btn[data-link]');
    if (!btn) return;
    e.stopPropagation();
    openSongLink(btn.dataset.link);
  });
  const openSetlistModal = setlistid => {
    const entry = setlistData.find(e => e.setlistid === setlistid);
    if (!entry) {
      setlistModalBody.innerHTML = '<div class="setlist-modal-empty">SETLIST NOT FOUND</div>';
      setlistModalOverlay.classList.add('is-open');
      return;
    }
    try {
      const songsHtml = (Array.isArray(entry.songs) ? entry.songs : [])
        // 文字列だけの要素(""など)や、titleが空のオブジェクトは「曲ではない」として除外する
        .filter(s => s && typeof s === 'object' && String(s.title || '').trim() !== '')
        .slice()
        .sort((a, b) => (a.order || 0) - (b.order || 0))
        .map(s => {
          const isSong = !s.type || s.type === 'song';
          // song以外の行(allow等)も同じ幅の枠を確保し、曲名の開始位置がずれないようにする
          const link = isSong ? findSongLinkByTitle(s.title) : null;
          const playBtnHtml = link
            ? `<span class="setlist-song-play-btn" data-link="${escapeHtml(link)}" role="button" aria-label="Play">\u25B6</span>`
            : `<span class="setlist-song-play-btn is-hidden" aria-hidden="true">\u25B6</span>`;
          const typeBadge = s.type && s.type !== 'song' ? `<span class="setlist-song-type">${escapeHtml(displayNameForSetlistType(s.type))}</span>` : '';
          const notesHtml = s.notes ? `<span class="setlist-song-notes">${escapeHtml(s.notes)}</span>` : '';
          const titleText = s.original ? `${escapeHtml(s.title || '')}\uFF08${escapeHtml(s.original)}\uFF09` : escapeHtml(s.title || '');
          return `<li><span class="setlist-song-order">${s.order != null ? s.order : ''}</span>${playBtnHtml}<span class="setlist-song-title">${titleText}</span>${typeBadge}${notesHtml}</li>`;
        })
        .join('');
      setlistModalBody.innerHTML =
        `<div class="setlist-modal-title">${escapeHtml(entry.title || '')}</div>` +
        (() => {
          const memberList = Array.isArray(entry.member) ? entry.member : [];
          const memberCodes = memberOrder.filter(v => memberList.includes(v));
          const heartsHtml = memberCodes.map(code => {
            const info = memberInfoByCode[code];
            return info ? `<span class="setlist-heart">${info.c}</span>` : '';
          }).join('');
          if (!entry.artist && !heartsHtml) return '';
          return `<div class="setlist-modal-artist">${entry.artist ? escapeHtml(entry.artist) : ''}${heartsHtml ? `<span class="setlist-modal-hearts">${heartsHtml}</span>` : ''}</div>`;
        })() +
        (() => {
          const { dateStr, timeStr } = formatSetlistDateTime(entry.setlistid);
          if (!dateStr && !timeStr) return '';
          return `<div class="setlist-modal-datetime">${escapeHtml(dateStr)}${timeStr ? ` \u958B\u6F14 ${escapeHtml(timeStr)}` : ''}</div>`;
        })() +
        (entry.venue ? `<div class="setlist-modal-venue">${escapeHtml(entry.venue)}</div>` : '') +
        (songsHtml ? `<ul class="setlist-modal-songlist">${songsHtml}</ul>` : '<div class="setlist-modal-empty">no songs</div>');
    } catch (err) {
      // データ形状が想定外でも、ポップアップ自体は必ず開いてエラー内容が分かるようにする
      console.error('Failed to render setlist modal:', err);
      setlistModalBody.innerHTML = '<div class="setlist-modal-empty">LOAD ERROR</div>';
    }
    setlistModalOverlay.classList.add('is-open');
  };
  const closeSetlistModal = () => setlistModalOverlay.classList.remove('is-open');
  $('setlistModalCloseBtn').onclick = closeSetlistModal;
  setlistModalOverlay.onclick = e => {
    if (e.target === setlistModalOverlay) closeSetlistModal(); // オーバーレイ部分クリックで閉じる(中身のクリックでは閉じない)
  };
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && setlistModalOverlay.classList.contains('is-open')) closeSetlistModal();
  });

  // コンテンツ種類フィルターを除いた条件(年・グループ/メンバー・検索・TODAY・セトリ検索)だけでアイテムがマッチするか判定
  // セトリ検索モード中は、メンバーフィルターの判定元をlogs.json側のgroups/relationsではなく、
  // そのデータのsetlistidに紐づくsetlist.json側のmemberに切り替える
  const getFilterGroupsForItem = item => {
    if (setlistMode && item.setlistid) {
      const entry = setlistData.find(e => e.setlistid === item.setlistid);
      return (entry && Array.isArray(entry.member)) ? entry.member : [];
    }
    return [...(item.groups || []), ...(item.relations || [])];
  };
  const matchesOtherFilters = (item, ctx) => {
    const { cYears, sGroups, mGroups, kw, dq, setlistIds } = ctx;
    const yr = item.date ? item.date.slice(0, 4) : '';
    const itemGroupsAndRelations = getFilterGroupsForItem(item);
    const itemGroups = itemGroupsAndRelations; // STF除外判定もセトリ検索モード中は同じ配列(member)を参照する

    const yOk = cYears.length === 0 || cYears.includes(yr);

    const itemHasMeta = m => {
      if (itemGroupsAndRelations.includes(m)) return true; // groupsまたはrelationsに"G2"等のメタ表記そのものがある場合
      const mValues = cats.find(c => c.meta === m)?.values || [];
      return itemGroupsAndRelations.some(g => mValues.includes(g)); // 個別メンバーコードからメタ所属を推測
    };
    // 複数選択時はAND条件(それぞれについてgroupsまたはrelationsに該当すること)
    const memberOk = sGroups.length === 0 ? true : sGroups.every(g => itemGroupsAndRelations.includes(g));
    const metaOk = mGroups.length === 0 ? true : mGroups.every(itemHasMeta);
    // メンバーフィルターのみ選択時(グループフィルター未選択)は、groupsにSTFがある項目を除外する
    const stfExcluded = sGroups.length > 0 && mGroups.length === 0 && itemGroups.includes('STF');
    const gOk = memberOk && metaOk && !stfExcluded;

    let dateOk = true;
    let textOk = true;
    let setlistOk = true;
    if (setlistMode) {
      // セトリ検索モード中は、通常の日付検索・テキスト検索の代わりにsetlistidベースの判定を行う
      setlistOk = isSetlistOk(item, kw, setlistIds);
    } else {
      if (dq.isDateQuery) {
        const itemDateNum = item.date || '';
        let matchesDate = true;
        if (dq.targetMonthDay) {
          const itemMD = itemDateNum.slice(4, 8);
          matchesDate = itemMD === dq.targetMonthDay;
        } else if (dq.targetMonthDayRange) {
          const itemMD = itemDateNum.slice(4, 8);
          const [fromMD, toMD] = dq.targetMonthDayRange;
          matchesDate = fromMD <= toMD
            ? (itemMD >= fromMD && itemMD <= toMD)
            : (itemMD >= fromMD || itemMD <= toMD);
        } else {
          if (dq.startDate && itemDateNum < dq.startDate) matchesDate = false;
          if (dq.endDate && itemDateNum > dq.endDate) matchesDate = false;
        }
        const tagsMatch = !!(item.tags && item.tags.some(t => t.toLowerCase().includes(kw)));
        dateOk = matchesDate || tagsMatch;
      }

      if (kw && !dq.isDateQuery) {
        const searchText = (item.title + ' ' + (item.display_pc || '') + ' ' + (item.display_sm || '') + ' ' + item.date + ' ' + item.contents + ' ' + (item.tags ? item.tags.join(' ') : '')).toLowerCase();
        const tokens = kw.split(/\s+/).filter(Boolean);
        textOk = tokens.every(tok => {
          if (tok.length > 1 && tok.startsWith('-')) return !searchText.includes(tok.slice(1));
          return searchText.includes(tok);
        });
      }
    }

    const todayOk = isTodayDateOk(item, cYears);

    return yOk && gOk && dateOk && textOk && setlistOk && todayOk;
  };

  // TODAY/←/→ボタン、またはセトリ検索モードでの検索条件変化があった時のみ、コンテンツ種類ボタンを自動on/offする。
  // それ以外(通常検索・年・グループ・メンバーの変更)では、コンテンツ種類ボタンの自動on/offは一切行わない。
  //
  // ・TODAYまたはセトリ検索モードをONにした時、および関連する条件(←/→、検索ワード等)が変化した時:
  //     手動on/offされているものはそのまま保護し、それ以外は現在の絞り込み(今日基準・セトリ検索結果含む)に
  //     該当する/しないに応じて自動on/offする。
  // ・TODAY・セトリ検索モードの両方がOFFの時:
  //     残りのフィルタでの再判定はせず、手動on/offされているもの以外は無条件で全てOFFにする。
  const manuallyTouchedConts = new Set(); // ユーザーが手動でON/OFFしたコンテンツ種類の値(右上ランプの色分け・保護判定用)

  const autoUpdateContentTypeFilters = () => {
    const contentCheckboxes = Array.from(checkboxes).filter(cb => allConts.includes(cb.value));

    if (!todayMode && !setlistMode) {
      // TODAY・セトリ検索モードともにOFF:残りのフィルタでの再判定はせず、手動on/off以外は無条件でOFFにする
      contentCheckboxes.forEach(cb => {
        if (manuallyTouchedConts.has(cb.value)) return;
        cb.checked = false;
      });
      return;
    }

    const checked = Array.from(checkboxes).filter(cb => cb.checked);
    const cVals = new Set(checked.map(cb => cb.value));
    const cYears = checked.filter(cb => /^\d{4}$/.test(cb.value)).map(cb => cb.value);
    const sGroups = allGroupVals.filter(v => cVals.has(v));
    const mGroups = cats.map(c => c.meta).filter(m => cVals.has(m));
    const rawKw = searchInput.value.trim();
    const kw = rawKw.toLowerCase();
    const dq = setlistMode ? null : parseDateQuery(rawKw);
    const setlistIds = setlistMode && kw ? getMatchedSetlistIds(kw) : null;
    const ctx = { cYears, sGroups, mGroups, kw, dq, setlistIds };

    const matched = new Set();
    expandTodayBirthdayItems(logs, cYears).forEach(item => {
      if (matchesOtherFilters(item, ctx)) matched.add(normalizeContType(item.contents || ''));
    });

    contentCheckboxes.forEach(cb => {
      // 手動ONのものだけ保護する(手動OFFでも、該当するデータがあれば自動ONに戻す)
      const isProtected = manuallyTouchedConts.has(cb.value) && cb.checked;
      if (isProtected) return;

      const shouldBeOn = cb.value === 'ETC'
        ? Array.from(matched).some(c => !primaryConts.includes(c))
        : matched.has(cb.value);
      cb.checked = shouldBeOn;
      manuallyTouchedConts.delete(cb.value);
    });
  };

  const updateDisplay = (syncHash = true) => {

    const checked = Array.from(checkboxes).filter(cb => cb.checked);
    const cVals = new Set(checked.map(cb => cb.value));
    const cYears = checked.filter(cb => /^\d{4}$/.test(cb.value)).map(cb => cb.value);
    const cConts = checked.filter(cb => allConts.includes(cb.value)).map(cb => cb.value);
    const sGroups = allGroupVals.filter(v => cVals.has(v));
    const mGroups = cats.map(c => c.meta).filter(m => cVals.has(m));
    const rawKw = searchInput.value.trim();
    const kw = rawKw.toLowerCase();

    // 日付・年・月日クエリのパース処理(セトリ検索モード中はkwを曲名検索に使うため不要)
    const { isDateQuery, targetMonthDay, targetMonthDayRange, startDate, endDate } = setlistMode
      ? { isDateQuery: false, targetMonthDay: null, targetMonthDayRange: null, startDate: null, endDate: null }
      : parseDateQuery(rawKw);
    // セトリ検索モード中、キーワードがあればsetlist.jsonから該当するsetlistidを検索しておく
    const setlistIds = setlistMode && kw ? getMatchedSetlistIds(kw) : null;

    filtered = expandTodayBirthdayItems(logs, cYears).filter(item => {
      const yr = item.date ? item.date.slice(0, 4) : '';
      const itemGroupsAndRelations = getFilterGroupsForItem(item);
      const itemGroups = itemGroupsAndRelations; // STF除外判定もセトリ検索モード中は同じ配列(member)を参照する
      const ic = normalizeContType(item.contents || '');
      
      const yOk = cYears.length === 0 || cYears.includes(yr);
      
      const itemHasMeta = m => {
        if (itemGroupsAndRelations.includes(m)) return true;
        const mValues = cats.find(c => c.meta === m)?.values || [];
        return itemGroupsAndRelations.some(g => mValues.includes(g));
      };
      // 複数選択時はAND条件(それぞれについてgroupsまたはrelationsに該当すること)
      const memberOk = sGroups.length === 0 ? true : sGroups.every(g => itemGroupsAndRelations.includes(g));
      const metaOk = mGroups.length === 0 ? true : mGroups.every(itemHasMeta);
      // メンバーフィルターのみ選択時(グループフィルター未選択)は、groupsにSTFがある項目を除外する
      const stfExcluded = sGroups.length > 0 && mGroups.length === 0 && itemGroups.includes('STF');
      const gOk = memberOk && metaOk && !stfExcluded;

      const cOk = cConts.length === 0 || (cConts.includes('ETC') && !primaryConts.includes(ic)) || cConts.includes(ic);
      
      let dateOk = true;
      let textOk = true;
      let setlistOk = true;

      if (setlistMode) {
        // セトリ検索モード:通常の日付検索・テキスト検索の代わりにsetlistidベースで判定する
        setlistOk = isSetlistOk(item, kw, setlistIds);
      } else {
        if (isDateQuery) {
          const itemDateNum = item.date || '';
          let matchesDate = true;
          if (targetMonthDay) {
            const itemMD = itemDateNum.slice(4, 8);
            matchesDate = itemMD === targetMonthDay;
          } else if (targetMonthDayRange) {
            const itemMD = itemDateNum.slice(4, 8);
            const [fromMD, toMD] = targetMonthDayRange;
            matchesDate = fromMD <= toMD
              ? (itemMD >= fromMD && itemMD <= toMD)
              : (itemMD >= fromMD || itemMD <= toMD); // 年をまたぐ範囲(例:1201-0131)にも対応
          } else {
            if (startDate && itemDateNum < startDate) matchesDate = false;
            if (endDate && itemDateNum > endDate) matchesDate = false;
          }
          // 日付検索を優先しつつ、tagsに一致するものがあればそちらも結果に含める
          const tagsMatch = !!(item.tags && item.tags.some(t => t.toLowerCase().includes(kw)));
          dateOk = matchesDate || tagsMatch;
        }

        if (kw && !isDateQuery) {
          const searchText = (item.title + ' ' + (item.display_pc || '') + ' ' + (item.display_sm || '') + ' ' + item.date + ' ' + item.contents + ' ' + (item.tags ? item.tags.join(' ') : '')).toLowerCase();
          const tokens = kw.split(/\s+/).filter(Boolean);
          textOk = tokens.every(tok => {
            if (tok.length > 1 && tok.startsWith('-')) {
              return !searchText.includes(tok.slice(1));
            }
            return searchText.includes(tok);
          });
        }
      }
      
      const todayOk = isTodayDateOk(item, cYears);

      return yOk && gOk && cOk && dateOk && textOk && setlistOk && todayOk;
    });

    filtered.sort((a, b) => {
      const ka = sortKeyFor(a), kb = sortKeyFor(b);
      if (ka !== kb) return desc ? kb.localeCompare(ka) : ka.localeCompare(kb);
      // 日付+時刻が同一の場合のタイブレーク:
      // 1) グループ(G2とL2両方 > G2 > L2 > STF > それ以外)
      const ga = groupSortRank(a), gb = groupSortRank(b);
      if (ga !== gb) return ga - gb;
      // 2) メンバー(フィルターボタンの並び順)
      const ma = memberSortRank(a), mb = memberSortRank(b);
      if (ma !== mb) return ma - mb;
      // 3) コンテンツフィルターボタンの並び順
      return contentSortRank(a) - contentSortRank(b);
    });

    $('items').classList.add('is-animating');
    clearTimeout(renderTimer);
    renderTimer = setTimeout(() => {
      $('items').textContent = '';
      rendered = 0;
      defaultText = 'RESULTS > ' + filtered.length;
      $('resultCount').textContent = defaultText;
      renderActiveBadges(checked, kw);
      updateAllBadges();
      updateManualIndicators();

      const isZero = filtered.length === 0;
      $('noResult').style.display = isZero ? 'block' : 'none';
      $('sortBtn').style.display = isZero ? 'none' : 'block';
      $('inlineClearBtn').style.display = (checked.length > 0 || kw || todayMode || setlistMode) ? 'inline-block' : 'none';
      
      if (!isZero) renderBatch();
      $('items').classList.remove('is-animating');
    }, 120);

    if (syncHash) {
      updating = true;
      const active = checked.map(cb => cb.value);
      if (active.length > 0 || kw) window.location.hash = active.join(',');
      else history.replaceState(null, null, window.location.pathname + window.location.search);
      // hashchange(restoreFromHash)は非同期に発火するため、同期的にfalseへ戻すと
      // ガード(if (updating) return;)が効かず、自前のhash更新でrestoreFromHashが
      // 誤って再実行されてしまう(自動ON分までmanuallyTouchedContsに登録され、
      // 以後の自動OFFが効かなくなる原因になっていた)。
      // hashchangeが発火し終えたあとのタイミングまでresetを遅延させる。
      setTimeout(() => { updating = false; }, 0);
    }
  };

  const previewCountFor = (val, isChecked) => {
    const checked = Array.from(checkboxes).filter(c => c.checked);
    const cVals = new Set(checked.map(c => c.value));
    let cY = checked.filter(c => /^\d{4}$/.test(c.value)).map(c => c.value);
    let sG = allGroupVals.filter(v => cVals.has(v));
    let mG = cats.map(c => c.meta).filter(m => cVals.has(m));
    let cC = checked.filter(c => allConts.includes(c.value)).map(c => c.value);
    const rawKw = searchInput.value.trim();
    const kw = rawKw.toLowerCase();
    const { isDateQuery, targetMonthDay, targetMonthDayRange, startDate, endDate } = setlistMode
      ? { isDateQuery: false, targetMonthDay: null, targetMonthDayRange: null, startDate: null, endDate: null }
      : parseDateQuery(rawKw);
    const setlistIds = setlistMode && kw ? getMatchedSetlistIds(kw) : null;

    if (isChecked) {
      if (/^\d{4}$/.test(val)) cY = cY.filter(y => y !== val);
      if (allGroupVals.includes(val)) sG = sG.filter(g => g !== val);
      if (cats.some(c => c.meta === val)) mG = mG.filter(m => m !== val);
      if (allConts.includes(val)) cC = cC.filter(c => c !== val);
    } else {
      if (/^\d{4}$/.test(val) && !cY.includes(val)) cY.push(val);
      if (allGroupVals.includes(val) && !sG.includes(val)) sG.push(val);
      if (cats.some(c => c.meta === val) && !mG.includes(val)) mG.push(val);
      if (allConts.includes(val) && !cC.includes(val)) cC.push(val);
    }

    return expandTodayBirthdayItems(logs, cY).filter(item => {
      const yr = item.date ? item.date.slice(0, 4) : '';
      const itemGroupsAndRelations = getFilterGroupsForItem(item);
      const itemGroups = itemGroupsAndRelations; // STF除外判定もセトリ検索モード中は同じ配列(member)を参照する
      const ic = normalizeContType(item.contents || '');

      const itemHasMeta = m => {
        if (itemGroupsAndRelations.includes(m)) return true;
        const mValues = cats.find(c => c.meta === m)?.values || [];
        return itemGroupsAndRelations.some(g => mValues.includes(g));
      };
      // 複数選択時はAND条件(それぞれについてgroupsまたはrelationsに該当すること)
      const memberOk = sG.length === 0 ? true : sG.every(g => itemGroupsAndRelations.includes(g));
      const metaOk = mG.length === 0 ? true : mG.every(itemHasMeta);
      // メンバーフィルターのみ選択時(グループフィルター未選択)は、groupsにSTFがある項目を除外する
      const stfExcluded = sG.length > 0 && mG.length === 0 && itemGroups.includes('STF');
      const gOk = memberOk && metaOk && !stfExcluded;

      let dateOk = true;
      let kwOk = true;
      let setlistOk = true;

      if (setlistMode) {
        setlistOk = isSetlistOk(item, kw, setlistIds);
      } else {
        if (isDateQuery) {
          const itemDateNum = item.date || '';
          let matchesDate = true;
          if (targetMonthDay) {
            const itemMD = itemDateNum.slice(4, 8);
            matchesDate = itemMD === targetMonthDay;
          } else if (targetMonthDayRange) {
            const itemMD = itemDateNum.slice(4, 8);
            const [fromMD, toMD] = targetMonthDayRange;
            matchesDate = fromMD <= toMD
              ? (itemMD >= fromMD && itemMD <= toMD)
              : (itemMD >= fromMD || itemMD <= toMD);
          } else {
            if (startDate && itemDateNum < startDate) matchesDate = false;
            if (endDate && itemDateNum > endDate) matchesDate = false;
          }
          const tagsMatch = !!(item.tags && item.tags.some(t => t.toLowerCase().includes(kw)));
          dateOk = matchesDate || tagsMatch;
        }

        if (kw && !isDateQuery) {
          const searchText = (item.title + ' ' + (item.display_pc || '') + ' ' + (item.display_sm || '') + ' ' + item.date + ' ' + item.contents + ' ' + (item.tags ? item.tags.join(' ') : '')).toLowerCase();
          const tokens = kw.split(/\s+/).filter(Boolean);
          kwOk = tokens.every(tok =>
            tok.length > 1 && tok.startsWith('-') ? !searchText.includes(tok.slice(1)) : searchText.includes(tok)
          );
        }
      }

      const todayOk = isTodayDateOk(item, cY);
      const yOk = cY.length === 0 || cY.includes(yr);

      return yOk &&
             gOk &&
             (cC.length === 0 || (cC.includes('ETC') && !primaryConts.includes(ic)) || cC.includes(ic)) &&
             dateOk && kwOk && setlistOk && todayOk;
    }).length;
  };

  // BADGEモード:各フィルターボタンに、現在の他条件と連動した件数を常時表示する
  let badgeMode = false;
  const CAP = 9999;
  const updateAllBadges = () => {
    labels.forEach(l => {
      const badge = l.querySelector('.count-badge');
      if (!badge) return;
      const cb = l.querySelector('input');
      if (!badgeMode || !cb || cb.checked) {
        // 選択中のボタンは「外した場合の件数」になり分かりにくいためバッジを表示しない
        badge.style.display = 'none';
        return;
      }
      const cnt = previewCountFor(cb.value, cb.checked);
      badge.textContent = cnt > CAP ? String(CAP) : String(cnt);
      badge.style.display = 'flex';
    });
  };

  // 右上のランプの色を切り替える:コンテンツ種類はmanuallyTouchedContsに含まれていれば手動操作済み、
  // 年/グループ/メンバーは自動on/offの仕組みが無いため、チェック済みであれば常に手動ONとして扱う
  const updateManualIndicators = () => {
    labels.forEach(l => {
      const cb = l.querySelector('input');
      if (!cb) return;
      const isManual = allConts.includes(cb.value) ? manuallyTouchedConts.has(cb.value) : cb.checked;
      l.classList.toggle('is-manual-on', isManual);
    });
  };

  $('badgeToggleBtn').onclick = () => {
    badgeMode = !badgeMode;
    $('badgeToggleBtn').classList.toggle('is-active', badgeMode);
    updateAllBadges();
      updateManualIndicators();
  };

  // ICONボタン:コンテンツ種類フィルターの表示をテキストのみ⇔アイコンのみで切り替える。次回訪問時も記憶する
  const ICON_MODE_KEY = 'gl_log_icon_mode';
  let iconMode = lsGet(ICON_MODE_KEY) === 'true';

  // ICONモード時のみ、コンテンツ種類ボタンにツールチップ(名前)を表示する
  const updateContentTooltips = () => {
    document.querySelectorAll('#otherChecks label[data-tooltip-name]').forEach(l => {
      if (iconMode) l.title = l.dataset.tooltipName;
      else l.removeAttribute('title');
    });
  };

  document.body.classList.toggle('icon-only-mode', iconMode);
  $('iconToggleBtn').classList.toggle('is-active', iconMode);
  updateContentTooltips();
  $('iconToggleBtn').onclick = () => {
    iconMode = !iconMode;
    document.body.classList.toggle('icon-only-mode', iconMode);
    $('iconToggleBtn').classList.toggle('is-active', iconMode);
    lsSet(ICON_MODE_KEY, iconMode);
    updateContentTooltips();
    updateDisplay(false);
  };

  // ♪ボタン:検索窓の下にある楽曲紹介バー(PLAYボタン+タイトル/アーティスト)の表示/非表示を切り替える。
  // 次回訪問時も状態を記憶する。表示/非表示はCSSのmax-height/opacityで滑らかにアニメーションする

  // 📍ボタン(MAPモード):ONの間、データ部の日付/時刻表示の右にmap属性へのリンクアイコンを表示する。
  // 次回訪問時も状態を記憶する
  const MAP_MODE_KEY = 'gl_log_map_mode';
  let mapMode = lsGet(MAP_MODE_KEY) === 'true';
  $('mapToggleBtn').classList.toggle('is-active', mapMode);
  $('mapToggleBtn').onclick = () => {
    mapMode = !mapMode;
    $('mapToggleBtn').classList.toggle('is-active', mapMode);
    lsSet(MAP_MODE_KEY, mapMode);
    updateDisplay(false);
  };
  const SONG_MODE_KEY = 'gl_log_song_mode';
  let songMode = lsGet(SONG_MODE_KEY) === 'true';
  $('songToggleBtn').classList.toggle('is-active', songMode);
  $('songBar').classList.toggle('is-open', songMode);
  $('songToggleBtn').onclick = () => {
    songMode = !songMode;
    $('songToggleBtn').classList.toggle('is-active', songMode);
    $('songBar').classList.toggle('is-open', songMode);
    lsSet(SONG_MODE_KEY, songMode);
    if (songMode) updateSongTickerScroll(); // 表示直後に幅が確定するよう再計測する
  };

  // 💞ボタン:現在表示中の全行のハートを一括で展開/縮小する(押した時点の集約状態を反転させる)
  $('heartToggleBtn').onclick = () => {
    const nextOpen = !heartModeOn;
    $('items').querySelectorAll('.team-hearts').forEach(hearts => {
      hearts.classList.toggle('is-open', nextOpen);
      const icon = hearts.previousElementSibling;
      if (icon && icon.classList.contains('team-icon')) icon.setAttribute('aria-expanded', String(nextOpen));
    });
    heartModeOn = nextOpen;
    $('heartToggleBtn').classList.toggle('is-active', heartModeOn);
  };

  // 年/月/日/曜/時分:項目左端の日付表示を個別にon/offするボタン。状態はlocalStorageに保存し次回も復元する
  const datePartButtons = {
    year: $('showYearBtn'),
    month: $('showMonthBtn'),
    day: $('showDayBtn'),
    weekday: $('showWeekdayBtn'),
    time: $('showTimeBtn')
  };
  Object.keys(datePartButtons).forEach(key => {
    datePartButtons[key].classList.toggle('is-active', dateParts[key]);
    datePartButtons[key].onclick = () => {
      dateParts[key] = !dateParts[key];
      datePartButtons[key].classList.toggle('is-active', dateParts[key]);
      lsSet(DATE_PARTS_KEY, JSON.stringify(dateParts));
      updateDisplay(false);
    };
  });

  // TODAYモード:システム日付(端末のローカル日付)を基準に、todayOffset日ずらしたデータのみに絞り込む
  let todayMode = false;
  let todayOffset = 0; // 0=当日, 負=前日方向, 正=翌日方向
  let preTodaySort = null; // TODAYをONにする直前のソート状態(descの値)を退避
  let searchDateTodayActive = false; // 検索窓への日付入力によってTODAYモードがONにされている状態かどうか
  const getTargetDateStr = offsetDays => {
    const d = new Date();
    d.setDate(d.getDate() + offsetDays);
    // item.dateと直接比較するため、ドット無しの8桁(YYYYMMDD)形式で返す
    return String(d.getFullYear()) + String(d.getMonth() + 1).padStart(2, '0') + String(d.getDate()).padStart(2, '0');
  };
  const getTargetMonthDayStr = offsetDays => {
    const d = new Date();
    d.setDate(d.getDate() + offsetDays);
    return String(d.getMonth() + 1).padStart(2, '0') + String(d.getDate()).padStart(2, '0');
  };

  // 検索窓の文字列が「年月日8桁(例:20260907)」として完全な実在日付になっているかを判定する。
  // 該当すればその日付のDateオブジェクトを、そうでなければnullを返す
  const getExactSearchDate = rawKw => {
    if (!/^\d{8}$/.test(rawKw)) return null;
    const y = parseInt(rawKw.slice(0, 4), 10);
    const m = parseInt(rawKw.slice(4, 6), 10);
    const d = parseInt(rawKw.slice(6, 8), 10);
    if (m < 1 || m > 12 || d < 1 || d > 31) return null;
    const dt = new Date(y, m - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== m - 1 || dt.getDate() !== d) return null; // 2/31等の実在しない日付を弾く
    return dt;
  };

  // 検索窓に実在する年月日8桁が入力された時、その日付を基準にTODAYモードをONにする
  // (todayOffsetを「今日からその日付までの日数差」に設定し、ボタン色を該当日にあった状態にする)
  const enableTodayFromSearchDate = dt => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    dt.setHours(0, 0, 0, 0);
    const diffDays = Math.round((dt - today) / 86400000);
    if (!todayMode) {
      todayMode = true;
      preTodaySort = desc;
      // TODAYをONにした時だけソートを自動的に昇順にする(手動でTODAYをONにした時と同じ挙動)
      if (desc) {
        desc = false;
        $('sortBtn').textContent = '\u2191';
      }
    }
    todayOffset = diffDays;
    searchDateTodayActive = true;
    updateTodayButtonStyle();
    autoUpdateContentTypeFilters();
    updateManualIndicators();
  };

  // 検索窓の日付入力によってONにされていたTODAYモードをOFFに戻す
  const disableTodayFromSearchDate = () => {
    if (!searchDateTodayActive) return;
    searchDateTodayActive = false;
    todayMode = false;
    todayOffset = 0;
    if (preTodaySort !== null) {
      desc = preTodaySort;
      $('sortBtn').textContent = desc ? '\u2193' : '\u2191';
      preTodaySort = null;
    }
    updateTodayButtonStyle();
    autoUpdateContentTypeFilters();
    updateManualIndicators();
  };

  // 検索窓の現在の内容を見て、日付ならTODAYモードをON、日付でなくなった(変更・削除された)ならOFFにする
  const syncTodayModeFromSearch = () => {
    const rawKw = searchInput.value.trim();
    const exactDate = getExactSearchDate(rawKw);
    if (exactDate) {
      enableTodayFromSearchDate(exactDate);
    } else {
      disableTodayFromSearchDate();
    }
  };
  // BIRTHDAY/ANNIVERSARYかどうか(この2種類はTODAYモード時、登録年を問わず「同じ月日」であれば
  // 表示対象にする特別扱いをする)
  const isBirthdayAnniversary = item => item.contents === 'BIRTHDAY' || item.contents === 'ANNIVERSARY';

  // TODAYモード時の日付一致判定。年フィルターがONの場合は「その年の該当月日」で一致させる(年の絞り込み自体はyOk側で行う)
  const isTodayDateOk = (item, cYears) => {
    if (!todayMode) return true;
    if (cYears && cYears.length > 0) {
      const itemDateNum = item.date || '';
      return itemDateNum.slice(4, 8) === getTargetMonthDayStr(todayOffset);
    }
    return item.date === getTargetDateStr(todayOffset);
  };

  // TODAYモード中、BIRTHDAY/ANNIVERSARYを「表示すべき年」ごとに複製したアイテムへ展開する。
  // - 年フィルターが選択されている場合:選択されている年のうち、登録年以降かつ月日が一致するものを
  //   すべて複製して返す(例:19770317登録で、今日が0317、年フィルターに2027と2025が選択済みなら
  //   20270317と20250317の2件を生成する)
  // - 年フィルターが未選択の場合:登録日以降であれば「今日(offset適用後)」の年月日で1件だけ生成する
  // BIRTHDAY/ANNIVERSARY以外、およびTODAYモードOFF時は元のアイテムをそのまま返す
  const expandTodayBirthdayItems = (items, cYears) => {
    if (!todayMode) return items;
    const targetMonthDay = getTargetMonthDayStr(todayOffset);
    const targetDateNum = getTargetDateStr(todayOffset);
    const result = [];
    items.forEach(item => {
      if (!isBirthdayAnniversary(item)) { result.push(item); return; }
      const itemDateNum = item.date || '';
      if (!itemDateNum || itemDateNum.slice(4, 8) !== targetMonthDay) return; // 月日不一致は対象外
      const registeredYear = itemDateNum.slice(0, 4);
      const monthDay = itemDateNum.slice(4, 8); // "MMDD"
      if (cYears && cYears.length > 0) {
        cYears.forEach(y => {
          if (y < registeredYear) return; // 登録年より前の年フィルターは対象外
          result.push(Object.assign({}, item, { date: `${y}${monthDay}` }));
        });
      } else if (itemDateNum <= targetDateNum) {
        result.push(Object.assign({}, item, { date: getTargetDateStr(todayOffset) }));
      }
    });
    return result;
  };

  const updateTodayButtonStyle = () => {
    const btn = $('todayToggleBtn');
    btn.classList.toggle('is-active', todayMode && todayOffset === 0);
    btn.classList.toggle('is-offset-prev', todayMode && todayOffset < 0);
    btn.classList.toggle('is-offset-next', todayMode && todayOffset > 0);
    // 年フィルターが選択されている間は、前後日移動(offset)の色より黄色を優先する。年フィルターが外れたら通常の色に戻る
    btn.classList.toggle('is-year-filtered', todayMode && !!$('yearChecks').querySelector('input:checked'));
    $('prevDayBtn').classList.toggle('is-visible', todayMode);
    $('nextDayBtn').classList.toggle('is-visible', todayMode);
    if (todayOffset === 0) {
      $('prevDayBtn').classList.remove('is-pressed');
      $('nextDayBtn').classList.remove('is-pressed');
    }
  };

  $('todayToggleBtn').onclick = () => {
    // セトリ検索モード中にTODAYボタンが押されたら、セトリ検索モードはOFFにする(逆方向は現状維持)
    if (setlistMode) {
      setlistMode = false;
      $('setlistToggleBtn').classList.remove('is-active');
      updateSearchPlaceholder();
    }
    if (!todayMode) {
      // OFF -> ON(当日)。ON にする直前のソート状態を覚えておく
      todayMode = true;
      todayOffset = 0;
      preTodaySort = desc;
      // TODAYをONにした時だけソートを自動的に昇順にする
      if (desc) {
        desc = false;
        $('sortBtn').textContent = '\u2191';
      }
    } else {
      // ON(当日 or 前後日)状態からの押下は、常にOFFにする
      todayMode = false;
      todayOffset = 0;
      searchDateTodayActive = false; // 手動でOFFにした場合は検索窓連動フラグもリセットする
      if (preTodaySort !== null) {
        desc = preTodaySort;
        $('sortBtn').textContent = desc ? '\u2193' : '\u2191';
        preTodaySort = null;
      }
    }
    updateTodayButtonStyle();
    autoUpdateContentTypeFilters();
    updateManualIndicators();
    updateDisplay(true);
  };

  $('prevDayBtn').onclick = () => {
    if (!todayMode) return;
    todayOffset -= 1;
    $('prevDayBtn').classList.add('is-pressed');
    $('nextDayBtn').classList.remove('is-pressed');
    updateTodayButtonStyle();
    autoUpdateContentTypeFilters();
    updateManualIndicators();
    updateDisplay(true);
  };

  $('nextDayBtn').onclick = () => {
    if (!todayMode) return;
    todayOffset += 1;
    $('nextDayBtn').classList.add('is-pressed');
    $('prevDayBtn').classList.remove('is-pressed');
    updateTodayButtonStyle();
    autoUpdateContentTypeFilters();
    updateManualIndicators();
    updateDisplay(true);
  };

  // SETLISTボタン:セトリ検索モードのON/OFF。検索窓の文字列はモード切替時もクリアしない
  $('setlistToggleBtn').onclick = () => {
    setlistMode = !setlistMode;
    $('setlistToggleBtn').classList.toggle('is-active', setlistMode);
    searchSuggestions.classList.remove('is-open'); // モード切替時は検索候補ポップアップを一旦閉じる
    updateSearchPlaceholder();
    autoUpdateContentTypeFilters();
    updateManualIndicators();
    updateDisplay(true);
  };

  const bindCheckboxAndLabelEvents = () => {
    if (!isTouch) {
      labels.forEach(l => {
        const cb = l.querySelector('input');
        if (!cb) return;
        const val = cb.value;

        l.onmouseenter = () => {
          const cnt = previewCountFor(val, cb.checked);
          const name = l.querySelector('span[title]')?.getAttribute('title') || l.querySelector('.label-text').textContent.trim();
          $('resultCount').textContent = '[ ' + name + ' ] PREVIEW > ' + cnt;
        };

        l.onmouseleave = () => $('resultCount').textContent = defaultText;
      });
    }

    labels.forEach(l => l.onkeydown = e => {
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        const cb = l.querySelector('input');
        if (cb) {
          cb.checked = !cb.checked;
          if (allConts.includes(cb.value)) manuallyTouchedConts.add(cb.value);
          updateManualIndicators();
          updateTodayButtonStyle(); // 年フィルターの選択状態が変わるのでTODAYボタンの色を再評価
          updateDisplay(true);
          window.scrollTo({ top: 0, behavior: 'instant' });
        }
      }
    });

    checkboxes.forEach(cb => cb.onchange = () => {
      if (allConts.includes(cb.value)) {
        manuallyTouchedConts.add(cb.value);
      }
      updateManualIndicators();
      updateTodayButtonStyle(); // 年フィルターの選択状態が変わるのでTODAYボタンの色を再評価
      updateDisplay(true);
      window.scrollTo({ top: 0, behavior: 'instant' });
    });

    updateAllBadges();
      updateManualIndicators();
  };
  bindCheckboxAndLabelEvents();

  // データロード後、実データに含まれる年(4桁)をすべて年フィルターとして動的に生成する(上限なし)
  const refreshYearChecks = () => {
    const yearsSet = new Set();
    logs.forEach(item => {
      const y = item.date ? String(item.date).slice(0, 4) : '';
      if (/^\d{4}$/.test(y)) yearsSet.add(y);
    });
    const years = Array.from(yearsSet).sort((a, b) => b.localeCompare(a));

    $('yearChecks').innerHTML = '';
    years.forEach(y => $('yearChecks').appendChild(createLabel(y)));

    // 年チェックボックスを再生成したので、checkboxes/labelsを再取得してイベントも再登録する
    checkboxes = document.querySelectorAll('.checks input[type="checkbox"]');
    labels = document.querySelectorAll('.checks label:has(input)');
    bindCheckboxAndLabelEvents();
  };

  const restoreFromHash = () => {
    if (updating) return;
    const active = window.location.hash.replace('#', '').split(',').filter(Boolean);
    checkboxes.forEach(cb => cb.checked = active.includes(cb.value));
    // URLで明示的にONになっているコンテンツ種類は手動操作扱いにして保護する。OFFのものは自動on/offの対象に戻す
    manuallyTouchedConts.clear();
    checkboxes.forEach(cb => {
      if (allConts.includes(cb.value) && cb.checked) manuallyTouchedConts.add(cb.value);
    });
    updateSearchClearState();
    updateDisplay(false);
  };

  window.onhashchange = restoreFromHash;

  const resetAll = e => {
    if (e) e.preventDefault();
    checkboxes.forEach(cb => cb.checked = false);
    manuallyTouchedConts.clear();
    searchInput.value = '';
    updateSearchClearState();
    document.querySelectorAll('.checks-row-years, .checks-row-other').forEach(con => con.scrollLeft = 0);
    if (todayMode) {
      todayMode = false;
      todayOffset = 0;
      searchDateTodayActive = false; // CLEARで検索窓も空になるため連動フラグもリセットする
      if (preTodaySort !== null) {
        desc = preTodaySort;
        $('sortBtn').textContent = desc ? '\u2193' : '\u2191';
        preTodaySort = null;
      }
      updateTodayButtonStyle();
    }
    // CLEARでハートモードもOFFにする(再描画される行が展開済みの状態で作られないようにする)
    heartModeOn = false;
    $('heartToggleBtn').classList.remove('is-active');
    // CLEARでセトリ検索モードもOFFに戻す
    if (setlistMode) {
      setlistMode = false;
      $('setlistToggleBtn').classList.remove('is-active');
      updateSearchPlaceholder();
    }
    window.scrollTo({ top: 0, behavior: 'instant' });
    updateDisplay(true);
  };

  $('resetLink').onclick = e => {
    resetAll(e);
    forceReloadLogs(); // タイトルクリック時は直近チェック時刻やSHA比較を無視し、常に最新のlogs.jsonを取得し直す
    forceReloadSongs(); // songs.json(♪の楽曲データ)も同様に強制的に取得し直す
    forceReloadSetlist(); // setlist.json(セトリ検索用データ)も同様に強制的に取得し直す
  };
  $('quickResetBtn').onclick = resetAll;
  $('inlineClearBtn').onclick = resetAll;

  fetch('/feeds/posts/default?alt=json&max-results=1')
    .then(res => res.json())
    .then(data => {
      const entry = data.feed.entry;
      if (entry && entry.length > 0) {
        const updatedStr = entry[0].updated.$t;
        const dateObj = new Date(updatedStr);
        const y = dateObj.getFullYear();
        const m = String(dateObj.getMonth() + 1).padStart(2, '0');
        const d = String(dateObj.getDate()).padStart(2, '0');
        $('updateTime').textContent = `updated > ${y}.${m}.${d}`;
      }
    })
    .catch(err => {
      console.error('Failed to load blogger feed:', err);
    });

  // logs.json取得:GitHub上の最新コミットSHAを確認し、変更があった場合のみ
  // コミット固定のjsDelivr URL(長期キャッシュ可能)から取得しなおす。
  // 変更がなければlocalStorageのキャッシュをそのまま使い、通信を省略する。
  const REPO = 'piscenake52/gllogs';
  const BRANCH = 'main';
  const FILE = 'logs.json';
  const VERSION_KEY = 'gl_log_sha';
  const DATA_KEY = 'gl_log_data';
  const CHECK_TIME_KEY = 'gl_log_checked_at';
  const CHECK_COOLDOWN_MS = 1 * 60 * 1000; // 5分以内の再チェックはスキップ(同一端末でのAPI消費を抑制)

  const applyLogs = data => {
    // 日付、時刻、コンテンツ種類、タイトル、URLがすべて一致する重複データを排除
    const seen = new Set();
    logs = data.filter(item => {
      const identifier = `${item.date || ''}_${item.time || ''}_${item.contents || ''}_${item.title || ''}_${item.url || ''}`;
      if (seen.has(identifier)) return false;
      seen.add(identifier);
      return true;
    });

    refreshYearChecks();
    window.location.hash ? restoreFromHash() : updateDisplay(true);
  };

  const loadFromCacheIfAny = () => {
    const cached = lsGet(DATA_KEY);
    if (!cached) return false;
    try {
      applyLogs(JSON.parse(cached));
      return true;
    } catch (e) {
      // 壊れたキャッシュは無視して素通り(新規取得に進む)
      return false;
    }
  };

  const fetchFreshData = sha => {
    const url = sha
      ? `https://cdn.jsdelivr.net/gh/${REPO}@${sha}/${FILE}`
      // SHA取得に失敗した場合の保険:キャッシュバスト付きでrawから直接取得
      : `https://raw.githubusercontent.com/${REPO}/${BRANCH}/${FILE}?v=${Date.now()}`;

    return fetch(url)
      .then(res => {
        if (!res.ok) throw new Error('Network response was not ok');
        return res.json();
      })
      .then(data => {
        applyLogs(data);
        lsSet(DATA_KEY, JSON.stringify(data));
        if (sha) lsSet(VERSION_KEY, sha);
      });
  };

  // まずキャッシュがあれば即表示(体感速度アップ)
  const hadCache = loadFromCacheIfAny();

  const showLoadError = () => {
    $('resultCount').textContent = '';
    $('sortBtn').style.display = 'none';
    $('inlineClearBtn').style.display = 'none';
    $('noResult').style.display = 'none';
    $('loadError').style.display = 'block';
  };

  $('retryBtn').onclick = () => {
    $('loadError').style.display = 'none';
    $('resultCount').textContent = 'LOADING...';
    checkForUpdates();
  };

  // 最新コミットSHAを確認し、更新があれば取り直す(初回読み込み・再試行ボタンの両方から呼ばれる)
  const checkForUpdates = () => {
    fetch(`https://api.github.com/repos/${REPO}/commits?path=${FILE}&sha=${BRANCH}&page=1&per_page=1`, { cache: 'no-store' })
      .then(res => {
        if (!res.ok) throw new Error('GitHub API error');
        return res.json();
      })
      .then(commits => {
        lsSet(CHECK_TIME_KEY, String(Date.now()));
        const latestSha = commits[0]?.sha;
        const cachedSha = lsGet(VERSION_KEY);
        if (latestSha && latestSha !== cachedSha) {
          return fetchFreshData(latestSha);
        }
        // 変更なし:キャッシュを表示済みでなければ念のため取得
        if (!logs.length) return fetchFreshData(latestSha);
      })
      .catch(error => {
        console.error('Failed to check logs.json version:', error);
        // API失敗時のフォールバック:キャッシュがなければ直接取得を試みる
        if (!logs.length) {
          fetchFreshData(null).catch(err2 => {
            console.error('Failed to load logs.json:', err2);
            showLoadError();
          });
        }
      });
  };

  // 直近チェックから一定時間以内なら、GitHub APIへの問い合わせ自体をスキップする
  const lastCheckedAt = parseInt(lsGet(CHECK_TIME_KEY) || '0', 10);
  const withinCooldown = hadCache && (Date.now() - lastCheckedAt < CHECK_COOLDOWN_MS);

  // トップのタイトルリンク(GL log)クリック時に呼ばれる:直近チェック時刻のクールダウンや
  // SHA比較によるスキップを行わず、常に最新コミットのlogs.jsonを取得し直す
  const forceReloadLogs = () => {
    fetch(`https://api.github.com/repos/${REPO}/commits?path=${FILE}&sha=${BRANCH}&page=1&per_page=1`, { cache: 'no-store' })
      .then(res => {
        if (!res.ok) throw new Error('GitHub API error');
        return res.json();
      })
      .then(commits => {
        lsSet(CHECK_TIME_KEY, String(Date.now()));
        return fetchFreshData(commits[0]?.sha);
      })
      .catch(error => {
        console.error('Failed to force-reload logs.json:', error);
        fetchFreshData(null).catch(err2 => {
          console.error('Failed to load logs.json:', err2);
          showLoadError();
        });
      });
  };

  // 特定の配信元からのアクセス時は、直近チェック時刻やSHA比較によるスキップを行わず常に最新のlogs.jsonを取得し直す
  // (対象URLは難読化のためソースに直接書かず、head内のスクリプトと同じハッシュ比較で判定する)
  if (isForcedFreshSource()) {
    forceReloadLogs();
  } else if (!withinCooldown) {
    checkForUpdates();
  }

  // ================= 楽曲紹介バー(♪) =================
  // songs.json(artist/title/link)取得:logs.jsonと同じ方式(GitHub上の最新コミットSHAを確認し、
  // 変更があった場合のみコミット固定のjsDelivr URLから取得しなおす。変更がなければキャッシュを使う)。
  // 画面が表示される(=データ取得が走る)たびに、その中から1曲をランダムに抽出して表示する。
  const SONG_FILE = 'songs.json';
  const SONG_VERSION_KEY = 'gl_song_sha';
  const SONG_DATA_KEY = 'gl_song_data';
  const SONG_CHECK_TIME_KEY = 'gl_song_checked_at';

  let currentSong = null;

  // テロップ:表示エリアに収まりきらない場合のみ、テキストを複製してループスクロールさせる
  const updateSongTickerScroll = () => {
    const viewport = $('songTickerViewport');
    const textEl = $('songTickerText');
    if (!viewport || !textEl) return;
    const label = textEl.dataset.label || '';
    viewport.classList.remove('is-scrolling');
    textEl.style.animationDuration = '';
    textEl.textContent = label;
    if (!label) return;
    // 表示中(is-open)でなければ幅が0のため正しく測れない。表示中のみ判定する
    if (!$('songBar').classList.contains('is-open')) return;
    requestAnimationFrame(() => {
      if (textEl.scrollWidth <= viewport.clientWidth) return; // 収まっていればスクロール不要
      textEl.textContent = '';
      const first = document.createElement('span');
      first.textContent = label;
      const gap = document.createElement('span');
      gap.textContent = '\u3000\u3000\u3000';
      const second = document.createElement('span');
      second.textContent = label;
      textEl.append(first, gap, second);
      const singleWidth = first.getBoundingClientRect().width + gap.getBoundingClientRect().width;
      const duration = Math.max(6, singleWidth / 40); // 速度:約40px/秒、最短6秒
      textEl.style.animationDuration = duration + 's';
      viewport.classList.add('is-scrolling');
    });
  };

  // PC/モバイル問わず、PLAYボタンはリンク先を新しいタブで開くだけ(元のタブへのフォーカス復帰は行わない)
  const openSongLink = link => {
    if (!link) return;
    window.open(link, '_blank');
  };

  $('songPlayBtn').onclick = () => {
    if (!currentSong || !currentSong.link) return;
    openSongLink(currentSong.link);
  };

  const applySong = song => {
    currentSong = song || null;
    const textEl = $('songTickerText');
    textEl.dataset.label = currentSong ? `${currentSong.title || ''} / ${currentSong.artist || ''}` : '';
    updateSongTickerScroll();
  };

  const applySongs = data => {
    if (!Array.isArray(data)) return;
    songsData = data; // SETLISTポップアップの曲名照合用に全件保持しておく
    if (data.length === 0) return;
    applySong(data[Math.floor(Math.random() * data.length)]);
  };

  const loadSongsFromCacheIfAny = () => {
    const cached = lsGet(SONG_DATA_KEY);
    if (!cached) return false;
    try {
      applySongs(JSON.parse(cached));
      return true;
    } catch (e) {
      return false; // 壊れたキャッシュは無視して素通り(新規取得に進む)
    }
  };

  const fetchFreshSongs = sha => {
    const url = sha
      ? `https://cdn.jsdelivr.net/gh/${REPO}@${sha}/${SONG_FILE}`
      : `https://raw.githubusercontent.com/${REPO}/${BRANCH}/${SONG_FILE}?v=${Date.now()}`;
    return fetch(url)
      .then(res => {
        if (!res.ok) throw new Error('Network response was not ok');
        return res.json();
      })
      .then(data => {
        applySongs(data);
        lsSet(SONG_DATA_KEY, JSON.stringify(data));
        if (sha) lsSet(SONG_VERSION_KEY, sha);
      });
  };

  const hadSongCache = loadSongsFromCacheIfAny();

  const checkForSongUpdates = () => {
    fetch(`https://api.github.com/repos/${REPO}/commits?path=${SONG_FILE}&sha=${BRANCH}&page=1&per_page=1`, { cache: 'no-store' })
      .then(res => {
        if (!res.ok) throw new Error('GitHub API error');
        return res.json();
      })
      .then(commits => {
        lsSet(SONG_CHECK_TIME_KEY, String(Date.now()));
        const latestSha = commits[0]?.sha;
        const cachedSha = lsGet(SONG_VERSION_KEY);
        if (latestSha && latestSha !== cachedSha) {
          return fetchFreshSongs(latestSha);
        }
        if (!currentSong) return fetchFreshSongs(latestSha);
      })
      .catch(error => {
        console.error('Failed to check songs.json version:', error);
        if (!currentSong) {
          fetchFreshSongs(null).catch(err2 => {
            console.error('Failed to load songs.json:', err2);
          });
        }
      });
  };

  const lastSongCheckedAt = parseInt(lsGet(SONG_CHECK_TIME_KEY) || '0', 10);
  const withinSongCooldown = hadSongCache && (Date.now() - lastSongCheckedAt < CHECK_COOLDOWN_MS);

  // トップのタイトルリンク(GL log)クリック時に呼ばれる:直近チェック時刻のクールダウンやSHA比較による
  // スキップを行わず、常に最新コミットのsongs.jsonを取得し直す(logs側のforceReloadLogsと同じ考え方)
  const forceReloadSongs = () => {
    fetch(`https://api.github.com/repos/${REPO}/commits?path=${SONG_FILE}&sha=${BRANCH}&page=1&per_page=1`, { cache: 'no-store' })
      .then(res => {
        if (!res.ok) throw new Error('GitHub API error');
        return res.json();
      })
      .then(commits => {
        lsSet(SONG_CHECK_TIME_KEY, String(Date.now()));
        return fetchFreshSongs(commits[0]?.sha);
      })
      .catch(error => {
        console.error('Failed to force-reload songs.json:', error);
        fetchFreshSongs(null).catch(err2 => {
          console.error('Failed to load songs.json:', err2);
        });
      });
  };

  // 特定の配信元からのアクセス時は、logs.json同様にsongs.jsonも常に取得し直す
  if (isForcedFreshSource()) {
    forceReloadSongs();
  } else if (!withinSongCooldown) {
    checkForSongUpdates();
  }

  // ================= セトリ検索モード(SETLIST) =================
  // setlist.json(公演ごとのセットリスト)取得:logs.json/songs.jsonと同じ方式
  const SETLIST_FILE = 'setlist.json';
  const SETLIST_VERSION_KEY = 'gl_setlist_sha';
  const SETLIST_DATA_KEY = 'gl_setlist_data';
  const SETLIST_CHECK_TIME_KEY = 'gl_setlist_checked_at';

  const applySetlistData = data => {
    setlistData = Array.isArray(data) ? data : [];
    // 既にセトリ検索モード中に読み込みが完了した場合は、結果を反映するため再描画する
    if (setlistMode) {
      autoUpdateContentTypeFilters();
      updateManualIndicators();
      updateDisplay(true);
    }
  };

  const loadSetlistFromCacheIfAny = () => {
    const cached = lsGet(SETLIST_DATA_KEY);
    if (!cached) return false;
    try {
      applySetlistData(JSON.parse(cached));
      return true;
    } catch (e) {
      return false; // 壊れたキャッシュは無視して素通り(新規取得に進む)
    }
  };

  const fetchFreshSetlist = sha => {
    const url = sha
      ? `https://cdn.jsdelivr.net/gh/${REPO}@${sha}/${SETLIST_FILE}`
      : `https://raw.githubusercontent.com/${REPO}/${BRANCH}/${SETLIST_FILE}?v=${Date.now()}`;
    return fetch(url)
      .then(res => {
        if (!res.ok) throw new Error('Network response was not ok');
        return res.json();
      })
      .then(data => {
        applySetlistData(data);
        lsSet(SETLIST_DATA_KEY, JSON.stringify(data));
        if (sha) lsSet(SETLIST_VERSION_KEY, sha);
      });
  };

  const hadSetlistCache = loadSetlistFromCacheIfAny();

  const checkForSetlistUpdates = () => {
    fetch(`https://api.github.com/repos/${REPO}/commits?path=${SETLIST_FILE}&sha=${BRANCH}&page=1&per_page=1`, { cache: 'no-store' })
      .then(res => {
        if (!res.ok) throw new Error('GitHub API error');
        return res.json();
      })
      .then(commits => {
        lsSet(SETLIST_CHECK_TIME_KEY, String(Date.now()));
        const latestSha = commits[0]?.sha;
        const cachedSha = lsGet(SETLIST_VERSION_KEY);
        if (latestSha && latestSha !== cachedSha) {
          return fetchFreshSetlist(latestSha);
        }
        if (!setlistData.length) return fetchFreshSetlist(latestSha);
      })
      .catch(error => {
        console.error('Failed to check setlist.json version:', error);
        if (!setlistData.length) {
          fetchFreshSetlist(null).catch(err2 => {
            console.error('Failed to load setlist.json:', err2);
          });
        }
      });
  };

  const lastSetlistCheckedAt = parseInt(lsGet(SETLIST_CHECK_TIME_KEY) || '0', 10);
  const withinSetlistCooldown = hadSetlistCache && (Date.now() - lastSetlistCheckedAt < CHECK_COOLDOWN_MS);

  // トップのタイトルリンク(GL log)クリック時に呼ばれる:logs.json/songs.json同様にsetlist.jsonも常に取得し直す
  const forceReloadSetlist = () => {
    fetch(`https://api.github.com/repos/${REPO}/commits?path=${SETLIST_FILE}&sha=${BRANCH}&page=1&per_page=1`, { cache: 'no-store' })
      .then(res => {
        if (!res.ok) throw new Error('GitHub API error');
        return res.json();
      })
      .then(commits => {
        lsSet(SETLIST_CHECK_TIME_KEY, String(Date.now()));
        return fetchFreshSetlist(commits[0]?.sha);
      })
      .catch(error => {
        console.error('Failed to force-reload setlist.json:', error);
        fetchFreshSetlist(null).catch(err2 => {
          console.error('Failed to load setlist.json:', err2);
        });
      });
  };

  // 特定の配信元からのアクセス時は、logs.json/songs.json同様にsetlist.jsonも常に取得し直す
  if (isForcedFreshSource()) {
    forceReloadSetlist();
  } else if (!withinSetlistCooldown) {
    checkForSetlistUpdates();
  }
})();
