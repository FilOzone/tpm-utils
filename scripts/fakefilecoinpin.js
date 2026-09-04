// Transitional Worker for the filecoinpin.contact decommission
//
// Background: the filecoinpin.contact IPNI service is being shut down, but Curio's
// codebase still hardcodes it as a default (Market.StorageMarketConfig.IPNI's
// ServiceURL / DirectAnnounceURLs). That won't be fully clean until a future Curio
// release removes those two defaults. Until then, if this domain simply stops
// resolving, any Curio node still running the default config breaks in the ways
// described in the three routes below. We still control this domain, so this Worker
// keeps it "alive" to close that gap for now.
//
// When this can actually be retired: not the moment the release ships, but some time
// after. Nodes already running in the field only stop depending on this default once
// they upgrade and restart / reload config, and /cid/{cid} exists specifically to
// backstop old clients that haven't upgraded — which tend to lag even further behind.
// So before retiring, check this Worker's actual traffic (especially /announce,
// /providers/*, /cid/*) and confirm both the fleet and old clients have mostly moved
// on and traffic has dropped to an acceptable level before actually taking the domain
// down.
//
// The three routes serve three completely different callers. Come back to this list
// when deleting one, or when it's unclear why a route exists:
//
// 1) PUT /announce
//    Backs Curio's DirectAnnounceURLs config. Curio pushes the IPNI ad head to this
//    address every second. If the request fails (4xx/5xx/unreachable), Curio doesn't
//    error out, but treats the push as unsuccessful and retries the same head against
//    every configured URL again a second later (including the URLs that already
//    succeeded). So a persistently failing endpoint here causes unbounded repeated
//    requests against the other, healthy IPNI services too. Returning 200
//    unconditionally avoids that noise.
//
// 2) GET /providers/{peerID}
//    Backs Curio's ServiceURL config. Two callers hit this:
//      a. The web UI's IPNI status page (IPNISummary) — display only;
//      b. The background alert check ipniSyncCheck (runs every 5 minutes) — if the
//         LastAdvertisementTime this endpoint returns hasn't updated in over an hour,
//         it raises an "IPNISync" alert, and if that alert mentions a PDP provider it
//         also marks Curio's /ping health check unhealthy, which can trigger real ops
//         paging. So this must return a freshly computed timestamp on every request,
//         with caching disabled — a cached stale response would freeze the timestamp
//         in the past and eventually trigger the alert anyway.
//
// 3) GET /cid/{cid}
//    Unrelated to Curio's IPNI config — this is the content-resolution entry point for
//    old clients that haven't upgraded. Redirecting a newly-seen CID straight to origin
//    risks a 404 (origin not ready yet) that gets cached downstream as a negative
//    cache entry, which then keeps blocking the CID even after origin catches up. So
//    new CIDs are held behind a short window (always 404 during the window), and only
//    redirected with a normal 307 once the window has passed.
//
// Deploy: Cloudflare dashboard -> Workers & Pages -> Create Worker -> paste this whole
// file into the editor -> Deploy. Then attach the filecoinpin.contact domain to this
// Worker's route (the domain must be proxied / "orange-clouded").

