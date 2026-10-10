// Session middleware: resolve the cookie once, hand the user to every
// handler via context.data.uzivatel. Handlers stay one-purpose files.
//
// The subscription state rides along (context.data.predplatne): one extra
// query per API call, so a product route can gate with vyzadujPredplatne()
// and /api/ja can show it, without either re-deriving the rules.

import { nactiUzivatele } from "../spolecne.js";
import { stavPredplatneho } from "../predplatne.js";

export async function onRequest(context) {
  const uzivatel = await nactiUzivatele(context.request, context.env);
  context.data.uzivatel = uzivatel;
  context.data.predplatne = uzivatel
    ? await stavPredplatneho(context.env, uzivatel)
    : null;
  return context.next();
}
