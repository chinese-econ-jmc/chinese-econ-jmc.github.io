/* Light / dark / auto theme. Loaded in <head> so the choice applies before first paint.
   "auto" follows the OS setting; an explicit choice is stored per browser. */
(function () {
  var KEY = "jmc-theme", root = document.documentElement;
  function get() { try { return localStorage.getItem(KEY) || "auto"; } catch (e) { return "auto"; } }
  function apply(t) { if (t === "light" || t === "dark") root.setAttribute("data-theme", t); else root.removeAttribute("data-theme"); }
  apply(get());
  document.addEventListener("DOMContentLoaded", function () {
    function mark() {
      var t = get();
      document.querySelectorAll("[data-theme-set]").forEach(function (b) {
        var on = b.getAttribute("data-theme-set") === t;
        b.classList.toggle("active", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }
    mark();
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-theme-set]");
      if (!b) return;
      var t = b.getAttribute("data-theme-set");
      try { localStorage.setItem(KEY, t); } catch (err) { /* storage unavailable: applies to this page only */ }
      apply(t);
      mark();
    });
  });
})();
