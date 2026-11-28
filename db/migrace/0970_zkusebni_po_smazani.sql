-- The trial a deleted account already used (functions/api/ucet/smazat.js,
-- functions/api/_middleware.js). Numbered 0970 like 0910–0960: template
-- infrastructure, written into a product once and never changed.
--
-- zkusebni_po_smazani: when an account is deleted, a digest of its mailbox
-- (ochrana.otiskSchranky — never the address itself) and the time the
-- account was made. A new account under the same mailbox within 12 months
-- takes that time, so its trial continues instead of starting over. Rows
-- older than 12 months are swept on the next deletion. No account id: the
-- account is gone, and the row describes nobody who still has one.

CREATE TABLE zkusebni_po_smazani (
    otisk     TEXT PRIMARY KEY,
    vytvoreno INTEGER NOT NULL,
    vyprsi    INTEGER NOT NULL
);
