-- The language a customer uses the app in (functions/api/_middleware.js and
-- functions/api/jazyk.js, from the template; batch B, 14. 11. 2026).
-- Numbered 0950 so it never collides with a product's own migrations;
-- written into a product once, never changed.
--
-- Mails the firm sends later — the trial end, renewal, an answer to a
-- report (.github/nastroje/upominky.py) — went in Czech to everyone, also
-- to a customer who came from Google Play abroad and reads the app in
-- English. The language rides on the login link until the account exists
-- (the login mail itself goes in it), then stays on the account; the page
-- corrects it when the customer switches. NULL = Czech, as before.

ALTER TABLE uzivatele ADD COLUMN jazyk TEXT;
ALTER TABLE prihlasovaci_odkazy ADD COLUMN jazyk TEXT;
