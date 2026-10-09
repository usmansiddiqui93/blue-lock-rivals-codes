// Blue Lock Rivals Codes: email alerts.
//   POST /alerts/subscribe        { email, website? }  -> sends a confirmation email (double opt-in)
//   GET  /alerts/confirm?t=…      -> confirms, redirects to the site
//   GET  /alerts/unsubscribe?t=…  -> unsubscribes, redirects to the site
//   POST /alerts/unsubscribe?t=…  -> RFC 8058 one-click unsubscribe (mail clients)
//   POST /alerts/notify           -> emails confirmed subscribers about codes not announced yet
//
// /notify is safe to call publicly: it only announces codes that are already live on the public
// site, each code at most once (claimed in the database before sending). Calling it again is a no-op.
//
// Secrets (set in the Supabase dashboard): RESEND_API_KEY.
// Provided automatically: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
import { createClient } from "npm:@supabase/supabase-js@2";

const SITES = [
  "https://blue-lock-rivals-codes.com",
  "https://www.blue-lock-rivals-codes.com",
  "https://usmansiddiqui93.github.io",
];
// Where the site (and its public codes feed) currently lives, in order of preference.
const SITE_BASES = [
  "https://blue-lock-rivals-codes.com",
  "https://usmansiddiqui93.github.io/blue-lock-rivals-codes",
];
const FROM = "Blue Lock Rivals Codes <alerts@blue-lock-rivals-codes.com>";
const REPLY_TO = "privacy@blue-lock-rivals-codes.com";
const MAX_NEW_CODES_PER_RUN = 6;
const RESEND_COOLDOWN_MIN = 10;

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
  auth: { persistSession: false },
});
const FN_URL = `${Deno.env.get("SUPABASE_URL")}/functions/v1/alerts`;

function cors(origin: string | null): Record<string, string> {
  const allowed = origin && SITES.includes(origin) ? origin : SITES[0];
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Vary": "Origin",
  };
}
const json = (body: unknown, status: number, origin: string | null) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...cors(origin) } });

function siteBaseFor(origin: string): string {
  if (origin.startsWith("https://usmansiddiqui93.github.io")) return SITE_BASES[1];
  return SITE_BASES[0];
}
const redirect = (url: string) => new Response(null, { status: 303, headers: { Location: url } });
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
const EMAIL_RE = /^[^\s@]{1,64}@[^\s@]{1,190}\.[a-z]{2,24}$/i;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function sendEmails(messages: Record<string, unknown>[]) {
  const key = Deno.env.get("RESEND_API_KEY");
  if (!key) throw new Error("RESEND_API_KEY is not set");
  const single = messages.length === 1;
  const res = await fetch(single ? "https://api.resend.com/emails" : "https://api.resend.com/emails/batch", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify(single ? messages[0] : messages),
  });
  if (!res.ok) throw new Error(`Resend ${res.status}: ${await res.text()}`);
}

function shell(title: string, inner: string, unsubUrl?: string) {
  const foot = unsubUrl
    ? `<p style="margin:24px 0 0;font-size:12px;color:#8a8e9c">You get these emails because you subscribed on blue-lock-rivals-codes.com.
       <a href="${unsubUrl}" style="color:#8a8e9c">Unsubscribe</a> with one click.</p>`
    : `<p style="margin:24px 0 0;font-size:12px;color:#8a8e9c">If you didn't ask for this, ignore this email and you won't hear from us again.</p>`;
  return `<!doctype html><html><body style="margin:0;background:#f2f3f7;font-family:Arial,Helvetica,sans-serif;color:#14151b">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#fff;border-radius:14px;overflow:hidden">
<tr><td style="background:#0b0b10;padding:18px 24px;font-weight:900;font-style:italic;font-size:20px;color:#ff6a1a">BLUE LOCK RIVALS <span style="font-style:normal;font-size:12px;background:#3866ff;color:#fff;padding:3px 7px;border-radius:5px">CODES</span></td></tr>
<tr><td style="padding:26px 24px 22px"><h1 style="margin:0 0 12px;font-size:22px">${esc(title)}</h1>${inner}${foot}</td></tr>
</table></td></tr></table></body></html>`;
}

const button = (href: string, label: string) =>
  `<a href="${href}" style="display:inline-block;background:#e8263f;color:#fff;text-decoration:none;font-weight:bold;padding:13px 22px;border-radius:10px">${esc(label)}</a>`;

const codeBox = (code: string) =>
  `<div style="margin:6px 0 4px;border:2px dashed #ff7a1a;border-radius:12px;padding:14px 16px;font-family:'Courier New',monospace;font-size:24px;font-weight:bold;letter-spacing:2px;color:#14151b">${esc(code)}</div>`;

