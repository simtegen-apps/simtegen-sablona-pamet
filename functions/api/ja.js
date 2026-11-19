// GET /api/ja — who am I. The frontend's only window into the session:
// the cookie is HttpOnly, so this is how the page decides which screen
// to show — and, via predplatne, whether to show the "expired" state.

import { json } from "../../spolecne.js";

export async function onRequestGet(context) {
  const uzivatel = context.data.uzivatel;
  if (!uzivatel) return json({ prihlasen: false });
  return json({
    prihlasen: true,
    email: uzivatel.email,
    predplatne: context.data.predplatne,
  });
}
