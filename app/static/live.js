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
    if (typeof data.shelf_alerts_html === "string") {
      const alerts = document.querySelector("[data-live-shelf-alerts]");
      if (alerts) alerts.outerHTML = data.shelf_alerts_html;
    }
  }

  function tick() {
    if (document.hidden) return;
    fetch(url, {
      headers: { Accept: "application/json", "X-Setuora-Background": "true" },
    })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (d) {
        if (d) apply(d);
      })
      .catch(function () {});
  }

  setInterval(tick, INTERVAL);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) tick();
  });
})();
