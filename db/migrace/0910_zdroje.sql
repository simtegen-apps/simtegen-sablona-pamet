-- Where customers come from (functions/api/_middleware.js, from the
-- template; SimteGen etapa 7). Numbered 0910 so it never collides with a
-- product's own migrations; written into a product once, never changed.
--
-- The source is the utm_source / utm_campaign of the link the customer
-- came by — labels SimteGen itself puts on the links it places (an ad, a
-- catalogue entry). Nothing is stored in the browser and nothing about the
-- device: the label rides on the login link until the account exists, then
-- stays on the account (first touch, deleted with it). Visits are counted
-- per source as plain numbers, like navstevy.

ALTER TABLE uzivatele ADD COLUMN zdroj TEXT;
ALTER TABLE uzivatele ADD COLUMN kampan TEXT;
ALTER TABLE prihlasovaci_odkazy ADD COLUMN zdroj TEXT;
ALTER TABLE prihlasovaci_odkazy ADD COLUMN kampan TEXT;

CREATE TABLE zdroje_navstev (
    den    TEXT NOT NULL,
    zdroj  TEXT NOT NULL,
    kampan TEXT NOT NULL DEFAULT '',
    pocet  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (den, zdroj, kampan)
);
