/* Static ASCII art banner for re-terminal: optional effects only.
   Colours are already in the HTML. This script sizes the art to the exact
   page width and adds a hover trail and click ripple. If it fails to load,
   the banner still shows in full colour. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function mount(root) {
    try { init(root); } catch (e) { console.warn("[ascii-banner]", e); }
  }
  document.querySelectorAll("[data-ascii-banner]").forEach(mount);
  window.asciiBanner = { mount: mount };   // call again after swapping banners by hand

  function init(root) {
    var pre = root.querySelector("pre.ascii-banner__art");
    if (!pre || pre.hasAttribute("data-ab-ready")) return;
    pre.setAttribute("data-ab-ready", "");
    var cells = [[]];            // cells[r][c] -> span
    var where = new WeakMap();   // span -> [r, c]
    var cols = 0;

    // Split each coloured run into one span per character (same class) and
    // record each character's row and column.
    var r = 0, c = 0, frag = document.createDocumentFragment();
    Array.prototype.slice.call(pre.childNodes).forEach(function (node) {
      var text = node.textContent, cls = node.nodeType === 1 ? node.className : "";
      for (var i = 0; i < text.length; i++) {
        var ch = text[i];
        if (ch === "\n") { frag.appendChild(document.createTextNode("\n")); r++; c = 0; cells[r] = []; continue; }
        if (ch === " " || !cls) { frag.appendChild(document.createTextNode(ch)); c++; continue; }
        var s = document.createElement("span");
        s.className = cls;
        s.textContent = ch;
        cells[r][c] = s;
        where.set(s, [r, c]);
        frag.appendChild(s);
        c++;
        if (c > cols) cols = c;
      }
    });
    pre.textContent = "";
    pre.appendChild(frag);
    cols = Math.max(cols, parseInt(getComputedStyle(pre).getPropertyValue("--ab-cols"), 10) || 0);

    function fit() {
      var probe = document.createElement("span");
      probe.textContent = "MMMMMMMMMM";
      probe.style.cssText = "position:absolute;visibility:hidden;font-size:100px";
      pre.appendChild(probe);
      var ratio = probe.getBoundingClientRect().width / 1000;
      pre.removeChild(probe);
      var maxFs = parseFloat(getComputedStyle(root).getPropertyValue("--ab-max-fs")) || 16;
      var fs = Math.min(maxFs, root.clientWidth / (cols * (ratio || 0.6)));
      pre.style.setProperty("font-size", Math.floor(fs * 100) / 100 + "px", "important");
    }

    function hi() {
      return getComputedStyle(root).getPropertyValue("--ab-hi").trim() || "#ff6266";
    }

    function flash(span, delay, strength, color) {
      if (!span || !span.animate) return;
      span.animate(
        [
          { color: strength > 0.6 ? "#fff" : color, textShadow: "0 0 " + (6 * strength).toFixed(1) + "px " + color },
          { color: color, offset: 0.25 },
          {}
        ],
        { duration: 700 + 500 * strength, delay: delay || 0, easing: "ease-out" }
      );
    }

    function hoverTrail(span) {
      var rc = where.get(span);
      if (!rc) return;
      var color = hi();
      flash(span, 0, 1, color);
      if (reduceMotion.matches) return;
      [[0, -1], [0, 1], [-1, 0], [1, 0]].forEach(function (d) {
        var row = cells[rc[0] + d[0]];
        flash(row && row[rc[1] + d[1]], 40, 0.4, color);
      });
    }

    function ripple(span) {
      var rc = where.get(span);
      if (!rc || reduceMotion.matches) return;
      var color = hi(), R = 14;
      for (var dr = -R / 2; dr <= R / 2; dr++) {
        var row = cells[rc[0] + dr];
        if (!row) continue;
        for (var dc = -R; dc <= R; dc++) {
          var s = row[rc[1] + dc];
          if (!s) continue;
          var d = Math.sqrt(dc * dc + 4 * dr * dr);   // cells are twice as tall as wide
          if (d <= R) flash(s, d * 22, 1 - d / R, color);
        }
      }
    }

    pre.addEventListener("pointerover", function (e) {
      if (e.pointerType === "touch" || e.buttons) return;   // don't fight drag-selection
      if (e.target.tagName === "SPAN") hoverTrail(e.target);
    });
    pre.addEventListener("click", function (e) {
      var sel = window.getSelection();
      if (sel && !sel.isCollapsed) return;                  // that was a selection
      if (e.target.tagName === "SPAN") ripple(e.target);
    });

    fit();
    if ("ResizeObserver" in window) {
      var w = root.clientWidth;
      new ResizeObserver(function () {
        if (root.clientWidth !== w && pre.isConnected) { w = root.clientWidth; fit(); }
      }).observe(root);
    }
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  }
})();
