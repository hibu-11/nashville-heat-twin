// =====================================================================
// 【中文】级联模型可视化（简易版）：读取 pipeline 生成的 data/twin/ 文件——
//   graph_nodes / graph_edges（依赖图）、logic.json（规则统计）、results/（模拟结果）。
// 地图按所选情景和小时给分区、变电站、医疗设施着色；底部时间轴可点击或播放。
// Cascade-model viewer: reads data/twin/ written by the pipeline.
// =====================================================================
const DATA = "data/";
const TWIN = DATA + "twin/";
const RES = TWIN + "results/";
const PLAY_MS = 120;

const TYPE_COLOR = {
  substation: "#2a6f89", hospital: "#b8432f", dialysis: "#7a3e9d", nursing_home: "#c27c0e",
  water_works: "#3b7fbf", water_tower: "#3b7fbf", reservoir_covered: "#3b7fbf", wastewater_plant: "#8fa3ad",
  traffic_signal: "#5b6a70",
};
const TYPE_LABEL = {
  substation: "Substation", service_zone: "Service zone (placeholder)", hospital: "Hospital", dialysis: "Dialysis facility",
  nursing_home: "Nursing home", water_works: "Water works", water_tower: "Water tower", reservoir_covered: "Covered reservoir",
  wastewater_plant: "Wastewater plant", traffic_signal: "Traffic signal",
};
// 【中文】依赖边按类型分图层，占位边画虚线 / one layer per edge class; placeholders dashed
const EDGE_CLASSES = [
  { key: "power", label: "Power supply (station → station)", color: "#1f5a70", on: true },
  { key: "power_peer", label: "Load-transfer peers", color: "#6aa7bd", on: true },
  { key: "service", label: "Station / zone → served asset", color: "#8c9993", on: false },
  { key: "water", label: "Water supply and storage", color: "#3b7fbf", on: false },
  { key: "control", label: "Signal → road segment", color: "#5b6a70", on: false },
  { key: "structural", label: "Bridge → road segment", color: "#8a6d3b", on: false },
];
const RISK = [0, "#d6ddd9", 0.002, "#f2d7a6", 0.02, "#eea05a", 0.1, "#d4562e", 0.5, "#8c1d18"];

const S = { map: null, idx: 0, scen: "+0", H: 0, bins: {}, timer: null, card: null };
const $ = (id) => document.getElementById(id);

init();

async function init() {
  const [nodes, edges, logic, summary, ts, pidx, pav, manifest] = await Promise.all([
    json(TWIN + "graph_nodes.geojson"), json(TWIN + "graph_edges.geojson"), json(TWIN + "logic.json"),
    json(RES + "summary.json"), json(RES + "timeseries.json"), json(RES + "p_down_index.json"),
    json(RES + "pavement.json"), json(DATA + "layers.json"),
  ]);
  Object.assign(S, { nodes, edges, logic, summary, ts, pidx, pav, manifest, H: ts.n, tz: ts.timezone });
  S.nodeRow = new Map(pidx.nodes.map((id, i) => [id, i]));
  edges.features.forEach((f) => {
    const p = f.properties;
    p.cls = p.dep_type === "power" && ["R-P3", "R-P4", "R-P4b"].includes(p.rule_id) ? "service"
      : p.dep_type === "water_storage" ? "water" : p.dep_type;
    p.ph = p.placeholder === "yes";
  });
  S.idx = hottestHour(ts);
  await loadScenario("+0");

  const aoi = manifest.aoi;
  S.map = new maplibregl.Map({
    container: "map", maxZoom: 18,
    bounds: [[aoi[0], aoi[1]], [aoi[2], aoi[3]]], fitBoundsOptions: { padding: { left: 400, right: 40, top: 30, bottom: 200 } },
    style: {
      version: 8,
      sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19,
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' } },
      layers: [
        { id: "bg", type: "background", paint: { "background-color": "#e4e8e5" } },
        { id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.75, "raster-saturation": -0.9, "raster-contrast": -0.15 } },
      ],
    },
    attributionControl: { compact: true, customAttribution: "Model v0 · Vanderbilt DSI" },
  });
  S.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  S.map.on("load", async () => {
    await addLayers();
    buildPanel();
    buildChart();
    setHour(S.idx);
  });
  $("play").addEventListener("click", () => (S.timer ? stop() : play()));
}