// ---------------------------------------------------------------- handlers

async function subscribe(req: Request, origin: string | null) {
  if (!origin || !SITES.includes(origin)) return json({ ok: false, error: "Forbidden" }, 403, origin);
  let body: { email?: string; website?: string };
  try { body = await req.json(); } catch { return json({ ok: false, error: "Bad request" }, 400, origin); }
  if (body.website) return json({ ok: true }, 200, origin); // honeypot: bots fill hidden fields
  const email = String(body.email || "").trim().toLowerCase();
  if (!EMAIL_RE.test(email) || email.length > 254) return json({ ok: false, error: "Please enter a valid email address." }, 400, origin);

  const { data: existing } = await db.from("subscribers").select("*").eq("email", email).maybeSingle();
  if (existing?.status === "confirmed") return json({ ok: true, already: true }, 200, origin);

  let row = existing;
  if (!row) {
    const { data, error } = await db.from("subscribers").insert({ email, origin }).select().single();
    if (error) return json({ ok: false, error: "Could not save your email. Please try again." }, 500, origin);
    row = data;
  } else if (row.status === "unsubscribed") {
    const { data } = await db.from("subscribers")
      .update({ status: "pending", origin, confirm_token: crypto.randomUUID(), unsubscribed_at: null })
      .eq("id", row.id).select().single();
    row = data;
  }
  // Don't let anyone flood an inbox with confirmation emails.
  if (row.confirm_sent_at && Date.now() - new Date(row.confirm_sent_at).getTime() < RESEND_COOLDOWN_MIN * 60_000) {
    return json({ ok: true }, 200, origin);
  }
  const link = `${FN_URL}/confirm?t=${row.confirm_token}`;
  try {
    await sendEmails([{
      from: FROM, to: [email], reply_to: REPLY_TO,
      subject: "Confirm your Blue Lock Rivals code alerts",
      html: shell("One click to start getting new codes",
        `<p style="margin:0 0 18px;line-height:1.6">Confirm your email and we'll send you every new Blue Lock: Rivals code the moment it goes live. No other emails, ever.</p>${button(link, "Confirm my email")}`),
      text: `Confirm your email to get new Blue Lock Rivals codes: ${link}\n\nIf you didn't ask for this, ignore this email.`,
    }]);
  } catch (e) {
    console.error(e);
    return json({ ok: false, error: "We couldn't send the confirmation email right now. Please try again later." }, 502, origin);
  }
  await db.from("subscribers").update({ confirm_sent_at: new Date().toISOString() }).eq("id", row.id);
  return json({ ok: true }, 200, origin);
}

async function confirm(url: URL) {
  const t = url.searchParams.get("t") || "";
  if (!UUID_RE.test(t)) return redirect(`${SITE_BASES[0]}/alerts/`);
  const { data } = await db.from("subscribers").select("id,status,origin").eq("confirm_token", t).maybeSingle();
  if (!data) return redirect(`${SITE_BASES[0]}/alerts/`);
  if (data.status !== "confirmed") {
    await db.from("subscribers").update({ status: "confirmed", confirmed_at: new Date().toISOString() }).eq("id", data.id);
  }
  return redirect(`${siteBaseFor(data.origin)}/alerts/confirmed/`);
}

async function unsubscribe(req: Request, url: URL) {
  const t = url.searchParams.get("t") || "";
  let origin = SITES[0];
  if (UUID_RE.test(t)) {
    const { data } = await db.from("subscribers").select("id,origin").eq("unsub_token", t).maybeSingle();
    if (data) {
      origin = data.origin;
      await db.from("subscribers").update({ status: "unsubscribed", unsubscribed_at: new Date().toISOString() }).eq("id", data.id);
    }
  }
  if (req.method === "POST") return new Response("Unsubscribed", { status: 200 });
  return redirect(`${siteBaseFor(origin)}/alerts/unsubscribed/`);
}

type Code = { code: string; reward?: string; spins?: number; flows?: number };

async function liveCodes(): Promise<{ codes: Code[]; base: string } | null> {
  for (const base of SITE_BASES) {
    try {
      const r = await fetch(`${base}/api/codes.json`, { headers: { "Cache-Control": "no-cache" } });
      if (!r.ok) continue;
      const j = await r.json();
      if (Array.isArray(j.active)) return { codes: j.active, base };
    } catch { /* try next */ }
  }
  return null;
}

