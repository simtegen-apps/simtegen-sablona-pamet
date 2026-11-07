-- From "using" to "paying" (SimteGen, konverze). Numbered 0920 like 0910:
-- template infrastructure, written into a product once and never changed,
-- out of the way of the product's own numbering.
--
-- zkusebni_doba — when this account's trial ends, AS THE PRODUCT COMPUTES
--   IT. functions/api/_middleware.js copies it from context.data.predplatne
--   whenever the app asks /api/ja. Not derived here from uzivatele.vytvoreno
--   on purpose: the two live products already disagree with the template
--   (a 14-day trial; a shop-keyed trial with its own end date), and a
--   reminder that names the wrong day is worse than none. An account that
--   never opened the app since this table existed has no row and gets no
--   reminder.
-- upominky — which trial reminder went out and when (Upominky workflow).
--   The primary key is the "once per account" promise: the workflow claims
--   the row first and only then sends.
-- ukazkova_data — sample data loaded into this account on request
--   (functions/api/ukazka-uctu.js): per product table, the rowid range
--   the sample rows got. Removal deletes exactly those rows of this
--   account, nothing else.
--
-- All three carry uzivatel_id, so export and account deletion reach them
-- like any other table, and no state column has a CHECK constraint.

CREATE TABLE zkusebni_doba (
    uzivatel_id INTEGER PRIMARY KEY REFERENCES uzivatele(id) ON DELETE CASCADE,
    konec       INTEGER NOT NULL,
    zapsano     INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE upominky (
    uzivatel_id INTEGER NOT NULL REFERENCES uzivatele(id) ON DELETE CASCADE,
    druh        TEXT NOT NULL,
    odeslano    INTEGER NOT NULL DEFAULT (unixepoch()),
    PRIMARY KEY (uzivatel_id, druh)
);
CREATE INDEX idx_upominky_odeslano ON upominky(odeslano);

CREATE TABLE ukazkova_data (
    uzivatel_id INTEGER PRIMARY KEY REFERENCES uzivatele(id) ON DELETE CASCADE,
    pred        TEXT NOT NULL,
    po          TEXT,
    nahrano     INTEGER NOT NULL DEFAULT (unixepoch())
);
