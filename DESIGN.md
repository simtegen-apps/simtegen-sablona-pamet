# Design produktu — závazné pro stavitele i recenzenta

Proč tenhle soubor existuje: první produkty vypadaly jako webový formulář
a design se musel vracet. Od teď je vzhled součást zadání, ne dodatek.

## Stavební kameny

- **Návrhový systém `web/styl.css` je jediný zdroj barev, písem, rozměrů
  a komponent.** Skládáš z tříd (`.appka`, `.hlavicka`, `.obsah`,
  `.lista-dole`, `.navigace`, `.obrazovka`, `.tlacitko`, `.pole`, `.karta`,
  `.seznam/.radek`, `.prazdno`, `.kostra`, `.hlaska`, `.toast`, `.panel`).
  Vlastní CSS smí přidat jen rozložení konkrétní obrazovky — **žádné nové
  barvy, písma ani velikosti mimo proměnné `--barva-*`, `--velikost-*`,
  `--mezera-*`**.
- Žádné externí písma, ikony ani knihovny. Ikony = emoji nebo inline SVG.

## Obrazovka, ne stránka

- Cílové zařízení je telefon ~390 px. Jedna obrazovka = jeden úkol; k hlavní
  hodnotě produktu vedou **nejvýš tři klepnutí** od otevření.
- Hlavní akce každé obrazovky je **dole v dosahu palce** (`.lista-dole`),
  ne pod dlouhým scrollem. Mezi sekcemi `.navigace` (max 4 položky).
- Hierarchie: jeden `h1` (název obrazovky), sekce `h2`, popisky `.popisek`.
  Číslo nebo stav, na kterém záleží, je největší věc na obrazovce.

## Každá obrazovka má čtyři stavy

1. **Prázdný** (`.prazdno`) — řekne, co tu bude a jak začít; má tlačítko.
2. **Načítání** (`.kostra`) — tvar budoucího obsahu, ne točící kolečko.
3. **Chyba** (`.hlaska.chyba`) — česky, co se stalo a co s tím; bez kódů.
4. **Úspěch** (`.toast` / `.hlaska.uspech`) — krátce potvrdí, co se stalo.

Bez těchto stavů není obrazovka hotová. Recenzent je kontroluje.

## Dotyk a čitelnost

- Dotykové cíle min. 44 px, řádky seznamu 56 px, mezi cíli ≥ 8 px.
- Kontrast textu ≥ 4.5:1 (proměnné to drží; nepřebarvuj text na akcent).
- Formuláře: štítek nad polem, chyba pod polem, `inputmode`/`autocomplete`
  správně (e-mail, telefon, čísla), klávesa Enter odešle.
- Text česky, zákazníkovi se vyká, žádný lorem ipsum, žádná hlášková
  „Chyba 500".

## Pohyb

Jen krátké přechody na `transform`/`opacity` (přepnutí obrazovky, panel,
toast). `prefers-reduced-motion` je respektováno automaticky přes styl.css.

## Co recenzent zamítá bez debaty

- Vzhled webového formuláře (dlouhá stránka s poli a tlačítkem dole).
- Vlastní barvy/písma mimo návrhový systém; externí CSS/fonty/knihovny.
- Chybějící prázdný nebo chybový stav; tlačítka pod 44 px; nečitelný kontrast.
- Cokoliv, co na 390 px přetéká vodorovně nebo vyžaduje zoom.
