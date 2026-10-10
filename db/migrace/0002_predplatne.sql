-- Subscription state, one row per account. The app never handles money:
-- the owner invoices, sees the payment arrive, and marks it through the
-- "Predplatne" workflow, which upserts plati_do here. The app only ever
-- asks "is this account paid up?" (predplatne.js). A trial period needs no
-- row at all — it is derived from uzivatele.vytvoreno — so a fresh product
-- works before anyone has marked a single payment.
--
-- uzivatel_id is the primary key on purpose: export and account deletion
-- reach this table generically, and "one account, one subscription" is a
-- constraint, not a convention.

CREATE TABLE predplatne (
    uzivatel_id INTEGER PRIMARY KEY REFERENCES uzivatele(id) ON DELETE CASCADE,
    plati_do    INTEGER NOT NULL,
    poznamka    TEXT,
    zmeneno     INTEGER NOT NULL DEFAULT (unixepoch())
);