// ------------------------------------------------------------------ data
async function loadScenario(key) {
  S.scen = key;
  if (!S.bins[key]) {
    const buf = await fetch(RES + S.pidx.files[key]).then((r) => r.arrayBuffer());
    S.bins[key] = new Uint8Array(buf);
  }
}

function p(id, h = S.idx) {
  const r = S.nodeRow.get(id);
  return r === undefined ? null : S.bins[S.scen][r * S.H + h] / S.pidx.scale;
}

function seasonHours(id) {
  const r = S.nodeRow.get(id), b = S.bins[S.scen];
  if (r === undefined) return null;
  let s = 0;
  for (let h = 0; h < S.H; h++) s += b[r * S.H + h];
  return s / S.pidx.scale;
}

function hottestHour(ts) {
  let best = 0;
  ts.air_temp_c.forEach((t, i) => { if (t > ts.air_temp_c[best]) best = i; });
  return best;
}

// ------------------------------------------------------------------ map
async function addLayers() {
  const map = S.map;
  const zones = { type: "FeatureCollection", features: S.nodes.features.filter((f) => f.properties.asset_type === "service_zone") };
  const pts = { type: "FeatureCollection", features: S.nodes.features.filter((f) => f.properties.asset_type !== "service_zone") };
  // 【中文】OSM 电压如 "69000;23900"，取最高值（kV）/ highest voltage in kV
  pts.features.forEach((f) => { f.properties.kvmax = Math.max(0, ...String(f.properties.kv ?? "").split(";").map(Number).filter(Number.isFinite)) / 1000; });
  const roads = await json(DATA + "vector/roads_lst.geojson");
  map.addSource("zones", { type: "geojson", data: zones, promoteId: "asset_id" });
  map.addSource("nodes", { type: "geojson", data: pts, promoteId: "asset_id" });
  map.addSource("edges", { type: "geojson", data: S.edges });
  map.addSource("roads", { type: "geojson", data: roads, promoteId: "asset_id" });

  const risk = (prop) => ["interpolate", ["linear"], ["coalesce", ["feature-state", prop], 0], ...RISK];
  map.addLayer({ id: "zones-fill", type: "fill", source: "zones", paint: { "fill-color": risk("p"), "fill-opacity": 0.45 } });
  map.addLayer({ id: "zones-line", type: "line", source: "zones",
    paint: { "line-color": "#1e2b31", "line-width": 0.8, "line-opacity": 0.5, "line-dasharray": [3, 2] } });

  // 【中文】路面热损伤：P(7 天平均最高 LST > PG 高温等级)（Eq. 15）/ pavement exceedance probability
  const maxDays = 1;
  map.addLayer({ id: "roads-pav", type: "line", source: "roads", layout: { visibility: "none", "line-cap": "round" },
    paint: { "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1, 15, 3.5],
      "line-color": ["interpolate", ["linear"], ["coalesce", ["feature-state", "pav"], 0],
        0, "#d6ddd9", maxDays * 0.1, "#f2d7a6", maxDays * 0.4, "#eea05a", maxDays, "#8c1d18"] } });

  for (const c of EDGE_CLASSES) {
    for (const ph of [false, true]) {
      map.addLayer({ id: `edge-${c.key}-${ph ? "ph" : "real"}`, type: "line", source: "edges",
        filter: ["all", ["==", ["get", "cls"], c.key], ["==", ["get", "ph"], ph]],
        layout: { visibility: c.on ? "visible" : "none" },
        paint: { "line-color": c.color, "line-opacity": c.key === "power" ? 0.85 : 0.55,
          "line-width": c.key === "power" || c.key === "power_peer" ? 1.6 : 0.8,
          ...(ph ? { "line-dasharray": [2, 2] } : {}) } });
    }
  }

  const kvRadius = ["case", [">=", ["get", "kvmax"], 161], 8, [">=", ["get", "kvmax"], 69], 6, 4.5];
  map.addLayer({ id: "signals", type: "circle", source: "nodes", filter: ["==", ["get", "asset_type"], "traffic_signal"],
    layout: { visibility: "none" }, paint: { "circle-radius": 2, "circle-color": "#5b6a70", "circle-opacity": 0.7 } });
  map.addLayer({ id: "nodes", type: "circle", source: "nodes", filter: ["!=", ["get", "asset_type"], "traffic_signal"],
    paint: {
      "circle-radius": ["case", ["==", ["get", "asset_type"], "substation"], kvRadius, 6],
      "circle-color": ["case", ["in", ["get", "asset_type"], ["literal", ["substation", "hospital", "dialysis", "nursing_home"]]],
        risk("p"), "#ffffff"],
      "circle-stroke-color": ["match", ["get", "asset_type"], ...Object.entries(TYPE_COLOR).flat(), "#1e2b31"],
      "circle-stroke-width": ["case", ["==", ["get", "asset_type"], "substation"], 2, 2.5],
    } });

  for (const [id, v] of Object.entries(S.pav.roads)) map.setFeatureState({ source: "roads", id }, { pav: v });

  map.on("click", "nodes", (e) => openCard(e.features[0].properties));
  map.on("click", "zones-fill", (e) => {
    if (!map.queryRenderedFeatures(e.point, { layers: ["nodes"] }).length) openCard(e.features[0].properties);
  });
  for (const l of ["nodes", "zones-fill"]) {
    map.on("mouseenter", l, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", l, () => (map.getCanvas().style.cursor = ""));
  }
}

function paintHour() {
  const map = S.map;
  for (const id of S.pidx.nodes) map.setFeatureState({ source: "nodes", id }, { p: p(id) });
  for (const [zone, sub] of Object.entries(S.pidx.zone_substation)) {
    if (sub) map.setFeatureState({ source: "zones", id: zone }, { p: p(sub) });
  }
}

// ------------------------------------------------------------------ time
const fmtTime = () => new Intl.DateTimeFormat("en-US", { timeZone: S.tz, weekday: "short", month: "short", day: "numeric",
  hour: "2-digit", minute: "2-digit", hour12: false, timeZoneName: "short" });
const hourDate = (h) => new Date(Date.parse(S.ts.start) + h * 3600e3);

function setHour(h) {
  S.idx = Math.max(0, Math.min(S.H - 1, h));
  paintHour();
  updateNow();
  moveCursor();
  if (S.card) openCard(S.card);
}

function play() {
  S.timer = setInterval(() => setHour((S.idx + 1) % S.H), PLAY_MS);
  $("playIcon").setAttribute("d", "M4 2.5h3v11H4zM9 2.5h3v11H9z");
  $("play").setAttribute("aria-label", "Pause");
}
function stop() {
  clearInterval(S.timer); S.timer = null;
  $("playIcon").setAttribute("d", "M4 2.5v11l9-5.5z");
  $("play").setAttribute("aria-label", "Play");
}

// ------------------------------------------------------------------ panel
function buildPanel() {
  const seg = $("scenario");
  seg.innerHTML = Object.keys(S.summary.scenarios).map((k) =>
    `<button role="radio" data-k="${k}" aria-checked="${k === S.scen}">${k === "+0" ? "2023 observed" : `${k} °C`}</button>`).join("");
  seg.querySelectorAll("button").forEach((b) => b.addEventListener("click", async () => {
    await loadScenario(b.dataset.k);
    seg.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
    buildChart(); setHour(S.idx); updateSeason();
  }));
  $("runsNote").textContent = `${S.summary.runs.toLocaleString()} Monte Carlo runs`;
  $("runId").textContent = S.summary.run_id;
  updateSeason();
  buildLogic();
  buildToggles();
  buildValidation();
  buildSensitivity();
}

function scenSeries(key) {
  const sc = S.ts.scenarios[key];
  return { mean: sc.pop_out_mean, p95: sc.pop_out_p95, subs: sc.subs_down_mean, share: sc.share_runs_out };
}

function updateNow() {
  const h = S.idx, off = Number(S.scen);
  const ser = scenSeries(S.scen);
  $("nowTime").textContent = fmtTime().format(hourDate(h));
  const sum = (ids) => ids.reduce((s, id) => s + (p(id) ?? 0), 0);
  const ids = (t) => S.nodes.features.filter((f) => f.properties.asset_type === t).map((f) => f.properties.asset_id);
  const rows = [
    ["Air temperature", `${fmt(S.ts.air_temp_c[h] + off)} °C`, S.ts.storm[h] ? "thunder within ±3 h" : ""],
    ["Substations down (expected)", fmt(ser.subs[h], 2), `of ${S.summary.network.substations}`],
    ["Population without power (mean)", `${int(ser.mean[h])}`, `outage in ${pct(ser.share[h], 1)} of runs`],
    ["Hospitals without power", fmt(sum(ids("hospital")), 2), `of ${S.summary.network.hospitals}`],
    ["Dialysis facilities down", fmt(sum(ids("dialysis")), 2), `of ${S.summary.network.dialysis}`],
    ["Nursing homes without power", fmt(sum(ids("nursing_home")), 2), `of ${S.summary.network.nursing_homes}`],
    ["Observed outages, county", int(S.ts.observed_customers_out[h]), "EAGLE-I customers out"],
  ];
  $("kpis").innerHTML = rows.map(([k, v, s]) => `<div class="kpi"><span>${k}</span><b>${v}</b><small>${s}</small></div>`).join("");
}

function updateSeason() {
  const t = S.summary.scenarios[S.scen];
  const rows = [
    ["Runs with any substation failure", pct(t.share_runs_with_any_failure), ""],
    ["Person-hours without power", int(t.pop_hours.mean), `median ${int(t.pop_hours["50"])} · p95 ${int(t.pop_hours["95"])}`],
    ["…of which at ≥ heat threshold", int(t.compound_pop_hours.mean), "compound heat–outage exposure (Eq. 14)"],
    ["Thermal failures", fmt(t.thermal.mean, 1), `p95 ${fmt(t.thermal["95"], 0)}`],
    ["Overload trips", fmt(t.overload.mean, 1), `${fmt(t.amplification.mean, 2)} per thermal failure`],
    ["Dialysis facility-hours down", fmt(t.dialysis_hours.mean, 1), ""],
  ];
  $("season").innerHTML = rows.map(([k, v, s]) => `<div class="kpi"><span>${k}</span><b>${v}</b><small>${s}</small></div>`).join("");
}

// 【中文】逻辑图：系统级节点 + 规则 / 耦合编号与边数 / system-level logic diagram
function buildLogic() {
  const n = (pred) => S.logic.links.filter(pred).reduce((s, l) => s + l.n, 0);
  const byC = (c) => n((l) => l.coupling_id === c);
  const byR = (rs) => n((l) => rs.includes(l.rule_id));
  const boxes = {
    air: [8, 10, "Air temperature", "ASOS BNA, hourly"], lst: [8, 214, "LST 10 m", "hourly frames"],
    sub: [118, 60, "Substations", `${S.summary.network.substations} · OSM`], zone: [118, 150, "Service zones", `${S.summary.network.zones} · Voronoi`],
    hosp: [232, 10, "Hospitals", `${S.summary.network.hospitals} · CMS`], nurs: [232, 52, "Nursing homes", `${S.summary.network.nursing_homes} · CMS`],
    dial: [232, 94, "Dialysis", `${S.summary.network.dialysis} · CMS`], water: [232, 136, "Water plants", `${S.summary.network.water_plants} · OSM`],
    sig: [232, 178, "Traffic signals", `${S.summary.network.signals} · OSM`], pop: [232, 220, "Population", `${int(S.summary.population_in_zones)} · ACS`],
    road: [118, 240, "Road segments", "TIGER"],
  };
  const W = 104, Hh = 34;
  const mid = (k, side) => { const [x, y] = boxes[k]; return side === "r" ? [x + W, y + Hh / 2] : side === "l" ? [x, y + Hh / 2] : side === "t" ? [x + W / 2, y] : [x + W / 2, y + Hh]; };
  const links = [
    ["air", "r", "sub", "l", "C-P1–P3 · Eq. 2–7", false],
    ["sub", "b", "zone", "t", `R-P1/1b/2 · ${byR(["R-P1", "R-P1b", "R-P2"])} links`, false],
    ["zone", "r", "hosp", "l", `C-H1 · ${byC("C-H1")}`, true], ["zone", "r", "nurs", "l", `C-H2 · ${byC("C-H2")}`, true],
    ["zone", "r", "dial", "l", `C-H3 · ${byC("C-H3")}`, true], ["zone", "r", "water", "l", `C-W2 · ${byC("C-W2")}`, true],
    ["zone", "r", "sig", "l", `C-T2 · ${byC("C-T2")}`, true], ["zone", "r", "pop", "l", `C-POP1 · ${byC("C-POP1")}`, true],
    ["water", "t", "dial", "b", "C-W1/W3", true], ["sig", "l", "road", "r", `C-T3 · ${byC("C-T3")}`, false],
    ["lst", "r", "road", "l", "C-T1 · Eq. 15", false],
  ];
  const lines = links.map(([a, sa, b, sb, label, ph], i) => {
    const [x1, y1] = mid(a, sa), [x2, y2] = mid(b, sb);
    const lx = (x1 + x2) / 2, ly = (y1 + y2) / 2 - 3;
    const showLabel = !(a === "zone" && i > 2);
    return `<path d="M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}" class="lg-edge${ph ? " ph" : ""}" marker-end="url(#arrow)"/>`
      + (showLabel ? `<text x="${lx}" y="${ly}" class="lg-label" text-anchor="middle">${label}</text>` : "");
  }).join("");
  const rect = Object.entries(boxes).map(([k, [x, y, t, s]]) =>
    `<g><rect x="${x}" y="${y}" width="${W}" height="${Hh}" rx="5" class="lg-box lg-k-${k}"/>
     <text x="${x + 7}" y="${y + 14}" class="lg-title">${t}</text><text x="${x + 7}" y="${y + 27}" class="lg-sub">${s}</text></g>`).join("");
  const zoneLinks = ["C-H1", "C-H2", "C-H3", "C-W2", "C-T2", "C-POP1"].map((c) => `${c} ${byC(c)}`).join(" · ");
  $("logic").innerHTML = `<svg viewBox="0 0 340 280" width="100%" role="img" aria-label="System-level dependency logic">
      <defs><marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M0,0 L8,4 L0,8 z" class="lg-arrow"/></marker></defs>${lines}${rect}</svg>
    <p class="hint">Zone → asset links (series gates, placeholder service areas): ${zoneLinks}.
      Solid = inferred from real data, dashed = placeholder. ${pct(S.logic.stats.placeholder_share)} of ${int(S.logic.stats.edges)} edges are placeholders.</p>`;
}

function buildToggles() {
  const rows = [
    ...EDGE_CLASSES.map((c) => ({ id: c.key, label: c.label, color: c.color, on: c.on, layers: [`edge-${c.key}-real`, `edge-${c.key}-ph`] })),
    { id: "zones", label: "Service zones (placeholder)", color: "#eea05a", on: true, layers: ["zones-fill", "zones-line"] },
    { id: "signals", label: "Traffic signals", color: "#5b6a70", on: false, layers: ["signals"] },
    { id: "pav", label: `Pavement: P(7-day max LST > PG 64), ${S.summary.validation.pavement_requests_lst_period.period}`, color: "#d4562e", on: false, layers: ["roads-pav"] },
  ];
  $("toggles").innerHTML = rows.map((r) => `<label class="tg"><input type="checkbox" data-id="${r.id}" ${r.on ? "checked" : ""}>
    <span class="tg-sw" style="background:${r.color}"></span>${r.label}</label>`).join("");
  $("toggles").querySelectorAll("input").forEach((inp) => inp.addEventListener("change", () => {
    const r = rows.find((x) => x.id === inp.dataset.id);
    r.layers.forEach((l) => S.map.setLayoutProperty(l, "visibility", inp.checked ? "visible" : "none"));
  }));
}

function buildValidation() {
  const v = S.summary.validation;
  const ci = (r) => r.rho === null ? "—" : `${fmt(r.rho, 2)} [${fmt(r.lo, 2)}, ${fmt(r.hi, 2)}]`;
  const a = (r) => r.auc === null || r.auc === undefined ? "—" : fmt(r.auc, 2);
  const bins = v.observed_by_temperature_non_storm.map((b) =>
    `<tr><td>${b.bin_c.replace("(", "").replace("]", "").replace(", ", "–")} °C</td><td>${b.hours}</td><td>${int(b.median)}</td><td>${int(b.p90)}</td></tr>`).join("");
  $("validation").innerHTML = `
    <table class="vt"><tbody>
      <tr><th colspan="2">Power: model vs EAGLE-I (Spearman ρ, 95% day-block CI)</th></tr>
      <tr><td>All hours</td><td>${ci(v.power_all_hours)}</td></tr>
      <tr><td>Non-storm hours</td><td>${ci(v.power_non_storm_hours)}</td></tr>
      <tr><th colspan="2">Data only: air temperature vs observed outages</th></tr>
      <tr><td>Non-storm hours</td><td>${ci(v.temperature_vs_observed_non_storm)}</td></tr>
      <tr><td>Daily max (all days)</td><td>${ci(v.daily_tmax_vs_observed)}</td></tr>
      <tr><th colspan="2">Roads: 311 pavement requests (AUC, ${v.pavement_requests_lst_period.n_pos} segments with requests)</th></tr>
      <tr><td>P(7-day max LST > PG grade) (Eq. 15)</td><td>${a(v.pavement_requests_lst_period)}</td></tr>
      <tr><td>Segment length only (baseline)</td><td>${a(v.pavement_requests_lst_period_length_only)}</td></tr>
      <tr><td>7-day max LST within length quintiles</td><td>${a(v.pavement_requests_lst_period_within_length_quintiles)}</td></tr>
    </tbody></table>
    <details><summary>Observed outages by air temperature (non-storm hours)</summary>
      <table class="vt"><thead><tr><th>Air temp.</th><th>Hours</th><th>Median</th><th>p90</th></tr></thead><tbody>${bins}</tbody></table>
    </details>`;
}

function buildSensitivity() {
  const rows = S.summary.sensitivity.slice(0, 6).map((r) =>
    `<tr><td><code>${r.param}</code> ${r.name}</td><td><span class="basis ${r.basis}">${r.basis}</span></td><td>${fmt(r.pop_hours, 2)}</td></tr>`).join("");
  $("sensitivity").innerHTML = `<table class="vt"><thead><tr><th>Parameter</th><th>Basis</th><th>ρ with person-hours</th></tr></thead><tbody>${rows}</tbody></table>
    <p class="hint">Rank correlation between each sampled parameter and season person-hours without power (baseline scenario).
      Placeholders near the top are the first to replace with utility data.</p>`;
}

// ------------------------------------------------------------------ chart
function buildChart() {
  const el = $("chart");
  const W = Math.max(600, el.clientWidth), H = 150, pad = { l: 46, r: 46, t: 8, b: 18 };
  const n = S.H, ser = scenSeries(S.scen), off = Number(S.scen);
  const x = (i) => pad.l + (i / (n - 1)) * (W - pad.l - pad.r);
  const ta = S.ts.air_temp_c.map((t) => t + off);
  const tH = 34, tTop = pad.t;
  const tMin = 15, tMax = 45;
  const yT = (t) => tTop + (1 - (t - tMin) / (tMax - tMin)) * tH;
  const pTop = tTop + tH + 10, pH = H - pTop - pad.b;
  const pMax = Math.max(1, ...ser.p95);
  const oMax = Math.max(1, ...S.ts.observed_customers_out);
  const yP = (v) => pTop + (1 - v / pMax) * pH;
  const yO = (v) => pTop + (1 - v / oMax) * pH;
  const poly = (arr, y) => arr.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  // 【中文】雷暴小时与 ≥ 35 °C 的日子做底色 / shade storm hours and days reaching 35 °C
  const storm = S.ts.storm.map((s, i) => (s ? `<rect x="${x(i)}" y="${pTop}" width="${Math.max(1, x(1) - x(0))}" height="${pH}" class="c-storm"/>` : "")).join("");
  const hot = [];
  for (let d = 0; d < n; d += 24) {
    const mx = Math.max(...ta.slice(d, d + 24));
    if (mx >= 35) hot.push(`<rect x="${x(d)}" y="${tTop}" width="${x(Math.min(n - 1, d + 24)) - x(d)}" height="${H - tTop - pad.b}" class="c-hot"/>`);
  }
  const months = [];
  for (let i = 0; i < n; i++) {
    const d = hourDate(i);
    const loc = new Intl.DateTimeFormat("en-US", { timeZone: S.tz, day: "numeric", hour: "numeric", hour12: false }).formatToParts(d);
    const day = loc.find((q) => q.type === "day").value, hr = loc.find((q) => q.type === "hour").value;
    if ((day === "1" || day === "15") && (hr === "0" || hr === "24"))
      months.push(`<line x1="${x(i)}" x2="${x(i)}" y1="${tTop}" y2="${H - pad.b}" class="c-tick"/><text x="${x(i) + 3}" y="${H - 5}" class="c-txt">${new Intl.DateTimeFormat("en-US", { timeZone: S.tz, month: "short", day: "numeric" }).format(d)}</text>`);
  }
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" id="chartSvg" role="img" aria-label="Hourly air temperature, modelled population without power and observed outages">
    ${hot.join("")}${storm}${months.join("")}
    <polyline points="${poly(ta, yT)}" class="c-ta"/>
    <text x="${pad.l - 6}" y="${yT(40) + 3}" class="c-txt" text-anchor="end">40 °C</text>
    <text x="${pad.l - 6}" y="${yT(20) + 3}" class="c-txt" text-anchor="end">20 °C</text>
    <polygon points="${x(0)},${yP(0)} ${poly(ser.p95, yP)} ${x(n - 1)},${yP(0)}" class="c-band"/>
    <polyline points="${poly(ser.mean, yP)}" class="c-mod"/>
    <polyline points="${poly(S.ts.observed_customers_out, yO)}" class="c-obs"/>
    <text x="${pad.l - 6}" y="${pTop + 8}" class="c-txt c-mod-t" text-anchor="end">${short(pMax)}</text>
    <text x="${W - pad.r + 6}" y="${pTop + 8}" class="c-txt c-obs-t">${short(oMax)}</text>
    <line id="cursor" y1="${tTop}" y2="${H - pad.b}" class="c-cursor"/>
    <rect x="${pad.l}" y="0" width="${W - pad.l - pad.r}" height="${H}" fill="transparent" id="hit"/>
  </svg>`;
  S.chartX = x; S.chartPad = pad; S.chartW = W;
  $("dockLegend").innerHTML = `<span><i class="lg c-ta-i"></i>Air temperature${off ? ` (+${off} °C)` : ""}</span>
    <span><i class="lg c-mod-i"></i>Modelled population without power (mean; band = p95, left axis)</span>
    <span><i class="lg c-obs-i"></i>Observed customers out, Davidson County (EAGLE-I, right axis)</span>
    <span><i class="lg c-storm-i"></i>Thunder ±3 h</span><span><i class="lg c-hot-i"></i>Day ≥ 35 °C</span>`;
  const svg = $("chartSvg");
  const pick = (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    setHour(Math.round(((px - pad.l) / (W - pad.l - pad.r)) * (n - 1)));
  };
  let drag = false;
  $("hit").addEventListener("pointerdown", (e) => { drag = true; stop(); pick(e); });
  window.addEventListener("pointermove", (e) => drag && pick(e));
  window.addEventListener("pointerup", () => (drag = false));
  moveCursor();
}

function moveCursor() {
  const c = document.getElementById("cursor");
  if (c && S.chartX) { const xx = S.chartX(S.idx); c.setAttribute("x1", xx); c.setAttribute("x2", xx); }
}

// ------------------------------------------------------------------ card
function openCard(props) {
  S.card = props;
  const id = props.asset_id;
  const isZone = props.asset_type === "service_zone";
  const sub = isZone ? S.pidx.zone_substation[id] : null;
  const pid = isZone ? sub : id;
  const pNow = p(pid), season = seasonHours(pid);
  const rel = S.edges.features.map((f) => f.properties).filter((e) => e.from_asset === id || e.to_asset === id);
  const nameOf = (a) => S.nodes.features.find((f) => f.properties.asset_id === a)?.properties.name || a;
  const relRows = rel.slice(0, 14).map((e) => {
    const out = e.from_asset === id;
    return `<tr><td>${out ? "→" : "←"} ${esc(nameOf(out ? e.to_asset : e.from_asset))}</td><td><code>${e.rule_id}</code></td>
      <td><code>${e.coupling_id}</code></td><td>${e.gate}</td><td>${e.ph ? "placeholder" : "real"}</td></tr>`;
  }).join("");
  const facts = [
    ["Type", TYPE_LABEL[props.subtype] ?? TYPE_LABEL[props.asset_type] ?? props.asset_type],
    props.kv && ["Voltage", `${String(props.kv).split(";").map((v) => `${Number(v) / 1000} kV`).join(" / ")}`],
    isZone && ["Population", int(props.pop_total)], isZone && ["Age 65+", int(props.pop_elderly)],
    isZone && ["Building footprint", `${int(props.building_area_m2 / 1e4)} ha`],
    pNow !== null && ["P(down) this hour", pct(pNow, 2)],
    season !== null && ["Expected hours down, Jun–Aug", fmt(season, 2)],
    ["Asset ID", `<code>${esc(isZone ? id : id)}</code>`],
  ].filter(Boolean);
  $("card").innerHTML = `<button class="close" id="cardClose" aria-label="Close">×</button>
    <h3>${esc(props.name || TYPE_LABEL[props.asset_type] || id)}</h3>
    <dl>${facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
    ${rel.length ? `<h4>Dependencies (${rel.length}${rel.length > 14 ? ", first 14" : ""})</h4>
      <table class="vt"><thead><tr><th>Linked asset</th><th>Rule</th><th>Coupling</th><th>Gate</th><th></th></tr></thead><tbody>${relRows}</tbody></table>` : ""}`;
  $("card").hidden = false;
  $("cardClose").addEventListener("click", () => { $("card").hidden = true; S.card = null; });
}

// ------------------------------------------------------------------ utils
async function json(url) { const r = await fetch(url); if (!r.ok) throw new Error(`${url}: ${r.status}`); return r.json(); }
function fmt(v, d = 1) { return v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toFixed(d); }
function int(v) { return v === null || v === undefined ? "—" : Math.round(v).toLocaleString("en-US"); }
function pct(v, d = 0) { return v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`; }
function short(v) { return v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}k` : `${Math.round(v)}`; }
function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]); }
