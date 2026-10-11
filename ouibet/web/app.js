"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => Math.round(n).toLocaleString("fr-FR");
const pct = (p) => `${Math.round(p * 100)}%`;
const chance = (p) => (p >= 0.1 ? `${Math.round(p * 100)} % de chances` : p > 0 ? `1 chance sur ${fmt(1 / p)}` : "-");
const RISK = {
  sur: { label: "Sûr", hint: "Passe plus de 6 fois sur 10. Petit gain." },
  modere: { label: "Modéré", hint: "Entre 1 chance sur 4 et 6 sur 10." },
  risque: { label: "Risqué", hint: "Entre 1 chance sur 20 et 1 sur 4." },
  tres_risque: { label: "Très risqué", hint: "Moins d'1 chance sur 20. Le gros lot, rarement." },
};
const FAMILY_LABEL = { "1x2": "1X2", dc: "Double chance", buts: "Buts +/-", btts: "Les 2 marquent", handicap: "Handicap", combo: "Combinés" };
const TZ = "Africa/Brazzaville";
const dayOf = (iso) => new Date(iso).toLocaleDateString("sv-SE", { timeZone: TZ });
const hour = (iso) => new Date(iso).toLocaleString("fr-FR", { timeZone: TZ, weekday: "short", hour: "2-digit", minute: "2-digit" });
const dayLabel = (d) => new Date(d + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });

const store = {
  get(k, d) { try { const v = localStorage.getItem("ouibet." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("ouibet." + k, JSON.stringify(v)); } catch {} },
};

let status = null;
let excluded = new Set(store.get("excluded", []));
let reports = {};
let lastCoupons = [];

async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || r.statusText);
  return j;
}

// ---------- navigation ----------
$$("nav.bottom button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  $$("nav.bottom button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + name));
  store.set("tab", name);
  if (name === "values") loadValues();
  if (name === "matches") loadMatches();
  if (name === "status") renderStatus();
  window.scrollTo(0, 0);
}

// ---------- formulaire ----------
function setupChips(id, multi, saved) {
  const box = $("#" + id);
  $$("button", box).forEach((b) => {
    b.classList.toggle("on", saved.includes(b.dataset.v));
    b.addEventListener("click", () => {
      if (multi) b.classList.toggle("on");
      else $$("button", box).forEach((x) => x.classList.toggle("on", x === b));
      if (multi && !$$("button.on", box).length) b.classList.add("on");
      saveForm();
    });
  });
}
function chipValues(id) { return $$(`#${id} button.on`).map((b) => b.dataset.v); }

function initForm() {
  $("#mise").value = store.get("mise", 10000);
  $("#families").innerHTML = Object.entries(FAMILY_LABEL).map(([k, v]) => `<button type="button" data-v="${k}">${v}</button>`).join("");
  setupChips("mode", false, [store.get("mode", "combine")]);
  setupChips("style", false, [store.get("style", "best")]);
  setupChips("period", false, [store.get("period", "all")]);
  $("#custom").value = store.get("custom", "");
  $("#custom").addEventListener("change", saveForm);
  setupChips("families", true, store.get("families", Object.keys(FAMILY_LABEL)));
  $("#maxOdds").value = store.get("maxOdds", 1.8);
  $("#maxOddsVal").textContent = $("#maxOdds").value;
  $("#refOnly").checked = store.get("refOnly", false);
  $("#keepSuspects").checked = store.get("keepSuspects", false);
  $("#maxOdds").addEventListener("input", () => { $("#maxOddsVal").textContent = $("#maxOdds").value; saveForm(); });
  ["mise", "refOnly", "keepSuspects"].forEach((id) => $("#" + id).addEventListener("change", saveForm));
  $("#form").addEventListener("submit", (e) => { e.preventDefault(); build(); });
}
function saveForm() {
  store.set("mise", +$("#mise").value || 10000);
  store.set("mode", chipValues("mode")[0] || "combine");
  store.set("style", chipValues("style")[0] || "best");
  store.set("custom", $("#custom").value);
  store.set("period", chipValues("period")[0] || "all");
  store.set("families", chipValues("families"));
  store.set("maxOdds", +$("#maxOdds").value);
  store.set("refOnly", $("#refOnly").checked);
  store.set("keepSuspects", $("#keepSuspects").checked);
}

