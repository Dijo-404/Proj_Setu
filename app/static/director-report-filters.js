(function () {
  document.querySelectorAll("[data-director-stock-filter]").forEach(function (form) {
    const select = form.querySelector("select");
    if (!select) return;
    select.addEventListener("change", function () {
      form.requestSubmit();
    });
  });
})();
