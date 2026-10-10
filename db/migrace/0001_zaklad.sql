-- Template base: accounts, one-time login links, sessions.
--
-- Times are unix epoch SECONDS (integers) everywhere: the Functions compare
-- them with Math.floor(Date.now()/1000), and mixing SQLite's datetime('now')
-- text format with JS ISO strings makes lexicographic comparisons silently
-- wrong. unixepoch() needs no format at all.
--
-- Tokens are never stored, only their SHA-256 hex digests: a leaked database
-- must not be a bag of valid logins.

CREATE TABLE uzivatele (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    email     TEXT NOT NULL UNIQUE,
    vytvoreno INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE prihlasovaci_odkazy (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    otisk_tokenu TEXT NOT NULL UNIQUE,
    email        TEXT NOT NULL,
    expirace     INTEGER NOT NULL,
    pouzito      INTEGER NOT NULL DEFAULT 0,
    vytvoreno    INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_odkazy_email ON prihlasovaci_odkazy(email, vytvoreno);

CREATE TABLE relace (
    otisk_tokenu TEXT PRIMARY KEY,
    uzivatel_id  INTEGER NOT NULL REFERENCES uzivatele(id) ON DELETE CASCADE,
    expirace     INTEGER NOT NULL,
    vytvoreno    INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_relace_uzivatel ON relace(uzivatel_id);
