# Design produktu — návrhový systém v3 „Papír a výkres“

Závazné pro stavitele i recenzenta. Tenhle soubor a `web/styl.css`,
`web/simtegen.js` a písma ve `web/pismo/` jsou **infrastruktura šablony**:
stavitel je při každé stavbě přepíše aktuální verzí, v produktu se
neupravují. Produkt mění jen `web/produkt.css` (svou barvu) a vlastní
obrazovky.

Proč v3: v2 nesla firemní podpis všemi vrstvami naráz — tečková mřížka,
ořezové značky, mono štítky velkými písmeny, číslované sekce, obří číslo
na každé obrazovce. Zákazníci appky četli jako nepřehledné. v3 nechává
podpis tam, kde ho člověk pozná (logo, úvodní obrazovka, papír, černá
akce, barva produktu), a všechno ostatní ztišuje. A přidává druhý typ
obrazovky — **nástroj** — protože u produktu, kde zákazník něco skládá,
je hodnota ve výkresu, ne v čísle.

**Pravidlo jednoduchosti:** když váháš, jestli prvek přidat, nepřidávej ho.
Každá obrazovka má jednu věc, kvůli které existuje — ta je největší a
první; všechno ostatní ustoupí.

## Podpis firmy (co má každá appka)

- **Úvodní obrazovka s logem SimteGen** při každém startu — dělá ji
  `web/simtegen.js`, stránka ho jen načte (viz Kostra). Logo „Díl“ se při
  prvním otevření poskládá animací; kulatý díl v něm má barvu produktu.
  Značku jinde v appce dává jen třída `.znacka-ctverec` — nikdy ji nekresli
  vlastním obrázkem.
- **Papír a inkoust.** Teplý papír (bez teček — ty patří jen úvodní
  obrazovce a grafice v obchodě), černý inkoust, vlasové linky místo
  stínů, ostré rohy.
- **Písmo.** Schibsted Grotesk na všechno včetně štítků a nadpisů sekcí —
  normální věty, malá písmena. **Plex Mono jen na to, co se měří nebo
  kóduje:** `205/55 R16`, `A-12`, `600 × 720`, čas v deníku. Nikdy na věty,
  nikdy velkými písmeny.
- **Černá hlavní akce** (`.tlacitko`) — jedna na obrazovku.
- **Barva produktu jen jako ukazatel**: čtvereček u názvu, aktivní položka
  menu, plnění stupnice, „Dnes“, vybraný díl a kóty na výkresu. Nikdy
  jako plocha pod textem, nikdy na hlavním tlačítku — to je vždy černé.

## Téma produktu (co má každá appka jiné)

- Barva v `web/produkt.css` podle tématu (pneuservis rumělka, truhlář
  jedle …), kontrast na papíře ≥ 4.5:1 — CI to spočítá.
- Slovník a jednotky oboru (rozměry, kódy míst, čísla zakázek),
  piktogram tématu v ikoně aplikace.
- Detail, který **nese informaci**: výkres s kótami, stupnice s čísly,
  rozpad podle druhu, týdenní pás, deník posledních pohybů. Ne ozdoby,
  ne vymyšlené statistiky.

## Dva typy obrazovek

Ve specifikaci má každá obrazovka svůj typ. Většina produktů má oba:
přehled zakázek a nástroj, ve kterém se zakázka skládá.

### Přehled (seznam, stav, číslo)

- Nahoře nadpis obrazovky; když je na ní číslo, na kterém opravdu záleží
  (počet dnešních zakázek, částka k úhradě), smí být velké
  (`.cislo-obri`). Není-li takové číslo, obrazovka žádné nemá — číslo
  pro ozdobu je chyba.
- Obsah v **1–3 sekcích** s nadpisem (`.sekce-titulek`, obyčejná slova,
  bez čísel „01 —“).
- Seznam ukazuje 3–5 nejbližších položek a odkaz „Vše →“, ne všechno.

### Nástroj (výkres přes celou plochu)

