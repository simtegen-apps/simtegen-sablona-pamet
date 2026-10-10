# Design produktu — návrhový systém v2 „Mřížka a papír“

Závazné pro stavitele i recenzenta. Tenhle soubor a `web/styl.css`,
`web/simtegen.js` a písma ve `web/pismo/` jsou **infrastruktura šablony**:
stavitel je při každé stavbě přepíše aktuální verzí, v produktu se
neupravují. Produkt mění jen `web/produkt.css` (svou barvu) a vlastní
obrazovky.

Proč v2: první appky vypadaly jako první, co vygeneruje AI — stejné karty,
stejná tlačítka, nic, co by říkalo „tohle je od SimteGenu“. v2 nese
firemní podpis a zároveň nechává vyniknout téma produktu.

## Podpis firmy (co má každá appka)

- **Papír a inkoust.** Teplý papír s jemnou tečkovou mřížkou, černý
  inkoust, vlasové linky místo stínů a zaoblení. Rohy jsou ostré.
- **Písmo.** Schibsted Grotesk na všechno, Plex Mono jen na popisky, kódy
  a rozměry (`205/55 R16`, `A-12`). Hierarchii dělá velikost, ne barva.
- **Číslované sekce.** Nadpis sekce je mono štítek `01 — STAV SKLADU`
  s linkou pod ním (`.sekce-titulek`).
- **Obří číslo.** To, na čem na obrazovce záleží nejvíc, je obří číslo
  (`.cislo-obri`) — počet, částka, stav. Jedno na obrazovku.
- **Úvodní obrazovka s logem SimteGen** při každém startu — dělá ji
  `web/simtegen.js`, stránka ho jen načte (viz Kostra).
- **Barva produktu jen jako ukazatel**: čtvereček u názvu, aktivní položka
  menu, plnění stupnice, „Dnes“. Nikdy jako plocha pod textem, nikdy na
  hlavním tlačítku — to je vždy černé.

## Téma produktu (co má každá appka jiné)

- Barva v `web/produkt.css` podle tématu (pneuservis rumělka, truhlář
  jedle …), kontrast na papíře ≥ 4.5:1 — CI to spočítá.
- Slovník a jednotky oboru v mono popiscích (rozměry, kódy míst, čísla
  zakázek), piktogram tématu v ikoně aplikace.
- Detail, který **nese informaci**: stupnice s čísly, rozpad podle druhu,
  týdenní pás, kód místa, deník posledních pohybů. Ne ozdoby, ne
  vymyšlené statistiky.

## Přehlednost

- **Jedna hlavní akce na obrazovku** (černé tlačítko se šipkou,
  `.tlacitko`). Další akce jsou vedlejší (`.tlacitko.vedlejsi`) nebo
  odkazy — nejvýš dvě vedlejší vedle hlavní. Víc akcí = rozdělit
  obrazovku nebo schovat do „Více“.
- Obsah obrazovky je ve 2–4 sekcích oddělených `.sekce-titulek`, ne
  v jedné dlouhé stěně polí a tlačítek.
- Seznam ukazuje 3–5 nejbližších položek a odkaz „Vše →“, ne všechno.

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
    <main class="obsah"> … sekce … </main>
  </div>
