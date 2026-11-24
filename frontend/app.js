/* TripPilot web app: chat with the agent, render result cards, trips and price alerts. */
(() => {
  "use strict";

  // ---------- helpers ----------
  const $ = (sel) => document.querySelector(sel);

  function storage(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (_) { /* private mode: fall back to memory */ }
    return null;
  }

  const deviceId = (() => {
    let id = storage("tp_device");
    if (!id) {
      id = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
      storage("tp_device", id);
    }
    return id;
  })();
  let sessionId = null; // a page load starts a fresh conversation

  /** el("div", {class: "x", onclick: fn}, "text", childNode) */
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else if (k === "class") node.className = v;
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  function safeUrl(url) {
    try {
      const u = new URL(url, location.href);
      return u.protocol === "https:" || u.protocol === "http:" ? u.href : null;
    } catch (_) { return null; }
  }

  function bookLink(url, label, primary) {
    const href = safeUrl(url);
    if (!href) return null;
    return el("a", {
      class: "btn" + (primary ? " primary grow" : ""), href, target: "_blank", rel: "sponsored noopener",
    }, label || "Book");
  }

  function money(price, currency) {
    if (price == null) return "";
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "AUD", maximumFractionDigits: 0 }).format(price);
    } catch (_) { return `${currency || ""} ${price}`; }
  }

  function when(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  function duration(mins) {
    if (!mins) return "";
    return `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, "0")}m`;
  }

  let toastTimer;
  function toast(text) {
    const t = $("#toast");
    t.textContent = text;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 2500);
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", "X-Device-Id": deviceId, ...(options.headers || {}) },
    });
    if (res.status === 204) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = Array.isArray(data.detail) ? "Please check the details and try again." : data.detail;
      throw new Error(detail || `Request failed (${res.status})`);
    }
    return data;
  }

  // ---------- chat ----------
  const log = $("#log");
  const input = $("#q");
  const form = $("#composer");
  const sendBtn = form.querySelector(".send");

  // Small, safe markdown renderer: escapes everything first, then adds bold, italics,
  // code, http(s) links, lists and paragraphs. No external library needed.
  function escapeHtml(str) {
    return str.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function inline(str) {
    return str
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*(?!\s)(.+?)\*/g, "$1<em>$2</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  }
  function markdown(text) {
    let html = "", list = null, para = [];
    const flushPara = () => { if (para.length) { html += "<p>" + inline(para.join("<br>")) + "</p>"; para = []; } };
    const flushList = () => {
      if (list) { html += `<${list.tag}>` + list.items.map((i) => "<li>" + inline(i) + "</li>").join("") + `</${list.tag}>`; list = null; }
    };
    for (const line of escapeHtml(text).split("\n")) {
      const ul = line.match(/^\s*[-*]\s+(.*)/), ol = line.match(/^\s*\d+[.)]\s+(.*)/), h = line.match(/^#{1,6}\s+(.*)/);
      if (ul || ol) {
        flushPara();
        const tag = ul ? "ul" : "ol";
        if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
        list.items.push((ul || ol)[1]);
      } else if (h) { flushPara(); flushList(); html += "<p><strong>" + inline(h[1]) + "</strong></p>"; }
      else if (!line.trim()) { flushPara(); flushList(); }
      else { flushList(); para.push(line); }
    }
    flushPara(); flushList();
    return html;
  }

  function renderMarkdown(text) {
    const box = el("div", { class: "msg bot" });
    box.innerHTML = markdown(text);
    return box;
  }

  function scrollDown(node) { node.scrollIntoView({ behavior: "smooth", block: "end" }); }

  function setChatting(on) {
    $("#home").hidden = on;
    $("#new-chat").hidden = !on;
  }

  async function quickSave(item, button) {
    button.disabled = true;
    try {
      await api("/api/trips/quick-save", { method: "POST", body: JSON.stringify(item) });
      button.textContent = "Saved";
      toast("Saved to My trips");
    } catch (e) {
      button.disabled = false;
      toast(e.message);
    }
  }

  function saveButton(item) {
    const b = el("button", { class: "btn ghost", type: "button" }, "Save");
    b.addEventListener("click", () => quickSave(item, b));
    return b;
  }

  function flightCard(card) {
    const wrap = el("div", { class: "results" },
      el("div", { class: "results-head" },
        el("span", { class: "results-title" }, card.title),
        el("span", { class: "results-sub" }, card.one_way ? "One way" : "Return")));

    card.results.forEach((f, i) => {
      const stops = f.stops === 0 ? "Direct" : f.stops == null ? "" : `${f.stops} stop${f.stops > 1 ? "s" : ""}`;
      const meta = [stops, duration(f.duration_minutes)].filter(Boolean).join(" · ");
      const item = {
        kind: "flight",
        title: `${f.from} → ${f.to}${f.airline ? " · " + f.airline : ""}`,
        date: f.departure_at, price: f.price, currency: f.currency, link: f.booking_link,
        details: { airline: f.airline, flight_number: f.flight_number, stops: f.stops, return_at: f.return_at },
      };
      wrap.append(el("div", { class: "card" + (i === 0 ? " best" : "") },
        i === 0 ? el("span", { class: "badge" }, "Best value") : null,
        el("div", { class: "row" },
          el("div", { class: "stack" },
            el("span", { class: "strong" }, `${f.airline || "Airline"}${f.flight_number ? " " + f.flight_number : ""}`),
            el("span", { class: "muted" }, when(f.departure_at)),
            meta ? el("span", { class: "muted" }, meta) : null,
            f.return_at ? el("span", { class: "muted" }, "Return " + when(f.return_at)) : null),
          el("div", { class: "price" }, el("small", {}, "from"), money(f.price, f.currency))),
        el("div", { class: "actions" }, bookLink(f.booking_link, "Book", true), saveButton(item))));
    });
    if (card.note) wrap.append(el("p", { class: "note" }, card.note));
    return wrap;
  }

  function hotelCard(card) {
    const wrap = el("div", { class: "results" },
      el("div", { class: "results-head" },
        el("span", { class: "results-title" }, card.title),
        el("span", { class: "results-sub" }, card.subtitle || "")));

    card.results.forEach((h, i) => {
      const facts = [
        h.distance_km != null ? `${h.distance_km} km away` : null,
        h.rating ? `Rating ${h.rating}` : null,
        h.free_cancellation ? "Free cancellation" : null,
      ].filter(Boolean).join(" · ");
      const item = {
        kind: "hotel", title: h.name || "Hotel", date: card.subtitle,
        price: h.price_total, currency: h.currency, link: h.booking_link, details: { area: h.area, stars: h.stars },
      };
      wrap.append(el("div", { class: "card" + (i === 0 ? " best" : "") },
        el("div", { class: "row" },
          el("div", { class: "stack" },
            el("span", { class: "strong" }, h.name || "Hotel"),
            facts ? el("span", { class: "muted" }, facts) : null),
          el("div", { class: "price" }, money(h.price_total, h.currency))),
        el("div", { class: "actions" }, bookLink(h.booking_link, "Book", true), saveButton(item))));
    });

    wrap.append(el("div", { class: "card" },
      el("span", { class: "muted" }, card.results.length ? "Want more choice?" : "See live availability and prices for your dates."),
      el("div", { class: "actions" }, bookLink(card.search_link, card.search_label || "See hotels", true))));
    return wrap;
  }

  function extrasCard(card) {
    const wrap = el("div", { class: "results" }, el("span", { class: "results-title" }, card.title));
    card.results.forEach((x) => {
      wrap.append(el("div", { class: "card" },
        el("div", { class: "row" },
          el("span", { class: "strong" }, x.label),
          bookLink(x.link, "Open"))));
    });
    return wrap;
  }

  function alertCard(card) {
    const a = card.alert;
    const dates = a.return_month ? `${a.depart_month} to ${a.return_month}` : a.depart_month;
    return el("div", { class: "card" },
      el("span", { class: "badge ok" }, card.title),
      el("span", {}, `${a.origin} → ${a.destination}, ${dates}. We'll tell you when it's ${money(a.target_price, a.currency)} or less.`),
      el("a", { href: "#alerts" }, "Manage alerts"));
  }

  const CARD_RENDERERS = { flights: flightCard, hotels: hotelCard, extras: extrasCard, alert: alertCard };

  async function send(text) {
    text = text.trim();
    if (!text) return;
    setChatting(true);
    log.append(el("div", { class: "msg user" }, text));
    const typing = el("div", { class: "msg bot", "aria-label": "TripPilot is searching" },
      el("span", { class: "typing" }, el("span"), el("span"), el("span")));
    log.append(typing);
    scrollDown(typing);
    sendBtn.disabled = true;

    try {
      const data = await api("/api/chat", { method: "POST", body: JSON.stringify({ message: text, session_id: sessionId }) });
      sessionId = data.session_id;
      typing.replaceWith(renderMarkdown(data.reply));
      let last = log.lastElementChild;
      for (const card of data.cards || []) {
        const render = CARD_RENDERERS[card.type];
        if (!render) continue;
        last = render(card);
        log.append(last);
      }
      scrollDown(last);
    } catch (e) {
      typing.replaceWith(el("div", { class: "msg bot error" }, e.message || "Something went wrong. Please try again."));
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value;
    input.value = "";
    autosize();
    send(text);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; }
  input.addEventListener("input", autosize);

  document.querySelectorAll("[data-send]").forEach((b) => b.addEventListener("click", () => send(b.textContent)));
  document.querySelectorAll("[data-starter]").forEach((b) => b.addEventListener("click", () => {
    input.value = b.dataset.starter;
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }));
  $("#new-chat").addEventListener("click", () => {
    sessionId = null;
    log.replaceChildren();
    setChatting(false);
    input.focus();
  });

  // ---------- trips ----------
  async function loadTrips() {
    const box = $("#trips");
    box.replaceChildren(el("p", { class: "empty" }, "Loading…"));
    try {
      const trips = await api("/api/trips");
      box.replaceChildren();
      const withItems = trips.filter((t) => t.items.length);
      if (!withItems.length) {
        box.append(el("p", { class: "empty" }, "No trips yet. Search for a flight or hotel and tap Save."));
        return;
      }
      for (const trip of withItems) {
        if (withItems.length > 1 || trip.name !== "My trips") box.append(el("h2", { class: "section-label" }, trip.name));
        for (const item of trip.items) box.append(tripItem(item));
      }
    } catch (e) {
      box.replaceChildren(el("p", { class: "error" }, e.message));
    }
  }

  const KIND_ICONS = {
    flight: '<path d="M2 16l20-8-8 14-2-6z"/>',
    hotel: '<path d="M3 20V6M3 16h18v4M21 16v-4a3 3 0 0 0-3-3h-7v7"/><circle cx="7" cy="12" r="2"/>',
    car_rental: '<path d="M5 17h14v-5l-2-5H7l-2 5zM5 12h14"/><circle cx="8" cy="17" r="2"/><circle cx="16" cy="17" r="2"/>',
    transfer: '<path d="M4 7h16v10H4zM8 17v2M16 17v2M9 4h6v3H9z"/>',
    esim: '<path d="M7 3h7l4 4v14H7zM10 11h5v6h-5z"/>',
    insurance: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
  };
  function kindIcon(kind) {
    const span = el("div", { class: "icon", "aria-hidden": "true" });
    // Constant SVG markup from KIND_ICONS only (never user data).
    span.innerHTML = `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${KIND_ICONS[kind] || '<path d="M4 8h16v12H4zM9 8V5h6v3"/>'}</svg>`;
    return span;
  }

  function tripItem(item) {
    const status = item.status === "booked"
      ? el("span", { class: "badge ok" }, "Booked")
      : item.status === "cancelled" ? el("span", { class: "badge" }, "Cancelled") : el("span", { class: "badge" }, "Saved");

    const markBooked = el("button", { class: "btn ghost", type: "button" }, item.status === "booked" ? "Mark saved" : "I booked it");
    markBooked.addEventListener("click", async () => {
      try {
        await api(`/api/trips/items/${item.id}`, { method: "PATCH", body: JSON.stringify({ status: item.status === "booked" ? "saved" : "booked" }) });
        loadTrips();
      } catch (e) { toast(e.message); }
    });
    const remove = el("button", { class: "btn ghost", type: "button", "aria-label": `Remove ${item.title}` }, "Remove");
    remove.addEventListener("click", async () => {
      try { await api(`/api/trips/items/${item.id}`, { method: "DELETE" }); loadTrips(); } catch (e) { toast(e.message); }
    });

    return el("div", { class: "card trip-item" },
      el("div", { class: "row" },
        kindIcon(item.kind),
        el("div", { class: "stack", style: "flex:1" },
          el("span", { class: "strong" }, item.title),
          el("span", { class: "muted" }, [when(item.date) || item.date, money(item.price, item.currency)].filter(Boolean).join(" · "))),
        status),
      el("div", { class: "actions" },
        item.status !== "booked" ? bookLink(item.link, "Book", true) : null, markBooked, remove));
  }

  // ---------- alerts ----------
  async function loadAlerts() {
    const box = $("#alerts");
    try {
      const alerts = await api("/api/alerts");
      box.replaceChildren();
      if (!alerts.length) { box.append(el("p", { class: "empty" }, "No alerts yet.")); return; }
      for (const a of alerts) {
        const del = el("button", { class: "btn ghost", type: "button", "aria-label": `Delete alert ${a.origin} to ${a.destination}` }, "Delete");
        del.addEventListener("click", async () => {
          try { await api(`/api/alerts/${a.id}`, { method: "DELETE" }); loadAlerts(); } catch (e) { toast(e.message); }
        });
        const state = a.triggered_at
          ? el("span", { class: "badge ok" }, "Price dropped")
          : el("span", { class: "badge" }, "Watching");
        const dates = a.return_month ? `${a.depart_month} to ${a.return_month}` : `${a.depart_month}, one way`;
        box.append(el("div", { class: "card" },
          el("div", { class: "row" },
            el("div", { class: "stack" },
              el("span", { class: "strong" }, `${a.origin} → ${a.destination}`),
              el("span", { class: "muted" }, `${dates} · below ${money(a.target_price, a.currency)}`),
              a.last_price != null ? el("span", { class: "muted" }, `Last seen ${money(a.last_price, a.currency)}`) : null),
            state),
          el("div", { class: "actions" }, del)));
      }
    } catch (e) {
      box.replaceChildren(el("p", { class: "error" }, e.message));
    }
  }

  const alertForm = $("#alert-form");
  const alertError = $("#alert-error");
  alertForm.addEventListener("input", () => { alertError.textContent = ""; });
  alertForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(alertForm);
    const body = {
      origin: String(f.get("origin") || "").trim().toUpperCase(),
      destination: String(f.get("destination") || "").trim().toUpperCase(),
      depart_month: String(f.get("depart_month") || ""),
      return_month: String(f.get("return_month") || "") || null,
      target_price: Number(f.get("target_price")),
      email: String(f.get("email") || "").trim() || null,
    };
    if (!/^[A-Z]{3}$/.test(body.origin) || !/^[A-Z]{3}$/.test(body.destination)) {
      alertError.textContent = "Enter 3-letter codes for From and To, e.g. PER and DPS."; return;
    }
    if (!/^\d{4}-\d{2}$/.test(body.depart_month)) { alertError.textContent = "Choose a departure month."; return; }
    if (!(body.target_price > 0)) { alertError.textContent = "Enter the price you want to be alerted below."; return; }
    try {
      await api("/api/alerts", { method: "POST", body: JSON.stringify(body) });
      alertForm.reset();
      toast("Alert created");
      loadAlerts();
    } catch (err) { alertError.textContent = err.message; }
  });

  // ---------- tabs ----------
  const VIEWS = { ask: "#view-ask", trips: "#view-trips", alerts: "#view-alerts" };
  function route() {
    const tab = VIEWS[location.hash.slice(1)] ? location.hash.slice(1) : "ask";
    for (const [name, sel] of Object.entries(VIEWS)) $(sel).hidden = name !== tab;
    document.querySelectorAll(".tabbar a").forEach((a) => {
      if (a.dataset.tab === tab) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    if (tab === "trips") loadTrips();
    if (tab === "alerts") loadAlerts();
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);
  route();
})();
