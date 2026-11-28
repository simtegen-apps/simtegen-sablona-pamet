-- Subscription orders placed in the app. The order is the "button binding
-- to pay" the terms describe (§ 1826 (3) obč. zák.); the consumer consent
-- to start before the 14-day withdrawal window (§ 1837 l) is a separate
-- checkbox, stored as its own flag with the time it was given. Billing
-- details are personal data of the customer; they live here, go to the
-- operator by e-mail for the invoice, and never into the GitHub mirror.
--
-- stav: nova → fakturovana → zaplacena | zrusena

CREATE TABLE objednavky (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    uzivatel_id        INTEGER NOT NULL REFERENCES uzivatele(id) ON DELETE CASCADE,
    mesice             INTEGER NOT NULL,
    varianta           TEXT,
    cena_czk           INTEGER,
    fakturace          TEXT,
    spotrebitel        INTEGER NOT NULL DEFAULT 0,
    souhlas_zahajeni   INTEGER NOT NULL DEFAULT 0,
    souhlas_cas        INTEGER,
    stav               TEXT NOT NULL DEFAULT 'nova',
    issue_cislo        INTEGER,
    vytvoreno          INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_objednavky_uzivatel ON objednavky(uzivatel_id, vytvoreno);
