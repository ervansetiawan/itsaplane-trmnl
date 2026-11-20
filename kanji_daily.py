"""Daily Kanji & Japanese Typography Poster generator."""

from datetime import date, timedelta

KANJI_BANK = [
    ("空", "Sky / Empty", "クウ (kuu)", "そら (sora)", 8, "穴 (cave)", "N4", "星空 (hoshizora) — Starry sky"),
    ("海", "Ocean / Sea", "カイ (kai)", "うみ (umi)", 9, "氵 (water)", "N4", "海岸 (kaigan) — Seashore"),
    ("星", "Star / Planet", "セイ (sei)", "ほし (hoshi)", 9, "日 (sun)", "N4", "流星 (ryūsei) — Shooting star"),
    ("風", "Wind / Style", "フウ (fū)", "かぜ (kaze)", 9, "風 (wind)", "N4", "風鈴 (fūrin) — Wind chime"),
    ("光", "Light / Ray", "コウ (kō)", "ひかり (hikari)", 6, "儿 (legs)", "N4", "日光 (nikkō) — Sunlight"),
    ("森", "Forest", "シン (shin)", "もり (mori)", 12, "木 (tree)", "N4", "森林 (shinrin) — Deep woods"),
    ("火", "Fire / Flame", "カ (ka)", "ひ (hi)", 4, "火 (fire)", "N5", "花火 (hanabi) — Fireworks"),
    ("水", "Water", "スイ (sui)", "みず (mizu)", 4, "水 (water)", "N5", "水平線 (suiheisen) — Horizon"),
    ("山", "Mountain", "サン (san)", "やま (yama)", 3, "山 (mountain)", "N5", "火山 (kazan) — Volcano"),
    ("月", "Moon / Month", "ゲツ (getsu)", "つき (tsuki)", 4, "月 (moon)", "N5", "満月 (mangetsu) — Full moon"),
    ("日", "Sun / Day", "ニチ (nichi)", "ひ (hi)", 4, "日 (sun)", "N5", "朝日 (asahi) — Morning sun"),
    ("花", "Flower / Blossom", "カ (ka)", "はな (hana)", 7, "艹 (grass)", "N5", "桜花 (ōka) — Cherry blossom"),
    ("雪", "Snow", "セツ (setsu)", "ゆき (yuki)", 11, "雨 (rain)", "N4", "新雪 (shinsetsu) — Fresh snow"),
    ("雨", "Rain", "ウ (u)", "あめ (ame)", 8, "雨 (rain)", "N5", "五月雨 (samidare) — Early summer rain"),
    ("夢", "Dream / Vision", "ム (mu)", "ゆめ (yume)", 13, "夕 (evening)", "N3", "夢中 (muchū) — Absorbed in"),
    ("心", "Heart / Mind", "シン (shin)", "こころ (kokoro)", 4, "心 (heart)", "N4", "安心 (anshin) — Peace of mind"),
    ("道", "Path / Way", "ドウ (dō)", "みち (michi)", 12, "辶 (walk)", "N4", "茶道 (sadō) — Tea ceremony"),
    ("時", "Time / Hour", "ジ (ji)", "とき (toki)", 10, "日 (sun)", "N5", "時計 (tokei) — Clock / Watch"),
    ("音", "Sound / Tone", "オン (on)", "おと (oto)", 9, "音 (sound)", "N4", "音楽 (ongaku) — Music"),
    ("影", "Shadow / Silhouette", "エイ (ei)", "かげ (kage)", 15, "彡 (rays)", "N2", "面影 (omokage) — Vestige"),
    ("雲", "Cloud", "ウン (un)", "くも (kumo)", 12, "雨 (rain)", "N3", "雲海 (unkai) — Sea of clouds"),
    ("波", "Wave / Ripple", "ハ (ha)", "なみ (nami)", 8, "氵 (water)", "N3", "電波 (denpa) — Radio wave"),
    ("雷", "Thunder / Lightning", "ライ (rai)", "かみなり (kaminari)", 13, "雨 (rain)", "N2", "落雷 (rakurai) — Lightning strike"),
    ("龍", "Dragon", "リュウ (ryū)", "たつ (tatsu)", 16, "龍 (dragon)", "N1", "恐竜 (kyōryū) — Dinosaur"),
    ("鳥", "Bird", "チョウ (chō)", "とり (tori)", 11, "鳥 (bird)", "N4", "白鳥 (hakuchō) — Swan"),
    ("魚", "Fish", "ギョ (gyo)", "さかな (sakana)", 11, "魚 (fish)", "N5", "金魚 (kingyo) — Goldfish"),
    ("桜", "Cherry Blossom", "オウ (ō)", "さくら (sakura)", 10, "木 (tree)", "N2", "夜桜 (yozakura) — Night sakura"),
    ("竹", "Bamboo", "チク (chiku)", "たけ (take)", 6, "竹 (bamboo)", "N2", "竹林 (chikurin) — Bamboo grove"),
    ("石", "Stone / Rock", "セキ (seki)", "いし (ishi)", 5, "石 (stone)", "N4", "宝石 (hōseki) — Gemstone"),
    ("鉄", "Iron / Steel", "テツ (tetsu)", "くろがね (kurogane)", 13, "金 (metal)", "N3", "鉄道 (tetsudō) — Railway"),
    ("金", "Gold / Metal", "キン (kin)", "かね (kane)", 8, "金 (metal)", "N5", "黄金 (ōgon) — Pure gold"),
    ("銀", "Silver", "ギン (gin)", "しろがね (shirogane)", 14, "金 (metal)", "N4", "銀河 (ginga) — Milky Way"),
    ("剣", "Sword / Blade", "ケン (ken)", "つるぎ (tsurugi)", 10, "刂 (knife)", "N1", "剣道 (kendō) — Kendo"),
    ("城", "Castle / Fortress", "ジョウ (jō)", "しろ (shiro)", 9, "土 (earth)", "N3", "城下町 (jōkamachi) — Castle town"),
    ("橋", "Bridge", "キョウ (kyō)", "はし (hashi)", 16, "木 (tree)", "N3", "鉄橋 (tekkyō) — Iron bridge"),
    ("船", "Ship / Boat", "セン (sen)", "ふね (fune)", 11, "舟 (boat)", "N3", "宇宙船 (uchūsen) — Spaceship"),
    ("旅", "Journey / Travel", "リョ (ryo)", "たび (tabi)", 10, "方 (direction)", "N4", "旅人 (tabibito) — Traveler"),
    ("夜", "Night / Evening", "ヤ (ya)", "よる (yoru)", 8, "夕 (evening)", "N4", "夜空 (yozora) — Night sky"),
    ("朝", "Morning", "チョウ (chō)", "あさ (asa)", 12, "月 (moon)", "N4", "今朝 (kesa) — This morning"),
    ("春", "Spring", "シュン (shun)", "はる (haru)", 9, "日 (sun)", "N4", "春風 (harukaze) — Spring breeze"),
    ("夏", "Summer", "カ (ka)", "なつ (natsu)", 10, "夂 (go)", "N4", "真夏 (manatsu) — Midsummer"),
    ("秋", "Autumn / Fall", "シュウ (shū)", "あき (aki)", 9, "禾 (grain)", "N4", "秋空 (akizora) — Autumn sky"),
    ("冬", "Winter", "トウ (tō)", "ふゆ (fuyu)", 5, "冫 (ice)", "N4", "冬眠 (tōmin) — Hibernation"),
    ("東", "East", "トウ (tō)", "ひがし (higashi)", 8, "木 (tree)", "N5", "東京 (Tōkyō) — Tokyo"),
    ("西", "West", "セイ (sei)", "にし (nishi)", 6, "襾 (cover)", "N5", "関西 (Kansai) — Kansai region"),
    ("南", "South", "ナン (nan)", "みなみ (minami)", 9, "十 (ten)", "N5", "南極 (nankyoku) — South Pole"),
    ("北", "North", "ホク (hoku)", "きた (kita)", 5, "匕 (spoon)", "N5", "北極 (hokkyoku) — North Pole"),
    ("天", "Heaven / Sky", "テン (ten)", "あま (ama)", 4, "大 (big)", "N5", "天気 (tenki) — Weather"),
    ("地", "Earth / Ground", "チ (chi)", "じ (ji)", 6, "土 (earth)", "N4", "地球 (chikyū) — Planet Earth"),
    ("人", "Person / Human", "ジン (jin)", "ひと (hito)", 2, "人 (person)", "N5", "職人 (shokunin) — Artisan"),
    ("友", "Friend", "ユウ (yū)", "とも (tomo)", 4, "又 (right hand)", "N5", "友情 (yūjō) — Friendship"),
    ("愛", "Love / Affection", "アイ (ai)", "いと (ito)", 13, "心 (heart)", "N3", "愛読書 (aidokusho) — Favorite book"),
    ("希", "Hope / Rare", "キ (ki)", "まれ (mare)", 7, "巾 (cloth)", "N3", "希望 (kibō) — Hope"),
    ("力", "Power / Strength", "リョク (ryoku)", "ちから (chikara)", 2, "力 (power)", "N4", "重力 (jūryoku) — Gravity"),
    ("知", "Knowledge / Wisdom", "チ (chi)", "しる (shiru)", 8, "矢 (arrow)", "N4", "知識 (chishiki) — Knowledge"),
    ("書", "Write / Book", "ショ (sho)", "かく (kaku)", 10, "曰 (say)", "N5", "書道 (shodō) — Calligraphy"),
    ("画", "Picture / Stroke", "ガ (ga)", "えがく (egaku)", 8, "田 (field)", "N4", "映画 (eiga) — Cinema"),
    ("詩", "Poem / Verse", "シ (shi)", "うた (uta)", 13, "言 (word)", "N3", "詩人 (shijin) — Poet"),
    ("舞", "Dance / Flutter", "ブ (bu)", "まう (mau)", 15, "舛 (oppose)", "N2", "舞台 (butai) — Stage"),
    ("静", "Quiet / Still", "セイ (sei)", "しずか (shizuka)", 14, "青 (blue)", "N3", "静寂 (seijaku) — Silence"),
]


def _entry(idx: int) -> dict:
    ch, meaning, onyomi, kunyomi, strokes, radical, jlpt, example = KANJI_BANK[idx % len(KANJI_BANK)]
    return {
        "kanji": ch,
        "meaning": meaning,
        "onyomi": onyomi,
        "kunyomi": kunyomi,
        "strokes": strokes,
        "radical": radical,
        "jlpt": jlpt,
        "example": example,
        "number": (idx % len(KANJI_BANK)) + 1,
    }


def generate_daily_kanji(target_date: date | None = None) -> dict:
    d = target_date or date.today()
    idx = d.toordinal() % len(KANJI_BANK)
    y_idx = (d - timedelta(days=1)).toordinal() % len(KANJI_BANK)

    today_k = _entry(idx)
    yest_k = _entry(y_idx)

    return {
        "title": "Kanji of the Day",
        "date": d.strftime("%b %d, %Y").upper(),
        **today_k,
        "yesterday_kanji": yest_k["kanji"],
        "yesterday_meaning": yest_k["meaning"],
    }
