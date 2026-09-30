const $ = (s) => document.querySelector(s);
const api = (p, o) => fetch(p, o).then(async (r) => {
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
});
const debounce = (f, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => f(...a), ms); }; };

let excluded = new Set();
let state = null;
let seed = 7;

// ---------- 1. modèle ----------
async function initGroups() {
  const sets = await api("/api/charsets");
  const st = await api("/api/state");
  const spec = st.spec;
  $("#variants").value = spec.variants;
  $("#groups").innerHTML = Object.entries(sets).map(([k, v]) =>
    `<label><input type="checkbox" value="${k}" ${spec.groups.includes(k) ? "checked" : ""}> ${v.label} <span class="muted">${[...v.chars].slice(0, 6).join("")}…</span></label>`).join("");
  $("#groups").addEventListener("change", saveSpec);
  $("#variants").addEventListener("input", debounce(saveSpec, 300));
  await saveSpec(true);
}

async function saveSpec(initial) {
  const groups = [...document.querySelectorAll("#groups input:checked")].map((i) => i.value);
  const variants = +$("#variants").value || 3;
  const r = await api("/api/spec", { method: "POST", body: JSON.stringify({ groups, variants }) });
  $("#tplinfo").textContent = `${r.cells} cases à remplir, sur ${r.pages} page${r.pages > 1 ? "s" : ""}.`;
  $("#tplimg").src = "/api/template.png?page=1&_=" + Date.now();
  if (initial !== true) { excluded.clear(); refresh(); }
  $("#nvar").value = Math.max(+$("#nvar").value, Math.min(8, Math.max(variants, 2)));
  $("#nvar").dispatchEvent(new Event("input"));
}

// ---------- 2. scans ----------
async function upload(files) {
  for (const f of files) {
    const line = document.createElement("div");
    line.textContent = `${f.name} : analyse…`;
    $("#files").prepend(line);
    try {
      const r = await api("/api/upload", { method: "POST", body: f });
      line.innerHTML = `${f.name} → <b class="ok">page ${r.page}/${r.total} reconnue</b>`;
    } catch (e) {
      line.innerHTML = `${f.name} → <b class="bad">${e.message}</b>`;
    }
  }
  refresh();
}

const drop = $("#drop"), pick = $("#pick");
drop.onclick = () => pick.click();
pick.onchange = () => { upload([...pick.files]); pick.value = ""; };
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); upload([...e.dataTransfer.files]); };
$("#reset").onclick = async () => { await api("/api/reset", { method: "POST" }); $("#files").innerHTML = ""; refresh(); };

const thr = $("#thr");
thr.oninput = () => { $("#thrv").textContent = thr.value; refreshDebounced(); };

async function refresh() {
  const t = +thr.value;
  state = await api("/api/state?t=" + t);
  $("#pages").innerHTML = Array.from({ length: state.total }, (_, i) =>
    `<span class="chip ${state.pages.includes(i + 1) ? "on" : ""}">Page ${i + 1}</span>`).join("");
  const byChar = new Map();
  for (const it of state.items) {
    if (!it.scanned) continue;
    if (!byChar.has(it.ch)) byChar.set(it.ch, []);
    byChar.get(it.ch).push(it);
  }
  $("#gallery").innerHTML = [...byChar].map(([ch, its]) =>
    `<div class="ch"><b>${ch.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</b>${its.map((it) =>
      `<div class="cell ${it.ink ? "" : "empty"} ${excluded.has(it.i) ? "off" : ""}" data-i="${it.i}"><img loading="lazy" src="/api/cell?i=${it.i}&t=${t}"></div>`).join("")}</div>`).join("");
}
const refreshDebounced = debounce(refresh, 250);
$("#gallery").addEventListener("click", (e) => {
  const c = e.target.closest(".cell"); if (!c) return;
  const i = +c.dataset.i;
  excluded.has(i) ? excluded.delete(i) : excluded.add(i);
  c.classList.toggle("off");
});

// ---------- 3. construction ----------
for (const r of document.querySelectorAll(".grid2 input[type=range]")) {
  const out = r.parentElement.querySelector("output");
  const upd = () => (out.textContent = r.id === "smooth" ? (r.value / 100).toFixed(2) : r.value);
  r.addEventListener("input", upd); upd();
}

async function build() {
  $("#build").disabled = true;
  $("#buildmsg").textContent = "Vectorisation et assemblage… (quelques secondes)";
  try {
    const r = await api("/api/build", {
      method: "POST",
      body: JSON.stringify({
        family: $("#family").value.trim() || "MonEcriture",
        threshold: +thr.value, variants: +$("#nvar").value, jitter: +$("#jitter").value,
        sidebearing: +$("#sb").value, space: +$("#space").value, size: +$("#size").value,
        smooth: +$("#smooth").value / 100, seed, excluded: [...excluded],
      }),
    });
    const v = Date.now();
    $("#dlotf").href = `/out/${r.files.otf}?dl=1`;
    $("#dlttf").href = `/out/${r.files.ttf}?dl=1`;
    $("#resinfo").textContent = `${r.chars} caractères · ${r.variants} variantes chacun (${r.synthetic} synthétiques)` +
      (r.missing ? ` · manquants : ${r.missing}` : "");
    const ff = new FontFace("Preview" + v, `url(/out/${r.files.otf}?v=${v})`);
    await ff.load(); document.fonts.add(ff);
    $("#preview").style.fontFamily = `"Preview${v}", serif`;
    $("#result").hidden = false;
    $("#buildmsg").textContent = "";
  } catch (e) {
    $("#buildmsg").innerHTML = `<b class="bad">${e.message}</b>`;
  }
  $("#build").disabled = false;
}
$("#build").onclick = build;
$("#reroll").onclick = () => { seed = Math.floor(Math.random() * 1e6); build(); };
$("#calt").onchange = (e) => ($("#preview").style.fontFeatureSettings = e.target.checked ? '"calt" 1' : '"calt" 0');
$("#fs").oninput = (e) => ($("#preview").style.fontSize = e.target.value + "px");

initGroups().then(refresh);
