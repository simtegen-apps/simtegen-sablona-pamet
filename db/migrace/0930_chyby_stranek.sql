-- Script errors customers' browsers hit (SimteGen, P9 "data místo
-- stížností"). Numbered 0930 like 0910/0920: template infrastructure,
-- written into a product once and never changed.
--
-- A tally, not a log: one row per day, screen and place in OUR code
-- (file:line), and a count. No message — an error text can carry what the
-- customer typed — no account, no IP, no user agent; the CI checker holds
-- an aggregate to that (kontrola_manifestu.SABLONOVE_AGREGATY). Before, a
-- broken screen was known only when a customer bothered to report it, and
-- most never do; the review and the support agent read these counts
-- (Metriky workflow → SimteGen), the code location is what a fix needs.

CREATE TABLE chyby_stranek (
    den       TEXT NOT NULL,
    obrazovka TEXT NOT NULL,
    misto     TEXT NOT NULL,
    pocet     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (den, obrazovka, misto)
);