Pro obrazovku, kde zákazník něco skládá nebo upravuje a výsledek je
vidět: stěna kuchyně ze skříněk, rozložení regálů, plán místnosti.
Konkurence tohle umí a zákazník to od nástroje čeká — „naskládat to
rychle a ukázat zákazníkovi jinak než na papíře“.

```html
<section class="obrazovka nastroj" id="stena">
  <div class="nastroj-lista">
    <a class="zpet" href="#zakazka">Zakázka</a>
    <h2>Novákovi · stěna A</h2>
    <span class="rozmer">300 cm</span>
    <button type="button" class="nahlasit-chybu jen-telefon" aria-label="Nahlásit chybu"><svg …/></button>
  </div>
  <div class="platno">
    <svg viewBox="0 0 340 260" role="img" aria-label="Pohled na stěnu A">
      <rect class="stena" …/>
      <g class="dil vybrany" data-id="…"><rect …/></g>      <!-- skříňka -->
      <path class="detail" …/>                               <!-- úchytky, dvířka -->
      <rect class="otvor" …/>                                <!-- okno, dveře -->
      <g class="kota"><line …/><text …>60</text></g>        <!-- rozměr -->
    </svg>
  </div>
  <div class="nastroje" role="toolbar" aria-label="Nástroje">
    <button type="button" class="nastroj-tlacitko" aria-pressed="true"><svg …/>Skříňka</button>
    … 3–5 nástrojů …
  </div>
  <aside class="vlastnosti" aria-label="Vybraná skříňka"> pole, .barvy </aside>
  <div class="lista-dole"><button class="tlacitko">Ukázat zákazníkovi</button></div>
</section>
```

- **Výkres je obsah obrazovky.** Žádné karty, sekce ani čísla kolem něj.
- **Jednotky výkresu:** 1 = 1 cm, výkres široký 300–400 jednotek (delší
  sestavu rozděl po stěnách) — pak je text kót (`.kota text`, 13) na
  telefonu čitelný. Čáry drží tloušťku při každém zvětšení samy.
- **Kóty v barvě produktu** u každého dílu a celkový rozměr stěny.
- **Barva materiálu**, kterou zákazník vybírá, jsou data: JS ji nastaví
  na dílu jako proměnnou (`el.style.setProperty("--barva-dilu", hodnota)`),
  vzorník je `.barvy` s tlačítkem na barvu a `aria-label` s jejím názvem.
  Barvy zapsané v HTML CI odmítne.
- **Nástroje** (`.nastroje`): 3–5, ikona a slovo, aktivní má
  `aria-pressed="true"`. Klepnutí na díl ho vybere (`.vybrany`) a ukáže
  `.vlastnosti` (rozměry, barva, smazat); bez výběru jsou `hidden`.
- **Předpřipravené díly:** přidání dílu nabízí hotové typy oboru
  (spodní skříňka 60, horní 60, vysoká …), ne prázdný obdélník.
- **Hlavní akce** dotahuje práci k zákazníkovi: „Ukázat zákazníkovi“
  (náhled přes celou obrazovku bez nástrojů), „Uložit“.
- Na telefonu se menu i hlavička schovají (výkres potřebuje výšku), proto
  `.nastroj-lista` nese cestu zpět (`.zpet`) i `.nahlasit-chybu`. Na
  tabletu a notebooku je výkres vlevo a vlastnosti s hlavní akcí vpravo.

## Přehlednost

- **Jedna hlavní akce na obrazovku** (černé tlačítko se šipkou,
  `.tlacitko`). Další akce jsou vedlejší (`.tlacitko.vedlejsi`) nebo
  odkazy — nejvýš dvě vedlejší vedle hlavní. Víc akcí = rozdělit
  obrazovku nebo schovat do „Více“. CI počítá černá tlačítka na celé
  obrazovce, ne jen na tom, co je vidět.
- Text nejméně 13 px (třídy systému to drží samy; vlastní menší písmo
  CI odmítne).
- Nadpis obrazovky, pak obsah — žádný štítek nad nadpisem, žádná
  ozdobná linka navíc.

## Kostra (každá stránka aplikace)

