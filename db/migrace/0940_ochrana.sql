-- Abuse limits and single-use check signatures (ochrana.js,
-- functions/api/_middleware.js, functions/api/kontrolni-prihlaseni.js).
-- Numbered 0940 like 0910–0930: template infrastructure, written into a
-- product once and never changed.
--
-- limity: request counters per (kind, key, window). The key is a digest
-- that changes with every window (ochrana.vLimitu), never an IP address or
-- an e-mail as such; rows are swept soon after their window ends. They are
-- security records (the policy's "provozní a bezpečnostní záznamy"), kept
-- in D1 because an in-memory or per-data-centre counter lets a script
-- spread over the network — and a limit that is cheaper to dodge than to
-- hit protects nothing.
--
-- pouzite_podpisy: a signed check login (overeni.py) works once. The
-- PRIMARY KEY makes the second use fail at the INSERT itself, so two
-- requests racing with the same signature cannot both pass a "was it
-- used?" read before either writes.

CREATE TABLE limity (
    druh   TEXT NOT NULL,
    klic   TEXT NOT NULL,
    okno   INTEGER NOT NULL,
    pocet  INTEGER NOT NULL DEFAULT 0,
    vyprsi INTEGER NOT NULL,
    PRIMARY KEY (druh, klic, okno)
);
CREATE INDEX limity_vyprsi ON limity (vyprsi);

CREATE TABLE pouzite_podpisy (
    otisk  TEXT PRIMARY KEY,
    vyprsi INTEGER NOT NULL
);
