// GET /api/prostredi → {zeme: "CZ" | null}
// Infrastruktura šablony (NEUPRAVOVAT V PRODUKTU), veřejný endpoint.
//
// Which country the visitor is in, as Cloudflare already knows it from the
// connection (request.cf.country) — so web/simtegen.js can show the price
// list in the visitor's currency (CZ → Kč, Europe → EUR, elsewhere USD).
// Only the two-letter code goes back, to the visitor's own page; nothing
// is stored or logged here, and the IP address never leaves Cloudflare.
// No country (a local run, Tor's "T1", an unknown "XX") means null: the
// page then guesses from the language, never from anything else.

export async function onRequestGet(context) {
  const kod = context.request.cf && context.request.cf.country;
  const zeme = typeof kod === "string" && /^[A-Z]{2}$/.test(kod) && kod !== "XX" && kod !== "T1" ? kod : null;
  return new Response(JSON.stringify({ zeme }), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      // Per visitor: a shared cache would hand one country to everyone.
      "Cache-Control": "private, no-store",
    },
  });
}