```html
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="application-name" content="Název produktu">
  <meta name="simtegen-verze" content="1.0">
  <link rel="stylesheet" href="styl.css">
  <link rel="stylesheet" href="produkt.css">
</head>
<body>
  <script src="simtegen.js"></script>
  <div class="appka">
    <nav class="navigace" aria-label="Hlavní menu">
      <a class="znacka" href="/"><span class="znacka-ctverec"></span><span class="znacka-slovo">simtegen</span></a>
      <a href="#prehled" aria-current="page"><svg …/>Přehled</a>
      … nejvýš 4 položky …
      <span class="mezera"></span>
      <button class="nahlasit-chybu"><svg …/>Nahlásit chybu</button>
      <span class="verze">V 1.0</span>
    </nav>
    <header class="hlavicka"><h1>Název produktu</h1> <button class="nahlasit-chybu jen-telefon" aria-label="Nahlásit chybu">…</button></header>
    <main class="obsah"> … obrazovky … </main>
  </div>
</body>
```

`styl.css` z toho sám udělá tři rozvržení:

| Šířka | Navigace | Obsah |
|---|---|---|
| telefon < 768 px | pás dole s textem (na nástroji schovaný) | jeden sloupec, `.lista-dole` drží hlavní akci v dosahu palce |
| tablet 768–1199 px | levý pruh s ikonami, dole Nahlásit chybu a verze | `.mrizka` o 12 sloupcích, třídy `.s4`–`.s8`; nástroj od 1000 px: výkres vlevo, vlastnosti vpravo |
| notebook ≥ 1200 px | boční menu s textem a značkou | totéž, obsah do 1200 px; `.dva-sloupce` se skládá samo |

Na žádné šířce nic nepřetéká vodorovně; tabulky jsou v `.tabulka-obal`.

## Komponenty (`web/styl.css`)

| Třída | K čemu |
|---|---|
| `.sekce-titulek` | nadpis sekce obyčejnými slovy s odkazem vpravo („Vše →“) |
| `.stitek` | krátký popisek nad hodnotou („Přihlášeni jako“) |
| `.karta`, `.karta.vykres` | plocha; `.vykres` ji orámuje inkoustem — jen ta nejdůležitější |
| `.cislo-obri`, `.cislo-radek` | velké číslo a popis vedle něj — jen když číslo nese informaci |
| `.nastroj`, `.nastroj-lista`, `.zpet` | obrazovka typu nástroj a její horní lišta |
| `.platno` + `<svg>` s `.stena`, `.dil`(`.vybrany`), `.detail`, `.otvor`, `.kota`, `.popis-dilu` | výkres přes celou plochu |
| `.nastroje` / `.nastroj-tlacitko` | lišta nástrojů pod výkresem |
| `.vlastnosti`, `.barvy` | vlastnosti vybraného dílu, vzorník barev (`--barva-dilu`) |
| `.stupnice` + `style="--hodnota: 80%"` | rysky, plnění v barvě produktu, `.stupnice-popisky` s čísly |
| `.segmenty` + `.legenda` | rozpad celku do 3 dílů ve stupních šedi s popisky |
| `.tyden` (`.dnes`, `.volno`, `.nula`) | 7 dní s počtem |
| `.seznam` / `.radek` (`.hlavni`, `.vpravo`, `.vpravo.dnes`) | seznam na telefonu |
| `.tabulka-obal` + `.tabulka` | tabulka na širších obrazovkách |
| `.kod`, `.rozmer`, `.ukazatel` | štítek kódu, mono rozměr, čtvereček barvy produktu |
| `.denik` | krátký výpis událostí, čas v mono |
| `.tlacitko`, `.vedlejsi`, `.varovne`, `.ikona`, `.plne` | akce |
| `.pole`, `.volba` | formulář: popisek nad polem, spodní linka, zaškrtávátko |
| `.prazdno`, `.kostra`, `.hlaska`, `.toast`, `.panel` | stavy a překryvy |
| `.jen-telefon`, `.jen-siroke` | ukázat jen na telefonu / jen na tabletu a výš |

