/* Russian Practice — vanilla JS, no build step. Content lives in /data. */
window.LEVELS = [];
window.registerLevel = l => window.LEVELS.push(l);
window.VOCAB = {};
window.registerVocab = (id, txt) => {
  window.VOCAB[id] = txt.split("\n").map(s => s.trim()).filter(s => s.includes("|"))
    .map(s => { const k = s.indexOf("|"); return [s.slice(0, k).trim(), s.slice(k + 1).trim()]; });
};

(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const app = $("#app"), tip = $("#tip");
  const CEFR = ["A1", "A2", "B1", "B2"];
  const ICON = {
    play: '<svg viewBox="0 0 24 24"><path d="M7 4.5v15a1 1 0 0 0 1.5.86l12-7.5a1 1 0 0 0 0-1.72l-12-7.5A1 1 0 0 0 7 4.5z"/></svg>',
    pause: '<svg viewBox="0 0 24 24"><rect x="6" y="5" width="4.5" height="14" rx="1.2"/><rect x="13.5" y="5" width="4.5" height="14" rx="1.2"/></svg>',
    first: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h2v14H6z"/><path d="M19.5 5.7v12.6a1 1 0 0 1-1.6.8l-8.7-6.3a1 1 0 0 1 0-1.6l8.7-6.3a1 1 0 0 1 1.6.8z"/></svg>',
    prev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 6l-6 6 6 6M19 6l-6 6 6 6"/></svg>',
    next: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 6l6 6-6 6M5 6l6 6-6 6"/></svg>'
  };

  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem("ru:" + k)) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem("ru:" + k, JSON.stringify(v)); } catch {} }
  };
  let prog = store.get("prog", {});
  let prefs = store.get("prefs", { mode: "read", rate: 0.85 });

  const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  const plain = t => t.replace(/\[([^|\]]+)\|[^\]]+\]/g, "$1");
  const mark = t => esc(t).replace(/\[([^|\]]+)\|([^\]]+)\]/g, '<span class="w" tabindex="0" data-t="$2">$1</span>');
  const glossary = t => {
    const seen = new Map();
    for (const m of t.matchAll(/\[([^|\]]+)\|([^\]]+)\]/g)) if (!seen.has(m[1].toLowerCase())) seen.set(m[1].toLowerCase(), [m[1], m[2]]);
    return [...seen.values()];
  };
  const best = (l, i) => prog[l.id + ":" + i];
  const bindClick = (el, fn) => {
    el.onclick = fn;
    el.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(); } };
  };
  const loadScript = (src, quiet) => new Promise(res => {
    const s = document.createElement("script");
    s.src = src; s.onload = res; s.onerror = () => { if (!quiet) console.warn("Could not load", src); res(); };
    document.head.append(s);
  });

  /* ----- audio ----- */
  let onEnd = () => {};
  function speak(text, done) {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ru-RU"; u.rate = prefs.rate;
    const v = speechSynthesis.getVoices().find(v => v.lang.startsWith("ru"));
    if (v) u.voice = v;
    u.onend = u.onerror = () => done && done();
    speechSynthesis.speak(u);
  }
  let tipTimer;
  function showTip(msg) {
    tip.textContent = msg; tip.classList.add("show");
    clearTimeout(tipTimer); tipTimer = setTimeout(() => tip.classList.remove("show"), 2400);
  }
  function updateStat() {
    const total = LEVELS.reduce((n, l) => n + l.texts.length, 0);
    const done = LEVELS.reduce((n, l) => n + l.texts.filter((_, i) => best(l, i) != null).length, 0);
    $("#stat").textContent = `${done} / ${total} completed`;
  }
  const crumbs = parts => `<div class="crumbs">${parts.map((p, i) => i < parts.length - 1
    ? `<a data-c="${i}">${esc(p)}</a><span>/</span>` : `<span>${esc(p)}</span>`).join("")}</div>`;

  /* ----- views ----- */
  function home() {
    speechSynthesis.cancel(); updateStat();
    app.innerHTML = `<div class="head"><h1>Vocabulary sets</h1>
      <p class="mut">Short texts built around the words you are learning. Read or listen, then test your understanding.</p></div>
      <div class="cards">${LEVELS.map(l => {
        const done = l.texts.filter((_, i) => best(l, i) != null).length, pct = Math.round(done / l.texts.length * 100);
        return `<article class="set" tabindex="0" data-l="${esc(l.id)}">
          <div class="cover" data-g="${esc(l.title[0])}"><span class="tag">${VOCAB[l.id] ? VOCAB[l.id].length + " words · " : ""}${l.texts.length} exercises</span></div>
          <div class="set-b"><h2>${esc(l.title)}</h2><p class="mut">${esc(l.desc || "")}</p>
          <div class="pills">${CEFR.map(c => `<span class="pill ${c === l.target ? "on" : ""}">${c}</span>`).join("")}</div>
          <div class="foot"><span class="sm mut">${done}/${l.texts.length} done</span><span class="sm mut">${pct}%</span></div>
          <div class="bar"><i style="width:${pct}%"></i></div></div></article>`;
      }).join("")}</div>`;
    $$(".set", app).forEach(c => bindClick(c, () => level(c.dataset.l)));
  }

  function download(name, mime, content) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([content], { type: mime })); a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  function exportVocab(l, f) {
    const w = VOCAB[l.id] || [], q = s => '"' + s.replace(/"/g, '""') + '"';
    if (f === "csv") download(`${l.id}-vocabulary.csv`, "text/csv;charset=utf-8", "\ufeffRussian,French\n" + w.map(r => r.map(q).join(",")).join("\n"));
    if (f === "tsv") download(`${l.id}-anki.tsv`, "text/tab-separated-values;charset=utf-8", w.map(r => r.join("\t")).join("\n"));
    if (f === "txt") download(`${l.id}-vocabulary.txt`, "text/plain;charset=utf-8", w.map(r => r.join(" | ")).join("\n"));
  }
  function vocabRows(words, q) {
    q = q.trim().toLowerCase();
    const rows = words.map((r, i) => [i + 1, r[0], r[1]]).filter(r => !q || r[1].toLowerCase().includes(q) || r[2].toLowerCase().includes(q));
    return rows.length ? rows.map(([n, ru, fr]) => `<div class="vr"><span class="vi">${n}</span><b>${esc(ru)}</b><span class="fr">${esc(fr)}</span></div>`).join("")
      : '<p class="mut sm" style="padding:16px">No match.</p>';
  }

  function level(id) {
    speechSynthesis.cancel(); updateStat();
    const l = LEVELS.find(x => x.id === id), words = VOCAB[id] || [];
    app.innerHTML = `${crumbs(["Sets", l.title])}
      <h1>${esc(l.title)}</h1><p class="mut" style="margin:0 0 10px">${esc(l.desc || "")}</p>
      <div class="pills">${CEFR.map(c => `<span class="pill ${c === l.target ? "on" : ""}">${c}</span>`).join("")}</div>
      <div class="lay2"><section><h2 class="sec">Exercises</h2><div class="list">${l.texts.map((t, i) => {
        const b = best(l, i);
        return `<div class="item ${b != null ? "done" : ""}" tabindex="0" data-i="${i}">
          <div class="num">${b != null ? "✓" : i + 1}</div>
          <div class="grow"><div class="tag">${esc(t.type)}</div><h2>${esc(t.title)}</h2></div>
          <span class="score">${b != null ? b + "/" + t.qs.length : "Not started"}</span><span class="chev">›</span></div>`;
      }).join("")}</div></section>
      ${words.length ? `<section class="vocab"><div class="vh"><div><h2>Vocabulary</h2><span class="sm mut">${words.length} words · tap a row to hear it</span></div>
        <div class="dl"><button class="btn s" data-f="csv">CSV</button><button class="btn s" data-f="tsv" title="Tab-separated, ready to import in Anki">Anki</button><button class="btn s" data-f="txt">TXT</button></div></div>
        <div class="vtools"><input type="search" id="vq" placeholder="Search Russian or French…" aria-label="Search vocabulary">
        <label class="sw"><input type="checkbox" id="vh"> Hide French</label></div>
        <div class="vlist" id="vlist">${vocabRows(words, "")}</div></section>` : ""}</div>`;
    $("[data-c='0']", app).onclick = home;
    $$(".item", app).forEach(c => bindClick(c, () => exercise(l, +c.dataset.i)));
    if (!words.length) return;
    const list = $("#vlist");
    $("#vq").oninput = e => { list.innerHTML = vocabRows(words, e.target.value); };
    $("#vh").onchange = e => { $$(".vr.rev", list).forEach(r => r.classList.remove("rev")); list.classList.toggle("hidefr", e.target.checked); };
    list.onclick = e => {
      const r = e.target.closest(".vr"); if (!r) return;
      if (list.classList.contains("hidefr")) r.classList.toggle("rev"); speak(r.querySelector("b").textContent);
    };
    $$("[data-f]", app).forEach(b => b.onclick = () => exportVocab(l, b.dataset.f));
  }

  function exercise(l, i) {
    const t = l.texts[i], gl = glossary(t.body); let score = 0, answered = 0, playing = false, idx = 0, startAt = 0, elapsed = 0, token = 0;
    // Split the text into sentences (brackets protect [word|translation] markup); each becomes a clickable-free <span class="s">
    const sents = [], readerHtml = [...t.body.matchAll(/(?:\[[^\]]*\]|[^.!?…\n])+[.!?…]*[ \t]*|\n+|[.!?…]+/g)].map(m => {
      const sp = plain(m[0]).trim();
      if (!/\p{L}/u.test(sp)) return esc(m[0]);
      sents.push(sp); return `<span class="s" data-s="${sents.length - 1}">${mark(m[0])}</span>`;
    }).join("");
    speechSynthesis.cancel(); window.scrollTo(0, 0);
    app.innerHTML = `${crumbs(["Sets", l.title, t.title])}
    <div class="lay"><div class="article">
      <span class="tag">${esc(t.type)}</span><h1>${esc(t.title)}</h1>
      <div class="reader" id="reader">${readerHtml}</div>
      <p class="sm mut">Highlighted words are your target vocabulary. Tap one to see its meaning.</p>
      <div class="quiz-h"><h2>Comprehension</h2><span class="sm mut" id="qc">0 / ${t.qs.length}</span></div>
      <div class="bar"><i id="qp" style="width:0"></i></div>
      ${t.qs.map((q, k) => `<div class="q"><div class="q-n">Question ${k + 1} of ${t.qs.length}</div>
        <div class="q-h">${esc(q.q)}</div>
        ${q.o.map((o, j) => `<button class="opt" data-k="${k}" data-j="${j}"><i>${"ABCDE"[j]}</i>${esc(o)}</button>`).join("")}</div>`).join("")}
      <div id="result"></div></div>
      <aside class="side"><div class="flip" id="flip"><div class="fi">
        <div class="face front"><span class="tag">Vocabulary hint</span><h3>Stuck on a word?</h3>
          <p class="mut">The target words of this text are on the back of the card. Try the exercise first: the meanings can give away answers.</p>
          <button class="btn pri" data-flip>Flip card</button></div>
        <div class="face bk"><div class="bh"><span class="tag">Words in this text · ${gl.length}</span><button class="btn s" data-flip>Flip back</button></div>
          <div class="gls">${gl.map(([w, tr]) => `<button class="gl" data-w="${esc(w)}"><b>${esc(w)}</b><span>${esc(tr)}</span></button>`).join("")}</div></div>
      </div></div></aside></div>
    <div class="player">
      <button class="ctl" id="rs" title="Restart from the beginning" aria-label="Restart from the beginning">${ICON.first}</button>
      <button class="ctl" id="pv" title="Previous sentence (restarts the current one if you are past its start)" aria-label="Previous sentence">${ICON.prev}</button>
      <button class="play" id="play" aria-label="Play">${ICON.play}</button>
      <button class="ctl" id="nx" title="Next sentence" aria-label="Next sentence">${ICON.next}</button>
      <span class="seg" id="spd"><button data-r="0.65">0.7×</button><button data-r="0.85">1×</button><button data-r="1">1.2×</button></span>
      <span class="seg" id="mode"><button data-m="read">Show text</button><button data-m="listen">Hide text</button></span></div>`;

    const reader = $("#reader"), play = $("#play");
    const setPlaying = p => { playing = p; play.innerHTML = p ? ICON.pause : ICON.play; play.setAttribute("aria-label", p ? "Pause" : "Play"); };
    const mark_ = () => { $$(".s.cur", app).forEach(e => e.classList.remove("cur")); const e = $(`.s[data-s="${idx}"]`, app); if (e) e.classList.add("cur"); };
    function playFrom(k) {            // play sentence k, then keep going to the end
      idx = Math.max(0, Math.min(k, sents.length - 1)); const my = ++token;
      startAt = Date.now(); elapsed = 0; mark_(); setPlaying(true);
      speak(sents[idx], () => {
        if (my !== token || !document.body.contains(play)) return;   // superseded, paused, or page left
        if (idx + 1 < sents.length) playFrom(idx + 1); else { idx = 0; elapsed = 0; setPlaying(false); mark_(); $$(".s.cur", app).forEach(e => e.classList.remove("cur")); }
      });
    }
    function pause() { if (playing) elapsed = Date.now() - startAt; token++; speechSynthesis.cancel(); setPlaying(false); }
    play.onclick = () => playing ? pause() : playFrom(idx);          // resume = restart the sentence we stopped in
    $("#rs").onclick = () => playFrom(0);
    $("#nx").onclick = () => playFrom(idx + 1);
    $("#pv").onclick = () => { const heard = playing ? Date.now() - startAt : elapsed; playFrom(heard > 2000 || idx === 0 ? idx : idx - 1); };
    const setMode = m => {
      prefs.mode = m; store.set("prefs", prefs);
      reader.classList.toggle("hide", m === "listen");
      $$("#mode button").forEach(b => b.classList.toggle("on", b.dataset.m === m));
    };
    const setRate = r => { prefs.rate = r; store.set("prefs", prefs); $$("#spd button").forEach(b => b.classList.toggle("on", +b.dataset.r === r)); if (playing) playFrom(idx); };
    setMode(prefs.mode); setRate(prefs.rate);
    $$("#mode button").forEach(b => b.onclick = () => setMode(b.dataset.m));
    $$("#spd button").forEach(b => b.onclick = () => setRate(+b.dataset.r));
    $$(".crumbs a", app).forEach(a => a.onclick = () => (+a.dataset.c === 0 ? home() : level(l.id)));
    $$(".w", app).forEach(w => bindClick(w, () => showTip(w.textContent + " — " + w.dataset.t)));
    $$(".gl", app).forEach(b => b.onclick = () => { pause(); speak(b.dataset.w); });
    $$("[data-flip]", app).forEach(b => b.onclick = () => $("#flip").classList.toggle("on"));

    $$(".opt", app).forEach(b => b.onclick = () => {
      const k = +b.dataset.k, j = +b.dataset.j, q = t.qs[k];
      const group = $$(`.opt[data-k="${k}"]`);
      group.forEach(x => x.disabled = true);
      group[q.a].classList.add("ok");
      if (j === q.a) score++; else b.classList.add("no");
      answered++;
      $("#qp").style.width = (answered / t.qs.length * 100) + "%";
      $("#qc").textContent = `${answered} / ${t.qs.length}`;
      if (answered === t.qs.length) finish();
    });

    function finish() {
      prog[l.id + ":" + i] = Math.max(best(l, i) ?? 0, score); store.set("prog", prog); updateStat();
      const next = i + 1 < l.texts.length;
      $("#result").innerHTML = `<div class="result"><span class="tag">Result</span><b>${score} / ${t.qs.length}</b>
        <p class="mut">${score === t.qs.length ? "Perfect score." : "Re-read the text and try again to lock in the vocabulary."}</p>
        <div class="actions"><button class="btn" id="retry">Retry</button>
        ${next ? '<button class="btn pri" id="next">Next exercise</button>' : '<button class="btn pri" id="back">Back to set</button>'}</div></div>`;
      $("#retry").onclick = () => exercise(l, i);
      if (next) $("#next").onclick = () => exercise(l, i + 1); else $("#back").onclick = () => level(l.id);
      $("#result").scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  /* ----- boot ----- */
  $("#brand").onclick = $("#nav-sets").onclick = e => { e.preventDefault(); home(); };
  speechSynthesis.getVoices();
  Promise.all((window.LEVEL_FILES || []).map(id => loadScript(`data/levels/${id}.js`)))
    .then(() => Promise.all(LEVEL_FILES.map(id => loadScript(`data/vocab/${id}.js`, true)))).then(() => {
    LEVELS.sort((a, b) => LEVEL_FILES.indexOf(a.id) - LEVEL_FILES.indexOf(b.id));
    home();
  });
})();
