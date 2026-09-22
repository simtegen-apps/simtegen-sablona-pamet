<!-- GENEROVANÝ SOUBOR — neupravuj ručně. Zdroj: data-manifest.json, generátor: vykresli_zasady.py. -->
# Záznam o činnostech zpracování — Produkt SimteGen

**Verze:** 2.0 · **poslední aktualizace:** (doplnit datum) · **zpracoval:** (doplnit jméno)
**Přezkoumat:** nejméně 1× ročně a při každé změně zpracování, zpracovatelů nebo účelů.

**Správce:** SimteGen s.r.o., IČO (doplnit), se sídlem (doplnit),
e-mail (doplnit), datová schránka (doplnit).
**Zástupce podle čl. 27 GDPR:** nejmenován (správce je usazen v EU).
**Pověřenec pro ochranu osobních údajů:** nejmenován — nesplněna žádná z podmínek čl. 37 GDPR.

Vedeno podle čl. 30 GDPR. Záznam má dvě části: **A** pro zpracování, kde je SimteGen s.r.o.
správcem, a **B** pro zpracování prováděná pro zákazníky, kde je SimteGen s.r.o. zpracovatelem.

---

## A. Záznam správce (čl. 30 odst. 1 GDPR)

### A.1 Účely a rozsah

| Entita / oblast | Účel | Kategorie subjektů | Kategorie údajů | Právní základ | Doba uložení |
|---|---|---|---|---|---|
| uzivatele | účet zákazníka a přihlášení | zákazníci služby | e-mailová adresa, čas založení účtu | čl. 6/1/b — plnění smlouvy | do smazání účtu zákazníkem |
| prihlasovaci_odkazy | jednorázové přihlášení e-mailovým odkazem | zákazníci služby | otisk tokenu, e-mailová adresa, expirace | čl. 6/1/b — plnění smlouvy | 24 hodin |
| relace | udržení přihlášení | zákazníci služby | otisk tokenu, odkaz na účet, expirace | čl. 6/1/b — plnění smlouvy | 30 dní od přihlášení |
| predplatne | evidence zaplaceného období předplatného | zákazníci služby | odkaz na účet, datum konce předplatného, poznámka k platbě (např. číslo dokladu) | čl. 6/1/b — plnění smlouvy | do smazání účtu zákazníkem; účetní doklady vede provozovatel mimo aplikaci po zákonnou dobu |
| hlaseni | hlášení a dotazy zákazníka k aplikaci a naše odpovědi | zákazníci služby | text hlášení, stav vyřízení, odpověď, číslo záznamu v systému podpory, čas | čl. 6/1/b — plnění smlouvy | do smazání účtu zákazníkem |
| platby | evidence zaplacených období předplatného (historie plateb) | zákazníci služby | odkaz na účet, počet zaplacených měsíců, poznámka k platbě, čas zápisu | čl. 6/1/b — plnění smlouvy | do smazání účtu zákazníkem; účetní doklady vede provozovatel mimo aplikaci po zákonnou dobu |
| objednavky | objednávka předplatného a doklad o souhlasu se zahájením služby | zákazníci služby | odkaz na účet, délka a varianta předplatného, cena, fakturační údaje, zda jde o spotřebitele, souhlas se zahájením a jeho čas, stav | čl. 6/1/b — plnění smlouvy | do smazání účtu zákazníkem; účetní doklady vede provozovatel mimo aplikaci po zákonnou dobu |
| provozní a bezpečnostní logy | provozní a bezpečnostní záznamy (logy) | zákazníci a návštěvníci | IP adresa, čas a typ požadavku, identifikace prohlížeče | čl. 6/1/f — oprávněný zájem | (doplnit skutečnou dobu, typicky 30 dnů) |
| podpora a komunikace | vyřízení dotazu nebo požadavku podpory | zákazníci, zájemci | e-mailová adresa a obsah komunikace | čl. 6/1/b, u nezákazníků čl. 6/1/f | (doplnit, typicky 1 rok) |
| účetní a daňové doklady | účetní a daňové doklady | zákazníci | fakturační údaje, částka, datum | čl. 6/1/c — právní povinnost | 10 let; vedeno mimo aplikaci |

**Oprávněný zájem (čl. 6/1/f)** je u logů vymezen jako zajištění provozu, dostupnosti
a bezpečnosti služby a možnost dohledat příčinu poruchy nebo útoku. Test proporcionality:
(doplnit odkaz na provedený balanční test nebo datum jeho provedení).