Ikony: inline SVG, tah 1,6, mřížka 24, `stroke="currentColor"`, bez výplně.
Žádná emoji, žádné ikonové fonty, žádné externí knihovny.

## Každá obrazovka má čtyři stavy

1. **Prázdný** (`.prazdno`) — co tu bude a jak začít; má tlačítko. Na
   nástroji: prázdná stěna s kótou celé délky a výzva „Přidejte první
   skříňku“.
2. **Načítání** (`.kostra`) — tvar budoucího obsahu, ne kolečko.
3. **Chyba** (`.hlaska.chyba`) — česky, co se stalo a co s tím.
4. **Úspěch** (`.toast` / `.hlaska.uspech`) — krátce potvrdí.

**První přihlášení** (produkt s účty): prázdný stav hlavní obrazovky má vedle
hlavní akce `<button type="button" class="tlacitko vedlejsi" data-ukazkova-data>
Naplnit ukázkovými daty</button>`. Nahrání dat z `play/ukazka.json`, pruh
„V účtu máte ukázková data“ a jejich odstranění jedním klepnutím obstará
`simtegen.js`; tlačítko je vidět, jen když to jde.

**Zkušební období** kreslí `simtegen.js` jako pruh nad obsahem (`.sg-pruh`,
nebo do `<div data-pruh-predplatneho>`): klidně, dokud zbývá víc než týden,
varovně posledních 7 dní, chybově po vypršení — vždy s tlačítkem k platbě.
Vlastní odpočet nepiš. Platbu otevře přes `window.ukaz(id obrazovky)` nebo
klikem na prvek s `data-platba`; v aplikaci z Google Play vede jen na nákup
přes Google Play.

## Tisk a PDF

Co si zákazník odnáší na papíře — výkres pro svého zákazníka, kusovník do
dílny, seznam k vydání — se tiskne tlačítkem, ne snímkem obrazovky.
„Uložit jako PDF“ je tentýž dialog. Vzhled tisku dělá `styl.css` sám
(bez menu a tlačítek, světle i z tmavého režimu, výkres přes šířku
stránky s barvami materiálů, nic se nedělí uprostřed řádku):

```html
<button type="button" class="tlacitko vedlejsi" data-tisk>Vytisknout</button>
<button type="button" class="tlacitko vedlejsi" data-tisk="#kusovnik">Vytisknout kusovník</button>
```

Bez hodnoty se tiskne obrazovka, s `#id` jen ten prvek (má mít vlastní
nadpis, co to je a pro koho). Co na papír nepatří, dostane
`data-netisknout`. Vlastní tiskový kód ani `@media print` v produktu
nepiš — `SimteGen.tisk("#id")` je totéž ze skriptu.

## Čísla, peníze, data

Všechno, co je číslo, se píše jedním způsobem ve všech appkách — přes
`simtegen.js`, ne vlastním `toLocaleString` nebo skládáním textu. Mezery
uvnitř hodnoty jsou nezlomitelné, takže „Kč“ nikdy nezůstane samo na řádku.

| Volání | Výsledek |
|---|---|
| `SimteGen.kc(1249)` / `SimteGen.kc(124950, {halere: true})` | 1 249 Kč / 1 249,50 Kč |
| `SimteGen.cislo(12345.5, 1)` | 12 345,5 |
| `SimteGen.datum(d)` | 25. 10. (letos), jinak 25. 10. 2025 |
| `SimteGen.datum(d, {dny: true, cas: true})` | Dnes 14:05 / Zítra / Včera / 28. 10. 9:30 |
| `SimteGen.rozmer([600, 720, 510], "mm")` | 600 × 720 × 510 mm |
| `SimteGen.pocet(3, ["sada", "sady", "sad"])` | 3 sady |

Datum bere `Date`, ISO text nebo unixové sekundy (co vrací D1). Počty se
skloňují — „1 sad“ ani „5 sady“ zákazník vidět nesmí. Počítání s penězi
zůstává na serveru v haléřích; tohle jen píše hotové číslo.

## Potvrzení a vrácení