function periodRange() {
  const today = new Date().toLocaleDateString("sv-SE", { timeZone: TZ });
  const add = (d, n) => { const x = new Date(d + "T12:00:00Z"); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
  const p = chipValues("period")[0] || "all";
  if (p === "today") return [today, today];
  if (p === "tomorrow") return [add(today, 1), add(today, 1)];
  if (p === "weekend") {
    const wd = new Date(today + "T12:00:00Z").getUTCDay();  // 0 = dimanche
    const sat = wd === 0 ? add(today, -1) : add(today, (6 - wd + 7) % 7);
    return [sat, add(sat, 1)];
  }
  return [null, null];
}

function query() {
  const [from, to] = periodRange();
  return {
    from, to,
    families: chipValues("families"),
    mode: chipValues("mode")[0],
    style: chipValues("style")[0],
    targets: +$("#custom").value > 1 ? [+$("#custom").value] : null,
    max_odds: +$("#maxOdds").value,
    ref_only: $("#refOnly").checked,
    keep_suspects: $("#keepSuspects").checked,
    exclude: [...excluded],
  };
}

// ---------- coupons ----------
async function build() {
  saveForm();
  const btn = $("#form .primary");
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Calcul...';
  try {
    const res = await api("/api/coupons", query());
    lastCoupons = res.coupons;
    renderCoupons(res);
  } catch (e) {
    $("#results").innerHTML = `<div class="card empty">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = "Voir les possibilités";
  }
}

function renderExcluded() {
  const box = $("#excluded");
  box.hidden = !excluded.size;
  box.innerHTML = `${excluded.size} match(s) retiré(s) par toi. <button id="resetExcl">Tout remettre</button>`;
  $("#resetExcl")?.addEventListener("click", () => { excluded.clear(); store.set("excluded", []); renderExcluded(); build(); });
}

function legHTML(l) {
  const e = l.event;
  const v = l.value - 1;
  const r = reports[l.key];
  const src = l.src === "marché" ? "réf. marché" : l.src === "modèle" ? "modèle" : "cote PremierBet";
  return `<li class="leg">
    <div class="row"><span class="match">${esc(e.home)} - ${esc(e.away)}</span>
      <span><span class="odds">${l.odds.toFixed(2)}</span><button class="x" data-key="${esc(l.key)}" title="Retirer ce match">×</button></span></div>
    <div class="meta">${esc(hour(e.start))} · ${esc(e.league)}</div>
    <div class="pick">${esc(l.label)}</div>
    <div class="badges">
      <span class="badge">vraie chance ${pct(l.p)}</span>
      ${l.src !== "PremierBet" ? `<span class="badge ${v > 0.01 ? "good" : v < -0.03 ? "bad" : ""}">valeur ${v >= 0 ? "+" : ""}${Math.round(v * 100)}%</span>` : ""}
      <span class="badge">${src}</span>
    </div>
    ${r ? `<div class="news ${esc(r.niveau)}"><b>${esc(r.niveau.toUpperCase())}</b> ${esc(r.resume)}
      ${r.absents?.length ? `<br>Absents : ${esc(r.absents.join(", "))}` : ""}
      <br>${esc(r.impact_pari)}${r.compo_officielle ? " (compo officielle sortie)" : ""}</div>` : ""}
  </li>`;
}

function renderCoupons(res) {
  renderExcluded();
  const mise = +$("#mise").value || 10000;
  const box = $("#results");
  box.innerHTML = "";
  if (!res.candidates) {
    box.innerHTML = `<div class="card empty">Aucun pari disponible pour cette période. ${status?.scanning ? "Le scan est en cours, réessaie dans un instant." : ""}</div>`;
    return;
  }
  const possible = res.coupons.filter((x) => x.coupon);
  const impossible = res.coupons.filter((x) => !x.coupon).map((x) => `x${x.target}`);
  if (!possible.length) {
    box.innerHTML = `<div class="card empty">Aucune combinaison possible avec ces réglages.</div>`;
    return;
  }
  let currentRisk = null;
  for (const item of possible) {
    const c = item.coupon;
    if (c.risk !== currentRisk) {
      currentRisk = c.risk;
      const h = document.createElement("div");
      h.className = `risk-title risk-${c.risk}`;
      h.innerHTML = `<b>${RISK[c.risk].label}</b><span>${RISK[c.risk].hint}</span>`;
      box.appendChild(h);
    }
    const node = $("#tpl-coupon").content.firstElementChild.cloneNode(true);
    node.classList.add(`risk-${c.risk}`);
    $(".target", node).textContent = `Cote ${c.odds.toFixed(2)}`;
    $(".gain", node).textContent = `${fmt(mise * c.odds)} FCFA`;
    $(".chance", node).textContent = chance(c.p);
    $(".count", node).textContent = c.legs.length === 1 ? "1 match" : `${c.legs.length} matchs`;
    $(".legs", node).innerHTML = c.legs.map(legHTML).join("");
    const ev = c.p * c.odds - 1;
    $(".sum", node).innerHTML = `${fmt(mise)} FCFA misés → <b>${fmt(mise * c.odds)} FCFA</b> si ça passe<br>
      Le bookmaker la paie comme ${chance(c.p_book)} · espérance ${ev >= 0 ? "+" : ""}${Math.round(ev * 100)}%`;
    const newsBtn = $(".news-btn", node);
    if (!status?.keys?.news) { newsBtn.title = "Ajoute ANTHROPIC_API_KEY pour activer"; newsBtn.disabled = true; }
    newsBtn.addEventListener("click", () => checkNews(c, newsBtn));
    $(".copy-btn", node).addEventListener("click", (e) => copyCoupon(item, mise, e.target));
    if (navigator.share) {
      const s = $(".share-btn", node); s.hidden = false;
      s.addEventListener("click", () => navigator.share({ text: couponText(item, mise) }).catch(() => {}));
    }
    box.appendChild(node);
  }
  if (impossible.length) {
    const p = document.createElement("p");
    p.className = "fine";
    p.textContent = `Impossible avec ces réglages : ${impossible.join(", ")}.`;
    box.appendChild(p);
  }
  $$(".leg .x", box).forEach((b) => b.addEventListener("click", () => {
    excluded.add(b.dataset.key); store.set("excluded", [...excluded]); build();
  }));
}

function couponText(item, mise) {
  const c = item.coupon;
  const lines = c.legs.map((l) => `• ${l.event.home} - ${l.event.away} (${hour(l.event.start)}) : ${l.label} @ ${l.odds.toFixed(2)}`);
  return `Coupon ouibet (${RISK[c.risk].label})\n${lines.join("\n")}\nCote ${c.odds.toFixed(2)} · ${fmt(mise)} FCFA → ${fmt(mise * c.odds)} FCFA\nVraie chance : ${chance(c.p)}`;
}
async function copyCoupon(item, mise, btn) {
  try { await navigator.clipboard.writeText(couponText(item, mise)); btn.textContent = "Copié"; }
  catch { btn.textContent = "Copie impossible"; }
  setTimeout(() => (btn.textContent = "Copier"), 1500);
}

async function checkNews(c, btn) {
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Recherche...';
  try {
    const res = await api("/api/news", { keys: c.legs.map((l) => l.key) });
    Object.assign(reports, res.reports);
    const danger = c.legs.filter((l) => reports[l.key]?.niveau === "danger");
    renderCoupons({ coupons: lastCoupons, candidates: 1 });
    if (danger.length) {
      danger.forEach((l) => excluded.add(l.key));
      store.set("excluded", [...excluded]);
      banner(`${danger.length} match(s) en DANGER retiré(s), coupons reconstruits.`);
      build();
    }
  } catch (e) { banner(e.message); btn.disabled = false; btn.textContent = "Vérifier les news"; }
}

// ---------- valeurs ----------
async function loadValues() {
  const box = $("#values");
  box.innerHTML = '<div class="empty"><span class="spinner"></span></div>';
  try {
    const { values } = await api("/api/values", { ...query(), exclude: [] });
    box.innerHTML = values.length
      ? `<div class="card"><ol class="legs">${values.map(legHTML).join("")}</ol></div>`
      : `<div class="card empty">Aucune valeur détectée pour l'instant. Il faut une référence marché : ajoute ODDS_API_KEY ou attends le vendredi.</div>`;
    $$(".x", box).forEach((b) => b.remove());
  } catch (e) { box.innerHTML = `<div class="card empty">${esc(e.message)}</div>`; }
}

// ---------- matchs ----------
let allMatches = [];
let currentDay = null;
async function loadMatches() {
  const { matches } = await api("/api/matches");
  allMatches = matches;
  const days = [...new Set(matches.map((m) => dayOf(m.start)))];
  if (!days.includes(currentDay)) currentDay = days[0];
  $("#days").innerHTML = days.map((d) => `<button data-v="${d}" class="${d === currentDay ? "on" : ""}">${dayLabel(d)}</button>`).join("");
  $$("#days button").forEach((b) => b.addEventListener("click", () => { currentDay = b.dataset.v; loadMatches(); }));
  renderMatches();
}
function renderMatches() {
  const q = $("#search").value.trim().toLowerCase();
  const ms = allMatches.filter((m) => dayOf(m.start) === currentDay && (!q || `${m.home} ${m.away} ${m.league}`.toLowerCase().includes(q)));
  const byLeague = {};
  ms.forEach((m) => (byLeague[m.league] ||= []).push(m));
  const order = Object.keys(byLeague).sort((a, b) => (byLeague[b].some((m) => m.ref) - byLeague[a].some((m) => m.ref)) || a.localeCompare(b));
  $("#matches").innerHTML = order.map((lg) => `<div class="day-title">${esc(lg)}</div><div class="card">${byLeague[lg].map(matchRow).join("")}</div>`).join("")
    || `<div class="card empty">Aucun match.</div>`;
}
function matchRow(m) {
  const cell = (k) => `<span>${m.odds[k].toFixed(2)}${m.ref ? `<small>${pct(m.ref.p[k])}</small>` : ""}</span>`;
  return `<div class="mrow"><div class="teams">${esc(m.home)}<br>${esc(m.away)}</div>
    <div class="odds3">${cell("1")}${cell("X")}${cell("2")}</div>
    <div class="meta">${esc(hour(m.start))}${m.ref ? ` · réf. ${esc(m.ref.src)}` : ""}${m.suspect ? " · cote suspecte (news ?)" : ""}</div></div>`;
}
$("#search").addEventListener("input", renderMatches);

// ---------- état ----------
let builtFor = null;  // date du scan pour lequel les possibilités sont affichées
async function refreshStatus() {
  try { status = await api("/api/status"); } catch { return; }
  // en arrivant (et après chaque nouveau scan), les possibilités s'affichent toutes seules
  if (status.scanned_at && status.scanned_at !== builtFor && !status.scanning) {
    builtFor = status.scanned_at;
    build();
  }
  const b = $("#banner");
  if (status.scanning) { b.hidden = false; b.innerHTML = `<span class="spinner"></span> ${esc(status.progress || "Scan en cours...")}`; }
  else if (status.error) { b.hidden = false; b.textContent = `Dernier scan en erreur : ${status.error}`; }
  else if (!status.scanned_at) { b.hidden = false; b.textContent = "Premier scan en cours..."; }
  else b.hidden = true;
  if ($("#tab-status").classList.contains("active")) renderStatus();
}
function banner(msg) { const b = $("#banner"); b.hidden = false; b.textContent = msg; setTimeout(() => (b.hidden = true), 5000); }
function renderStatus() {
  if (!status) return;
  const s = status;
  const ago = s.scanned_at ? `${Math.round((Date.now() - new Date(s.scanned_at)) / 60000)} min` : "jamais";
  $("#status").innerHTML = `<div class="card"><dl class="kv">
    <dt>Dernier scan</dt><dd>il y a ${ago}</dd>
    <dt>Scan automatique</dt><dd>toutes les ${s.scan_minutes} min</dd>
    <dt>Période scannée</dt><dd>${s.window ? `${esc(s.window[0])} → ${esc(s.window[1])}` : "-"}</dd>
    <dt>Matchs PremierBet</dt><dd>${s.matches}</dd>
    <dt>Avec référence marché</dt><dd>${s.with_ref} (${s.live_ref} en direct)</dd>
    <dt>Suspects (cote bougée)</dt><dd>${s.suspects}</dd>
    <dt>Paris évalués</dt><dd>${fmt(s.legs)}</dd>
  </dl></div>
  <div class="card"><dl class="kv">
    <dt>Référence en direct (The Odds API)</dt><dd>${s.keys.odds_api ? `active${s.odds_api_remaining != null ? ` · ${esc(s.odds_api_remaining)} crédits` : ""}` : "inactive"}</dd>
    <dt>News IA</dt><dd>${s.keys.news ? "active" : "inactive"}</dd>
  </dl>${!s.keys.odds_api || !s.keys.news ? `<p class="intro">Les clés se mettent dans le fichier <code>.env</code> du moteur (voir README).</p>` : ""}</div>`;
}
$("#refresh").addEventListener("click", async () => { await api("/api/refresh", {}); setTimeout(refreshStatus, 500); });

// ---------- démarrage ----------
initForm();
showTab(store.get("tab", "coupon"));
refreshStatus();
setInterval(refreshStatus, 5000);
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
