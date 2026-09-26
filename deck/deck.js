// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
// TRACE pitch deck renderer. Content: deck/content.json. Data: the repo, via deck/build.py.
(function () {
  'use strict';

  var PACK = window.TRACE_DECK || { content: { slides: [], speakers: [], meta: {} }, data: {} };
  var C = PACK.content, D = PACK.data;
  var SLIDES = C.slides || [];
  var SPEAKERS = {};
  (C.speakers || []).forEach(function (s) { SPEAKERS[s.slot] = s; });

  var stage = document.getElementById('stage');
  var i = 0, notesOn = false, gridOn = false, helpOn = false;
  var timer = { on: false, t0: 0, raf: 0 };

  // ── helpers ───────────────────────────────────────────────────────────────
  function tok(s) {
    if (typeof s !== 'string') return s;
    return s.replace(/\{\{([a-z_.]+)\}\}/g, function (m, path) {
      var cur = D;
      var parts = path.split('.');
      for (var k = 0; k < parts.length; k++) {
        if (cur && Object.prototype.hasOwnProperty.call(cur, parts[k])) cur = cur[parts[k]];
        else return m;
      }
      return String(cur);
    });
  }
  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }
  function shotSrc(sid) { return (D.screenshots || {})[sid] || null; }

  // ── blocks ────────────────────────────────────────────────────────────────
  var BLOCK = {
    kicker: function (b) { return el('div', 'kicker', tok(b.text)); },

    lines: function (b) {
      var n = el('div', 'lines s-' + (b.scale || 'l') + (b.tone ? ' t-' + b.tone : ''));
      (b.items || []).forEach(function (t) { n.appendChild(el('p', null, tok(t))); });
      return n;
    },

    sub: function (b) { return el('div', 'sub', tok(b.text)); },
    source: function (b) { return el('div', 'source', tok(b.text)); },
    rule: function () { return el('div', 'rule'); },

    wordmark: function (b) {
      var w = el('div', 'wordmark-wrap');
      if (!b.small) w.appendChild(arcs());
      w.appendChild(el('div', 'wordmark' + (b.small ? ' small' : ''), tok(b.text)));
      return w;
    },

    swap: function (b) {
      var n = el('div', 'swap');
      n.appendChild(el('div', 'q-old', tok(b.from)));
      n.appendChild(el('div', 'q-new', tok(b.to)));
      return n;
    },

    lagrow: function (b) {
      var n = el('div', 'lagrow');
      var years = (b.items || []).map(function (it) { return parseInt(it.year, 10) || 2024; });
      var now = 2026, oldest = Math.min.apply(null, years);
      (b.items || []).forEach(function (it, k) {
        var r = el('div', 'r');
        r.appendChild(el('div', 'l', tok(it.label)));
        var bar = el('div', 'bar');
        var lag = now - (parseInt(it.year, 10) || now);
        var maxLag = Math.max(1, now - oldest);
        var fill = el('i');
        fill.style.setProperty('--w', Math.round((lag / maxLag) * 100) + '%');
        fill.style.setProperty('--d', (260 + k * 130) + 'ms');
        bar.appendChild(fill);
        r.appendChild(bar);
        var y = el('div');
        y.appendChild(el('div', 'y', tok(it.year)));
        y.appendChild(el('div', 'c', tok(it.code || '')));
        r.appendChild(y);
        n.appendChild(r);
      });
      return n;
    },

    list: function (b) {
      var n = el('div', 'list c' + (b.columns || 3));
      (b.items || []).forEach(function (it, k) {
        var d = el('div', 'it');
        if (b.numbered) d.appendChild(el('span', 'n', String(k + 1).padStart(2, '0')));
        d.appendChild(el('div', 't', tok(it.title)));
        d.appendChild(el('div', 'x', tok(it.text)));
        n.appendChild(d);
      });
      return n;
    },

    statgrid: function (b) {
      var n = el('div', 'statgrid' + (b.compact ? ' compact' : ''));
      (b.items || []).forEach(function (it) {
        var d = el('div', 'stat');
        var v = el('div', 'v', tok(it.value));
        v.setAttribute('data-count', tok(it.value));
        d.appendChild(v);
        d.appendChild(el('div', 'l', tok(it.label)));
        if (it.source) d.appendChild(el('div', 's', tok(it.source)));
        n.appendChild(d);
      });
      return n;
    },

    commandline: function (b) {
      var n = el('div', 'cmds');
      (b.items || []).forEach(function (it, k) {
        var d = el('div', 'cmd');
        var inp = el('div', 'in', tok(it.cmd));
        if (k === 0) inp.appendChild(el('span', 'caret'));
        d.appendChild(inp);
        d.appendChild(el('div', 'out', tok(it.out)));
        n.appendChild(d);
      });
      return n;
    },

    pipeline: function (b) {
      var n = el('div', 'pipe');
      (b.steps || []).forEach(function (s) {
        var d = el('div', 'st');
        d.appendChild(el('div', 'tag', tok(s.step)));
        d.appendChild(el('div', 'h', tok(s.title)));
        d.appendChild(el('div', 'x', tok(s.text)));
        n.appendChild(d);
      });
      return n;
    },

    compare: function (b) {
      var n = el('div', 'compare');
      (b.items || []).forEach(function (it, k) {
        var d = el('div', 'cmp ' + (it.tone || 'up'));
        d.appendChild(el('div', 'cl', tok(it.label)));
        var track = el('div', 'track');
        var fill = el('i');
        fill.style.setProperty('--w', (it.pct || 0) + '%');
        fill.style.setProperty('--d', (300 + k * 260) + 'ms');
        track.appendChild(fill);
        d.appendChild(track);
        var v = el('div', 'cv', tok(it.value));
        v.setAttribute('data-count', tok(it.value));
        d.appendChild(v);
        if (it.note) d.appendChild(el('div', 'cn', tok(it.note)));
        n.appendChild(d);
      });
      return n;
    },

    chart: function (b) {
      var spec = (D.charts || {})[b.cid];
      var w = el('div', 'chartwrap');
      if (!spec) { w.appendChild(el('div', 'chartcap', 'chart data unavailable — run deck/build.py')); return w; }
      w.appendChild(lineChart(spec));
      w.appendChild(el('div', 'chartcap', tok(b.caption || '')));
      return w;
    },

    roadmap: function (b) {
      var n = el('div', 'road');
      (b.items || []).forEach(function (it) {
        var d = el('div', 'r');
        d.appendChild(el('div', 'w', tok(it.when)));
        d.appendChild(el('div', 'x', tok(it.what)));
        n.appendChild(d);
      });
      return n;
    },

    shot: function (b) {
      var src = shotSrc(b.sid);
      var n = el('div', 'shot' + (src ? '' : ' ph'));
      n.style.setProperty('--ar', b.aspect || '16/9');
      if (src) {
        var img = document.createElement('img');
        img.src = src;
        img.alt = tok(b.caption || b.sid);
        n.appendChild(img);
        if (b.caption) n.appendChild(el('div', 'capline', tok(b.caption)));
      } else {
        n.appendChild(wf(b.sid));
        n.appendChild(el('div', 'tag', 'Screenshot placeholder · ' + b.sid));
        n.appendChild(el('div', 'cap', tok(b.caption || '')));
        n.appendChild(el('div', 'spec', tok(b.spec || '')));
        n.appendChild(el('div', 'spec', 'Future agent walks out with the screenshot — drop ' + b.sid +
          '.png into deck/screenshots/ and re-run deck/build.py.'));
      }
      return n;
    },

    shotgrid: function (b) {
      var n = el('div', 'shotgrid');
      (b.items || []).forEach(function (it) {
        var cell = el('div', 'cell');
        var thumb = el('div', 'thumb');
        var src = shotSrc(it.sid);
        if (src) {
          var img = document.createElement('img');
          img.src = src; img.alt = tok(it.title);
          thumb.appendChild(img);
        } else {
          thumb.appendChild(wf(it.sid));
          thumb.appendChild(el('div', 'miss', 'PLACEHOLDER · ' + it.sid));
        }
        cell.appendChild(thumb);
        var meta = el('div', 'meta');
        meta.appendChild(el('div', 't', tok(it.title)));
        meta.appendChild(el('div', 'x', tok(it.text)));
        cell.appendChild(meta);
        n.appendChild(cell);
      });
      return n;
    }
  };


  // ── schematic wireframes (stand in for screenshots that don't exist yet) ──
  function wf(sid) {
    var ns = 'http://www.w3.org/2000/svg', W = 320, H = 180;
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'wf');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.setAttribute('preserveAspectRatio', 'xMidYMid slice');
    svg.setAttribute('aria-hidden', 'true');

    var A = '#FFB000', C = '#4DD8FF', R = '#FF4D4D', G = '#35D07F';
    function n(tag, attrs) {
      var e = document.createElementNS(ns, tag);
      for (var k in attrs) e.setAttribute(k, attrs[k]);
      svg.appendChild(e);
      return e;
    }
    function box(x, y, w, h, o) { n('rect', { x: x, y: y, width: w, height: h, fill: 'none', stroke: A, 'stroke-width': .6, opacity: o == null ? .55 : o }); }
    function fill(x, y, w, h, c, o) { n('rect', { x: x, y: y, width: w, height: h, fill: c || A, opacity: o == null ? .35 : o }); }
    function ln(x1, y1, x2, y2, c, o, w) { n('line', { x1: x1, y1: y1, x2: x2, y2: y2, stroke: c || A, 'stroke-width': w || .6, opacity: o == null ? .4 : o }); }
    function arc(x1, y1, x2, y2, lift, c, o) {
      n('path', { d: 'M' + x1 + ',' + y1 + ' Q' + ((x1 + x2) / 2) + ',' + (Math.min(y1, y2) - lift) + ' ' + x2 + ',' + y2,
                  fill: 'none', stroke: c || A, 'stroke-width': 1, opacity: o == null ? .8 : o, 'stroke-linecap': 'round' });
      n('circle', { cx: x2, cy: y2, r: 1.6, fill: c || A, opacity: .9 });
      n('circle', { cx: x1, cy: y1, r: 1.6, fill: c || A, opacity: .9 });
    }
    function rows(x, y, w, count, gap, len) {
      for (var k = 0; k < count; k++) fill(x, y + k * gap, (len || 1) * w * (0.45 + ((k * 37) % 55) / 100), 2, A, .3);
    }
    // shared chrome: command bar + status strip
    box(6, 6, W - 12, H - 12, .5);
    ln(6, 20, W - 6, 20, A, .35);
    fill(10, 12, 42, 4, A, .6);
    ln(6, H - 16, W - 6, H - 16, A, .25);
    rows(10, H - 12, 60, 1, 0, 1);

    if (sid === 'route-map') {
      for (var gx = 24; gx < W - 18; gx += 26) ln(gx, 24, gx, H - 20, A, .07);
      for (var gy = 32; gy < H - 20; gy += 22) ln(12, gy, W - 12, gy, A, .07);
      arc(42, 118, 128, 64, 34, A, .9); arc(128, 64, 214, 92, 30, A, .75);
      arc(60, 96, 236, 128, 44, C, .7); arc(150, 132, 276, 70, 38, R, .6);
      box(12, 26, 62, 52, .45); rows(17, 34, 52, 5, 8, .9);
      for (var t = 0; t < 14; t++) ln(30 + t * 18, H - 26, 30 + t * 18, H - 22, A, .35);
      fill(30, H - 25, 108, 1.6, A, .7);
    } else if (sid === 'country-screen') {
      box(12, 26, 86, H - 48, .45); rows(17, 34, 76, 9, 10, .95);
      for (var q = 0; q < 4; q++) box(106 + (q % 2) * 102, 26 + Math.floor(q / 2) * 46, 94, 38, .4);
      for (var q2 = 0; q2 < 4; q2++) fill(112 + (q2 % 2) * 102, 34 + Math.floor(q2 / 2) * 46, 34, 7, A, .55);
      n('path', { d: 'M110,150 L136,138 L160,146 L186,122 L212,132 L240,110 L296,118', fill: 'none', stroke: G, 'stroke-width': 1, opacity: .8 });
      box(106, 118, 196, 40, .35);
    } else if (sid === 'risk-board') {
      ln(12, 32, W - 12, 32, A, .3);
      for (var r = 0; r < 9; r++) {
        var y = 40 + r * 13;
        fill(14, y, 8, 2.4, A, .5); fill(28, y, 40, 2.4, A, .35);
        fill(84, y, 46 * (1 - r * .07), 4, A, .6);
        fill(150, y, 40 * (.4 + ((r * 29) % 60) / 100), 4, R, .5);
        fill(206, y, 34 * (.3 + ((r * 17) % 70) / 100), 4, C, .45);
        fill(258, y, 46, 1.6, A, .22);
      }
    } else if (sid === 'simulator') {
      box(12, 26, W - 24, 16, .5); fill(17, 32, 120, 4, A, .6);
      ln(W / 2, 48, W / 2, H - 24, A, .2);
      arc(28, 108, 92, 72, 26, A, .5); arc(92, 72, 140, 96, 20, A, .45);
      arc(178, 108, 250, 66, 30, A, .95); arc(250, 66, 300, 104, 24, R, .85);
      fill(20, H - 34, 44, 3, G, .6); fill(72, H - 34, 30, 3, R, .6);
      fill(178, H - 34, 58, 3, G, .8); fill(244, H - 34, 42, 3, R, .8);
    } else if (sid === 'livewire') {
      for (var f = 0; f < 6; f++) {
        var fy = 28 + f * 22;
        box(12, fy, W - 24, 18, f === 2 ? .7 : .3);
        fill(17, fy + 5, 8, 8, f === 2 ? R : A, f === 2 ? .9 : .5);
        fill(31, fy + 5, 150 - f * 9, 2.6, A, .4);
        fill(31, fy + 11, 96 + f * 7, 2, A, .22);
        fill(W - 52, fy + 7, 34, 4, f === 2 ? R : G, .5);
      }
    } else if (sid === 'market-board') {
      for (var m = 0; m < 6; m++) {
        var my = 30 + m * 22;
        fill(16, my, 40, 3, A, .55);
        n('path', { d: 'M74,' + (my + 6) + ' L104,' + (my + (m % 2 ? 1 : 9)) + ' L134,' + (my + 4) + ' L164,' + (my + (m % 2 ? 8 : 0)) + ' L196,' + (my + 3),
                    fill: 'none', stroke: m % 2 ? R : G, 'stroke-width': .9, opacity: .8 });
        fill(226, my, 30, 4, m % 2 ? R : G, .6);
        fill(272, my, 30, 3, A, .3);
        ln(12, my + 14, W - 12, my + 14, A, .12);
      }
    } else if (sid === 'experiment') {
      ln(W / 2, 26, W / 2, H - 22, A, .2);
      n('path', { d: 'M22,60 L52,52 L82,64 L112,58 L142,132', fill: 'none', stroke: A, 'stroke-width': 1.1, opacity: .85 });
      n('path', { d: 'M22,120 L52,118 L82,116 L112,112 L142,92', fill: 'none', stroke: C, 'stroke-width': 1.1, opacity: .7 });
      n('path', { d: 'M182,62 L212,54 L242,66 L272,60 L300,130', fill: 'none', stroke: A, 'stroke-width': 1.1, opacity: .85, 'stroke-dasharray': '3 3' });
      n('path', { d: 'M182,122 L212,119 L242,117 L272,110 L300,86', fill: 'none', stroke: C, 'stroke-width': 1.1, opacity: .7, 'stroke-dasharray': '3 3' });
      ln(132, 26, 132, H - 22, R, .5); ln(292, 26, 292, H - 22, R, .5);
      fill(18, 30, 30, 3, A, .5); fill(178, 30, 44, 3, A, .5);
    } else {
      for (var d = 0; d < 5; d++) box(14 + d * 60, 40, 52, 44, .3);
    }
    return svg;
  }

  // ── svg bits ──────────────────────────────────────────────────────────────
  function arcs() {
    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'arcs');
    svg.setAttribute('viewBox', '0 0 1000 420');
    svg.setAttribute('preserveAspectRatio', 'none');
    var defs = [
      ['M20,340 Q260,60 520,250', '#FFB000', 0],
      ['M80,390 Q420,120 860,300', '#FFD979', 180],
      ['M0,240 Q300,-20 700,180', '#4DD8FF', 340],
      ['M140,410 Q560,200 980,380', '#FF7A45', 500],
      ['M60,180 Q380,380 940,120', '#FFB000', 660]
    ];
    defs.forEach(function (d) {
      var p = document.createElementNS(ns, 'path');
      p.setAttribute('d', d[0]);
      p.setAttribute('stroke', d[1]);
      p.setAttribute('opacity', '0.5');
      p.style.setProperty('--len', '1400');
      p.style.animationDelay = d[2] + 'ms';
      svg.appendChild(p);
    });
    return svg;
  }

  function lineChart(spec) {
    var ns = 'http://www.w3.org/2000/svg';
    var W = 1000, H = 300, pad = { l: 54, r: 90, t: 16, b: 28 };
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'chart');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.setAttribute('preserveAspectRatio', 'none');

    var pts = [];
    spec.series.forEach(function (s) { s.points.forEach(function (p) { pts.push(p); }); });
    if (!pts.length) return svg;
    var xs = pts.map(function (p) { return p.x; }), ys = pts.map(function (p) { return p.y; });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
    var rawMax = Math.max.apply(null, ys) * 1.08;
    var mag = Math.pow(10, Math.floor(Math.log(rawMax) / Math.LN10));
    var y1 = Math.ceil(rawMax / (mag / 2)) * (mag / 2);
    var X = function (v) { return pad.l + ((v - x0) / Math.max(1, x1 - x0)) * (W - pad.l - pad.r); };
    var Y = function (v) { return H - pad.b - (v / y1) * (H - pad.t - pad.b); };

    var g = document.createElementNS(ns, 'g');
    g.setAttribute('class', 'grid');
    [0, 0.5, 1].forEach(function (f) {
      var ln = document.createElementNS(ns, 'line');
      ln.setAttribute('x1', pad.l); ln.setAttribute('x2', W - pad.r);
      ln.setAttribute('y1', Y(y1 * f)); ln.setAttribute('y2', Y(y1 * f));
      g.appendChild(ln);
      var tx = document.createElementNS(ns, 'text');
      tx.setAttribute('x', pad.l - 10); tx.setAttribute('y', Y(y1 * f) + 3.5);
      tx.setAttribute('text-anchor', 'end');
      var tv = y1 * f;
      tx.textContent = tv >= 1000 ? Math.round(tv / 1000) + 'k' : Math.round(tv);
      g.appendChild(tx);
    });
    svg.appendChild(g);

    if (spec.ban_year) {
      var b = document.createElementNS(ns, 'line');
      b.setAttribute('class', 'ban');
      b.setAttribute('x1', X(spec.ban_year)); b.setAttribute('x2', X(spec.ban_year));
      b.setAttribute('y1', pad.t); b.setAttribute('y2', H - pad.b);
      svg.appendChild(b);
      var bt = document.createElementNS(ns, 'text');
      bt.setAttribute('x', X(spec.ban_year) + 6); bt.setAttribute('y', pad.t + 10);
      bt.setAttribute('fill', '#FF4D4D');
      bt.textContent = 'BAN ' + spec.ban_year;
      svg.appendChild(bt);
    }

    var colors = ['#FFB000', '#4DD8FF'];
    spec.series.forEach(function (s, k) {
      var d = s.points.map(function (p, n) { return (n ? 'L' : 'M') + X(p.x) + ',' + Y(p.y); }).join(' ');
      var path = document.createElementNS(ns, 'path');
      path.setAttribute('class', 'ln');
      path.setAttribute('d', d);
      path.setAttribute('stroke', colors[k % colors.length]);
      path.style.setProperty('--len', '2600');
      path.style.animationDelay = (260 + k * 220) + 'ms';
      svg.appendChild(path);
      var last = s.points[s.points.length - 1];
      var lb = document.createElementNS(ns, 'text');
      lb.setAttribute('class', 'lbl');
      lb.setAttribute('x', X(last.x) + 10); lb.setAttribute('y', Y(last.y) + 4);
      lb.setAttribute('fill', colors[k % colors.length]);
      lb.textContent = s.label;
      svg.appendChild(lb);
    });

    [x0, spec.ban_year || x0, x1].forEach(function (v) {
      if (v == null) return;
      var tx = document.createElementNS(ns, 'text');
      tx.setAttribute('x', X(v)); tx.setAttribute('y', H - 8);
      tx.setAttribute('text-anchor', 'middle');
      tx.textContent = v;
      svg.appendChild(tx);
    });
    return svg;
  }

  // ── render ────────────────────────────────────────────────────────────────
  function render() {
    SLIDES.forEach(function (sl, idx) {
      var s = el('section', 'slide');
      s.setAttribute('data-theme', sl.theme || 'terminal');
      s.setAttribute('data-idx', String(idx));
      var order = 0;
      (sl.blocks || []).forEach(function (b) {
        var fn = BLOCK[b.type];
        if (!fn) return;
        var node = fn(b);
        node.setAttribute('data-anim', '');
        node.style.transitionDelay = (order * 90) + 'ms';
        order++;
        s.appendChild(node);
      });
      stage.appendChild(s);
    });
    buildGrid();
    go(0, true);
  }

  function countUp(node) {
    var raw = node.getAttribute('data-count') || '';
    var m = raw.match(/^([\d.]+)(.*)$/);
    if (!m || raw.indexOf('/') > -1) return;
    var target = parseFloat(m[1]);
    if (!isFinite(target)) return;
    var dec = (m[1].split('.')[1] || '').length;
    var suffix = m[2] || '';
    var t0 = performance.now(), dur = 900;
    function step(t) {
      var p = Math.min(1, (t - t0) / dur);
      var e = 1 - Math.pow(1 - p, 3);
      node.textContent = (target * e).toFixed(dec) + suffix;
      if (p < 1) requestAnimationFrame(step);
      else node.textContent = raw;
    }
    node.textContent = (0).toFixed(dec) + suffix;
    requestAnimationFrame(step);
  }

  function go(n, initial) {
    n = Math.max(0, Math.min(SLIDES.length - 1, n));
    var prev = stage.children[i];
    i = n;
    Array.prototype.forEach.call(stage.children, function (s, idx) {
      s.classList.toggle('active', idx === i);
      s.classList.toggle('past', idx < i);
    });
    if (prev && !initial) { /* transition handled by CSS */ }
    var cur = stage.children[i];
    if (cur) {
      setTimeout(function () {
        Array.prototype.forEach.call(cur.querySelectorAll('[data-count]'), countUp);
      }, 260);
    }
    paintChrome();
    paintNotes();
    Array.prototype.forEach.call(document.querySelectorAll('#grid .g'), function (g, idx) {
      g.classList.toggle('cur', idx === i);
    });
  }

  // ── chrome / notes / timer ────────────────────────────────────────────────
  function cumulative(n) {
    var t = 0;
    for (var k = 0; k < n; k++) t += SLIDES[k].seconds || 0;
    return t;
  }
  function total() { return cumulative(SLIDES.length); }
  function mmss(s) {
    s = Math.max(0, Math.round(s));
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  function paintChrome() {
    var sl = SLIDES[i] || {};
    var sp = SPEAKERS[sl.speaker] || {};
    document.getElementById('progress').firstElementChild.style.width =
      (((i + 1) / SLIDES.length) * 100) + '%';
    document.getElementById('spk').textContent = (sp.name || '') + (sp.section ? ' · ' + sp.section : '');
    document.getElementById('pos').textContent = (i + 1) + ' / ' + SLIDES.length;
    var rt = document.getElementById('rt');
    if (!timer.on) {
      rt.className = 'rt';
      rt.textContent = 'target ' + mmss(cumulative(i + 1)) + ' / ' + mmss(total());
    }
  }

  function paintNotes() {
    var sl = SLIDES[i] || {};
    var sp = SPEAKERS[sl.speaker] || {};
    var box = document.getElementById('notes');
    box.innerHTML = '';
    box.appendChild(el('h4', null,
      (sp.name || sl.speaker || '') + ' — ' + (sp.section || '') +
      ' · slide ' + (i + 1) + ' · ' + (sl.seconds || 0) + 's'));
    var ul = el('ul');
    (sl.cues || []).forEach(function (c) { ul.appendChild(el('li', null, tok(c))); });
    if (sl.handoff) ul.appendChild(el('li', 'hand', 'HANDOFF → “' + tok(sl.handoff) + '”'));
    box.appendChild(ul);
    box.appendChild(el('div', 'meta',
      'cumulative target ' + mmss(cumulative(i + 1)) + ' of ' + mmss(total()) +
      ' · next: ' + (SLIDES[i + 1] ? (SPEAKERS[SLIDES[i + 1].speaker] || {}).name || '—' : 'LIVE DEMO')));
  }

  function tick() {
    if (!timer.on) return;
    var elapsed = (performance.now() - timer.t0) / 1000;
    var target = cumulative(i + 1);
    var rt = document.getElementById('rt');
    var drift = elapsed - target;
    rt.textContent = mmss(elapsed) + '  ' + (drift >= 0 ? '+' : '−') + mmss(Math.abs(drift));
    rt.className = 'rt' + (drift > 20 ? ' over' : drift > 8 ? ' warn' : '');
    var pace = document.getElementById('pace').firstElementChild;
    pace.style.width = Math.min(100, (elapsed / total()) * 100) + '%';
    pace.className = drift > 20 ? 'over' : drift > 8 ? 'warn' : '';
    timer.raf = requestAnimationFrame(tick);
  }

  function toggleTimer() {
    timer.on = !timer.on;
    document.getElementById('pace').classList.toggle('on', timer.on);
    if (timer.on) { timer.t0 = performance.now(); tick(); }
    else { cancelAnimationFrame(timer.raf); paintChrome(); }
  }

  function buildGrid() {
    var g = document.getElementById('grid');
    g.innerHTML = '';
    SLIDES.forEach(function (sl, idx) {
      var d = el('div', 'g');
      d.appendChild(el('div', 'i', String(idx + 1).padStart(2, '0') + ' · ' + (sl.seconds || 0) + 's'));
      var head = '';
      (sl.blocks || []).some(function (b) {
        if (b.type === 'kicker') { head = b.text; return true; }
        if (b.type === 'lines') { head = (b.items || []).join(' '); return true; }
        if (b.type === 'swap') { head = b.to; return true; }
        if (b.type === 'wordmark') { head = b.text; return true; }
        return false;
      });
      d.appendChild(el('div', 'h', tok(head).slice(0, 78)));
      d.appendChild(el('div', 's', ((SPEAKERS[sl.speaker] || {}).name || sl.speaker || '').toUpperCase()));
      d.onclick = function () { gridOn = false; g.classList.remove('on'); go(idx); };
      g.appendChild(d);
    });
  }

  // ── input ─────────────────────────────────────────────────────────────────
  document.addEventListener('keydown', function (e) {
    var k = e.key;
    if (k === 'Escape') { gridOn = helpOn = false; document.getElementById('grid').classList.remove('on'); document.getElementById('help').classList.remove('on'); return; }
    if (k === 'ArrowRight' || k === ' ' || k === 'PageDown' || k === 'ArrowDown') { e.preventDefault(); go(i + 1); }
    else if (k === 'ArrowLeft' || k === 'PageUp' || k === 'ArrowUp') { e.preventDefault(); go(i - 1); }
    else if (k === 'Home') go(0);
    else if (k === 'End') go(SLIDES.length - 1);
    else if (k === 'n' || k === 'N') { notesOn = !notesOn; document.getElementById('notes').classList.toggle('on', notesOn); }
    else if (k === 't' || k === 'T') toggleTimer();
    else if (k === 'g' || k === 'G') { gridOn = !gridOn; document.getElementById('grid').classList.toggle('on', gridOn); }
    else if (k === 'f' || k === 'F') {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    }
    else if (k === '?' || k === '/') { helpOn = !helpOn; document.getElementById('help').classList.toggle('on', helpOn); }
  });

  stage.addEventListener('click', function (e) {
    go(i + (e.clientX < window.innerWidth * 0.25 ? -1 : 1));
  });

  var idleT;
  document.addEventListener('mousemove', function () {
    document.body.classList.remove('idle');
    clearTimeout(idleT);
    idleT = setTimeout(function () { document.body.classList.add('idle'); }, 2600);
  });

  // ── boot ──────────────────────────────────────────────────────────────────
  document.getElementById('build').textContent =
    (D.git && D.git.sha ? D.git.sha + ' · ' : '') + (D.built_at || '');
  render();
})();