Okna prohlížeče (`confirm()`, `prompt()`, `alert()`) se nepoužívají — jsou
mimo design, v aplikaci z Google Play působí cize a zamrazí stránku. CI je
odmítne. Místo nich `simtegen.js`:

- **Vrátit místo otázky** — běžné mazání, vydání, přesun: udělej to hned
  a nabídni vrácení. Otázka „Opravdu?“ se odklikává ze zvyku a jen zdržuje.
  ```js
  await api("/api/sady/" + id, "DELETE");
  SimteGen.vratitelne("Sada smazána", () => api("/api/sady/" + id + "/obnovit", "POST"));
  ```
- **Potvrzení** jen u toho, co vrátit nejde (smazání účtu, odeslání
  faktury). Nebezpečné má červené tlačítko a fokus na „Zrušit“:
  ```js
  if (!await SimteGen.potvrd("Smazat účet a všechna data?",
      { popis: "Krok je nevratný.", ano: "Smazat účet", nebezpecne: true })) return;
  ```
- **Dotaz na jednu hodnotu** (nové místo ve skladu):
  ```js
  const misto = await SimteGen.zeptej("Kam sadu ukládáte?", { popisek: "Místo ve skladu", hodnota: "A-12" });
  if (misto === null) return;  // zrušeno
  ```

Nadpis panelu je otázka nebo věta, tlačítko říká, co udělá („Smazat účet“,
ne „OK“).

## Doporučit kolegovi

Nejlepší další zákazník je kolega z oboru. Produkt s účty má na obrazovce
Účet kartu s vedlejším tlačítkem; po úspěchu, na který je zákazník hrdý
(hotová kuchyň ukázaná zákazníkovi, první měsíc bez chyby), smí tlačítko
být i tam — nikdy jako vyskakovací okno ani opakované připomínání:

```html
<button type="button" class="tlacitko vedlejsi" data-doporucit="ucet">Doporučit kolegovi</button>
```

`simtegen.js` otevře sdílení telefonu (WhatsApp, SMS, e-mail) s odkazem
`?utm_source=doporuceni&utm_campaign=<hodnota>`; bez sdílení odkaz
zkopíruje, jinak ho ukáže k ručnímu zkopírování. Nové účty z doporučení
počítají Metriky (zdroj `doporuceni`), nic se neukládá. Hodnota atributu
říká, odkud doporučení šlo (`ucet`, `po-ukazce` …).

## Dotyk, čitelnost, pohyb

- Dotykové cíle ≥ 44 px, řádky seznamu ≥ 56 px, mezi cíli ≥ 8 px.
- Text česky, zákazníkovi se vyká, bez lorem ipsum a bez „Chyba 500“.
- Pohyb jen krátký, na `transform`/`opacity`; `prefers-reduced-motion`
  ho vypne automaticky.

## Aplikace v obchodě (modul aplikace)

Záznam v Google Play kreslí vydání samo, z podkladů v repu. Vypadá u všech
appek SimteGen stejně: papír s tečkovanou mřížkou, nahoře štítek a jedna
věta, pod ní telefon s obrazovkou aplikace, který jde přes spodní okraj.

- **Ikona** vzniká z `play/piktogram.svg`: jeden předmět z oboru produktu
  nakreslený rovnými čarami na mřížce 24×24 (`line`, `rect`, `polyline`,
  `circle`, `path` jen s M L H V Z). Tloušťku, barvu, přechod z barvy
  produktu, rýsovací mřížku a stín dodá generátor; v souboru nejsou.
  Všechno musí ležet do 14 od středu (12,12), jinak to Android v kulaté
  ikoně uřízne. Jeden drobný doplněk z praxe oboru (kóta pod linkou, ryska)
  patří do `<g class="detail">` — kreslí se tenčeji a průhledněji.
- **Snímky**: `aplikace.snimky` v manifestu, 3–6 položek. Každá je jedna
  obrazovka a jedna věta (titulek 8–40 znaků), štítek do 24 znaků, `kliky`
  otevřou obrazovku s daty (např. první zakázku), `tablet: true` ji vyfotí
  i na tabletu. Web bez `.obrazovka` (jedna stránka) místo obrazovky
  posune stránku (`posun` v px). Pořadí vypráví práci zákazníka od začátku
  do výsledku; má-li produkt nástroj, jeho výkres je první snímek.