function rewardText(c: Code) {
  const parts = [];
  if (c.spins) parts.push(`${c.spins} Lucky Style Spins`);
  if (c.flows) parts.push(`${c.flows} Lucky Flow Spins`);
  return parts.join(" and ") || c.reward || "Free rewards";
}

async function notify() {
  const live = await liveCodes();
  if (!live) return json({ ok: false, error: "Codes feed unreachable" }, 502, null);

  const { count } = await db.from("notified_codes").select("code", { count: "exact", head: true });
  if (!count) {
    // First run: remember what's already live so subscribers only get genuinely new codes.
    await db.from("notified_codes").upsert(live.codes.map((c) => ({ code: c.code.toUpperCase(), reward: rewardText(c) })));
    return json({ ok: true, seeded: live.codes.length }, 200, null);
  }

  const { data: known } = await db.from("notified_codes").select("code");
  const knownSet = new Set((known || []).map((r) => r.code));
  const fresh = live.codes.filter((c) => !knownSet.has(c.code.toUpperCase()));
  if (!fresh.length) return json({ ok: true, sent: 0 }, 200, null);
  if (fresh.length > MAX_NEW_CODES_PER_RUN) {
    return json({ ok: false, error: `Refusing to announce ${fresh.length} codes at once` }, 409, null);
  }

  // Claim the codes first; only codes this run inserted get announced.
  const { data: claimed } = await db.from("notified_codes")
    .upsert(fresh.map((c) => ({ code: c.code.toUpperCase(), reward: rewardText(c) })), { onConflict: "code", ignoreDuplicates: true })
    .select("code");
  const claimedSet = new Set((claimed || []).map((r) => r.code));
  const toSend = fresh.filter((c) => claimedSet.has(c.code.toUpperCase()));
  if (!toSend.length) return json({ ok: true, sent: 0 }, 200, null);

  const subject = toSend.length === 1
    ? `New Blue Lock Rivals code: ${toSend[0].code}`
    : `${toSend.length} new Blue Lock Rivals codes`;
  const listHtml = toSend.map((c) => `${codeBox(c.code)}<p style="margin:0 0 14px;color:#3c4050">${esc(rewardText(c))}</p>`).join("");
  const listText = toSend.map((c) => `${c.code} — ${rewardText(c)}`).join("\n");

  let sent = 0, from = 0;
  const PAGE = 100;
  while (true) {
    const { data: subs } = await db.from("subscribers").select("email,unsub_token,origin")
      .eq("status", "confirmed").order("created_at").range(from, from + PAGE - 1);
    if (!subs?.length) break;
    const batch = subs.map((s) => {
      const unsub = `${FN_URL}/unsubscribe?t=${s.unsub_token}`;
      const site = `${siteBaseFor(s.origin)}/`;
      return {
        from: FROM, to: [s.email], reply_to: REPLY_TO, subject,
        headers: { "List-Unsubscribe": `<${unsub}>`, "List-Unsubscribe-Post": "List-Unsubscribe=One-Click" },
        html: shell(toSend.length === 1 ? "A new code just dropped" : "New codes just dropped",
          `<p style="margin:0 0 12px;line-height:1.6">Redeem ${toSend.length === 1 ? "it" : "them"} before ${toSend.length === 1 ? "it expires" : "they expire"}. Codes are case-sensitive.</p>${listHtml}
           <p style="margin:18px 0 0">${button(site, "See all working codes")}</p>`, unsub),
        text: `New Blue Lock Rivals code${toSend.length > 1 ? "s" : ""}:\n${listText}\n\nAll working codes: ${site}\nUnsubscribe: ${unsub}`,
      };
    });
    try {
      await sendEmails(batch);
      sent += batch.length;
    } catch (e) {
      console.error("batch failed", from, e);
    }
    if (subs.length < PAGE) break;
    from += PAGE;
  }
  await db.from("notified_codes").update({ recipients: sent }).in("code", toSend.map((c) => c.code.toUpperCase()));
  return json({ ok: true, codes: toSend.map((c) => c.code), sent }, 200, null);
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const origin = req.headers.get("origin");
  const route = url.pathname.replace(/^.*\/alerts/, "") || "/";
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(origin) });
  try {
    if (route === "/subscribe" && req.method === "POST") return await subscribe(req, origin);
    if (route === "/confirm" && req.method === "GET") return await confirm(url);
    if (route === "/unsubscribe") return await unsubscribe(req, url);
    if (route === "/notify" && req.method === "POST") return await notify();
    return json({ ok: false, error: "Not found" }, 404, origin);
  } catch (e) {
    console.error(e);
    return json({ ok: false, error: "Something went wrong. Please try again." }, 500, origin);
  }
});
