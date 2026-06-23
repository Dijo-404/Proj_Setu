// Auto-save helper. Two modes, driven by data attributes:
//   form[data-autosave="<url>"]  -> debounced POST of the form to <url> (existing records -> DB).
//   form[data-draft="<key>"]     -> debounced save of fields to localStorage (creation forms).
// Fields marked [data-no-autosave] are skipped (e.g. the Tally-sync toggle, which must
// only change via the explicit Save button so the readiness gate is preserved).
// Pattern mirrors app/static/scanner.js (fetch + FormData + JSON {ok,error}).

(function () {
  const DEBOUNCE = 600;

  function debounce(fn, ms) {
    let timer;
    return function () {
      clearTimeout(timer);
      timer = setTimeout(fn, ms);
    };
  }

  function statusNode(form) {
    let el = form.querySelector("[data-autosave-status]");
    if (!el) {
      el = document.createElement("span");
      el.setAttribute("data-autosave-status", "");
      el.className = "autosave-status";
      form.appendChild(el);
    }
    return el;
  }

  function setStatus(el, text, kind) {
    el.textContent = text;
    el.className = "autosave-status " + (kind || "");
  }

  function fields(form) {
    return form.querySelectorAll("input, select, textarea");
  }

  function initDbAutosave(form) {
    const url = form.getAttribute("data-autosave");
    const status = statusNode(form);
    const save = debounce(function () {
      const data = new FormData();
      fields(form).forEach(function (field) {
        if (!field.name || field.hasAttribute("data-no-autosave")) return;
        if ((field.type === "checkbox" || field.type === "radio") && !field.checked) return;
        data.append(field.name, field.value);
      });
      setStatus(status, "Saving…", "saving");
      fetch(url, { method: "POST", body: data, headers: { Accept: "application/json" } })
        .then(function (r) { return r.json().catch(function () { return { ok: r.ok }; }); })
        .then(function (p) { setStatus(status, p.ok ? "Saved ✓" : (p.error || "Save failed"), p.ok ? "ok" : "error"); })
        .catch(function () { setStatus(status, "Save failed", "error"); });
    }, DEBOUNCE);
    fields(form).forEach(function (field) {
      if (field.hasAttribute("data-no-autosave")) return;
      field.addEventListener("input", save);
      field.addEventListener("change", save);
    });
  }

  function initDraft(form) {
    const key = form.getAttribute("data-draft");
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) { saved = {}; }
    Object.keys(saved).forEach(function (name) {
      const field = form.elements[name];
      if (field && !field.value) field.value = saved[name];
    });
    const status = statusNode(form);
    const save = debounce(function () {
      const draft = {};
      fields(form).forEach(function (field) {
        if (field.name && field.type !== "password") draft[field.name] = field.value;
      });
      try {
        localStorage.setItem(key, JSON.stringify(draft));
        setStatus(status, "Draft saved", "ok");
      } catch (e) { /* storage full / disabled */ }
    }, DEBOUNCE);
    fields(form).forEach(function (field) {
      field.addEventListener("input", save);
      field.addEventListener("change", save);
    });
    form.addEventListener("submit", function () {
      try { localStorage.removeItem(key); } catch (e) { /* ignore */ }
    });
  }

  function init() {
    document.querySelectorAll("form[data-autosave]").forEach(initDbAutosave);
    document.querySelectorAll("form[data-draft]").forEach(initDraft);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
