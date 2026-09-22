# Produkt SimteGen — šablona s pamětí

Repozitář vznikl ze šablony `simtegen-sablona-pamet`: produkt, který si smí
pamatovat data zákazníka. Oproti základní šabloně nese účty (přihlášení
jednorázovým e-mailovým odkazem, žádná hesla), databázi Cloudflare D1
s primární instancí v EU a hotová GDPR API. Pravidla:

- **`web/` je frontend, `functions/` je API.** Frontend zůstává statická
  stránka bez závislostí a build systému; serverová logika jsou Cloudflare
  Pages Functions — čisté JS soubory, žádné závislosti, sdílené pomůcky
  v `spolecne.js` (mimo `functions/`, aby se nestaly routou).
- **Každá nová tabulka = tři kroky.** Migrace v `db/migrace/NNNN_*.sql`
  (append-only, aplikuje ji CI), sloupec `uzivatel_id` (export a smazání
  účtu jsou generické právě přes něj) a záznam v `data-manifest.json`
  (`ukladame`: entita, účel, pole, retence). CI shodí build, když něco
  z toho chybí.
- **Právní texty se nikdy nepíšou ručně.** `web/zasady.html`,
  `web/podminky.html`, `web/zpracovatelska-smlouva.html`,
  `web/odstoupeni-formular.html`, `ZAZNAM_O_ZPRACOVANI.md` i
  `POSTUP_PRI_INCIDENTU.md` generuje `python3 vykresli_zasady.py`
  z manifestu (texty verze 2.0 = právní revize 19. 9. 2026); CI je porovnává
  se skutečností. Prázdné sloty (IČO, sídlo, DIČ, zápis v OR, kontakt,
  účinnost, DPH, retence logů a podpory, odpovědná osoba…) se vykreslí
  červeně jako „(doplnit …)“ — s nimi se do produkce nejde. Sloty
  `obsah_zakaznika_popis` a `subjekty_obsahu` popisují, co do produktu
  vkládá zákazník (čl. 2 zpracovatelské smlouvy) — vyplňuje stavitel podle
  produktu. Generátor i kontrolu si stavitel obnovuje ze šablony při každé
  stavbě, takže nová verze právního balíku dojde do každého produktu.
- **Objednávka předplatného je v aplikaci** (`POST /api/objednavka`):
  rozsah, délka a cena před tlačítkem, tlačítko „Objednávka zavazující
  k platbě“, u spotřebitele zvláštní souhlas se zahájením před 14denní
  lhůtou (§ 1837 l) s potvrzením e-mailem. Fakturační údaje zůstávají
  v databázi produktu (kopie e-mailem na `KONTAKT_EMAIL` z manifestu), do
  issue jen číslo a délka. Ceník do aplikace dodá stavitel ze schválené
  ceny (`window.CENIK`). **Fakturu vystaví firma sama:** SimteGen na issue
  reaguje, přidělí číslo a částku (ze schválené ceny) a spustí workflow
  **Faktura** v repu šablony (`.github/nastroje/faktura.py`: PDF s QR
  platbou, e-mail zákazníkovi, kopie firmě, objednávka `fakturovana`).
  Platbu potvrdí majitel jednou větou („zaplaceno“ přes ARGA) → workflow
  **Platba** zapíše předplatné a deník plateb a napíše zákazníkovi.
- **Ven se volá jen to, co manifest deklaruje** (`sluzby_treti_strany`).
  Frontend nevolá ven vůbec — jen vlastní `/api/`.
- **Nasazuje se výhradně merge do `main`.** Stavitel pushuje jen větve
  `build/*`; preview má **vlastní databázi** `<repo>-db-nahled`, takže se
  test nikdy nedotkne zákaznických dat.
- **`.github/` patří člověku.** Token SimteGenu na workflow soubory nemá
  právo, GitHub takový push odmítne celý.
- Časy v databázi jsou unixové sekundy (INTEGER); tokeny se ukládají jen
  jako SHA-256 otisky.

Přihlášení bez nastaveného `RESEND_API_KEY`/`EMAIL_ODESILATEL` (typicky
preview) běží ve **vývojovém režimu** — odkaz se vrací v odpovědi místo
e-mailu. Takové nasazení se nesmí vydávat za skutečnou přihlašovací hranici;
produkce se zákazníky ty dva údaje vyžaduje (org secret + variable).

