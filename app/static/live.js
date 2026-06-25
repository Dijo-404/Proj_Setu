// Live dashboard refresh. Polls the JSON endpoint named by [data-live-url] and
// updates metric numbers + the recent tables in place, so concurrent mobile and
// desktop users see fresh data without a manual reload. Pauses while the tab is
// hidden. Read-only — there are no editable fields on the dashboard to clobber.

(function () {
  const root = document.querySelector("[data-live-url]");
  if (!root) return;
  const url = root.getAttribute("data-live-url");
  const INTERVAL = 20000;

  function apply(data) {
    if (data.counts) {
      Object.keys(data.counts).forEach(function (key) {
        const el = document.querySelector('[data-metric="' + key + '"]');
        if (el) el.textContent = data.counts[key];
      });
    }
    if (typeof data.charts_html === "string") {
      const charts = document.querySelector("[data-live-charts]");
      if (charts) charts.outerHTML = data.charts_html;
    }
    if (typeof data.expiry_html === "string") {
      const expiry = document.querySelector("[data-live-expiry]");
      if (expiry) expiry.outerHTML = data.expiry_html;
    }
    if (typeof data.batches_html === "string") {
      const tbody = document.querySelector("[data-live-batches]");
      if (tbody) tbody.innerHTML = data.batches_html;
    }
    if (typeof data.scans_html === "string") {
      const tbody = document.querySelector("[data-live-scans]");
      if (tbody) tbody.innerHTML = data.scans_html;
    }
  }

  function tick() {
    if (document.hidden) return;
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d) apply(d); })
      .catch(function () { /* transient network error; try again next tick */ });
  }

  setInterval(tick, INTERVAL);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) tick();
  });
})();
