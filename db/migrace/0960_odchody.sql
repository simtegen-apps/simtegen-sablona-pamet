-- Why customers leave (SimteGen, batch D2 14. 11. 2026). Numbered 0960
-- like 0910–0950: template infrastructure, written into a product once and
-- never changed, out of the way of the product's own numbering.
--
-- A tally like chyby_stranek: (day, channel, reason, count) — no account, no
-- text, nothing a person can be found by. Two ways in:
--   po_zkusebni / po_predplatnem — the one-tap question the app shows after
--     a trial or a paid period ran out (functions/api/odchod.js); that the
--     account answered is remembered in upominky ("once per period"), what
--     it answered is not
--   play / play_platba — the reason Google's own cancel survey recorded,
--     or a payment Google could not collect (play_nakupy.js)
-- The reason is one of a fixed list (odchod.js DUVODY); anything else is
-- refused, so nobody can write text into it.

CREATE TABLE odchody (
    den    TEXT NOT NULL,
    kanal  TEXT NOT NULL,
    duvod  TEXT NOT NULL,
    pocet  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (den, kanal, duvod)
);