Produkční URL: `https://<název-repa>.pages.dev`, preview:
`https://<větev>.<název-repa>.pages.dev`. Postup při úniku dat:
`POSTUP_PRI_INCIDENTU.md`.

**Předplatné je součást šablony, peníze ne.** Každý účet má zkušební
období (`ZKUSEBNI_DNI` v `predplatne.js`), pak platí jen to, co je
v tabulce `predplatne` (`plati_do`). Middleware dává každému požadavku
`context.data.predplatne` (stav `zkusebni` / `aktivni` / `vyprselo`),
`/api/ja` ho vrací frontendu a **produktové** API se hlídá jedním řádkem:
`const stop = vyzadujPredplatne(context); if (stop) return stop;` (402).
Účet, export, smazání a přihlášení se nehlídají nikdy — práva zákazníka
nevyprší. Platbu vidí jen člověk (banka); zapíše ji workflow **Platba**
z objednávky po jeho slově, nebo ručně workflow **Predplatne** (e-mail,
počet měsíců, poznámka) — obojí z repa šablony pro kterýkoli produkt
(vstup `projekt`). Aplikace s platbou nikdy nepracuje, jen čte `plati_do`.

**Aplikace do Google Play je modul, ne jiný produkt.** Sekce `aplikace`
v `data-manifest.json` (balíček, název ≤ 30, krátký název ≤ 12, popis ≤ 80,
otisky podpisového klíče) a `python vykresli_aplikaci.py` z webu udělají
instalovatelnou aplikaci: manifest, ikony z návrhového systému, offline
stránku, service worker (nikdy nesahá na `/api/`), `.well-known/assetlinks.json`
a odkazy v `index.html`. Nic z toho se needituje ručně — CI to porovnává
s generátorem. Balíček se po prvním vydání nesmí změnit nikdy. Sestavení
a nahrání na interní kanál dělá workflow **Vydani** v repu šablony (vstup
`projekt`); do produkce aplikaci pouští majitel klepnutím v Play Console.

**Schránka je součást šablony.** Zákazník píše z aplikace
(`POST /api/hlaseni`, tabulka `hlaseni`), text se BEZ údajů o účtu zrcadlí
jako issue se štítkem `hlaseni` do tohoto repa (org secret
`GITHUB_ISSUES_TOKEN`, jen produkce). Firma issue přečte a udělá triage;
odpověď je komentář začínající `odpoved:` od majitele nebo firmy — workflow
**Odpoved** ji zapíše k hlášení a zákazník ji vidí v aplikaci. Schránka se
nehlídá předplatným.

**Metriky jsou čísla, ne řádky.** Workflow **Metriky** (plánovaně v repu
šablony pro každý produkt s databází `<repo>-db` na Cloudflare — seznam
si zjistí sám, org variable `SIMTEGEN_PRODUKTY` je jen volitelný přepis; ručně kdekoli
s `projekt`) spočítá účty, aktivitu, zkušební období, předplatné, platby
(deník `platby` plní workflow Predplatne), hlášení a počty řádků
produktových tabulek, a uloží je do větve `metriky` repa šablony
(`produkty/<repo>.json`). SimteGen je odtud čte pro měsíční revizi.
Žádná osobní data tudy neprojdou — jen COUNT.

**Úvodní obrazovka je zároveň přihlášení.** Cizí návštěvník musí za deset
sekund pochopit, co produkt dělá, co stojí a že ho 30 dní zkouší zdarma;
texty píše stavitel podle kontraktu kandidáta, cena je ze schválené
cenotvorby (`window.CENIK`). Zobrazení se počítají anonymně
(`POST /api/navsteva`, tabulka `navstevy`: den, stránka, počet — agregát
bez `uzivatel_id`, deklarovaný v manifestu pod `agregaty`; CI hlídá, že
v agregátech není žádný osobní sloupec). Metriky pak vidí celý řetěz od
zobrazení po druhou platbu.

**Design je součást zadání.** `web/styl.css` je jediný návrhový systém
(barvy, písma, rozměry, komponenty) a `DESIGN.md` říká, jak z něj skládat
obrazovku: čtyři stavy (prázdný, načítání, chyba, úspěch), hlavní akce
v dosahu palce, dotykové cíle 44 px, žádné vlastní barvy ani externí
písma. CI hlídá deterministickou část (styl.css, viewport, žádné externí
styly); recenzent hlídá zbytek a vzhled webového formuláře vrací.