### A.2 Kategorie příjemců

Zpracovatelé uvedení v části A.3; účetní ((doplnit obchodní firmu)); orgány veřejné moci
v rozsahu, v jakém to ukládá zákon. Údaje se neprodávají ani nepředávají k reklamním účelům.

### A.3 Zpracovatelé a předávání mimo EU

| Zpracovatel | Co dělá | Umístění | Záruky pro předání mimo EU |
|---|---|---|---|
| Cloudflare, Inc. (USA) | hosting aplikace a databáze (primární instance v EU) | primární instance databáze v EU | standardní smluvní doložky EK (čl. 46/2/c), případně rámec EU–USA pro ochranu údajů |
| Resend (Plus Five Five, Inc.) (USA) | odeslání přihlašovacího odkazu na e-mail | USA / EU | standardní smluvní doložky EK (čl. 46/2/c), případně rámec EU–USA pro ochranu údajů |
| GitHub, Inc. (Microsoft) (USA) | evidence hlášení zákazníků pro podporu (jen text hlášení, bez údajů o účtu) | USA / EU | standardní smluvní doložky EK (čl. 46/2/c), případně rámec EU–USA pro ochranu údajů |

Kopie záruk: uloženy u správce, na žádost poskytovány subjektům údajů.

### A.4 Technická a organizační opatření (obecný popis, čl. 30 odst. 1 písm. g)

Šifrovaný přenos (HTTPS) a šifrování dat v klidu; přihlášení bez hesel (jednorázové e-mailové
odkazy, v databázi jen otisky tokenů); oddělená databáze na produkt s primární instancí v EU;
oddělená testovací databáze bez produkčních dat; omezený a evidovaný přístup k produkci;
zálohování s přepisem do 30 dnů; smazání účtu zákazníkem přímo v aplikaci maže všechna jeho
data; písemný postup při incidentu v `POSTUP_PRI_INCIDENTU.md`; roční přezkum opatření.

---

## B. Záznam zpracovatele (čl. 30 odst. 2 GDPR)

SimteGen s.r.o. zpracovává osobní údaje jako **zpracovatel** pro zákazníky služby, kteří
do aplikace vkládají údaje třetích osob. Právním rámcem je
`web/zpracovatelska-smlouva.html` (čl. 28 GDPR), uzavíraná jako součást obchodních podmínek.

| Položka | Obsah |
|---|---|
| **Správci, pro které se zpracovává** | zákazníci služby Produkt SimteGen; jmenný seznam vede správce v evidenci účtů (viz entita `uzivatele`) |
| **Kategorie zpracování** | uložení v databázi, zpřístupnění a zobrazení v aplikaci, zálohování, export na pokyn správce, výmaz |
| **Kategorie subjektů údajů** | osoby, jejichž údaje správce do služby vloží — typicky jeho zákazníci a kontaktní osoby jeho obchodních partnerů, případně jeho pracovníci |
| **Kategorie údajů** | identifikační a kontaktní údaje (jméno, adresa, telefon, e-mail), údaje o zakázce nebo objednávce (popis, termíny, cena, místo plnění), fakturační údaje a obsah poznámek a volných textových polí, které správce vyplní |
| **Zvláštní kategorie (čl. 9/10)** | služba k nim není určena; jejich vkládání je smluvně vyloučeno |
| **Další zpracovatelé** | Cloudflare, Inc.; Resend (Plus Five Five, Inc.); GitHub, Inc. (Microsoft) (viz A.3) |
| **Předání mimo EU** | jen na pokyn správce nebo v rámci dalších zpracovatelů, se zárukami podle A.3 |
| **Doba zpracování** | po dobu trvání smlouvy o službě; poté výmaz nebo vrácení dle volby správce |
| **Technická a organizační opatření** | shodná s A.4 |

---

## Poznámky k vedení záznamu

- Výjimka z vedení záznamu pro subjekty pod 250 zaměstnanců (čl. 30 odst. 5 GDPR)
  se **nepoužije**, protože zpracování probíhá pravidelně a není příležitostné.
- Záznam se na vyžádání předkládá Úřadu pro ochranu osobních údajů.
- Zdrojem je `data-manifest.json` tohoto repozitáře; generuje `vykresli_zasady.py`.