// ------- Adjust these as needed -------
const REDIRECT_BASE = "https://cid.contact/cid/";  // Real target prefix /cid/xxx redirects to once its window has passed
const WINDOW_SECONDS = 10;                         // How long to hold a newly-seen CID (seconds); always 404 during this window
const REMEMBER_SECONDS = 2592000;                  // How long to remember a CID (seconds), currently 1 month — effectively "redirect forever once past the window". Deliberately not accounting for the CID being deleted / re-synced for now. The Cache API has no documented hard cap, but this is only an upper bound, not a guarantee — Cloudflare may evict earlier under cache pressure (which just re-triggers the 404 window, not an error)
const FAKE_HEAD_CID = "fake-head-not-in-curio-db";  // Placeholder value used in the /providers/{peerID} response; Curio only compares this as a plain string, no CID-format validation, so it's deliberately written to look nothing like a real CID
// ---------------------------------------

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    // Curio DirectAnnounceURLs: PUT /announce — treat any method, any request as a successful push.
    // Matches the real IPNI reference implementation (storetheindex server/ingest/server.go putAnnounce),
    // which replies 204 No Content with an empty body on success.
    if (path === "/announce") {
      return new Response(null, {
        status: 204,
        headers: { "Cache-Control": "no-store" },
      });
    }

    // Curio ServiceURL: GET /providers/{peerID} — used by IPNISummary / ipniSyncCheck to judge sync status
    // LastAdvertisementTime must be "now" on every request, or the IPNISync alert fires after an hour.
    // Shape verified against a real response from cid.contact (GET /providers) — FrozenAt is a bare
    // JSON null on the wire, not an empty string; Go's json.Unmarshal leaves a null field at its zero
    // value for any target type, so either would work, but null matches the real payload.
    if (path.startsWith("/providers/")) {
      const body = JSON.stringify({
        AddrInfo: { ID: "", Addrs: [] },
        LastAdvertisement: { "/": FAKE_HEAD_CID },
        LastAdvertisementTime: new Date().toISOString(),
        Publisher: { ID: "", Addrs: [] },
        FrozenAt: null,
      });
      return new Response(body, {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          // Disable caching at every layer — a cached stale response would freeze LastAdvertisementTime in the past
          "Cache-Control": "no-store",
        },
      });
    }

    // Legacy-client content resolution: /cid/{cid}
    // Hold a newly-seen CID behind a short window and return 404, to avoid a negative-cache hit while
    // origin isn't ready yet; redirect normally once the window has passed.
    // Status code is what old clients actually act on (404 = "not found yet, retry"), so the body text
    // below is purely informational for humans hitting this URL directly; it's not part of any IPNI
    // response contract, so it's fine for it to say this endpoint is deprecated instead of mirroring
    // the real "no results for query" wording used elsewhere.
    if (path.startsWith("/cid/")) {
      const cid = path.slice("/cid/".length);
      if (!cid) {
        return new Response("no results for query", { status: 404, headers: { "Cache-Control": "no-store" } });
      }

      const deprecationNotice = (remainingSeconds) =>
        `This endpoint (filecoinpin.contact) has been deprecated. This request is held briefly to avoid ` +
        `a negative-cache hit on this CID while origin isn't ready yet; it will redirect to ${REDIRECT_BASE}${cid} ` +
        `in ${remainingSeconds} second(s).`;

      const cache = caches.default;
      // Build the cache key against a host that's never actually served, so it can't collide with real routes
      const markerKey = new Request(`https://cid-marker.internal/${encodeURIComponent(cid)}`);

      const cached = await cache.match(markerKey);
      const now = Date.now();

      if (!cached) {
        // First time this colo has seen this CID: record the first-seen time, return 404 for this request
        const marker = new Response(String(now), {
          headers: { "Cache-Control": `public, max-age=${REMEMBER_SECONDS}` },
        });
        ctx.waitUntil(cache.put(markerKey, marker));
        return new Response(deprecationNotice(WINDOW_SECONDS), {
          status: 404,
          headers: { "Cache-Control": "no-store", "Retry-After": String(WINDOW_SECONDS) },
        });
      }

      const firstSeen = Number(await cached.text());
      const elapsed = (now - firstSeen) / 1000;

      if (elapsed < WINDOW_SECONDS) {
        // Still inside the hold window — keep returning 404, and disallow caching this response too
        const remaining = Math.ceil(WINDOW_SECONDS - elapsed);
        return new Response(deprecationNotice(remaining), {
          status: 404,
          headers: { "Cache-Control": "no-store", "Retry-After": String(remaining) },
        });
      }

      // Window has passed — redirect normally
      return Response.redirect(REDIRECT_BASE + cid, 307);
    }

    return new Response("Not Found", { status: 404, headers: { "Cache-Control": "no-store" } });
  },
};
