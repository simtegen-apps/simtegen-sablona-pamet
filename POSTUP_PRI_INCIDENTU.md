<!-- GENEROVANÝ SOUBOR — neupravuj ručně. Zdroj: data-manifest.json, generátor: vykresli_zasady.py. -->
# Postup při bezpečnostním incidentu

Platí pro každý produkt z této šablony. „Incidentem" se myslí důvodné podezření, že se
k uloženým údajům dostal někdo nepovolaný, že byly změněny nebo zničeny nebo se staly
nedostupnými (únik databáze, kompromitovaný token, chyba zpřístupňující cizí data,
ransomware, ztráta záloh).

**Odpovědná osoba:** (doplnit jméno), zástup: (doplnit jméno).
Kdo incident zjistí, uvědomí ji neprodleně — lhůty níže běží od okamžiku, kdy se
o incidentu dozvěděl kdokoli z firmy, ne od okamžiku, kdy se to dozvěděla odpovědná osoba.

---

## 1. Zastav škodu (hned)

Otoč Cloudflare API token a klíč k odesílání e-mailů, smaž všechny relace
(`DELETE FROM relace`), v krajním případě pozastav Pages projekt.
Nic z toho nepotřebuje ničí souhlas. Kompromitované přístupové údaje se nikdy
nepoužívají znovu ani v jiném prostředí.

## 2. Zapiš, co se stalo

Do evidence incidentů (`incidenty/RRRR-MM-DD-nazev.md`) zapiš:

- čas incidentu a čas zjištění (obojí),
- co uniklo — které entity a kategorie údajů,
- kolika účtů a přibližně kolika subjektů údajů se to týká,
- jak k tomu došlo a jak to bylo zjištěno,
- pravděpodobné důsledky pro dotčené osoby,
- přijatá a navržená opatření.

**Zapisuje se každý incident, i ten, který se nikam nehlásí.** Evidenci vyžaduje
čl. 33 odst. 5 GDPR a slouží jako doklad, že posouzení proběhlo.

## 3. Urči roli — tohle rozhoduje, komu se hlásí

| Čích údajů se incident týká | Naše role | Komu hlásíme |
|---|---|---|
| účty zákazníků, přihlašovací tokeny, relace, předplatné, logy | **správce** | ÚOOÚ do 72 h + dotčeným osobám při vysokém riziku |
| obsah, který do aplikace vložil zákazník (údaje jeho klientů) | **zpracovatel** | **dotčenému zákazníkovi do 24 h** — on pak hlásí ÚOOÚ sám |
| obojí zároveň | obě role | obě větve současně |

V roli zpracovatele **nehlásíme ÚOOÚ ani subjektům údajů** — to je povinnost zákazníka
jako správce (čl. 33 odst. 2 GDPR). Naší povinností je dát mu včas úplné podklady.

## 4. V roli správce: ohlášení ÚOOÚ do 72 hodin

Ohlas na https://uoou.gov.cz (formulář pro ohlášení porušení zabezpečení)
**do 72 hodin od zjištění**, pokud je pravděpodobné, že incident představuje riziko
pro práva a svobody dotčených osob (čl. 33 odst. 1 GDPR).

Riziko posuzuj podle typu a citlivosti údajů, snadnosti identifikace osob, závažnosti
důsledků, počtu dotčených osob a toho, zda byly údaje čitelné (šifrované × nešifrované).
U této šablony uniká nejvýš e-mail a data deklarovaná v manifestu — u úniku e-mailů
spolu s otisky tokenů riziko zpravidla dosaženo je; samostatný únik nečitelných otisků
tokenů bez e-mailů zpravidla ne. Závěr vždy odůvodni v evidenci.

Nestihne-li se 72 h, ohlas i tak a připoj **důvody prodlení** — pozdní ohlášení s odůvodněním
je přípustné, neohlášení ne. Nejsou-li všechny informace k dispozici, ohlas, co víš,
a zbytek doplň postupně.

## 5. Informuj dotčené osoby

- **V roli správce:** informuj dotčené osoby bez zbytečného odkladu, pokud incident
  představuje **vysoké riziko** pro jejich práva a svobody (čl. 34 GDPR). Sděl jim
  srozumitelně, co se stalo, co s tím děláme, co mají udělat oni a kontakt na nás.
  Informovat nemusíš, pokud byly údaje nečitelné (šifrované), pokud jsi přijal opatření,
  která vysoké riziko odvrátila, nebo pokud by to vyžadovalo nepřiměřené úsilí —
  tehdy stačí veřejné oznámení. Důvod zapiš do evidence.
- **V roli zpracovatele:** dotčené osoby neinformuješ ty, ale zákazník. Nabídni mu
  součinnost a podklady.
- **Vždy:** ať už je povinnost jakákoli, zvaž informování zákazníků z hlediska důvěry.
  Dobrovolné oznámení je v pořádku — jen ho neprezentuj jako zákonnou povinnost.

## 6. Oprav příčinu

Normální cestou (build větev → recenze → merge). Po vyřešení doplň poučení
do tohoto souboru v šabloně, ať ho zdědí další produkty, a zkontroluj, zda
zjištění nemění technická a organizační opatření popsaná v záznamu o činnostech
zpracování a ve zpracovatelské smlouvě — pokud ano, aktualizuj i je.

---

## Lhůty na jednom místě

| Kdy | Co |
|---|---|
| ihned | zastavit škodu, uvědomit odpovědnou osobu |
| do 24 h | v roli zpracovatele ohlásit dotčenému zákazníkovi |
| do 72 h od zjištění | v roli správce ohlásit ÚOOÚ (je-li riziko) |
| bez zbytečného odkladu | informovat dotčené osoby (je-li vysoké riziko) |
| průběžně | vést evidenci incidentů |

## Kontakty

- Odpovědná osoba a kontakt na správce: viz výše a `data-manifest.json` (`kontakt_email`)
- Úřad pro ochranu osobních údajů: https://uoou.gov.cz, Pplk. Sochora 27, 170 00 Praha 7
- **K ověření:** spadá-li firma pod zákon o kybernetické bezpečnosti (NIS2), hlásí se
  incidenty také NÚKIB. U poskytovatele cloudových služeb pod 50 zaměstnanci a s obratem
  do 10 mil. EUR to zpravidla neplatí — potvrdit a zapsat závěr sem.