- **Ukázková data**: produkt s databází má `play/ukazka.json` — kroky přes
  vlastní API, které vytvoří věrohodný, ale vymyšlený obsah. Žádné skutečné
  osoby ani firmy, e-maily jen `@example.cz`. CI je spouští při každé stavbě
  (UAT), snímky se fotí přihlášené právě s nimi.
- **Grafika** nese `aplikace.hlavni_veta` (12–60 znaků) a výřez první
  obrazovky.
- **Co je nového**: `play/co_je_noveho.txt`, přepsaný každou stavbou —
  změna z pohledu zákazníka, nejvýš 500 znaků.

## Co CI odmítne (deterministicky)

- Stránka aplikace bez `styl.css`, `produkt.css`, `simtegen.js`,
  viewportu nebo `application-name`.
- Barva zapsaná přímo v HTML (`#hex`, `rgb()`, `hsl()` ve stylu nebo
  v `<style>`) — barvy jsou jen v `styl.css` a `produkt.css` (a barva
  materiálu jako `--barva-dilu` z JS).
- `produkt.css` s čímkoli jiným než `--barva-produktu`, nebo s kontrastem
  pod 4.5:1. Externí styly, písma a skripty.
- `confirm()`, `prompt()` a `alert()` v HTML nebo JS produktu (viz Potvrzení
  a vrácení).

Stránku navíc vykreslí v prohlížeči (`vizualni_kontrola.py`) na šířkách
360, 390, 820, 1180 a 1440 px, světle i tmavě, každou obrazovku zvlášť, a odmítne:

- Vodorovné posouvání — jmenuje prvek, který vyčnívá.
- Pole bez `<label>` (nebo `aria-label`), tlačítko či odkaz bez textu,
  obrázek bez `alt`.
- Dotykový cíl menší než 44 px na telefonu.
- Text s kontrastem pod 4.5:1 (velký pod 3:1). Na text jen
  `--barva-inkoust` a `--barva-tuzka`; `--barva-tuzka-2/-3` jsou na linky.
- **Víc než jedno černé (hlavní) tlačítko na obrazovce** — počítá se celá
  obrazovka; pruhy a formuláře, které kreslí `simtegen.js`, se nepočítají.
- **Text menší než 13 px** (mimo text uvnitř výkresu).
- **Částku nebo datum v nečeském tvaru**: „1249 Kč“, „1249.50 Kč“, „2026-10-25“
  (piš přes `SimteGen.kc` a `SimteGen.datum`).
- **Větu velkými písmeny** (víc než 24 znaků) **nebo v mono písmu** (víc
  než 40 znaků, převážně písmena).
- Úvodní obrazovku, která se neukáže nebo nezmizí.
- Obrazovku, na které na telefonu není vidět „Nahlásit chybu“ (`.nahlasit-chybu`
  v navigaci, hlavičce, liště nástroje nebo patičce), a tlačítko, které
  neotevře formulář. Formulář i odeslání dělá `simtegen.js` — vlastní
  obsluhu nepiš.

## Co recenzent zamítá

Recenzent dostane snímky telefonu, tabletu a notebooku — posuzuje to,
co uvidí zákazník, ne jen kód.

- Přeplácaná obrazovka: víc prvků, než potřebuje jedna věc, kvůli které
  existuje; ozdoby, štítky nad nadpisy, karta v kartě, stěna tlačítek a polí.
- Chybějící stav (prázdný, načítání, chyba, úspěch).
- Detail bez informace (dekorace, vymyšlená čísla, číslo jen pro efekt).
- Produkt, kde zákazník něco skládá, a výkres je malý obrázek v kartě
  místo obrazovky typu nástroj — nebo výkres bez kót.
- Rozvržení, které na tabletu nebo notebooku jen roztáhne telefon.
- Barva produktu jako plocha pod textem nebo na hlavním tlačítku.