</body>
```

`styl.css` z toho sám udělá tři rozvržení:

| Šířka | Navigace | Obsah |
|---|---|---|
| telefon < 768 px | pás dole s textem | jeden sloupec, `.lista-dole` drží hlavní akci v dosahu palce |
| tablet 768–1199 px | levý pruh s ikonami, dole Nahlásit chybu a verze | `.mrizka` o 12 sloupcích, třídy `.s4`–`.s8` |
| notebook ≥ 1200 px | boční menu s textem a značkou | totéž, obsah do 1200 px; `.dva-sloupce` se skládá samo |

Na žádné šířce nic nepřetéká vodorovně; tabulky jsou v `.tabulka-obal`.

## Komponenty (`web/styl.css`)

| Třída | K čemu |
|---|---|
| `.sekce-titulek` | číslovaný mono nadpis sekce s odkazem vpravo |
| `.karta`, `.karta.vykres` | plocha; `.vykres` přidá ořezové značky — jen pro tu nejdůležitější kartu |
| `.cislo-obri`, `.cislo-radek` | hlavní číslo a popis vedle něj |
| `.stupnice` + `style="--hodnota: 80%"` | rysky, plnění v barvě produktu, `.stupnice-popisky` s čísly |
| `.segmenty` + `.legenda` | rozpad celku do 3 dílů ve stupních šedi s popisky |
| `.tyden` (`.dnes`, `.volno`, `.nula`) | 7 dní s počtem |
| `.seznam` / `.radek` (`.poradi`, `.hlavni`, `.vpravo`, `.vpravo.dnes`) | seznam na telefonu |
| `.tabulka-obal` + `.tabulka` | tabulka na širších obrazovkách |
| `.kod`, `.rozmer`, `.ukazatel` | štítek kódu, mono rozměr, čtvereček barvy produktu |
| `.denik` | krátký výpis událostí v mono |
| `.tlacitko`, `.vedlejsi`, `.varovne`, `.ikona`, `.plne` | akce |
| `.pole`, `.volba` | formulář: mono štítek nad polem, spodní linka, zaškrtávátko |
| `.prazdno`, `.kostra`, `.hlaska`, `.toast`, `.panel` | stavy a překryvy |
| `.jen-telefon`, `.jen-siroke` | ukázat jen na telefonu / jen na tabletu a výš |

Ikony: inline SVG, tah 1,6, mřížka 24, `stroke="currentColor"`, bez výplně.
Žádná emoji, žádné ikonové fonty, žádné externí knihovny.

## Každá obrazovka má čtyři stavy

1. **Prázdný** (`.prazdno`) — co tu bude a jak začít; má tlačítko.
2. **Načítání** (`.kostra`) — tvar budoucího obsahu, ne kolečko.
3. **Chyba** (`.hlaska.chyba`) — česky, co se stalo a co s tím.
4. **Úspěch** (`.toast` / `.hlaska.uspech`) — krátce potvrdí.

## Dotyk, čitelnost, pohyb

- Dotykové cíle ≥ 44 px, řádky seznamu ≥ 56 px, mezi cíli ≥ 8 px.
- Text česky, zákazníkovi se vyká, bez lorem ipsum a bez „Chyba 500“.
- Pohyb jen krátký, na `transform`/`opacity`; `prefers-reduced-motion`
  ho vypne automaticky.

## Co CI odmítne (deterministicky)

- Stránka aplikace bez `styl.css`, `produkt.css`, `simtegen.js`,
  viewportu nebo `application-name`.
- Barva zapsaná přímo v HTML (`#hex`, `rgb()`, `hsl()` ve stylu nebo
  v `<style>`) — barvy jsou jen v `styl.css` a `produkt.css`.
- `produkt.css` s čímkoli jiným než `--barva-produktu`, nebo s kontrastem
  pod 4.5:1. Externí styly, písma a skripty.

Stránku navíc vykreslí v prohlížeči (`vizualni_kontrola.py`) na šířkách
360, 390, 820, 1180 a 1440 px, světle i tmavě, každou obrazovku zvlášť, a odmítne:

- Vodorovné posouvání — jmenuje prvek, který vyčnívá.
- Pole bez `<label>` (nebo `aria-label`), tlačítko či odkaz bez textu,
  obrázek bez `alt`.
- Dotykový cíl menší než 44 px na telefonu.
- Text s kontrastem pod 4.5:1 (velký pod 3:1). Na text jen
  `--barva-inkoust` a `--barva-tuzka`; `--barva-tuzka-2/-3` jsou na linky.
- Úvodní obrazovku, která se neukáže nebo nezmizí.
- Obrazovku, na které na telefonu není vidět „Nahlásit chybu“ (`.nahlasit-chybu`
  v navigaci, hlavičce nebo patičce), a tlačítko, které neotevře formulář.
  Formulář i odeslání dělá `simtegen.js` — vlastní obsluhu nepiš.

## Co recenzent zamítá

Recenzent dostane snímky telefonu, tabletu a notebooku — posuzuje to,
co uvidí zákazník, ne jen kód.

- Víc než jedna hlavní akce na obrazovce, nebo stěna tlačítek a polí.
- Chybějící stav (prázdný, načítání, chyba, úspěch).
- Detail bez informace (dekorace, vymyšlená čísla) i opak — holá obrazovka
  bez sekcí, bez čísla, na kterém záleží.
- Rozvržení, které na tabletu nebo notebooku jen roztáhne telefon.
- Barva produktu jako plocha pod textem nebo na hlavním tlačítku.
