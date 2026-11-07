-- The product's mailbox: what a customer wrote us, and what we answered.
-- One row per report; the customer sees their own rows (and the answer) in
-- the app, the firm sees a copy WITHOUT the account (issue in the product
-- repo, see functions/api/hlaseni.js). uzivatel_id keeps export and
-- account deletion generic; issue_cislo links the copy so the answer
-- written on the issue lands back here (workflow "Odpoved").
--
-- stav: nove → vyrizuje_se → vyrizeno | odlozeno

CREATE TABLE hlaseni (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    uzivatel_id  INTEGER NOT NULL REFERENCES uzivatele(id) ON DELETE CASCADE,
    text         TEXT NOT NULL,
    stav         TEXT NOT NULL DEFAULT 'nove',
    odpoved      TEXT,
    issue_cislo  INTEGER,
    vytvoreno    INTEGER NOT NULL DEFAULT (unixepoch()),
    zmeneno      INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_hlaseni_uzivatel ON hlaseni(uzivatel_id, vytvoreno);
