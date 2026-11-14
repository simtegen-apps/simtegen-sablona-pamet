/* simtegen-navrh v2 — úvodní obrazovka s logem SimteGen. NEUPRAVOVAT V PRODUKTU.
 *
 * Proč skript a ne kus HTML v každé appce: logo firmy musí být při startu
 * vidět VŽDY a všude stejně — v prohlížeči i v Android aplikaci — a nesmí
 * záviset na tom, jestli si ho stavitel vzpomene napsat. Stavitel ho při
 * každé stavbě přepíše aktuální verzí ze šablony; CI hlídá, že ho každá
 * stránka aplikace načítá.
 *
 * Vkládá se hned za <body> (synchronně, je malý), aby se logo ukázalo dřív
 * než obsah. Když člověk do aplikace přichází zvenku, logo se poskládá
 * animací (1,75 s); mezi stránkami produktu už jen hotová značka. Zmizí po
 * načtení stránky, nejdřív po animaci, jinak za 700 ms (aby nebliklo),
 * a nejpozději za 2,5 s (pojistka, kdyby se něco zaseklo). Nic neukládá
 * (jedinou výjimkou je koncept formuláře, o který si produkt výslovně řekne
 * atributem data-koncept a má ho v manifestu — viz Formuláře níž);
 * posílá jen hlášení chyby, které zákazník sám odešle (níž), a to jen na
 * vlastní /api/ produktu. Název produktu a verze se čtou z <meta>:
 *   <meta name="application-name" content="Pneusklad">
 *   <meta name="simtegen-verze" content="1.4">
 * Stránka, která úvod nechce (zásady, formulář pro odstoupení), skript
 * prostě nenačítá.
 */
