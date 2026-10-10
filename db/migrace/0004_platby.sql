-- Payment ledger: one row per payment the owner marked (workflow
-- "Predplatne"). predplatne holds only the current end date; the review
-- needs the history — first payment, second payment, churn — because
-- "no second purchase" is the zadání's kill signal. Amounts are not here:
-- the invoice is the accounting document, the app only knows "paid N
-- months on this day".

CREATE TABLE platby (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uzivatel_id INTEGER NOT NULL REFERENCES uzivatele(id) ON DELETE CASCADE,
    mesice      INTEGER NOT NULL,
    poznamka    TEXT,
    zapsano     INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_platby_uzivatel ON platby(uzivatel_id, zapsano);