(function () {
  "use strict";
  var doc = document;
  if (!doc.body || doc.querySelector(".sg-start")) return;

  function meta(jmeno) {
    var el = doc.querySelector('meta[name="' + jmeno + '"]');
    return el ? el.getAttribute("content") || "" : "";
  }
  function prvek(tag, trida, text) {
    var el = doc.createElement(tag);
    if (trida) el.className = trida;
    if (text) el.textContent = text;
    return el;
  }

  /* ── Jazyk a měna ──────────────────────────────────────────────────
   * Apps are sold through Google Play abroad too, so a product speaks the
   * customer's language and shows prices in the customer's currency.
   *
   * Language. The product declares what it speaks in its <head>:
   *   <meta name="simtegen-jazyky" content="cs en">
   * and brings its own words right after this script:
   *   <script src="texty.js"></script>   →   SimteGen.slovnik({"cs": {…}, "en": {…}})
   * Czech stays written in the HTML (a page without script and a search
   * engine read Czech); elements marked data-t="klic" (data-t-placeholder,
   * data-t-aria-label, data-t-title for attributes) get the chosen language
   * when the page is parsed, and again whenever the product inserts marked
   * elements later. A product's script asks SimteGen.t("klic", {n: 3}).
   * The choice: ?jazyk=en (CI renders the English page this way), then a
   * choice the customer made by hand, then the browser's languages
   * (Slovak reads Czech), then English — the bigger market — if the
   * product speaks it. A product without the meta tag stays Czech in full:
   * an old product must never mix English template bars into Czech screens.
   *
   * Currency. The approved price list is web/cenik.json, written by
   * SimteGen from the owner's approval (never by the builder, never
   * converted here): every amount in every currency is a fixed number the
   * owner said yes to. The default currency follows the country Cloudflare
   * sees (/api/prostredi: CZ → CZK, Europe → EUR, elsewhere USD) — the
   * country is not stored anywhere, not even here.
   *
   * Remembering a choice is the one thing kept in the browser, and only
   * after the customer switched by hand (browser storage, key "sg-volba": language
   * and currency, nothing else) — what they asked for, so no consent
   * (§ 89 odst. 3 ZEK); the policy says so.
   *
   * The block between the jazyk:zacatek / jazyk:konec marks is pure (no
   * DOM): tests/test_jazyky.py runs it in Node.
   */
  /* jazyk:zacatek */
  var NBSP = " ";
  var TEXTY_SABLONY = {
    cs: {
      "sg.nacitam": "Načítám",
      "sg.nacitam_nazev": "Načítám {nazev}",
      "sg.zavrit": "Zavřít",
      "sg.hlaseni.nadpis": "Nahlásit chybu",
      "sg.hlaseni.pro": "Zpráva pro {nazev}",
      "sg.hlaseni.pro_nas": "Zpráva pro nás",
      "sg.hlaseni.uvod": "Napište, co jste dělali a co se stalo. Přiložíme jen technické údaje " +
        "(verze, obrazovka, chyby stránky), nic o vás. Chcete-li odpověď a nejste přihlášeni, uveďte kontakt.",
      "sg.hlaseni.popisek": "Co se stalo",
      "sg.hlaseni.odeslat": "Odeslat hlášení",
      "sg.hlaseni.prazdne": "Napište nám prosím, o co jde.",
      "sg.hlaseni.prijato": "Děkujeme, hlášení jsme přijali.",
      "sg.hlaseni.limit": "Teď nemůžeme přijmout další zprávu — zkuste to prosím za chvíli.",
      "sg.hlaseni.chyba": "Hlášení se nepodařilo odeslat. Zkuste to prosím znovu.",
      "sg.hlaseni.offline": "Hlášení se nepodařilo odeslat — jste připojeni k internetu?",
      "sg.dny": { one: "den", few: "dny", many: "dne", other: "dní" },
      "sg.predplatit": "Předplatit",
      "sg.predplatne": "Předplatné",
      "sg.pruh.vyprselo": "Předplatné vypršelo. Data máte dál uložená — stáhnout si je, napsat nám i smazat " +
        "účet můžete i teď. Pokračovat v práci půjde po zaplacení.",
      "sg.pruh.zbyva": "Zkušební období: zbývá {pocet}{do}.",
      "sg.pruh.do": " (do {datum})",
      "sg.pruh.konci": "Zkušební období končí {kdy}.",
      "sg.dnes": "dnes",
      "sg.zitra": "zítra",
      "sg.za": "za {pocet}",
      "sg.za_datum": "za {pocet} ({datum})",
      "sg.ukazka.pripravuji": "Připravuji ukázková data…",
      "sg.ukazka.nejde": "Ukázková data teď nejde nahrát.",
      "sg.objednavka.mimo": "Objednávka na fakturu je zatím jen pro zákazníky v Česku.",
      "sg.objednavka.mimo_play": "Objednávka na fakturu je zatím jen pro zákazníky v Česku. Předplatné si koupíte v aplikaci pro Android (Google Play).",
      "sg.chyba.objednavka_jen_cesko": "Objednávka na fakturu je zatím jen pro zákazníky v Česku.",
      "sg.ukazka.pruh": "V účtu máte ukázková data — vymyšlené záznamy, ať je vidět, jak aplikace vypadá " +
        "v provozu. Až si zapíšete vlastní, ukázku odstraňte.",
      "sg.ukazka.odstranit": "Odstranit ukázková data",
      "sg.ukazka.odstranuji": "Odstraňuji…",
      "sg.znovu_nepovedlo": "Nepovedlo se — zkusit znovu",
      "sg.offline.text": "Nejde se spojit se serverem — nejspíš slabý signál nebo výpadek internetu. " +
        "Data zůstávají uložená; až se spojení vrátí, načteme je znovu.",
      "sg.offline.znovu": "Zkusit znovu",
      "sg.offline.zkousim": "Zkouším…",
      "sg.vcera": "Včera",
      "sg.dnes_velke": "Dnes",
      "sg.zitra_velke": "Zítra",
      "sg.dialog.odpoved": "Odpověď",
      "sg.dialog.ulozit": "Uložit",
      "sg.dialog.pokracovat": "Pokračovat",
      "sg.dialog.zrusit": "Zrušit",
      "sg.vratit": "Vrátit",
      "sg.vraceno": "Vráceno",
      "sg.vratit_chyba": "Vrátit se nepodařilo — zkuste to prosím znovu.",
      "sg.doporucit.text": "Doporučuji {nazev}.",
      "sg.doporucit.tuhle": "tuhle aplikaci",
      "sg.doporucit.posli": "Pošlete kolegovi tento odkaz",
      "sg.doporucit.odkaz": "Odkaz",
      "sg.doporucit.hotovo": "Hotovo",
      "sg.doporucit.zkopirovano": "Odkaz je zkopírovaný — vložte ho kolegovi do zprávy.",
      "sg.pole.zaskrtnete": "Zaškrtněte prosím.",
      "sg.pole.vyberte": "Vyberte prosím.",
      "sg.pole.vyplnte": "Vyplňte prosím.",
      "sg.pole.email": "Zadejte e-mail ve tvaru jmeno@firma.cz.",
      "sg.pole.url": "Zadejte celou webovou adresu.",
      "sg.pole.cislo": "Zadejte číslo.",
      "sg.pole.hodnota": "Zkontrolujte hodnotu.",
      "sg.pole.aspon": "Aspoň {n} znaků.",
      "sg.pole.nejvys_znaku": "Nejvýš {n} znaků.",
      "sg.pole.nejmene": "Nejméně {n}.",
      "sg.pole.nejvys": "Nejvýš {n}.",
      "sg.pole.cele": "Zadejte celé číslo.",
      "sg.pole.nasobek": "Zadejte násobek {n}.",
      "sg.pole.tvar": "Zkontrolujte tvar.",
      "sg.pruvodce.hotovo": "Hotovo: ",
      "sg.jazyk": "Jazyk",
      "sg.mena": "Měna",
      "sg.chyba.obecna": "Něco se nepovedlo. Zkuste to prosím znovu.",
      "sg.chyba.cizi_stranka": "Požadavek z cizí stránky jsme odmítli.",
      "sg.chyba.format": "Požadavek se nepodařilo přečíst. Obnovte prosím stránku.",
      "sg.chyba.moc_pokusu": "Příliš mnoho pokusů. Zkuste to prosím za hodinu.",
      "sg.chyba.moc_emailu": "Přihlašovacích e-mailů je teď příliš mnoho. Zkuste to prosím za chvíli.",
      "sg.chyba.email_nejde": "Přihlašování e-mailem teď nefunguje. Zkuste to prosím později, nebo nám chybu nahlaste.",
      "sg.chyba.email_neplatny": "Zadejte prosím platnou e-mailovou adresu.",
      "sg.chyba.email_neodeslan": "Odeslání e-mailu se nepodařilo. Zkuste to prosím znovu.",
      "sg.chyba.neprihlasen": "Nejste přihlášeni.",
    },
    en: {
      "sg.nacitam": "Loading",
      "sg.nacitam_nazev": "Loading {nazev}",
      "sg.zavrit": "Close",
      "sg.hlaseni.nadpis": "Report a problem",
      "sg.hlaseni.pro": "Message for {nazev}",
      "sg.hlaseni.pro_nas": "Message for us",
      "sg.hlaseni.uvod": "Tell us what you were doing and what happened. We attach only technical details " +
        "(version, screen, page errors), nothing about you. If you want a reply and are not signed in, " +
        "add your contact.",
      "sg.hlaseni.popisek": "What happened",
      "sg.hlaseni.odeslat": "Send report",
      "sg.hlaseni.prazdne": "Please tell us what it is about.",
      "sg.hlaseni.prijato": "Thank you, we have received your report.",
      "sg.hlaseni.limit": "We cannot take another message right now — please try again in a moment.",
      "sg.hlaseni.chyba": "The report could not be sent. Please try again.",
      "sg.hlaseni.offline": "The report could not be sent — are you connected to the internet?",
      "sg.dny": { one: "day", other: "days" },
      "sg.predplatit": "Subscribe",
      "sg.predplatne": "Subscription",
      "sg.pruh.vyprselo": "Your subscription has expired. Your data is still stored — you can download it, " +
        "write to us or delete your account even now. You can carry on working once it is paid.",
      "sg.pruh.zbyva": "Trial: {pocet} left{do}.",
      "sg.pruh.do": " (until {datum})",
      "sg.pruh.konci": "Your trial ends {kdy}.",
      "sg.dnes": "today",
      "sg.zitra": "tomorrow",
      "sg.za": "in {pocet}",
      "sg.za_datum": "in {pocet} ({datum})",
      "sg.ukazka.pripravuji": "Preparing sample data…",
      "sg.ukazka.nejde": "Sample data cannot be loaded right now.",
      "sg.objednavka.mimo": "Invoice orders are only available to customers in Czechia for now.",
      "sg.objednavka.mimo_play": "Invoice orders are only available to customers in Czechia for now. You can subscribe in the Android app (Google Play).",
      "sg.chyba.objednavka_jen_cesko": "Invoice orders are only available to customers in Czechia for now.",
      "sg.ukazka.pruh": "Your account holds sample data — made-up records that show the app at work. " +
        "Once you enter your own, remove the sample.",
      "sg.ukazka.odstranit": "Remove sample data",
      "sg.ukazka.odstranuji": "Removing…",
      "sg.znovu_nepovedlo": "That did not work — try again",
      "sg.offline.text": "Cannot reach the server — probably a weak signal or an internet outage. " +
        "Your data stays stored; we will load it again once the connection is back.",
      "sg.offline.znovu": "Try again",
      "sg.offline.zkousim": "Trying…",
      "sg.vcera": "Yesterday",
      "sg.dnes_velke": "Today",
      "sg.zitra_velke": "Tomorrow",
      "sg.dialog.odpoved": "Answer",
      "sg.dialog.ulozit": "Save",
      "sg.dialog.pokracovat": "Continue",
      "sg.dialog.zrusit": "Cancel",
      "sg.vratit": "Undo",
      "sg.vraceno": "Undone",
      "sg.vratit_chyba": "Undo did not work — please try again.",
      "sg.doporucit.text": "I recommend {nazev}.",
      "sg.doporucit.tuhle": "this app",
      "sg.doporucit.posli": "Send this link to a colleague",
      "sg.doporucit.odkaz": "Link",
      "sg.doporucit.hotovo": "Done",
      "sg.doporucit.zkopirovano": "The link is copied — paste it into a message to your colleague.",
      "sg.pole.zaskrtnete": "Please tick this box.",
      "sg.pole.vyberte": "Please choose one.",
      "sg.pole.vyplnte": "Please fill this in.",
      "sg.pole.email": "Enter an e-mail like name@company.com.",
      "sg.pole.url": "Enter the full web address.",
      "sg.pole.cislo": "Enter a number.",
      "sg.pole.hodnota": "Check the value.",
      "sg.pole.aspon": "At least {n} characters.",
      "sg.pole.nejvys_znaku": "At most {n} characters.",
      "sg.pole.nejmene": "At least {n}.",
      "sg.pole.nejvys": "At most {n}.",
      "sg.pole.cele": "Enter a whole number.",
      "sg.pole.nasobek": "Enter a multiple of {n}.",
      "sg.pole.tvar": "Check the format.",
      "sg.pruvodce.hotovo": "Done: ",
      "sg.jazyk": "Language",
      "sg.mena": "Currency",
      "sg.chyba.obecna": "Something went wrong. Please try again.",
      "sg.chyba.cizi_stranka": "We refused a request from another site.",
      "sg.chyba.format": "The request could not be read. Please reload the page.",
      "sg.chyba.moc_pokusu": "Too many attempts. Please try again in an hour.",
      "sg.chyba.moc_emailu": "Too many sign-in e-mails right now. Please try again shortly.",
      "sg.chyba.email_nejde": "Signing in by e-mail is not working right now. Please try later, or report the problem.",
      "sg.chyba.email_neplatny": "Please enter a valid e-mail address.",
      "sg.chyba.email_neodeslan": "The e-mail could not be sent. Please try again.",
      "sg.chyba.neprihlasen": "You are not signed in.",
    },
  };
  // Formats per language. English follows British order (25 Oct 2026) —
  // unambiguous for readers on both sides of the Atlantic.
  var MISTNI = { cs: "cs-CZ", en: "en-GB" };
  var MENY = ["CZK", "EUR", "USD"];
  // Europe pays in euros even outside the eurozone: a Pole or a Swiss
  // reads EUR more easily than USD, and the owner approves only three.
  var EVROPA = ("AD AL AT BA BE BG BY CH CY DE DK EE ES FI FO FR GB GI GR HR HU IE IS IT LI LT LU LV MC MD ME " +
    "MK MT NL NO PL PT RO RS SE SI SK SM UA VA XK").split(" ");

  var produktJazyky = ["cs"];
  var slovnikProduktu = {};
  var jazyk = "cs";

  function primarni(kod) {
    var p = String(kod || "").toLowerCase().split(/[-_]/)[0];
    return p === "sk" ? "cs" : p;
  }

  // Pure: what the product speaks, the ?jazyk= of the address, the hand
  // choice and the browser's list in → one language out.
  function vyberJazyk(nabidka, parametr, volba, prohlizec) {
    var mozne = (nabidka || []).filter(function (j) { return TEXTY_SABLONY[j]; });
    if (mozne.indexOf("cs") < 0) mozne.unshift("cs");
    if (mozne.length === 1) return "cs";
    if (parametr && mozne.indexOf(parametr) >= 0) return parametr;
    if (volba && mozne.indexOf(volba) >= 0) return volba;
    var seznam = prohlizec || [];
    for (var i = 0; i < seznam.length; i++) {
      var p = primarni(seznam[i]);
      if (mozne.indexOf(p) >= 0) return p;
    }
    return mozne.indexOf("en") >= 0 ? "en" : "cs";
  }

  // Pure: the country (or nothing), the hand choice and the currencies the
  // price list has → one currency.
  function vyberMenu(nabidka, zeme, volba, jaz) {
    var mozne = (nabidka && nabidka.length ? nabidka : ["CZK"]).filter(function (m) { return MENY.indexOf(m) >= 0; });
    if (!mozne.length) mozne = ["CZK"];
    if (volba && mozne.indexOf(volba) >= 0) return volba;
    var chci;
    if (zeme) chci = zeme === "CZ" ? "CZK" : EVROPA.indexOf(zeme) >= 0 ? "EUR" : "USD";
    else chci = jaz === "cs" ? "CZK" : "EUR";
    if (mozne.indexOf(chci) >= 0) return chci;
    if (chci !== "CZK" && mozne.indexOf("EUR") >= 0) return "EUR";
    return mozne[0];
  }

  function hledej(jaz, klic) {
    var z = slovnikProduktu[jaz] && slovnikProduktu[jaz][klic];
    if (z == null) z = TEXTY_SABLONY[jaz] && TEXTY_SABLONY[jaz][klic];
    return z;
  }

  /* An error from the server for the customer: the page's words for its
   * `kod` — the product's "chyba.<kod>", else the template's "sg.chyba.<kod>"
   * — and the server's Czech sentence only on a Czech page (batch B,
   * 14. 11. 2026: an English page showed "Příliš mnoho pokusů"). `zaloha`
   * is the page's own fallback, in the page's language (SimteGen.t on a
   * bilingual page); without it the generic sentence. */
  function chyba(data, zaloha) {
    var kod = data && typeof data.kod === "string" && /^[a-z0-9_]{1,40}$/.test(data.kod) ? data.kod : "";
    if (kod && hledej(jazyk, "chyba." + kod) != null) return tr("chyba." + kod);
    if (kod && hledej(jazyk, "sg.chyba." + kod) != null) return tr("sg.chyba." + kod);
    if (jazyk === "cs" && data && data.chyba) return String(data.chyba);
    return String(zaloha || tr("sg.chyba.obecna"));
  }

  function tr(klic, promenne) {
    promenne = promenne || {};
    var hodnota = hledej(jazyk, klic);
    // A missing English word shows Czech, not the key: CI catches the gap
    // (kontrola_manifestu.py), the customer still reads a sentence.
    if (hodnota == null) hodnota = hledej("cs", klic);
    if (hodnota == null) return String(klic);
    if (typeof hodnota === "object") {
      var n = Number(promenne.n);
      var tvar = "other";
      try { tvar = new Intl.PluralRules(MISTNI[jazyk] || jazyk).select(isFinite(n) ? n : 0); } catch (e) { /* old engine */ }
      hodnota = hodnota[tvar] != null ? hodnota[tvar] : hodnota.other;
    }
    return String(hodnota).replace(/\{(\w+)\}/g, function (cele, jmeno) {
      if (!(jmeno in promenne)) return cele;
      var v = promenne[jmeno];
      return typeof v === "number" ? cislo(v) : String(v);
    });
  }

  function cislo(n, desetinna) {
    var x = Number(n);
    if (!isFinite(x)) return "–";
    // Without a precision: at most two decimals, no trailing zeros (1,5 not 1,50).
    var s = (desetinna == null ? String(Number(x.toFixed(2))) : x.toFixed(desetinna)).split(".");
    var cele = s[0].replace(/^-/, "");
    var oddelovac = jazyk === "cs" ? NBSP : ",";
    var skupiny = cele.replace(/\B(?=(\d{3})+(?!\d))/g, oddelovac);
    var minus = x < 0 && Number(s.join(".")) !== 0 ? "−" : "";
    return minus + skupiny + (s[1] ? (jazyk === "cs" ? "," : ".") + s[1] : "");
  }

  // A price: the amount as the price list writes it (a decimal string
  // "4.90" or a number; {halere: true} for minor units, what the API
  // stores) and its ISO code. Whole amounts without decimals, otherwise two.
  // Czech writes the sign after the number (129 Kč, 4,90 €, 5,49 US$),
  // English before it (CZK 129, €4.90, US$5.49).
  var ZNACKY = { cs: { CZK: "Kč", EUR: "€", USD: "US$" }, en: { CZK: "CZK", EUR: "€", USD: "US$" } };
  function cena(castka, mena, volby) {
    var x = Number(castka);
    if (volby && volby.halere) x = x / 100;
    if (!isFinite(x)) return "–";
    mena = String(mena || "CZK").toUpperCase();
    var cela = Math.round(x * 100) % 100 === 0;
    var c = cislo(x, cela ? 0 : 2);
    var znacky = ZNACKY[jazyk] || ZNACKY.en;
    var znak = znacky[mena] || mena;
    if (jazyk === "cs") return c + NBSP + znak;
    if (znak.length > 2) return znak + (znak === "US$" ? "" : NBSP) + c;
    return znak + c;
  }
  function kc(castka, volby) {
    return cena(castka, "CZK", volby);
  }
  function naDatum(d) {
    if (d instanceof Date) return d;
    if (typeof d === "number") return new Date(d < 1e12 ? d * 1000 : d);
    // "2026-10-25 14:05:00" from SQLite is local-less; treat it as UTC like D1 writes it.
    var s = String(d || "");
    if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(s)) s = s.replace(" ", "T") + "Z";
    return new Date(s);
  }
  function datum(d, volby) {
    volby = volby || {};
    var t = naDatum(d);
    if (isNaN(t.getTime())) return "–";
    var dnes = new Date();
    var den = function (x) { return new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime(); };
    var cas = volby.cas ? NBSP + t.getHours() + ":" + ("0" + t.getMinutes()).slice(-2) : "";
    if (volby.dny) {
      var rozdil = Math.round((den(t) - den(dnes)) / 86400000);
      var slovo = { "-1": "sg.vcera", "0": "sg.dnes_velke", "1": "sg.zitra_velke" }[String(rozdil)];
      if (slovo) return tr(slovo) + cas;
    }
    var rok = volby.rok || t.getFullYear() !== dnes.getFullYear();
    if (jazyk !== "cs") {
      // 25 Oct / 25 Oct 2025 — the month as a word, so 3/4 is never a riddle.
      var mesic = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ")[t.getMonth()];
      return t.getDate() + NBSP + mesic + (rok ? NBSP + t.getFullYear() : "") + cas;
    }
    return t.getDate() + "." + NBSP + (t.getMonth() + 1) + "." + (rok ? NBSP + t.getFullYear() : "") + cas;
  }
  function pocet(n, tvary) {
    var x = Math.abs(Number(n));
    if (typeof tvary === "string") {
      // A dictionary word with its plural forms: SimteGen.pocet(3, "sada").
      return cislo(n) + NBSP + tr(tvary, { n: x });
    }
    // 1 sada, 2–4 sady, 5 sad; a fraction takes the genitive singular (1,5 sady).
    var cele = Math.round(x) === x;
    var tvar = !cele ? tvary[1] : x === 1 ? tvary[0] : (x >= 2 && x <= 4) ? tvary[1] : tvary[2];
    return cislo(n) + NBSP + tvar;
  }
  /* jazyk:konec */

  function prijmiJazyk() {
    var meta = doc.querySelector('meta[name="simtegen-jazyky"]');
    produktJazyky = meta ? (meta.getAttribute("content") || "").split(/[\s,]+/).filter(Boolean) : ["cs"];
    var parametr = null;
    try { parametr = new URLSearchParams(location.search).get("jazyk"); } catch (e) { /* old engine */ }
    jazyk = vyberJazyk(produktJazyky, parametr, nactiVolbu().jazyk, navigator.languages || [navigator.language]);
    doc.documentElement.setAttribute("lang", jazyk);
  }

  function nactiVolbu() {
    try { return JSON.parse(localStorage.getItem("sg-volba") || "{}") || {}; } catch (e) { return {}; }
  }
  function ulozVolbu(co, hodnota) {
    var v = nactiVolbu();
    v[co] = hodnota;
    try { localStorage.setItem("sg-volba", JSON.stringify(v)); } catch (e) { /* blocked: this visit only */ }
  }

  prijmiJazyk();

  // The product's words: texty.js calls this right after this script, so
  // the dictionary is there before the page's own script runs.
  function slovnik(texty) {
    Object.keys(texty || {}).forEach(function (j) {
      slovnikProduktu[j] = slovnikProduktu[j] || {};
      Object.keys(texty[j] || {}).forEach(function (k) { slovnikProduktu[j][k] = texty[j][k]; });
    });
  }

  // Text into a marked element without losing its icon: an element with
  // children keeps them and only its last piece of text changes.
  function vlozText(el, text) {
    if (!el.children.length) { el.textContent = text; return; }
    var uzly = Array.prototype.filter.call(el.childNodes, function (u) {
      return u.nodeType === 3 && u.nodeValue.trim();
    });
    if (!uzly.length) { el.appendChild(doc.createTextNode(text)); return; }
    var u = uzly[uzly.length - 1];
    u.nodeValue = u.nodeValue.match(/^\s*/)[0] + text + u.nodeValue.match(/\s*$/)[0];
  }

  var ATRIBUTY_T = ["placeholder", "aria-label", "title", "alt", "content"];
  function preloz(koren) {
    if (!koren || !koren.querySelectorAll) return;
    var vyber = "[data-t]," + ATRIBUTY_T.map(function (a) { return "[data-t-" + a + "]"; }).join(",");
    var prvky = Array.prototype.slice.call(koren.querySelectorAll(vyber));
    if (koren.matches && koren.matches(vyber)) prvky.unshift(koren);
    prvky.forEach(function (el) {
      var klic = el.getAttribute("data-t");
      if (klic && hledej(jazyk, klic) != null) vlozText(el, tr(klic));
      ATRIBUTY_T.forEach(function (a) {
        var k = el.getAttribute("data-t-" + a);
        if (k && hledej(jazyk, k) != null) el.setAttribute(a, tr(k));
      });
    });
  }

  function nastavJazyk(j) {
    ulozVolbu("jazyk", j);
    try {
      var url = new URL(location.href);
      url.searchParams.delete("jazyk");
      location.replace(url.toString());
    } catch (e) { location.reload(); }
  }

  /* Language names in their own language: someone who cannot read the
   * current one must still find theirs. */
  var NAZVY_JAZYKU = { cs: "Čeština", en: "English" };
  // The language is the device's; changing it by hand is one settings row
  // ("Jazyk · Čeština ▾"), the way phone apps do it. Until 12. 11. 2026 it
  // was a pair of big buttons in every footer and in the account, and the
  // owner said no app looks like that. A slot left in a footer by an older
  // product draws nothing — the account keeps the row.
  function prepinacJazyka(slot) {
    var mozne = produktJazyky.filter(function (j) { return TEXTY_SABLONY[j]; });
    if (mozne.indexOf("cs") < 0) mozne.unshift("cs");
    if (mozne.length < 2 || slot.querySelector(".sg-jazyk")) return;
    if (slot.closest && slot.closest("footer, .paticka")) return;
    var radek = prvek("label", "sg-jazyk");
    radek.appendChild(prvek("span", "sg-jazyk-popisek", tr("sg.jazyk")));
    var volba = prvek("select", "sg-jazyk-volba");
    mozne.forEach(function (j) {
      var o = prvek("option", "", NAZVY_JAZYKU[j] || j);
      o.value = j;
      o.setAttribute("lang", j);
      if (j === jazyk) o.selected = true;
      volba.appendChild(o);
    });
    volba.addEventListener("change", function () { if (volba.value !== jazyk) nastavJazyk(volba.value); });
    radek.appendChild(volba);
    slot.appendChild(radek);
  }

  /* Price list and currency. One request each, both kept for the page:
   *   SimteGen.cenik() → Promise {mena, meny, polozky, zkusebni_dni} | null
   *   SimteGen.mena()  → the currency now ("CZK" until the list arrives)
   *   SimteGen.nastavMenu("EUR") → remembered, prices redrawn, event sg-mena
   * Marked elements are filled by this script:
   *   <span data-cena="mesic"></span> <span data-cena-jednotka="mesic"></span>
   *   <div data-prepinac-meny></div>
   * A product drawing prices itself listens for the sg-mena event. */
  var cenikSlib = null;
  var menaTed = "CZK";
  // The visitor's country (Cloudflare, /api/prostredi), asked once a page:
  // the currency and the invoice order both need it.
  var zemeSlib = null;
  function nactiZemi() {
    if (!zemeSlib) {
      zemeSlib = fetch("/api/prostredi", { cache: "no-store", credentials: "omit" })
        .then(function (r) { return r.ok ? r.json() : {}; })
        .catch(function () { return {}; });
    }
    return zemeSlib;
  }

  /* The invoice order is for customers in Czechia only, for now (the
   * middleware refuses the rest — see objednavkaMimoCesko there for why).
   * Abroad the form goes away before anyone fills it in, and a line says
   * where to subscribe instead: the Android app, when the product has one. */
  function objednavkaJenCesko() {
    var formulare = doc.querySelectorAll("[data-objednavka]");
    if (!formulare.length) return;
    nactiZemi().then(function (p) {
      var zeme = p && p.zeme;
      if (!zeme || zeme === "CZ") return;
      var html = doc.documentElement;
      html.classList.add("sg-mimo-cesko");
      var klic = html.hasAttribute("data-aplikace") ? "sg.objednavka.mimo_play" : "sg.objednavka.mimo";
      Array.prototype.forEach.call(formulare, function (f) {
        if (f.nextElementSibling && f.nextElementSibling.classList.contains("sg-objednavka-mimo")) return;
        var veta = prvek("p", "popisek sg-objednavka-mimo", tr(klic));
        if (f.parentNode) f.parentNode.insertBefore(veta, f.nextSibling);
      });
    });
  }
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", objednavkaJenCesko);
  else objednavkaJenCesko();

  function cenik() {
    if (cenikSlib) return cenikSlib;
    var bezCache = { cache: "no-store", credentials: "omit" };
    var seznam = fetch("cenik.json", bezCache).then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
    var zeme = nactiZemi();
    cenikSlib = Promise.all([seznam, zeme]).then(function (v) {
      var c = v[0];
      if (!c || !Array.isArray(c.polozky)) return null;
      c.meny = (c.meny || ["CZK"]).filter(function (m) { return MENY.indexOf(m) >= 0; });
      menaTed = vyberMenu(c.meny, (v[1] && v[1].zeme) || null, nactiVolbu().mena, jazyk);
      c.mena = menaTed;
      return c;
    });
    return cenikSlib;
  }

  function jednotka(polozka) {
    var j = polozka && polozka.jednotka;
    if (!j || typeof j === "string") return j || "";
    return j[jazyk] || j.cs || "";
  }

  function vykresliCeny(c) {
    if (!c) return;
    c.mena = menaTed;
    var podle = {};
    c.polozky.forEach(function (p) { podle[p.id] = p; });
    Array.prototype.forEach.call(doc.querySelectorAll("[data-cena]"), function (el) {
      var p = podle[el.getAttribute("data-cena")];
      // A currency the list lacks for this item: Czech crowns, which the
      // owner approved for every item — never a converted guess.
      var ceny = (p && p.ceny) || {};
      var mena = ceny[menaTed] != null ? menaTed : "CZK";
      if (p && ceny[mena] != null) el.textContent = cena(ceny[mena], mena);
    });
    Array.prototype.forEach.call(doc.querySelectorAll("[data-cena-jednotka]"), function (el) {
      var p = podle[el.getAttribute("data-cena-jednotka")];
      if (p) el.textContent = jednotka(p);
    });
    // No currency buttons any more (12. 11. 2026): the currency follows the
    // country, and in the app from Google Play Google shows its own price.
    // A [data-prepinac-meny] slot an older page still has stays empty.
  }

  function nastavMenu(m) {
    if (MENY.indexOf(m) < 0) return;
    ulozVolbu("mena", m);
    menaTed = m;
    cenik().then(function (c) {
      vykresliCeny(c);
      try { doc.dispatchEvent(new CustomEvent("sg-mena", { detail: { mena: m } })); } catch (e) { /* old engine */ }
    });
  }

  doc.addEventListener("DOMContentLoaded", function () {
    preloz(doc.body);
    preloz(doc.head);
    Array.prototype.forEach.call(doc.querySelectorAll("[data-prepinac-jazyka]"), prepinacJazyka);
    if (window.MutationObserver) {
      // What the product draws later (a list row, a <template> clone) is
      // translated as it arrives — the builder marks it once, in Czech.
      new MutationObserver(function (zmeny) {
        zmeny.forEach(function (z) {
          Array.prototype.forEach.call(z.addedNodes, function (u) {
            if (u.nodeType !== 1) return;
            preloz(u);
            if (u.matches && u.matches("[data-prepinac-jazyka]")) prepinacJazyka(u);
          });
        });
      }).observe(doc.body, { childList: true, subtree: true });
    }
    if (doc.querySelector("[data-cena], [data-cena-jednotka], [data-prepinac-meny]")) cenik().then(vykresliCeny);
  });

  /* ── Logo „Díl“ a jeho animace ─────────────────────────────────────
   * Mřížka 5 × 5 modulů po 10: blok 4 × 4 s vykousnutým čtvrtkruhem
   * (střed 40,10, poloměr 10) a kulatý díl v barvě produktu (42,8; r 8).
   * Animace (1,75 s): moduly přiletí šikmo a zacvaknou do bloku, rohový
   * dílek se zbarví a vyjede ven, od výkusu se rozběhnou vlny, probleskne
   * mřížka spár, naběhne „simtegen“. Poslední políčko je statická značka.
   * Každé políčko se počítá z času, takže běží stejně v každém prohlížeči.
   */
  var NS = "http://www.w3.org/2000/svg";
  var BLOK = "M0 10H30A10 10 0 0 0 40 20V50H0Z";
  var ANIMACE_DELKA = 1.75;
  var SKLADANI = 0.6;

  function svgPrvek(tag, atributy, rodic) {
    var el = doc.createElementNS(NS, tag);
    for (var k in atributy) el.setAttribute(k, atributy[k]);
    if (rodic) rodic.appendChild(el);
    return el;
  }

  function znackaSvg() {
    var svg = svgPrvek("svg", { viewBox: "0 0 50 50", "class": "sg-start-znacka", "aria-hidden": "true" });
    var defs = svgPrvek("defs", {}, svg);
    var klipDil = svgPrvek("clipPath", { id: "sg-klip-dil" }, defs);
    var klipRect = svgPrvek("rect", { x: 0, y: 10, width: 40, height: 40 }, klipDil);
    var klipBlok = svgPrvek("clipPath", { id: "sg-klip-blok" }, defs);
    svgPrvek("path", { d: BLOK }, klipBlok);
    var blok = svgPrvek("path", { d: BLOK }, svg);
    var detail = svgPrvek("g", { "clip-path": "url(#sg-klip-blok)", fill: "none" }, svg);
    var spary = svgPrvek("path", { d: "M10 10V50M20 10V50M30 20V50M0 20H40M0 30H40M0 40H40", "stroke-width": 0.45 }, detail);
    var oblouky = svgPrvek("g", { "stroke-width": 0.7 }, detail);
    [[14, 0.32], [18.5, 0.18], [23, 0.08]].forEach(function (o) {
      svgPrvek("circle", { cx: 40, cy: 10, r: o[0], "stroke-opacity": o[1] }, oblouky);
    });
    var vlnyG = svgPrvek("g", { fill: "none", "stroke-width": 0.9 }, svg);
    var vlny = [0, 1, 2].map(function () { return svgPrvek("circle", { cx: 40, cy: 10, r: 10 }, vlnyG); });
    var dil = svgPrvek("circle", { cx: 40, cy: 10, r: 10, "clip-path": "url(#sg-klip-dil)" }, svg);
    var modulyG = svgPrvek("g", {}, svg);
    var moduly = [];
    for (var r = 0; r < 4; r++) for (var c = 0; c < 4; c++) {
      moduly.push({ el: svgPrvek("rect", {}, modulyG), cx: 5 + 10 * c, cy: 15 + 10 * r, poradi: (3 - r) + c });
    }
    return { svg: svg, klip: klipRect, blok: blok, spary: spary, oblouky: oblouky, vlny: vlny,
             dil: dil, modulyG: modulyG, moduly: moduly };
  }

  function omez(x) { return Math.max(0, Math.min(1, x)); }
  function usek(t, a, b) { return omez((t - a) / (b - a)); }
  function ven(x) { return 1 - Math.pow(1 - x, 3); }
  function odraz(x) { return 1 + 2.9 * Math.pow(x - 1, 3) + 1.9 * Math.pow(x - 1, 2); }
  function barva(jmeno, zaloha) {
    return (getComputedStyle(doc.documentElement).getPropertyValue(jmeno) || "").trim() || zaloha;
  }
  // Tokens are #rrggbb (the design check enforces it); anything else just
  // switches half-way instead of blending.
  function smichej(a, b, t) {
    var hex = /^#[0-9a-f]{6}$/i;
    if (!hex.test(a) || !hex.test(b)) return t < 0.5 ? a : b;
    var vysledek = "#";
    for (var i = 1; i < 7; i += 2) {
      var x = parseInt(a.slice(i, i + 2), 16), y = parseInt(b.slice(i, i + 2), 16);
      vysledek += ("0" + Math.round(x + (y - x) * t).toString(16)).slice(-2);
    }
    return vysledek;
  }

  function snimek(z, pismena, t) {
    var ink = barva("--barva-inkoust", "#141414");
    var papir = barva("--barva-papir", "#f6f4ef");
    var akcent = barva("--barva-produktu", ink);
    var slozeno = t >= SKLADANI;
    z.modulyG.setAttribute("display", slozeno ? "none" : "inline");
    z.blok.setAttribute("display", slozeno ? "inline" : "none");
    z.dil.setAttribute("display", slozeno ? "inline" : "none");
    var zacvak = ven(usek(t, 0.46, SKLADANI));
    z.moduly.forEach(function (m) {
      var u = usek(t, 0.05 * m.poradi, 0.05 * m.poradi + 0.2);
      var strana = Math.max(0, (8.6 + 1.6 * zacvak) * (u > 0 ? odraz(u) : 0));
      var prilet = (1 - ven(u)) * 6;
      m.el.setAttribute("x", (m.cx - strana / 2 - prilet).toFixed(3));
      m.el.setAttribute("y", (m.cy - strana / 2 + prilet).toFixed(3));
      m.el.setAttribute("width", strana.toFixed(3));
      m.el.setAttribute("height", strana.toFixed(3));
      m.el.setAttribute("fill", ink);
      m.el.setAttribute("opacity", ven(u).toFixed(3));
    });
    z.blok.setAttribute("fill", ink);
    // The corner takes the product colour, then the piece comes out.
    z.dil.setAttribute("fill", smichej(ink, akcent, usek(t, 0.6, 0.75)));
    var otevreni = ven(usek(t, 0.75, 0.86));
    z.klip.setAttribute("x", (0 - 14 * otevreni).toFixed(2));
    z.klip.setAttribute("y", (10 - 24 * otevreni).toFixed(2));
    z.klip.setAttribute("width", (40 + 38 * otevreni).toFixed(2));
    z.klip.setAttribute("height", (40 + 38 * otevreni).toFixed(2));
    var pohyb = usek(t, 0.75, 1.15);
    var m = odraz(pohyb);
    z.dil.setAttribute("cx", (40 + 2 * m).toFixed(3));
    z.dil.setAttribute("cy", (10 - 2 * m).toFixed(3));
    z.dil.setAttribute("r", (10 - 2 * ven(pohyb)).toFixed(3));
    z.vlny.forEach(function (v, i) {
      var u = usek(t, 0.85 + 0.09 * i, 1.45 + 0.09 * i);
      v.setAttribute("r", (10 + (18 + 7 * i) * ven(u)).toFixed(2));
      v.setAttribute("stroke", akcent);
      v.setAttribute("stroke-opacity", (u > 0 && u < 1 ? 0.6 * (1 - u) : 0).toFixed(3));
    });
    z.spary.setAttribute("stroke", papir);
    z.spary.setAttribute("stroke-opacity",
      (0.16 * ven(usek(t, 1.1, 1.5)) + 0.32 * Math.sin(Math.PI * usek(t, 0.9, 1.3))).toFixed(3));
    z.oblouky.setAttribute("stroke", papir);
    z.oblouky.setAttribute("opacity", ven(usek(t, 1.15, 1.55)).toFixed(3));
    pismena.forEach(function (p, i) {
      var u = ven(usek(t, 1.15 + 0.035 * i, 1.45 + 0.035 * i));
      p.style.opacity = u.toFixed(3);
      p.style.transform = "translateX(" + ((1 - u) * -10).toFixed(2) + "px)";
    });
  }

  function prehraj(z, pismena) {
    var zacatekAnimace = null;
    snimek(z, pismena, 0);
    function krok(cas) {
      if (zacatekAnimace === null) zacatekAnimace = cas;
      var t = (cas - zacatekAnimace) / 1000;
      snimek(z, pismena, Math.min(t, ANIMACE_DELKA));
      if (t < ANIMACE_DELKA) requestAnimationFrame(krok);
    }
    requestAnimationFrame(krok);
  }

  var nazev = meta("application-name") || doc.title || "";
  var verze = meta("simtegen-verze");

  var start = prvek("div", "sg-start");
  start.setAttribute("role", "status");
  start.setAttribute("aria-label", tr("sg.nacitam_nazev", { nazev: nazev }));

  start.appendChild(prvek("div", "sg-start-horni", nazev));

  var stred = prvek("div", "sg-start-stred");
  var znacka = znackaSvg();
  stred.appendChild(znacka.svg);
  var slovo = prvek("span", "znacka-slovo");
  slovo.setAttribute("aria-hidden", "true");
  var pismena = "SimteGen".split("").map(function (p) {
    var s = prvek("span", "", p);
    slovo.appendChild(s);
    return s;
  });
  stred.appendChild(slovo);
  var pravitko = prvek("div", "sg-start-pravitko");
  pravitko.appendChild(prvek("span"));
  pravitko.appendChild(prvek("i"));
  stred.appendChild(pravitko);
  start.appendChild(stred);

  var dolni = prvek("div", "sg-start-dolni");
  dolni.appendChild(prvek("span", "", tr("sg.nacitam")));
  dolni.appendChild(prvek("span", "", verze ? "V " + verze : ""));
  start.appendChild(dolni);

  doc.body.insertBefore(start, doc.body.firstChild);

  // The full animation only when someone comes in from outside (the app
  // launched, a link from an e-mail); moving between pages of the same
  // product, a reload or going back shows the finished mark — a craftsman
  // opening screens all day must not wait 1.8 s each time. Decided from
  // what the browser already knows (referrer, navigation type), so nothing
  // is stored: browser storage would have to be declared in every
  // product's privacy policy. Reduced motion: always the finished mark.
  var animovat = !(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  try {
    var navigace = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
    if (navigace && (navigace.type === "reload" || navigace.type === "back_forward")) animovat = false;
    if (doc.referrer && new URL(doc.referrer).origin === location.origin) animovat = false;
  } catch (e) { /* an odd referrer: animate, it is only the logo */ }
  var minimum = animovat ? Math.round(ANIMACE_DELKA * 1000) + 150 : 700;
  if (animovat) prehraj(znacka, pismena);
  else snimek(znacka, pismena, ANIMACE_DELKA);

  var zacatek = Date.now();
  var hotovo = false;
  function skryj() {
    if (hotovo) return;
    hotovo = true;
    var zbyva = Math.max(0, minimum - (Date.now() - zacatek));
    setTimeout(function () {
      start.classList.add("sg-start--pryc");
      setTimeout(function () { if (start.parentNode) start.parentNode.removeChild(start); }, 400);
    }, zbyva);
  }
  if (doc.readyState === "complete") skryj();
  else window.addEventListener("load", skryj);
  setTimeout(skryj, 2500);

  /* ── Nahlásit chybu ────────────────────────────────────────────────
   * Každé tlačítko .nahlasit-chybu v appce otevře tenhle formulář — skript
   * ho řídí sám (zachytí klik dřív než kód produktu), aby hlášení fungovalo
   * v každé appce stejně a nezáviselo na staviteli. Přihlášený zákazník jde
   * na /api/hlaseni (uloží se a dostane odpověď v aplikaci); bez přihlášení
   * nebo na statické stránce na /api/nahlasit. Text firma dostane šifrovaně.
   * Přikládá se jen technika: verze, obrazovka, velikost okna, prohlížeč
   * a posledních pět chyb skriptu na stránce — nic o člověku, nic se
   * neukládá do prohlížeče.
   */
  var chyby = [];
  function zapisChybu(text) {
    chyby.push(String(text).slice(0, 200));
    if (chyby.length > 5) chyby.shift();
  }
  window.addEventListener("error", function (e) {
    zapisChybu((e.message || "chyba") + (e.filename ? " @ " + e.filename.split("/").pop() + ":" + e.lineno : ""));
    var nase = e.filename && e.filename.indexOf(location.origin + "/") === 0;
    pocitejChybu(nase ? e.filename.split("/").pop().split("?")[0] + ":" + e.lineno : "jine");
  });
  window.addEventListener("unhandledrejection", function (e) {
    zapisChybu("promise: " + (e.reason && e.reason.message ? e.reason.message : e.reason));
    pocitejChybu("jine");
  });

  /* Počítadlo chyb (P9, „data místo stížností“): kolik chyb skriptu
   * zákazníci potkávají, i když nic nenahlásí. Anonymně — jen obrazovka
   * a místo v našem kódu (soubor:řádek), nikdy text chyby (může v něm být,
   * co zákazník napsal); každé místo jednou za načtení, nejvýš pět. Server
   * si to sečte (functions/api/chyba-stranky.js, tabulka chyby_stranek).
   * Statická stránka endpoint nemá: po první odpovědi 404 počítadlo mlčí. */
  var pocitano = {}, pocitanoKolik = 0, pocitadloVypnuto = false;
  function pocitejChybu(misto) {
    if (pocitadloVypnuto || pocitanoKolik >= 5 || pocitano[misto] || !/^https?:$/.test(location.protocol)) return;
    pocitano[misto] = true;
    pocitanoKolik++;
    var aktivni = doc.querySelector(".obrazovka.aktivni");
    var obrazovka = ((aktivni && aktivni.id) || location.pathname.split("/").pop().replace(/\.html$/, "") || "index")
      .toLowerCase().replace(/^obrazovka-/, "");
    try {
      fetch("/api/chyba-stranky", {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "omit", keepalive: true,
        body: JSON.stringify({ obrazovka: obrazovka, misto: misto }),
      }).then(function (r) {
        if (r.status === 404 || r.status === 405) pocitadloVypnuto = true;
      }, function () {});
    } catch (chyba) { /* počítadlo nesmí nic rozbít */ }
  }

  function kontext() {
    var aktivni = doc.querySelector(".obrazovka.aktivni") ||
      Array.prototype.filter.call(doc.querySelectorAll(".obrazovka"), function (o) { return !o.hidden; })[0];
    return {
      verze: verze,
      obrazovka: aktivni && aktivni.id ? aktivni.id : location.pathname,
      okno: window.innerWidth + "×" + window.innerHeight,
      prohlizec: navigator.userAgent.slice(0, 200),
      chyby: chyby.slice(),
    };
  }

  var panel = null;
  var pozadi = null;
  var posledniFokus = null;

  function zavri() {
    if (!panel) return;
    panel.hidden = true;
    pozadi.hidden = true;
    if (posledniFokus && posledniFokus.focus) posledniFokus.focus();
  }

  function postav() {
    pozadi = prvek("div", "panel-pozadi");
    pozadi.addEventListener("click", zavri);
    panel = prvek("div", "panel sg-hlaseni");
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-labelledby", "sg-hlaseni-nadpis");

    var nadpis = prvek("h2", "", tr("sg.hlaseni.nadpis"));
    nadpis.id = "sg-hlaseni-nadpis";
    panel.appendChild(prvek("p", "stitek", nazev ? tr("sg.hlaseni.pro", { nazev: nazev }) : tr("sg.hlaseni.pro_nas")));
    panel.appendChild(nadpis);
    panel.appendChild(prvek("p", "", tr("sg.hlaseni.uvod")));

    var pole = prvek("div", "pole");
    var popisek = prvek("label", "", tr("sg.hlaseni.popisek"));
    popisek.setAttribute("for", "sg-hlaseni-text");
    var text = doc.createElement("textarea");
    text.id = "sg-hlaseni-text";
    text.rows = 5;
    text.maxLength = 2000;
    pole.appendChild(popisek);
    pole.appendChild(text);
    panel.appendChild(pole);

    var hlaska = prvek("p", "hlaska");
    hlaska.setAttribute("role", "status");
    hlaska.hidden = true;
    panel.appendChild(hlaska);

    var akce = prvek("div", "dva-sloupce sg-hlaseni-akce");
    var odeslat = prvek("button", "tlacitko", tr("sg.hlaseni.odeslat"));
    odeslat.type = "button";
    var zrusit = prvek("button", "tlacitko tiche", tr("sg.zavrit"));
    zrusit.type = "button";
    zrusit.addEventListener("click", zavri);
    akce.appendChild(odeslat);
    akce.appendChild(zrusit);
    panel.appendChild(akce);

    function ukazHlasku(trida, zprava) {
      hlaska.className = "hlaska " + trida;
      hlaska.textContent = zprava;
      hlaska.hidden = false;
    }

    function posli(cesta, data) {
      return fetch(cesta, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
        credentials: "same-origin",
      });
    }

    odeslat.addEventListener("click", function () {
      var obsah = text.value.trim();
      if (obsah.length < 3) {
        ukazHlasku("chyba", tr("sg.hlaseni.prazdne"));
        text.focus();
        return;
      }
      odeslat.disabled = true;
      var data = { text: obsah, kontext: kontext() };
      posli("/api/hlaseni", data).then(function (r) {
        // Not signed in, or a page without accounts: the anonymous door.
        return (r.status === 401 || r.status === 404 || r.status === 405) ? posli("/api/nahlasit", data) : r;
      }).then(function (r) {
        if (r.ok) {
          text.value = "";
          ukazHlasku("uspech", tr("sg.hlaseni.prijato"));
        } else if (r.status === 429) {
          ukazHlasku("chyba", tr("sg.hlaseni.limit"));
        } else {
          ukazHlasku("chyba", tr("sg.hlaseni.chyba"));
        }
      }).catch(function () {
        ukazHlasku("chyba", tr("sg.hlaseni.offline"));
      }).then(function () { odeslat.disabled = false; });
    });

    // Tab stays in the form, Escape closes it — it is a dialog over the page.
    drzFokus(panel, zavri);
    doc.body.appendChild(pozadi);
    doc.body.appendChild(panel);
  }

  function otevri() {
    posledniFokus = doc.activeElement;
    if (!panel) postav();
    var hlaska = panel.querySelector(".hlaska");
    if (hlaska) hlaska.hidden = true;
    pozadi.hidden = false;
    panel.hidden = false;
    doc.getElementById("sg-hlaseni-text").focus();
  }

  // Capture phase: runs before any handler the product attached to the same
  // button, and stops it — one behaviour in every app.
  doc.addEventListener("click", function (e) {
    var cil = e.target && e.target.closest ? e.target.closest(".nahlasit-chybu") : null;
    if (!cil) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    otevri();
  }, true);

  /* ── Zkušební období a ukázková data ───────────────────────────────
   * Pruh nad obsahem: kolik zbývá ze zkušebního období, v posledních
   * 7 dnech a po vypršení výrazněji a s tlačítkem „Předplatit“, které
   * otevře platbu tak, jak ji produkt má — v prohlížeči fakturační
   * objednávku, v aplikaci z Google Play nákup přes Google Play (styl.css
   * a play.js tam objednávku schovávají; tady se jen vybere první viditelný
   * cíl, takže pravidla Google Play platí i pro pruh). Odkaz z upomínky
   * (?platba) otevře totéž po načtení.
   *
   * Ukázková data: tlačítko [data-ukazkova-data] v prázdném stavu produktu
   * nahraje do vlastního účtu vymyšlená data (functions/api/ukazka-uctu.js)
   * a pruh je pak jedním klepnutím odstraní. Tlačítko je vidět jen tam, kde
   * to jde (třída sg-ukazkova-nabidka na <html>, podle hlavičky z /api/ja).
   *
   * Proč tady: tenhle soubor se obnovuje v každém produktu, takže to dojde
   * i do produktů, které vznikly dřív. Produkt, který má vlastní pruh
   * (#pruh-predplatne), nedostane druhý. Nic se neukládá v prohlížeči.
   */
  var koren = doc.documentElement;
  var UKAZKOVY_UCET = /@ukazka\.invalid$/;
  var HACKY_PLATBY = "[data-predplatne-play], [data-objednavka], #predplatne-karta, [data-pruh-predplatneho], " +
    "[data-ukazkova-data], [data-platba]";

  function dny(n) {
    return pocet(n, "sg.dny");
  }

  function datumKratce(unix) {
    if (jazyk !== "cs") return datum(unix);
    var d = new Date(unix * 1000);
    return d.getDate() + ". " + (d.getMonth() + 1) + ".";
  }

  // Hidden by the product or by the Google Play rule — but an inactive
  // screen does not count: ukaz() opens it.
  function viditelny(el) {
    for (var e = el; e && e !== doc.body; e = e.parentElement) {
      if (e.classList && e.classList.contains("obrazovka")) return true;
      if (e.hidden || getComputedStyle(e).display === "none") return false;
    }
    return true;
  }

  function otevriPlatbu() {
    // A product's own way in wins: [data-platba], or the bar it drew itself.
    var vlastni = doc.querySelector("[data-platba]") || doc.getElementById("pruh-predplatne");
    if (vlastni && viditelny(vlastni) && /^(A|BUTTON)$/.test(vlastni.tagName)) {
      vlastni.click();
      return;
    }
    var cil = null;
    var vyber = ["[data-objednavka]", "[data-predplatne-play]", "#predplatne-karta"];
    for (var i = 0; i < vyber.length && !cil; i++) {
      cil = Array.prototype.filter.call(doc.querySelectorAll(vyber[i]), viditelny)[0] || null;
    }
    if (!cil) return;
    var obrazovka = cil.closest(".obrazovka");
    if (obrazovka && !obrazovka.classList.contains("aktivni") && typeof window.ukaz === "function") {
      try { window.ukaz(obrazovka.id); } catch (e) { /* the product's router: best effort */ }
    }
    setTimeout(function () {
      var karta = cil.closest(".karta") || cil;
      karta.style.scrollMarginTop = "6rem";  // clear of the sticky header
      // A jump, not a glide: a smooth scroll is cancelled by any layout the
      // product still does, and needs no reduced-motion exception.
      karta.scrollIntoView({ block: "start" });
      if (!karta.hasAttribute("tabindex")) karta.setAttribute("tabindex", "-1");
      try { karta.focus({ preventScroll: true }); } catch (e) { karta.focus(); }
    }, 80);
  }

  var pruhy = null;
  function vlozPruh(pruh) {
    if (!pruhy) {
      pruhy = prvek("div", "sg-pruhy");
      var slot = doc.querySelector("[data-pruh-predplatneho]");
      var obsah = doc.querySelector(".obsah") || doc.querySelector("main");
      if (slot) slot.appendChild(pruhy);
      else if (obsah) obsah.insertBefore(pruhy, obsah.firstChild);
      else {
        // Nothing to sit in: the very top, clear of the notch.
        pruhy.classList.add("sg-pruhy--nahore");
        doc.body.insertBefore(pruhy, doc.body.firstChild);
      }
    }
    pruhy.appendChild(pruh);
  }

  function pruh(trida, text, akce, priKliku) {
    var p = prvek("div", "sg-pruh" + (trida ? " sg-pruh--" + trida : ""));
    p.setAttribute("role", "status");
    p.appendChild(prvek("p", "sg-pruh-text", text));
    var t = prvek("button", "tlacitko vedlejsi", akce);
    t.type = "button";
    t.addEventListener("click", function () { priKliku(t); });
    p.appendChild(t);
    return p;
  }

  // The bar for one subscription state, or null. Pure on purpose (state and
  // clock in, text out): tests/test_konverze.py runs it in Node.
  function obsahPruhu(p, nyni) {
    if (!p || p.platce === false) return null;
    if (p.stav === "vyprselo") {
      return { trida: "konec", akce: tr("sg.predplatit"), text: tr("sg.pruh.vyprselo") };
    }
    if (p.stav !== "zkusebni") return null;
    var konec = Number(p.zkusebni_do || p.plati_do) || 0;
    var zbyva = Number(p.dni_zbyva) || 0;
    if (zbyva > 7) {
      return { trida: "", akce: tr("sg.predplatne"),
               text: tr("sg.pruh.zbyva", { pocet: dny(zbyva),
                                           "do": konec ? tr("sg.pruh.do", { datum: datumKratce(konec) }) : "" }) };
    }
    var kdy;
    if (konec) {
      // Calendar days, not 24-hour blocks: "zítra" must mean tomorrow.
      var dnes = new Date(nyni);
      dnes.setHours(0, 0, 0, 0);
      var den = new Date(konec * 1000);
      den.setHours(0, 0, 0, 0);
      var rozdil = Math.round((den - dnes) / 86400000);
      kdy = rozdil <= 0 ? tr("sg.dnes") : rozdil === 1 ? tr("sg.zitra")
        : tr("sg.za_datum", { pocet: dny(rozdil), datum: datumKratce(konec) });
    } else {
      kdy = tr("sg.za", { pocet: dny(zbyva) });
    }
    return { trida: "brzy", akce: tr("sg.predplatit"), text: tr("sg.pruh.konci", { kdy: kdy }) };
  }

  function dosad(hodnota, ulozene) {
    if (typeof hodnota === "string") {
      return hodnota.replace(/\{(\w+)\}/g, function (cele, jmeno) {
        return Object.prototype.hasOwnProperty.call(ulozene, jmeno) ? String(ulozene[jmeno]) : cele;
      });
    }
    if (Array.isArray(hodnota)) return hodnota.map(function (h) { return dosad(h, ulozene); });
    if (hodnota && typeof hodnota === "object") {
      var vysledek = {};
      Object.keys(hodnota).forEach(function (k) { vysledek[k] = dosad(hodnota[k], ulozene); });
      return vysledek;
    }
    return hodnota;
  }

  function vyberHodnotu(data, cesta) {
    return String(cesta).split(".").reduce(function (d, klic) {
      if (d === null || d === undefined) return undefined;
      return d[/^\d+$/.test(klic) ? Number(klic) : klic];
    }, data);
  }

  function apiJson(cesta, metoda, telo) {
    var nastaveni = { method: metoda, credentials: "same-origin", headers: {} };
    if (telo !== undefined) {
      nastaveni.headers["Content-Type"] = "application/json";
      nastaveni.body = JSON.stringify(telo);
    }
    return fetch(cesta, nastaveni).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        return { ok: r.ok, status: r.status, data: data, hlavicky: r.headers };
      });
    });
  }

  // The same replay as play.js (the demo account) and uat_kontrola.py.
  // Duplicated, not shared: play.js reaches a product only with a build,
  // this file also with the template refresh — a shared helper would leave
  // one of them calling something that is not there yet.
  function prehrajKroky(kroky) {
    var ulozene = {};
    return kroky.reduce(function (cesta, krok) {
      return cesta.then(function () {
        var casti = String(krok.pozadavek || "").split(" ");
        return apiJson(dosad(casti.slice(1).join(" "), ulozene), casti[0], dosad(krok.telo, ulozene))
          .then(function (r) {
            Object.keys(krok.uloz || {}).forEach(function (jmeno) {
              var hodnota = vyberHodnotu(r.data, krok.uloz[jmeno]);
              if (hodnota !== undefined) ulozene[jmeno] = hodnota;
            });
          });
      });
    }, Promise.resolve());
  }

  function nahrajUkazku(tlacitko) {
    var puvodni = tlacitko.textContent;
    tlacitko.disabled = true;
    tlacitko.textContent = tr("sg.ukazka.pripravuji");
    apiJson("/api/ukazka-uctu", "POST", { akce: "nahrat" }).then(function (r) {
      if (!r.ok) throw new Error(chyba(r.data, tr("sg.ukazka.nejde")));
      // The range is closed whatever the steps did: removal must work even
      // after a step that failed.
      return prehrajKroky(r.data.kroky || []).catch(function () { return null; }).then(function () {
        return apiJson("/api/ukazka-uctu", "POST", { akce: "hotovo" });
      });
    }).then(function () {
      location.reload();
    }).catch(function (e) {
      tlacitko.disabled = false;
      tlacitko.textContent = puvodni;
      var zprava = prvek("p", "zprava chyba", e.message || tr("sg.ukazka.nejde"));
      zprava.setAttribute("role", "status");
      if (tlacitko.parentNode) tlacitko.parentNode.insertBefore(zprava, tlacitko.nextSibling);
    });
  }

  function pruhUkazkovychDat() {
    return pruh("ukazka", tr("sg.ukazka.pruh"), tr("sg.ukazka.odstranit"), function (t) {
      t.disabled = true;
      t.textContent = tr("sg.ukazka.odstranuji");
      apiJson("/api/ukazka-uctu", "POST", { akce: "odstranit" }).then(function (r) {
        if (!r.ok) throw new Error(r.data.chyba);
        location.reload();
      }).catch(function () {
        t.disabled = false;
        t.textContent = tr("sg.znovu_nepovedlo");
      });
    });
  }

  // Wait until the product has drawn its first real screen (and, in an app
  // product, until play.js has said web or app) — opening the payment
  // before that would be overwritten by the product's own start.
  function azBudeAplikace(fn) {
    var zacatekCekani = Date.now();
    (function zkus() {
      var aktivni = doc.querySelector(".obrazovka.aktivni");
      var hotova = !doc.querySelector(".obrazovka") || (aktivni && !/nacitani/.test(aktivni.id));
      var playRozhodl = !koren.hasAttribute("data-aplikace") ||
        koren.classList.contains("sg-web") || koren.classList.contains("sg-v-aplikaci");
      if ((hotova && playRozhodl) || Date.now() - zacatekCekani > 6000) { fn(); return; }
      setTimeout(zkus, 120);
    })();
  }

  function bezParametru(jmeno) {
    try {
      var url = new URL(location.href);
      url.searchParams.delete(jmeno);
      history.replaceState(history.state, "", url.pathname + url.search + url.hash);
    } catch (e) { /* the link still works, it only stays in the address */ }
  }

  doc.addEventListener("click", function (e) {
    var cil = e.target && e.target.closest ? e.target.closest("[data-ukazkova-data]") : null;
    if (!cil || cil.disabled) return;
    e.preventDefault();
    nahrajUkazku(cil);
  });

  /* The wordmark is "SimteGen" (owner, 5. 11. 2026); it used to be all
   * lower case. A live product's index.html is its own code, which a
   * template refresh never touches, so its bar would keep the old word
   * until its next build. This file is refreshed everywhere: it puts the
   * word right on load. The source catches up on the next build. */
  doc.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(doc.querySelectorAll(".znacka-slovo"), function (el) {
      if (el.childElementCount === 0 && el.textContent.trim() === "simtegen") el.textContent = "SimteGen";
    });
  });

  doc.addEventListener("DOMContentLoaded", function () {
    // Only pages of a product with accounts: the hooks above, or a product
    // that draws its empty state from script (the button is in the source).
    var veSkriptu = Array.prototype.some.call(doc.scripts, function (s) {
      return !s.src && s.textContent.indexOf("data-ukazkova-data") >= 0;
    });
    if (!doc.querySelector(HACKY_PLATBY) && !veSkriptu) return;
    var chciPlatbu = /[?&]platba(?:[=&]|$)/.test(location.search);
    apiJson("/api/ja", "GET").then(function (r) {
      var ja = r.data || {};
      if (!r.ok || !ja.prihlasen || UKAZKOVY_UCET.test(ja.email || "")) return;
      // The account remembers the language the customer reads the app in,
      // for the mails sent later (trial end, renewal, answers); corrected
      // only when it differs — the header is absent before migration 0950.
      var jazykUctu = r.hlavicky.get("X-SimteGen-Jazyk-Uctu");
      if (jazykUctu !== null && produktJazyky.length > 1 && jazykUctu !== jazyk) {
        apiJson("/api/jazyk", "POST", { jazyk: jazyk }).catch(function () { /* next visit */ });
      }
      var ukazka = r.hlavicky.get("X-SimteGen-Ukazkova-Data");
      if (ukazka === "nabidka") koren.classList.add("sg-ukazkova-nabidka");
      if (ukazka === "nahrana") vlozPruh(pruhUkazkovychDat());
      var obsah = doc.getElementById("pruh-predplatne") ? null : obsahPruhu(ja.predplatne, Date.now());
      if (obsah) vlozPruh(pruh(obsah.trida, obsah.text, obsah.akce, otevriPlatbu));
      if (chciPlatbu && ja.predplatne && ja.predplatne.platce !== false) {
        bezParametru("platba");
        azBudeAplikace(otevriPlatbu);
      }
    }).catch(function () { /* offline or no accounts: nothing to say */ });
  });

  /* ── Connection: offline is not signed out ──────────────────────────
   * A mechanic in a garage with one bar of signal must not look signed
   * out. Pages used to show the login screen on ANY failed /api/ja, so a
   * signed-in customer asked for a new login link and wondered where the
   * data went. Signed out is only what the server says: 200 with
   * prihlasen:false, or 401/403. Everything else — fetch throws, 5xx, a 404
   * of a broken deploy, a captive portal's HTML instead of JSON — means
   * "we don't know", and "we don't know" keeps the last screen.
   *
   *   SimteGen.kdoJsem()       → Promise {stav: "prihlasen"|"odhlasen"|"offline", ja, status}
   *   SimteGen.offline(znovu)  → bar with "Zkusit znovu"; znovu() also runs on
   *                              the browser's `online` event
   *   SimteGen.spojeno()       → bar gone
   *
   * Here and not only in index.html: this file is refreshed in every
   * product on its next build (stavitel._NAVRH), index.html is the
   * product's own and the template never touches it again. The template's
   * obnov() is the pattern the builder copies.
   */
  function kdoJsem() {
    return apiJson("/api/ja", "GET").then(function (r) {
      var ja = r.data || {};
      if (r.status === 401 || r.status === 403) return { stav: "odhlasen", ja: {}, status: r.status };
      if (r.ok && typeof ja.prihlasen === "boolean") {
        return { stav: ja.prihlasen ? "prihlasen" : "odhlasen", ja: ja, status: r.status };
      }
      return { stav: "offline", ja: {}, status: r.status };
    }, function () {
      return { stav: "offline", ja: {}, status: 0 };
    });
  }

  var offlinePruh = null;
  var offlineZnovu = null;
  function offline(znovu) {
    // Without a callback the safest retry is the whole page: the product's
    // own start runs again.
    offlineZnovu = typeof znovu === "function" ? znovu : function () { location.reload(); };
    if (offlinePruh) {
      // A retry that failed again: the same bar, the button usable again.
      var t = offlinePruh.querySelector("button");
      if (t) { t.disabled = false; t.textContent = tr("sg.offline.znovu"); }
      return;
    }
    offlinePruh = pruh("offline", tr("sg.offline.text"), tr("sg.offline.znovu"), function (t) {
      t.disabled = true;
      t.textContent = tr("sg.offline.zkousim");
      offlineZnovu();
    });
    // An alert, not a status: the page did not change, so nothing else
    // would tell a screen reader why the tap did nothing.
    offlinePruh.setAttribute("role", "alert");
    vlozPruh(offlinePruh);
  }

  function spojeno() {
    if (offlinePruh && offlinePruh.parentNode) offlinePruh.parentNode.removeChild(offlinePruh);
    offlinePruh = null;
  }

  window.addEventListener("online", function () {
    if (offlinePruh && offlineZnovu) offlineZnovu();
  });

  /* ── Tisk a PDF ─────────────────────────────────────────────────────
   * <button class="tlacitko vedlejsi" data-tisk>Vytisknout</button> prints
   * the screen; data-tisk="#kusovnik" only that element (the cut list for
   * the workshop, the drawing for the customer). "Uložit jako PDF" is the
   * same dialog. The look is styl.css's @media print; here only the
   * choice of what, so no product writes its own print code.
   *   SimteGen.tisk("#kusovnik") — the same from a product's script.
   */
  function tisk(selektor) {
    var cil = selektor ? doc.querySelector(selektor) : null;
    if (cil) {
      cil.classList.add("sg-tisk-cil");
      koren.classList.add("sg-tisk-vyber");
    }
    window.print();
  }
  window.addEventListener("afterprint", function () {
    koren.classList.remove("sg-tisk-vyber");
    Array.prototype.forEach.call(doc.querySelectorAll(".sg-tisk-cil"), function (el) {
      el.classList.remove("sg-tisk-cil");
    });
  });
  doc.addEventListener("click", function (e) {
    var tlacitko = e.target && e.target.closest ? e.target.closest("[data-tisk]") : null;
    if (!tlacitko) return;
    e.preventDefault();
    tisk(tlacitko.getAttribute("data-tisk"));
  });

  /* ── Čísla, peníze, data, rozměry ───────────────────────────────────
   * One way to write them in every app. Products wrote their own:
   * toLocaleString here, string concatenation there, "1249 Kč" next to
   * "1 249,00 Kč", ISO dates on a screen. All spaces inside a value are
   * non-breaking, so "1 249 Kč" never ends a line with "Kč" alone.
   *
   *   SimteGen.cislo(12345.5, 1)            → "12 345,5"
   *   SimteGen.kc(1249)                     → "1 249 Kč"   (1249.5 → "1 249,50 Kč")
   *   SimteGen.kc(124950, {halere: true})   → "1 249,50 Kč" (the API stores haléře)
   *   SimteGen.datum(d)                     → "25. 10." this year, else "25. 10. 2025"
   *   SimteGen.datum(d, {rok: true, cas: true}) → "25. 10. 2026 14:05"
   *   SimteGen.datum(d, {dny: true})        → "Dnes" / "Zítra" / "Včera", else as above
   *   SimteGen.rozmer([600, 720, 510], "mm") → "600 × 720 × 510 mm"
   *   SimteGen.pocet(3, ["sada", "sady", "sad"]) → "3 sady"
   *   SimteGen.pocet(3, "sada")             → "3 sady" / "3 sets" (forms from texty.js)
   *   SimteGen.cena("4.90", "EUR")          → "4,90 €" / "€4.90"
   *   SimteGen.cena(549, "USD", {halere: true}) → "5,49 US$" / "US$5.49"
   *
   * In English: 12,345.5 · CZK 1,249 · 25 Oct / 25 Oct 2025 14:05 ·
   * Today / Tomorrow / Yesterday — the same calls, the language decides
   * (Jazyk a měna, at the top). The implementations live up there, in the
   * pure block the Node test runs.
   *
   * Dates take a Date, an ISO string or unix seconds (what D1 returns).
   * The arithmetic stays where it belongs — on the server, in haléře; this
   * only writes a finished number.
   */
  function rozmer(hodnoty, jednotka) {
    var cast = [].concat(hodnoty).map(function (h) { return cislo(h); }).join(NBSP + "×" + NBSP);
    return cast + (jednotka ? NBSP + jednotka : "");
  }

  /* ── Potvrzení, dotaz a „Vrátit“ ────────────────────────────────────
   * Instead of confirm() / prompt() / alert(). Those are the browser's own
   * grey boxes: different on every phone, foreign inside the Google Play
   * app, unstyled, and they freeze the page (the persona harness had to
   * stub them out). Live products had a dozen of them. CI now refuses them
   * in a product's HTML and JS (kontrola_manifestu.py).
   *
   *   SimteGen.potvrd(text, {popis, ano, ne, nebezpecne})  → Promise<boolean>
   *   SimteGen.zeptej(text, {popis, popisek, hodnota, typ, ano, ne}) → Promise<string|null>
   *   SimteGen.vratitelne(text, vratit, {ms})  → toast „… · Vrátit“; vratit() may return a Promise
   *
   * Prefer vratitelne: do the thing at once and offer to take it back for a
   * few seconds — the question "are you sure?" is answered "yes" by reflex
   * and only slows down the 99 % who meant it. potvrd with nebezpecne is
   * for what cannot be taken back (deleting the account); the safe button
   * then has the focus, so Enter never destroys anything.
   */
  /* ── Panel a klávesnice ────────────────────────────────────────────
   * A panel over the page (detail, filter, a form in a sheet) is a dialog:
   * Tab stays inside it — behind it is a page that cannot be used now, and
   * a keyboard user who tabs out is lost behind the backdrop — Escape
   * closes it, and the focus goes back to where it came from. Products used
   * to open their own .panel by toggling hidden, and none of that happened.
   *
   *   const p = SimteGen.panel(document.getElementById("detail"), {priZavreni})
   *   p.zavri()
   *
   * The element is the product's own markup (a .panel with a heading);
   * this only opens it, keeps the keyboard in it and closes it.
   */
  var FOKUSOVATELNE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), ' +
    'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function fokusovatelne(okno) {
    return Array.prototype.filter.call(okno.querySelectorAll(FOKUSOVATELNE), function (el) {
      return el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
    });
  }

  function drzFokus(okno, zavrit) {
    okno.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && zavrit) { e.preventDefault(); zavrit(); return; }
      if (e.key !== "Tab") return;
      var prvky = fokusovatelne(okno);
      if (!prvky.length) { e.preventDefault(); return; }
      var prvni = prvky[0], posledni = prvky[prvky.length - 1];
      var uvnitr = okno.contains(doc.activeElement);
      if (e.shiftKey && (doc.activeElement === prvni || !uvnitr)) { e.preventDefault(); posledni.focus(); }
      else if (!e.shiftKey && (doc.activeElement === posledni || !uvnitr)) { e.preventDefault(); prvni.focus(); }
    });
  }

  function otevriPanel(okno, volby) {
    volby = volby || {};
    if (okno.sgPanel) okno.sgPanel.zavri();
    var predtim = doc.activeElement;
    if (!okno.getAttribute("role")) okno.setAttribute("role", "dialog");
    okno.setAttribute("aria-modal", "true");
    if (!okno.getAttribute("aria-labelledby") && !okno.getAttribute("aria-label")) {
      var nadpis = okno.querySelector("h1, h2, h3");
      if (nadpis) {
        if (!nadpis.id) nadpis.id = "sg-panel-" + (++dialogu);
        okno.setAttribute("aria-labelledby", nadpis.id);
      }
    }
    var bg = null;
    if (volby.pozadi !== false) {
      bg = prvek("div", "panel-pozadi");
      okno.parentNode.insertBefore(bg, okno);
    }
    var otevreno = true;
    function zavri() {
      if (!otevreno) return;
      otevreno = false;
      okno.hidden = true;
      okno.sgPanel = null;
      if (bg && bg.parentNode) bg.parentNode.removeChild(bg);
      if (predtim && predtim.focus && predtim.isConnected) predtim.focus();
      if (volby.priZavreni) volby.priZavreni();
    }
    if (!okno.sgDrzi) { okno.sgDrzi = true; drzFokus(okno, function () { if (okno.sgPanel) okno.sgPanel.zavri(); }); }
    if (bg) bg.addEventListener("click", zavri);
    okno.hidden = false;
    var api = { zavri: zavri };
    okno.sgPanel = api;
    var prvni = okno.querySelector("[autofocus]") || fokusovatelne(okno)[0];
    if (prvni) prvni.focus();
    else { okno.setAttribute("tabindex", "-1"); okno.focus(); }
    return api;
  }

  var otevrenyDialog = null;
  var dialogu = 0;

  function dialog(volby) {
    return new Promise(function (hotovo) {
      if (otevrenyDialog) otevrenyDialog();  // a newer question replaces the open one
      var predtim = doc.activeElement;
      var bg = prvek("div", "panel-pozadi");
      var okno = prvek("div", "panel sg-dialog");
      var id = "sg-dialog-" + (++dialogu);
      okno.setAttribute("role", volby.nebezpecne ? "alertdialog" : "dialog");
      okno.setAttribute("aria-modal", "true");
      okno.setAttribute("aria-labelledby", id);
      var nadpis = prvek("h2", "", volby.text);
      nadpis.id = id;
      okno.appendChild(nadpis);
      if (volby.popis) okno.appendChild(prvek("p", "", volby.popis));
      var vstup = null;
      if (volby.pole) {
        var pole = prvek("div", "pole");
        var popisek = prvek("label", "", volby.pole.popisek || tr("sg.dialog.odpoved"));
        vstup = doc.createElement("input");
        vstup.id = id + "-pole";
        vstup.type = volby.pole.typ || "text";
        vstup.value = volby.pole.hodnota == null ? "" : String(volby.pole.hodnota);
        popisek.setAttribute("for", vstup.id);
        pole.appendChild(popisek);
        pole.appendChild(vstup);
        okno.appendChild(pole);
      }
      var akce = prvek("div", "radka sg-dialog-akce");
      var ano = prvek("button", volby.nebezpecne ? "tlacitko varovne" : "tlacitko",
        volby.ano || (vstup ? tr("sg.dialog.ulozit") : tr("sg.dialog.pokracovat")));
      var ne = prvek("button", "tlacitko vedlejsi", volby.ne || tr("sg.dialog.zrusit"));
      ano.type = "button";
      ne.type = "button";
      akce.appendChild(ano);
      akce.appendChild(ne);
      okno.appendChild(akce);

      var hotov = false;
      function konec(vysledek) {
        if (hotov) return;
        hotov = true;
        otevrenyDialog = null;
        if (bg.parentNode) bg.parentNode.removeChild(bg);
        if (okno.parentNode) okno.parentNode.removeChild(okno);
        if (predtim && predtim.focus) predtim.focus();
        hotovo(vysledek);
      }
      var zrus = function () { konec(vstup ? null : false); };
      otevrenyDialog = zrus;
      ano.addEventListener("click", function () { konec(vstup ? vstup.value.trim() : true); });
      ne.addEventListener("click", zrus);
      bg.addEventListener("click", zrus);
      okno.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && e.target === vstup) { e.preventDefault(); ano.click(); }
      });
      // Tab stays inside, Escape cancels (Panel a klávesnice, below).
      drzFokus(okno, zrus);
      doc.body.appendChild(bg);
      doc.body.appendChild(okno);
      (vstup || (volby.nebezpecne ? ne : ano)).focus();
    });
  }

  function potvrd(text, volby) {
    volby = volby || {};
    return dialog({ text: text, popis: volby.popis, ano: volby.ano, ne: volby.ne, nebezpecne: !!volby.nebezpecne });
  }

  function zeptej(text, volby) {
    volby = volby || {};
    return dialog({ text: text, popis: volby.popis, ano: volby.ano, ne: volby.ne,
      pole: { popisek: volby.popisek, hodnota: volby.hodnota, typ: volby.typ } });
  }

  function vratitelne(text, vratit, volby) {
    var ms = (volby && volby.ms) || 6000;
    var stary = doc.querySelector(".sg-vratit");
    if (stary && stary.parentNode) stary.parentNode.removeChild(stary);
    var t = prvek("div", "toast sg-vratit");
    t.setAttribute("role", "status");
    var zprava = prvek("span", "", text);
    var tlacitko = prvek("button", "", tr("sg.vratit"));
    tlacitko.type = "button";
    t.appendChild(zprava);
    t.appendChild(tlacitko);
    var casovac = null;
    function pryc() { if (t.parentNode) t.parentNode.removeChild(t); }
    // A hand on the button (hover, focus) holds the toast; leaving restarts the clock.
    function odpocet() { clearTimeout(casovac); casovac = setTimeout(pryc, ms); }
    function drz() { clearTimeout(casovac); }
    t.addEventListener("mouseenter", drz);
    t.addEventListener("mouseleave", odpocet);
    tlacitko.addEventListener("focus", drz);
    tlacitko.addEventListener("blur", odpocet);
    tlacitko.addEventListener("click", function () {
      drz();
      tlacitko.disabled = true;
      Promise.resolve().then(vratit).then(function () {
        zprava.textContent = tr("sg.vraceno");
        tlacitko.hidden = true;
        casovac = setTimeout(pryc, 1500);
      }, function () {
        zprava.textContent = tr("sg.vratit_chyba");
        tlacitko.disabled = false;
        odpocet();
      });
    });
    doc.body.appendChild(t);
    odpocet();
    return { zavri: pryc };
  }

  /* ── Doporučit kolegovi ─────────────────────────────────────────────
   * <button class="tlacitko vedlejsi" data-doporucit="ucet">Doporučit kolegovi</button>
   * A craftsman's colleague is the best next customer, and the phone's own
   * share sheet (WhatsApp, SMS, mail) is where that recommendation happens.
   * The link carries utm_source=doporuceni&utm_campaign=<the attribute> —
   * the template middleware already labels a new account by its first
   * source, so Metriky counts accounts and payments from recommendations
   * with no new code and nothing stored about either person. Without a
   * share sheet the link goes to the clipboard; without that, it is shown
   * in a panel to copy by hand.
   *   SimteGen.doporucit("ucet") → Promise "sdileno" | "zruseno" | "zkopirovano" | "ukazano"
   */
  function oznam(text) {
    var t = prvek("div", "toast", text);
    t.setAttribute("role", "status");
    doc.body.appendChild(t);
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 4000);
  }

  function doporucit(kde) {
    var kampan = String(kde || "aplikace").toLowerCase().replace(/[^a-z0-9_-]/g, "").slice(0, 30) || "aplikace";
    var odkaz = location.origin + "/?utm_source=doporuceni&utm_campaign=" + kampan;
    var text = tr("sg.doporucit.text", { nazev: nazev || tr("sg.doporucit.tuhle") });
    function ukaz() {
      return zeptej(tr("sg.doporucit.posli"), { popisek: tr("sg.doporucit.odkaz"), hodnota: odkaz,
                                             ano: tr("sg.doporucit.hotovo"), ne: tr("sg.zavrit") })
        .then(function () { return "ukazano"; });
    }
    function zkopiruj() {
      if (!navigator.clipboard || !navigator.clipboard.writeText) return ukaz();
      return navigator.clipboard.writeText(text + " " + odkaz).then(function () {
        oznam(tr("sg.doporucit.zkopirovano"));
        return "zkopirovano";
      }, ukaz);
    }
    if (navigator.share) {
      return navigator.share({ title: nazev || doc.title, text: text, url: odkaz }).then(function () {
        return "sdileno";
      }, function (e) {
        // Closing the share sheet is a choice, not a failure.
        return e && e.name === "AbortError" ? "zruseno" : zkopiruj();
      });
    }
    return zkopiruj();
  }

  doc.addEventListener("click", function (e) {
    var tlacitko = e.target && e.target.closest ? e.target.closest("[data-doporucit]") : null;
    if (!tlacitko) return;
    e.preventDefault();
    doporucit(tlacitko.getAttribute("data-doporucit"));
  });

  /* ── Formuláře ─────────────────────────────────────────────────────
   * SimteGen.formular(form), nebo jen <form data-formular>. Chyba patří
   * k poli, ne do okna nad stránkou: pole se kontroluje, až ho zákazník
   * opustí (dřív by ho okřikovalo uprostřed psaní), chyba je pod ním
   * a čtečka ji přečte (aria-describedby, aria-invalid), oprava ji smaže
   * hned při psaní. Odeslání s chybou nic nepošle, skočí na první chybné
   * pole a nic z vyplněného nezmizí. Pravidla jsou obyčejné HTML
   * (required, type, min, max, minlength, maxlength, pattern, step);
   * vlastní věta jde do data-chyba. Chybu ze serveru ukáže f.chyba(jmeno,
   * text) u pole, kterého se týká.
   *
   * Koncept: jen <form data-koncept="zakazka">. Rozepsaný obsah se drží
   * v prohlížeči (localStorage), aby ho nesmazalo zavření aplikace ani
   * výpadek signálu, a vrátí se při dalším otevření — nejvýš 30 dní. Je to
   * ukládání v prohlížeči, takže ho produkt musí mít v manifestu
   * (uloziste_v_prohlizeci): CI data-koncept bez deklarace odmítne. Hesla,
   * soubory a pole s data-bez-konceptu se neukládají nikdy. Po úspěšném
   * uložení na server f.hotovo() koncept smaže.
   *
   * Koncept patří jednomu účtu: klíč nese otisk účtu (SHA-256 z e-mailu
   * z /api/ja, nikdy e-mail sám), takže kolega na stejném telefonu cizí
   * rozepsanou zakázku neuvidí. Odhlášení a smazání účtu smažou všechny
   * koncepty v zařízení. Obnova proto přijde až po /api/ja: f.obnoveno
   * se nastaví potom, f.koncept je Promise s tím samým výsledkem.
   */
  var KONCEPT_DNI = 30;
  var KONCEPT = "sg-koncept:";
  // The last signed-in account's fingerprint, so a draft still comes back
  // when the signal is gone and /api/ja cannot answer (the reason drafts
  // exist). A hash, and gone with the drafts on logout.
  var KONCEPT_UCET = "sg-koncept-ucet";
  var znackaSlib = null;

  function hex(buf) {
    return Array.prototype.map.call(new Uint8Array(buf), function (b) {
      return (b < 16 ? "0" : "") + b.toString(16);
    }).join("");
  }

  // "u<16 hex>" for a signed-in account, "-" for no account (signed out,
  // a product without accounts). One /api/ja per page, shared by all forms.
  function znackaUctu() {
    if (znackaSlib) return znackaSlib;
    znackaSlib = kdoJsem().then(function (k) {
      if (k.stav === "prihlasen" && k.ja.email && window.crypto && crypto.subtle) {
        var otisk = location.host + ":" + String(k.ja.email).trim().toLowerCase();
        return crypto.subtle.digest("SHA-256", new TextEncoder().encode(otisk)).then(function (h) {
          var znacka = "u" + hex(h).slice(0, 16);
          try { localStorage.setItem(KONCEPT_UCET, znacka); } catch (e) { /* blocked storage */ }
          return znacka;
        });
      }
      if (k.stav === "offline") {
        try { return localStorage.getItem(KONCEPT_UCET) || "-"; } catch (e) { return "-"; }
      }
      return "-";
    }).catch(function () { return "-"; });
    return znackaSlib;
  }

  // Every draft on this device, of every account, and the remembered
  // fingerprint. Called on logout and account deletion (below and in the
  // template's index.html); a shared phone keeps nothing of the one who left.
  function zapomenKoncepty() {
    znackaSlib = null;
    try {
      var klice = [];
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (k && k.indexOf("sg-koncept") === 0) klice.push(k);
      }
      klice.forEach(function (k) { localStorage.removeItem(k); });
    } catch (e) { /* blocked storage: nothing was kept */ }
  }

  // Products built before this hook have their own logout and delete
  // buttons in index.html, which the template never touches again — but
  // this file reaches every product on its next build. So a successful
  // POST to the template's two endpoints clears the drafts, whoever made
  // the call.
  if (window.fetch) {
    var fetchPuvodni = window.fetch;
    window.fetch = function (vstup, volby) {
      var odpoved = fetchPuvodni.apply(window, arguments);
      try {
        var adresa = new URL(typeof vstup === "string" ? vstup : (vstup && vstup.url) || String(vstup), location.href);
        var metoda = String((volby && volby.method) || (vstup && vstup.method) || "GET").toUpperCase();
        if (metoda === "POST" && adresa.origin === location.origin &&
            /^\/api\/(odhlaseni|ucet\/smazat)\/?$/.test(adresa.pathname)) {
          odpoved.then(function (r) { if (r.ok) zapomenKoncepty(); }, function () { /* nothing happened */ });
        }
      } catch (e) { /* an address URL cannot parse is not ours */ }
      return odpoved;
    };
  }

  function hlaskaPole(pole) {
    var v = pole.validity;
    if (v.customError) return pole.validationMessage;
    var vlastni = pole.getAttribute("data-chyba");
    if (v.valueMissing) {
      if (vlastni) return vlastni;
      if (pole.type === "checkbox") return tr("sg.pole.zaskrtnete");
      if (pole.tagName === "SELECT" || pole.type === "radio") return tr("sg.pole.vyberte");
      return tr("sg.pole.vyplnte");
    }
    if (vlastni) return vlastni;
    if (v.typeMismatch && pole.type === "email") return tr("sg.pole.email");
    if (v.typeMismatch && pole.type === "url") return tr("sg.pole.url");
    if (v.badInput) return pole.type === "number" ? tr("sg.pole.cislo") : tr("sg.pole.hodnota");
    if (v.tooShort) return tr("sg.pole.aspon", { n: pole.minLength });
    if (v.tooLong) return tr("sg.pole.nejvys_znaku", { n: pole.maxLength });
    if (v.rangeUnderflow) return tr("sg.pole.nejmene", { n: Number(pole.min) });
    if (v.rangeOverflow) return tr("sg.pole.nejvys", { n: Number(pole.max) });
    if (v.stepMismatch) {
      var krok = Number(pole.step);
      return krok === 1 ? tr("sg.pole.cele") : tr("sg.pole.nasobek", { n: krok });
    }
    if (v.patternMismatch) return tr("sg.pole.tvar");
    return tr("sg.pole.hodnota");
  }

  var poradiChyby = 0;

  function ukazChybu(pole, text) {
    var obal = pole.closest(".pole") || pole.parentNode;
    var hlaska = obal.querySelector(".chyba[data-sg-chyba]");
    if (!text) {
      if (hlaska) hlaska.parentNode.removeChild(hlaska);
      if (obal.classList) obal.classList.remove("chybne");
      pole.removeAttribute("aria-invalid");
      var zbyle = (pole.getAttribute("aria-describedby") || "").split(" ").filter(function (id) {
        return id && id.indexOf("sg-chyba-") !== 0;
      });
      if (zbyle.length) pole.setAttribute("aria-describedby", zbyle.join(" "));
      else pole.removeAttribute("aria-describedby");
      return;
    }
    if (!hlaska) {
      hlaska = prvek("p", "chyba");
      hlaska.setAttribute("data-sg-chyba", "");
      hlaska.setAttribute("aria-live", "polite");
      hlaska.id = "sg-chyba-" + (++poradiChyby);
      obal.appendChild(hlaska);
      var popis = (pole.getAttribute("aria-describedby") || "").split(" ").filter(Boolean);
      popis.push(hlaska.id);
      pole.setAttribute("aria-describedby", popis.join(" "));
    }
    hlaska.textContent = text;
    if (obal.classList) obal.classList.add("chybne");
    pole.setAttribute("aria-invalid", "true");
  }

  function poleFormulare(form) {
    return Array.prototype.filter.call(form.elements, function (el) {
      return el.willValidate && !el.disabled && el.type !== "submit" && el.type !== "button";
    });
  }

  function zkontrolujPole(pole) {
    var ok = pole.checkValidity();
    ukazChybu(pole, ok ? "" : hlaskaPole(pole));
    return ok;
  }

  function klicKonceptu(form, znacka) {
    return KONCEPT + znacka + ":" + location.pathname + ":" + form.getAttribute("data-koncept");
  }

  // Before per-account keys a draft had no owner; nobody can tell whose it
  // is, so it is dropped rather than shown to whoever opens the form next.
  function zahodStaryKoncept(form) {
    try { localStorage.removeItem(KONCEPT + location.pathname + ":" + form.getAttribute("data-koncept")); } catch (e) { /* nothing */ }
  }

  function doKonceptu(el) {
    return el.name && !el.disabled && !el.hasAttribute("data-bez-konceptu") &&
      ["password", "file", "hidden", "submit", "button", "reset"].indexOf(el.type) < 0;
  }

  function ulozKoncept(form) {
    var data = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!doKonceptu(el)) return;
      if (el.type === "checkbox") data[el.name + (el.value && el.value !== "on" ? "=" + el.value : "")] = el.checked;
      else if (el.type === "radio") { if (el.checked) data[el.name] = el.value; }
      else data[el.name] = el.value;
    });
    var slib = znackaUctu();
    slib.then(function (znacka) {
      // Logged out meanwhile: the drafts were just cleared, keep it so.
      if (slib !== znackaSlib) return;
      try {
        localStorage.setItem(klicKonceptu(form, znacka), JSON.stringify({ kdy: Date.now(), data: data }));
      } catch (e) { /* full or blocked storage: the draft is a nicety */ }
    });
  }

  function obnovKoncept(form, znacka) {
    var ulozeno = null;
    zahodStaryKoncept(form);
    try { ulozeno = JSON.parse(localStorage.getItem(klicKonceptu(form, znacka)) || "null"); } catch (e) { ulozeno = null; }
    if (!ulozeno || !ulozeno.data) return false;
    if (Date.now() - (ulozeno.kdy || 0) > KONCEPT_DNI * 86400000) {
      try { localStorage.removeItem(klicKonceptu(form, znacka)); } catch (e) { /* nothing to drop */ }
      return false;
    }
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!doKonceptu(el)) return;
      var klic = el.type === "checkbox" && el.value && el.value !== "on" ? el.name + "=" + el.value : el.name;
      if (!(klic in ulozeno.data)) return;
      if (el.type === "checkbox") el.checked = !!ulozeno.data[klic];
      else if (el.type === "radio") el.checked = ulozeno.data[klic] === el.value;
      else el.value = ulozeno.data[klic];
      // The product's own listeners (live totals, previews) see the value.
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    });
    return true;
  }

  function zahodKoncept(form) {
    znackaUctu().then(function (znacka) {
      try { localStorage.removeItem(klicKonceptu(form, znacka)); } catch (e) { /* nothing to drop */ }
    });
  }

  function formular(form) {
    if (!form || form.tagName !== "FORM") return null;
    if (form.sgFormular) return form.sgFormular;
    form.noValidate = true;
    var koncept = form.hasAttribute("data-koncept");
    var casovac = null;
    // Typed into before the draft could come back (/api/ja is a round trip
    // away): the customer's fresh input wins, the draft stays untouched.
    var dotceno = false;
    var obnovuji = false;

    function kontroluj() {
      var prvniChybne = null;
      poleFormulare(form).forEach(function (pole) {
        if (!zkontrolujPole(pole) && !prvniChybne) prvniChybne = pole;
      });
      if (prvniChybne) {
        prvniChybne.focus();
        if (prvniChybne.scrollIntoView) prvniChybne.scrollIntoView({ block: "center" });
      }
      return !prvniChybne;
    }

    form.addEventListener("focusout", function (e) {
      var pole = e.target;
      if (!pole.willValidate || pole.type === "submit" || pole.type === "button") return;
      pole.setAttribute("data-sg-opusteno", "");
      zkontrolujPole(pole);
    });
    function priZmene(e) {
      var pole = e.target;
      if (pole.validity && pole.validity.customError) pole.setCustomValidity("");
      if (pole.hasAttribute && pole.hasAttribute("aria-invalid")) zkontrolujPole(pole);
      else if (e.type === "change" && pole.hasAttribute && pole.hasAttribute("data-sg-opusteno")) zkontrolujPole(pole);
      if (koncept) {
        if (!obnovuji) dotceno = true;
        clearTimeout(casovac);
        casovac = setTimeout(function () { ulozKoncept(form); }, 400);
      }
    }
    form.addEventListener("input", priZmene);
    form.addEventListener("change", priZmene);
    // Capture: at the form itself a capturing listener runs before the
    // product's own submit handler, so an invalid form never reaches it.
    form.addEventListener("submit", function (e) {
      if (!kontroluj()) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    }, true);

    var api = {
      kontroluj: kontroluj,
      chyba: function (jmeno, text) {
        var pole = form.elements[jmeno];
        if (!pole || !pole.setCustomValidity) return false;
        pole.setCustomValidity(text);
        ukazChybu(pole, text);
        pole.focus();
        return true;
      },
      hotovo: function () {
        clearTimeout(casovac);
        zahodKoncept(form);
        poleFormulare(form).forEach(function (pole) {
          pole.removeAttribute("data-sg-opusteno");
          ukazChybu(pole, "");
        });
      },
      obnoveno: false,
      koncept: Promise.resolve(false),
    };
    if (koncept) {
      api.koncept = znackaUctu().then(function (znacka) {
        if (dotceno) return false;
        obnovuji = true;
        try { api.obnoveno = obnovKoncept(form, znacka); } finally { obnovuji = false; }
        return api.obnoveno;
      });
    }
    form.sgFormular = api;
    return api;
  }

  /* ── Průvodce prvním spuštěním ──────────────────────────────────────
   * A new account must not open on an empty screen (D12). The product's
   * empty state carries <ol class="pruvodce" data-pruvodce> with two to
   * four <li data-krok="…"> steps, each with its one button; the product
   * says which are done FROM ITS OWN DATA (a first customer exists, a first
   * set is stored) — nothing is kept in the browser:
   *
   *   SimteGen.pruvodce(document.querySelector("[data-pruvodce]"), ["servis"])
   *
   * Done steps are ticked, the first open one is the current step and only
   * its button shows (one main action per screen); with all steps done the
   * guide hides and the call returns true.
   */
  function pruvodce(el, hotove) {
    if (!el) return false;
    var hotovo = {};
    (hotove || []).forEach(function (k) { hotovo[k] = true; });
    var kroky = Array.prototype.slice.call(el.querySelectorAll("li[data-krok]"));
    var aktualni = null;
    kroky.forEach(function (li) {
      var je = !!hotovo[li.getAttribute("data-krok")];
      li.classList.toggle("hotovo", je);
      var stav = li.querySelector(".pruvodce-stav");
      if (!stav) {
        stav = prvek("span", "pruvodce-stav jen-ctecka");
        li.insertBefore(stav, li.firstChild);
      }
      stav.textContent = je ? tr("sg.pruvodce.hotovo") : "";
      li.removeAttribute("aria-current");
      if (!je && !aktualni) { aktualni = li; li.setAttribute("aria-current", "step"); }
      Array.prototype.forEach.call(li.querySelectorAll("button, a.tlacitko"), function (b) {
        b.hidden = li !== aktualni;
      });
    });
    el.hidden = !aktualni;
    return !aktualni;
  }

  function napojFormulare() {
    Array.prototype.forEach.call(doc.querySelectorAll("form[data-formular], form[data-koncept]"), formular);
  }
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", napojFormulare);
  else napojFormulare();

  window.SimteGen = { kdoJsem: kdoJsem, offline: offline, spojeno: spojeno, tisk: tisk,
    cislo: cislo, kc: kc, datum: datum, rozmer: rozmer, pocet: pocet, cena: cena,
    t: tr, chyba: chyba, jazyk: function () { return jazyk; }, jazyky: function () { return produktJazyky.slice(); },
    slovnik: slovnik, preloz: preloz, nastavJazyk: nastavJazyk,
    cenik: cenik, mena: function () { return menaTed; }, nastavMenu: nastavMenu,
    potvrd: potvrd, zeptej: zeptej, vratitelne: vratitelne, doporucit: doporucit, formular: formular,
    zapomenKoncepty: zapomenKoncepty, panel: otevriPanel, pruvodce: pruvodce };

  /* Google Play v aplikaci — nákup předplatného a „Vyzkoušet ukázku“ —
   * žije v play.js: jen v produktu s modulem aplikace (<html data-aplikace>)
   * a jen když stránka má co obsloužit, ať statické stránky nic nenačítají. */
  doc.addEventListener("DOMContentLoaded", function () {
    if (!doc.documentElement.hasAttribute("data-aplikace")) return;
    if (!doc.querySelector("[data-objednavka], [data-predplatne-play], [data-ukazka]")) return;
    var skript = doc.createElement("script");
    skript.src = "play.js";
    doc.body.appendChild(skript);
  });
})();
