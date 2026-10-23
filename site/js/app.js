// =====================================================================
// 【中文】数字孪生前端：图层完全由 data/layers.json 驱动（由 pipeline 生成），
// 新增数据集不需要改这里的代码。逐小时序列（raster_series）带时间回放。
// Front end: layers are driven entirely by data/layers.json (written by the
// pipeline), so adding a dataset needs no code change here. Hourly series
// (raster_series) get a time playback bar.
// =====================================================================
const DATA = "data/";
const DEFAULT_AOI = [-86.837, 36.118, -86.727, 36.208];
const R = 6378137; // 【中文】Web Mercator 地球半径 / sphere radius
const PLAY_MS = 650;
const FRAME_CACHE = 36;

// 【中文】可选在线底图（OpenStreetMap，无需 key，需署名）；失效时自托管图层照常显示。
// CARTO 的免费底图现在会给无 key 请求加水印，所以改用 OSM。
// Optional online basemap (OpenStreetMap: no key, attribution required); the
// self-hosted layers still work if it fails. CARTO now watermarks keyless requests.
const ONLINE_BASEMAP = {
  id: "__basemap", title: "Street basemap (online)", group: "Basemap", kind: "basemap", visible: true,
  tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
};

const FIELD_LABELS = { asset_id: "Asset ID" };
const VALUE_KINDS = new Set(["raster", "raster_series"]); // 【中文】一次只显示一个 / one at a time

const state = {
  map: null, manifest: null, layers: [], meta: {}, grids: {}, active: null,
  click: null, pin: null, card: null, series: null, tz: "America/Chicago",
};
const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ boot
init();

async function init() {
  const manifest = await fetchJSON(DATA + "layers.json").catch(() => null);
  state.manifest = manifest;
  state.tz = manifest?.timezone ?? state.tz;
  const aoi = manifest?.aoi ?? DEFAULT_AOI;
  state.layers = [ONLINE_BASEMAP, ...(manifest?.layers ?? [])];
  if (manifest?.built_at) $("builtAt").textContent = `Built ${manifest.built_at.slice(0, 10)}`;

  state.map = new maplibregl.Map({
    container: "map",
    style: baseStyle(),
    bounds: [[aoi[0], aoi[1]], [aoi[2], aoi[3]]],
    fitBoundsOptions: { padding: 40 },
    maxZoom: 19,
    attributionControl: { compact: true, customAttribution: "LST: Nashville LST v4.1 · Vanderbilt DSI" },
  });
  state.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  state.map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "top-right");

  state.map.on("load", async () => {
    // 【中文】一次只显示一个温度图层，优先逐小时序列 / one value layer at a time, hourly first
    const values = state.layers.filter((l) => VALUE_KINDS.has(l.kind));
    const firstOn = values.find((l) => l.visible && l.kind === "raster_series") ?? values.find((l) => l.visible);
    values.forEach((l) => (l.visible = l === firstOn));
    state.active = firstOn?.id ?? null;

    for (const layer of state.layers) {
      try { await addLayer(layer); }
      catch (e) { console.error(layer.id, e); layer.failed = true; }
    }
    wireHourlyPaint();
    buildPanel(manifest);
    await buildTimeline();
    updateLegends();
    wireMap();
    if (state.series) await showFrame(state.series.idx);
  });

  $("openSources").addEventListener("click", openSources);
  $("openChain").addEventListener("click", openChain);
  fetchJSON(DATA + "analysis/chain_check.json").then((c) => { if (c?.ok) $("openChain").hidden = false; }).catch(() => {});
  const setCollapsed = (c) => {
    $("panel").classList.toggle("collapsed", c);
    $("panelToggle").setAttribute("aria-expanded", String(!c));
    $("panelToggle").textContent = c ? "Layers" : "Hide";
  };
  // 【中文】手机上默认收起图层面板 / panel starts collapsed on phones
  setCollapsed(window.matchMedia("(max-width: 640px)").matches);
  $("panelToggle").addEventListener("click", () => setCollapsed(!$("panel").classList.contains("collapsed")));
}

function baseStyle() {
  return {
    version: 8,
    sources: {
      [ONLINE_BASEMAP.id]: { type: "raster", tiles: ONLINE_BASEMAP.tiles, tileSize: 256, maxzoom: 19, attribution: ONLINE_BASEMAP.attribution },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": "#dde2de" } },
      // 【中文】降低饱和度，让温度色带更突出 / desaturated so the heat ramp stands out
      { id: ONLINE_BASEMAP.id, type: "raster", source: ONLINE_BASEMAP.id,
        paint: { "raster-opacity": 0.85, "raster-saturation": -0.85, "raster-contrast": -0.1 } },
    ],
  };
}

// ------------------------------------------------------------------ layers
async function addLayer(l) {
  const map = state.map;
  const vis = l.visible ? "visible" : "none";
  if (l.kind === "basemap") return;

  if (l.kind === "raster_series") return addSeries(l, vis);

  if (l.kind === "raster" || l.kind === "raster_rgb") {
    const meta = await fetchJSON(DATA + l.meta);
    state.meta[l.id] = meta;
    map.addSource(l.id, { type: "image", url: DATA + l.image, coordinates: meta.corners });
    map.addLayer({
      id: l.id, type: "raster", source: l.id, layout: { visibility: vis },
      paint: {
        "raster-opacity": l.opacity, "raster-fade-duration": 0,
        // 【中文】数值栅格用最近邻，保留 10 m 像元 / nearest keeps 10 m pixels honest
        "raster-resampling": l.kind === "raster" ? "nearest" : "linear",
      },
    });
    return;
  }

  if (l.kind === "vector") {
    // 【中文】promoteId 让逐小时着色可以用 feature-state / lets hourly colouring use feature-state
    map.addSource(l.id, { type: "geojson", data: DATA + l.data, promoteId: "asset_id" });
    const color = staticColor(l);
    if (l.geometry === "line") {
      // 【中文】深色衬线，让道路在温度栅格上可辨 / dark casing so roads read on top of the LST raster
      map.addLayer({
        id: `${l.id}__outline`, type: "line", source: l.id, layout: { visibility: vis, "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#1e2b31", "line-opacity": 0.85, "line-width": ["interpolate", ["linear"], ["zoom"], 11, 2.5, 14, 4.5, 17, 9] },
      });
      map.addLayer({
        id: l.id, type: "line", source: l.id, layout: { visibility: vis, "line-cap": "round", "line-join": "round" },
        paint: { "line-color": color, "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1, 14, 2.5, 17, 6] },
      });
    } else if (l.geometry === "circle") {
      map.addLayer({ id: l.id, type: "circle", source: l.id, layout: { visibility: vis },
        paint: { "circle-color": color, "circle-radius": 4, "circle-stroke-color": "#fff", "circle-stroke-width": 1 } });
    } else {
      map.addLayer({ id: l.id, type: "fill", source: l.id, layout: { visibility: vis },
        paint: { "fill-color": color, "fill-opacity": l.role === "events" ? l.opacity : 0.55 } });
      map.addLayer({ id: `${l.id}__outline`, type: "line", source: l.id, layout: { visibility: vis },
        paint: { "line-color": "#1e2b31", "line-width": 0.6, "line-opacity": 0.6 } });
    }
  }
}

function staticColor(l) {
  return l.color
    ? ["interpolate", ["linear"], ["to-number", ["get", l.color.field], l.color.vmin],
       ...rampStops(l.color.vmin, l.color.vmax, l.color.stops)]
    : l.fill_color;
}

function rampStops(vmin, vmax, stops) {
  const out = [];
  stops.forEach((c, i) => out.push(vmin + ((vmax - vmin) * i) / (stops.length - 1), c));
  return out;
}

function setVisible(l, on) {
  l.visible = on;
  const v = on ? "visible" : "none";
  for (const id of [l.id, `${l.id}__outline`]) {
    if (state.map.getLayer(id)) state.map.setLayoutProperty(id, "visibility", v);
  }
}

// ------------------------------------------------------------------ hourly series
// 【中文】每帧是 8 位灰度 + alpha PNG：灰度 g（1–255）→ 数值 lo + (g-1)/254·(hi-lo)。
// 浏览器解码一次，同时用于着色（查色表）和点击读数。
// Each frame is an 8-bit grey+alpha PNG: grey g (1–255) → lo + (g-1)/254·(hi-lo).
// Decoded once, used for both colouring (LUT) and click read-outs.
async function addSeries(l, vis) {
  const meta = await fetchJSON(DATA + l.meta);
  state.meta[l.id] = meta;
  const [w, h] = meta.size;
  const canvas = Object.assign(document.createElement("canvas"), { width: w, height: h });
  const ctx = canvas.getContext("2d");
  const S = {
    layer: l, meta, canvas, ctx, image: ctx.createImageData(w, h), lut: buildLut(meta.stops),
    scratch: Object.assign(document.createElement("canvas"), { width: w, height: h }),
    cache: new Map(), q: null, idx: hottestFrame(meta.frames), token: 0, timer: null, assets: {},
  };
  state.series = S;
  state.map.addSource(l.id, { type: "canvas", canvas, coordinates: meta.corners, animate: false });
  state.map.addLayer({
    id: l.id, type: "raster", source: l.id, layout: { visibility: vis },
    paint: { "raster-opacity": l.opacity, "raster-fade-duration": 0, "raster-resampling": "nearest" },
  });
  for (const [src, a] of Object.entries(meta.asset_series ?? {})) {
    const [ids, buf] = await Promise.all([fetchJSON(DATA + a.index), fetch(DATA + a.values).then((r) => r.arrayBuffer())]);
    S.assets[src] = { ids, row: new Map(ids.map((id, i) => [id, i])), values: new Int16Array(buf),
                      n: meta.frames.length, scale: a.scale, nodata: a.nodata };
  }
}

function hottestFrame(frames) {
  let best = 0;
  frames.forEach((f, i) => { if ((f.mean ?? -Infinity) > (frames[best].mean ?? -Infinity)) best = i; });
  return best;
}

function buildLut(stops) {
  const rgb = stops.map((h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)));
  const lut = new Uint8ClampedArray(256 * 4);
  for (let g = 1; g < 256; g++) {
    const t = ((g - 1) / 254) * (rgb.length - 1);
    const i = Math.min(rgb.length - 2, Math.floor(t)), f = t - i;
    for (let c = 0; c < 3; c++) lut[g * 4 + c] = rgb[i][c] + (rgb[i + 1][c] - rgb[i][c]) * f;
    lut[g * 4 + 3] = 255;
  }
  return lut;
}

function frameData(i) {
  const S = state.series;
  if (S.cache.has(i)) {
    const p = S.cache.get(i);
    S.cache.delete(i); S.cache.set(i, p);   // 【中文】LRU
    return p;
  }
  const p = (async () => {
    const img = new Image();
    img.src = DATA + S.meta.frames[i].image;
    await img.decode();
    const [w, h] = S.meta.size;
    const x = S.scratch.getContext("2d", { willReadFrequently: true });
    x.clearRect(0, 0, w, h);
    x.drawImage(img, 0, 0);
    const px = x.getImageData(0, 0, w, h).data;
    const q = new Uint8Array(w * h);
    for (let k = 0, j = 0; k < q.length; k++, j += 4) q[k] = px[j + 3] ? px[j] : 0;
    return q;
  })();
  S.cache.set(i, p);
  if (S.cache.size > FRAME_CACHE) S.cache.delete(S.cache.keys().next().value);
  p.catch(() => S.cache.delete(i));
  return p;
}

async function showFrame(i) {
  const S = state.series;
  if (!S) return;
  S.idx = i;
  const token = ++S.token;
  $("tlSlider").value = String(i);
  updateTimeLabel(i);
  const q = await frameData(i);
  if (token !== S.token) return;
  S.q = q;
  const out = S.image.data, lut = S.lut;
  for (let k = 0, j = 0; k < q.length; k++, j += 4) {
    const o = q[k] * 4;
    out[j] = lut[o]; out[j + 1] = lut[o + 1]; out[j + 2] = lut[o + 2]; out[j + 3] = lut[o + 3];
  }
  S.ctx.putImageData(S.image, 0, 0);
  // 【中文】canvas 源在 play 期间才上传纹理，渲染一次后暂停 / upload the canvas once, then pause
  const src = state.map.getSource(S.layer.id);
  src.play();
  state.map.once("render", () => src.pause());
  state.map.triggerRepaint();

  applyAssetState();
  if (state.click && state.active === S.layer.id) updateValue(state.click.lngLat);
  updateCardMarker();
  for (let k = 1; k <= 3; k++) if (i + k < S.meta.frames.length) frameData(i + k);
}

// 【中文】道路等资产按当前小时着色 / colour assets by the current hour
function wireHourlyPaint() {
  const S = state.series;
  if (!S) return;
  const [lo, hi] = S.meta.range;
  const hourly = ["interpolate", ["linear"], ["feature-state", "lst"], ...rampStops(lo, hi, S.meta.stops)];
  for (const l of state.layers) {
    if (l.kind !== "vector" || !S.assets[l.id] || !state.map.getLayer(l.id)) continue;
    const prop = l.geometry === "line" ? "line-color" : l.geometry === "circle" ? "circle-color" : "fill-color";
    state.map.setPaintProperty(l.id, prop,
      ["case", ["==", ["typeof", ["feature-state", "lst"]], "number"], hourly, staticColor(l)]);
    l.hourly = true;
  }
}

function hourlyMode() {
  return !!state.series && state.active === state.series.layer.id;
}

function applyAssetState() {
  const S = state.series;
  if (!S) return;
  for (const [src, a] of Object.entries(S.assets)) {
    if (!state.map.getSource(src)) continue;
    if (!hourlyMode()) { state.map.removeFeatureState({ source: src }); continue; }
    for (let r = 0; r < a.ids.length; r++) {
      const raw = a.values[r * a.n + S.idx];
      state.map.setFeatureState({ source: src, id: a.ids[r] }, { lst: raw === a.nodata ? null : raw / a.scale });
    }
  }
}

function seriesValue(lng, lat) {
  const S = state.series;
  if (!S?.q) return null;
  const [w, h] = S.meta.size;
  const cell = mercCell(S.meta.merc_bounds, w, h, lng, lat);
  if (!cell) return null;
  const g = S.q[cell.row * w + cell.col];
  const [lo, hi] = S.meta.range;
  return g === 0 ? null : lo + ((g - 1) / S.meta.levels) * (hi - lo);
}

// ------------------------------------------------------------------ timeline
const fmtDay = () => new Intl.DateTimeFormat("en-US", { timeZone: state.tz, weekday: "short", month: "short", day: "numeric", year: "numeric" });
const fmtHour = () => new Intl.DateTimeFormat("en-US", { timeZone: state.tz, hour: "2-digit", minute: "2-digit", hour12: false, timeZoneName: "short" });
const localDate = (iso) => new Intl.DateTimeFormat("en-CA", { timeZone: state.tz }).format(new Date(iso));

function inWindow(date, w) { return !!w && date >= w.start && date <= w.end; }

async function buildTimeline() {
  const S = state.series;
  if (!S) return;
  const frames = S.meta.frames;
  const heat = state.manifest?.heatwave, base = state.manifest?.baseline;
  S.days = [];
  frames.forEach((f, i) => {
    const d = localDate(f.t);
    f.date = d;
    const last = S.days[S.days.length - 1];
    if (last?.date === d) last.count++;
    else S.days.push({ date: d, start: i, count: 1 });
  });

  // 【中文】每日事件数（聚合）/ daily event counts (aggregated)
  const evLayer = state.layers.find((l) => l.daily);
  const daily = evLayer ? await fetchJSON(DATA + evLayer.daily).catch(() => null) : null;
  const perDay = new Map();
  daily?.dates.forEach((d, i) => perDay.set(d, daily.counts[i].reduce((a, b) => a + b, 0)));
  const maxEv = Math.max(1, ...S.days.map((d) => perDay.get(d.date) ?? 0));

  const strip = $("tlDays");
  strip.innerHTML = "";
  let prev = null;
  for (const day of S.days) {
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "tl-day" + (inWindow(day.date, heat) ? " heat" : "");
    cell.style.flexGrow = String(day.count);
    const n = perDay.get(day.date);
    const gap = prev && (Date.parse(day.date) - Date.parse(prev)) / 864e5 > 1;
    if (gap) cell.classList.add("after-gap");
    const missing = gap ? missingDates(prev, day.date) : [];
    cell.title = `${fmtDay().format(new Date(frames[day.start].t))} · ${day.count} LST frame${day.count > 1 ? "s" : ""}`
      + (n !== undefined ? ` · ${n} ${evLayer.title.toLowerCase()}` : "")
      + (missing.length ? ` · no LST on ${missing.join(", ")}` : "");
    cell.innerHTML = (n !== undefined ? `<span class="tl-bar" style="height:max(2px, calc((100% - 15px) * ${(n / maxEv).toFixed(3)}))"></span>` : "")
      + `<span class="tl-dnum">${Number(day.date.slice(8))}</span>`;
    cell.addEventListener("click", () => {
      // 【中文】跳到当天同一小时 / jump to the same hour on that day
      const hour = fmtHour().format(new Date(frames[S.idx].t)).slice(0, 2);
      let j = day.start;
      for (let k = day.start; k < day.start + day.count; k++) if (fmtHour().format(new Date(frames[k].t)).startsWith(hour)) j = k;
      stop(); showFrame(j);
    });
    strip.appendChild(cell);
    prev = day.date;
  }

  const key = [];
  if (heat) key.push(`<span class="k-heat"></span>${heat.name ?? "Heat window"} (${shortDate(heat.start)}–${shortDate(heat.end)})`);
  if (daily) key.push(`<span class="k-bar"></span>${evLayer.title} per day (max ${maxEv})`);
  if (base) key.push(`Baseline ${shortDate(base.start)}–${shortDate(base.end)}`);
  $("tlKey").innerHTML = key.map((k) => `<span>${k}</span>`).join("");

  const slider = $("tlSlider");
  slider.max = String(frames.length - 1);
  slider.addEventListener("input", () => { stop(); showFrame(Number(slider.value)); });
  $("tlPlay").addEventListener("click", () => (S.timer ? stop() : play()));
  setTimelineVisible();
}

function missingDates(a, b) {
  const out = [];
  for (let t = Date.parse(a) + 864e5; t < Date.parse(b); t += 864e5) out.push(shortDate(new Date(t).toISOString().slice(0, 10)));
  return out;
}

function shortDate(d) {
  return new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

function play() {
  const S = state.series;
  S.timer = setInterval(() => showFrame((S.idx + 1) % S.meta.frames.length), PLAY_MS);
  $("tlPlayIcon").setAttribute("d", "M4 2.5h3v11H4zM9 2.5h3v11H9z");
  $("tlPlay").setAttribute("aria-label", "Pause");
}

function stop() {
  const S = state.series;
  if (!S?.timer) return;
  clearInterval(S.timer);
  S.timer = null;
  $("tlPlayIcon").setAttribute("d", "M4 2.5v11l9-5.5z");
  $("tlPlay").setAttribute("aria-label", "Play");
}

function updateTimeLabel(i) {
  const f = state.series.meta.frames[i];
  const d = new Date(f.t);
  $("tlDate").textContent = fmtDay().format(d);
  $("tlHour").textContent = fmtHour().format(d);
  const heat = state.manifest?.heatwave, base = state.manifest?.baseline;
  const date = f.date ?? localDate(f.t);
  $("tlTag").textContent = inWindow(date, heat) ? "Heat window" : inWindow(date, base) ? "Baseline" : "";
  $("tlTag").className = "tl-tag" + (inWindow(date, heat) ? " heat" : "");
  // 【中文】与其他帧像元完全相同的帧（上游数据问题）/ frames identical to another frame (upstream issue)
  const warn = $("tlWarn");
  warn.hidden = !f.same_as;
  if (f.same_as) {
    const twins = f.same_as.map((t) => fmtHour().format(new Date(t)).slice(0, 5)).join(", ");
    warn.textContent = `Suspect frame: identical pixels to ${twins}`;
  }
  [...$("tlDays").children].forEach((c, k) => c.classList.toggle("current", state.series.days[k]?.date === date));
}

function setTimelineVisible() {
  const on = hourlyMode();
  $("timeline").hidden = !on;
  document.body.classList.toggle("has-timeline", on);
  if (!on) stop();
}

// ------------------------------------------------------------------ panel
function buildPanel(manifest) {
  const list = $("layerList");
  list.innerHTML = "";
  if (!manifest?.layers?.length) {
    list.innerHTML = `<p class="status">No layer data yet. Run <code>python -m pipeline.build</code>
      locally to generate <code>site/data/</code>, then commit it.</p>`;
  }
  const groups = new Map();
  for (const l of state.layers) {
    if (!groups.has(l.group)) groups.set(l.group, []);
    groups.get(l.group).push(l);
  }
  for (const [name, items] of groups) {
    const g = document.createElement("section");
    g.className = "group";
    g.innerHTML = `<h2>${name}</h2>`;
    for (const l of items) g.appendChild(layerRow(l));
    list.appendChild(g);
  }
}

function layerRow(l) {
  const wrap = document.createElement("div");
  const row = document.createElement("label");
  row.className = "layer" + (VALUE_KINDS.has(l.kind) ? " exclusive" : "");
  const sub = l.failed ? "Failed to load" : layerSub(l);
  row.innerHTML = `<input type="checkbox" ${l.visible ? "checked" : ""} ${l.failed ? "disabled" : ""}>
    <span class="check" aria-hidden="true"></span>
    <span class="layer-name">${l.title}${sub ? `<span class="layer-sub">${sub}</span>` : ""}</span>
    ${swatch(l)}`;
  const input = row.querySelector("input");
  input.addEventListener("change", () => toggle(l, input.checked));
  wrap.appendChild(row);

  if (l.kind === "raster" || l.kind === "raster_rgb" || l.kind === "raster_series") {
    const op = document.createElement("div");
    op.className = "opacity";
    op.hidden = !l.visible;
    op.innerHTML = `<span>Opacity</span><input type="range" min="0" max="1" step="0.05" value="${l.opacity}" aria-label="${l.title} opacity">`;
    op.querySelector("input").addEventListener("input", (e) =>
      state.map.setPaintProperty(l.id, "raster-opacity", Number(e.target.value)));
    wrap.appendChild(op);
    l._opacityRow = op;
  }
  l._input = input;
  return wrap;
}

function layerSub(l) {
  const m = state.meta[l.id];
  if (l.kind === "raster" && m) return `${fmt(m.vmin)}–${fmt(m.vmax)} ${m.units}`;
  if (l.kind === "raster_series" && m) {
    const days = new Set(m.frames.map((f) => localDate(f.t))).size;
    return `${m.frames.length} hours over ${days} days · ${fmt(m.range[0], 0)}–${fmt(m.range[1], 0)} ${m.units}`;
  }
  if (l.kind === "vector") {
    const extra = l.hourly ? " · hourly colour" : l.aggregated ? " · aggregated" : "";
    return `${l.count.toLocaleString()} ${l.count_label ?? "features"}${extra}`;
  }
  return "";
}

function swatch(l) {
  if (l.kind !== "vector") return "";
  const bg = l.color ? `linear-gradient(90deg, ${l.color.stops.join(",")})` : l.fill_color;
  return `<span class="swatch" style="background:${bg}"></span>`;
}

function toggle(l, on) {
  if (l.kind === "basemap") {
    state.map.setLayoutProperty(l.id, "visibility", on ? "visible" : "none");
    l.visible = on;
    return;
  }
  if (VALUE_KINDS.has(l.kind) && on) {
    for (const other of state.layers) {
      if (VALUE_KINDS.has(other.kind) && other !== l && other.visible) {
        setVisible(other, false);
        other._input.checked = false;
        other._opacityRow.hidden = true;
      }
    }
    state.active = l.id;
  } else if (VALUE_KINDS.has(l.kind) && !on && state.active === l.id) {
    state.active = null;
  }
  setVisible(l, on);
  if (l._opacityRow) l._opacityRow.hidden = !on;
  if (VALUE_KINDS.has(l.kind)) {
    applyAssetState();
    setTimelineVisible();
  }
  updateLegends();
  if (state.click) readAt(state.click);
}

// ------------------------------------------------------------------ readout
function activeScale() {
  const l = state.layers.find((x) => x.id === state.active);
  const m = l && state.meta[l.id];
  if (!m) return null;
  if (l.kind === "raster_series") return { l, vmin: m.range[0], vmax: m.range[1], stops: m.stops, units: m.units };
  return { l, vmin: m.vmin, vmax: m.vmax, stops: m.stops, units: m.units };
}

function updateLegends() {
  const s = activeScale();
  if (s) {
    $("readoutLayer").textContent = s.l.title;
    $("ramp").style.background = `linear-gradient(90deg, ${s.stops.join(",")})`;
    $("rampMin").textContent = `${fmt(s.vmin)} ${s.units}`;
    $("rampMax").textContent = `${fmt(s.vmax)} ${s.units}`;
    $("rampWrap").hidden = false;
  } else {
    $("readoutLayer").textContent = "No temperature layer selected";
    $("rampWrap").hidden = true;
  }
  if (!state.click) setIdle(s ? "to read the temperature there" : "Choose a temperature layer on the left");

  const vl = $("vectorLegends");
  vl.innerHTML = "";
  for (const v of state.layers) {
    if (v.kind !== "vector" || !v.visible) continue;
    const d = document.createElement("div");
    d.className = "vlegend";
    if (v.hourly && hourlyMode()) {
      d.textContent = `${v.title}: coloured by the hour shown, on the same scale as the LST layer`;
    } else if (v.color) {
      d.innerHTML = `${v.title}${v.color.label ? ` · ${v.color.label}` : ""}
        <div class="ramp" style="background:linear-gradient(90deg, ${v.color.stops.join(",")})"></div>
        <div class="ramp-labels"><span>${fmt(v.color.vmin)} ${v.color.units}</span><span>${fmt(v.color.vmax)} ${v.color.units}</span></div>`;
    } else continue;
    if (v.aggregated) d.insertAdjacentHTML("beforeend", `<div class="vnote">Aggregated counts only; individual requests are not published.</div>`);
    vl.appendChild(d);
  }
}

function setIdle(hint) {
  $("readoutNum").textContent = "Click the map";
  $("readoutNum").classList.add("idle");
  $("readoutUnit").textContent = "";
  $("readoutHint").textContent = hint;
  $("marker").hidden = true;
}

function wireMap() {
  const map = state.map;
  const vectorIds = () => state.layers.filter((l) => l.kind === "vector" && l.visible).map((l) => l.id);

  map.on("click", (e) => {
    state.click = e;
    if (!state.pin) {
      const el = document.createElement("div");
      el.style.cssText = "width:14px;height:14px;border-radius:50%;border:2.5px solid #1e2b31;background:rgba(255,255,255,.6)";
      state.pin = new maplibregl.Marker({ element: el });
    }
    state.pin.setLngLat(e.lngLat).addTo(map);
    readAt(e);
  });

  map.on("mousemove", (e) => {
    const ids = vectorIds();
    const hit = ids.length && map.queryRenderedFeatures(box(e.point, 4), { layers: ids }).length;
    map.getCanvas().style.cursor = hit ? "pointer" : "";
  });
}

async function readAt(e) {
  await updateValue(e.lngLat);
  const ids = state.layers.filter((x) => x.kind === "vector" && x.visible).map((x) => x.id);
  const f = ids.length ? state.map.queryRenderedFeatures(box(e.point, 4), { layers: ids })[0] : null;
  renderFeature(f);
}

async function updateValue({ lng, lat }) {
  const s = activeScale();
  if (s) {
    const v = s.l.kind === "raster_series" ? seriesValue(lng, lat) : await sample(s.l, lng, lat);
    if (v === null) {
      $("readoutNum").textContent = "No data";
      $("readoutNum").classList.add("idle");
      $("readoutUnit").textContent = "";
      $("marker").hidden = true;
    } else {
      $("readoutNum").textContent = fmt(v, 1);
      $("readoutNum").classList.remove("idle");
      $("readoutUnit").textContent = s.units;
      const t = Math.min(1, Math.max(0, (v - s.vmin) / (s.vmax - s.vmin)));
      $("marker").style.left = `${t * 100}%`;
      $("marker").hidden = false;
    }
  } else {
    setIdle("Choose a temperature layer on the left");
  }
  const where = `${lat.toFixed(5)}°N, ${Math.abs(lng).toFixed(5)}°W`;
  $("readoutHint").textContent = s?.l.kind === "raster_series"
    ? `${where} · ${fmtHour().format(new Date(state.series.meta.frames[state.series.idx].t))}` : where;
}

// 【中文】资产详情卡：属性 + 逐小时热暴露曲线 / asset card: attributes + hourly exposure curve
function renderFeature(f) {
  const el = $("feature");
  state.card = null;
  if (!f) { el.hidden = true; return; }
  const layer = state.layers.find((x) => x.id === f.layer.id.replace(/__outline$/, ""));
  const labels = { ...FIELD_LABELS, ...(layer.field_labels ?? {}) };
  const fields = [...(layer.popup_fields ?? []), ...(layer.aggregated ? [] : ["asset_id"])];
  const rows = fields
    .filter((k) => f.properties[k] !== undefined && f.properties[k] !== null && f.properties[k] !== "")
    .map((k) => `<dt>${labels[k] ?? k}</dt><dd>${fmtProp(f.properties[k])}</dd>`).join("");
  const series = state.series?.assets[layer.id];
  const r = series?.row.get(f.properties.asset_id);
  let chart = "";
  if (r !== undefined) {
    state.card = { a: series, r };
    chart = exposureChart(series, r);
  }
  el.innerHTML = `<h3>${layer.title}</h3>${chart}<dl>${rows}</dl>`;
  el.hidden = false;
  updateCardMarker();
}

function exposureChart(a, r) {
  const S = state.series, frames = S.meta.frames;
  const vals = frames.map((_, i) => { const v = a.values[r * a.n + i]; return v === a.nodata ? null : v / a.scale; });
  const ok = vals.filter((v) => v !== null);
  if (!ok.length) return `<p class="chart-empty">No hourly LST for this asset.</p>`;
  const W = 264, H = 92, pad = { l: 26, r: 4, t: 6, b: 14 };
  const lo = Math.floor(Math.min(...ok)), hi = Math.ceil(Math.max(...ok));
  const x = (i) => pad.l + (i / Math.max(1, frames.length - 1)) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - lo) / Math.max(1, hi - lo)) * (H - pad.t - pad.b);
  const heat = state.manifest?.heatwave, base = state.manifest?.baseline;
  const hf = frames.map((f, i) => (inWindow(f.date, heat) ? i : -1)).filter((i) => i >= 0);
  const band = hf.length ? `<rect class="c-heat" x="${x(hf[0])}" y="${pad.t}" width="${x(hf[hf.length - 1]) - x(hf[0])}" height="${H - pad.t - pad.b}"/>` : "";
  // 【中文】每天一条折线，夜间不连线 / one polyline per day, no lines across nights
  const paths = S.days.map((d) => {
    const pts = [];
    for (let i = d.start; i < d.start + d.count; i++) if (vals[i] !== null) pts.push(`${x(i).toFixed(1)},${y(vals[i]).toFixed(1)}`);
    return pts.length ? `<polyline points="${pts.join(" ")}"/>` : "";
  }).join("");
  const mean = (w) => { const v = vals.filter((v, i) => v !== null && inWindow(frames[i].date, w)); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null; };
  const mh = mean(heat), mb = mean(base);
  const summary = mh !== null && mb !== null
    ? `<p class="chart-sum">Heat window mean <b>${fmt(mh)} °C</b> · baseline ${fmt(mb)} °C (${mh - mb >= 0 ? "+" : ""}${fmt(mh - mb)})</p>` : "";
  return `<div class="chart"><div class="chart-title">Hourly LST at this asset, ${S.meta.units}</div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Hourly land surface temperature for this asset">
      ${band}
      <line class="c-axis" x1="${pad.l}" x2="${W - pad.r}" y1="${H - pad.b}" y2="${H - pad.b}"/>
      <text x="${pad.l - 4}" y="${y(hi) + 4}" text-anchor="end">${hi}</text>
      <text x="${pad.l - 4}" y="${y(lo) + 2}" text-anchor="end">${lo}</text>
      <text x="${pad.l}" y="${H - 2}">${shortDate(frames[0].date)}</text>
      <text x="${W - pad.r}" y="${H - 2}" text-anchor="end">${shortDate(frames[frames.length - 1].date)}</text>
      <g class="c-line">${paths}</g>
      <line class="c-now" id="chartNow" y1="${pad.t}" y2="${H - pad.b}" x1="0" x2="0"/>
    </svg>${summary}</div>`;
}

// 【中文】与 exposureChart 的 x() 用同一套坐标 / same x mapping as exposureChart
function updateCardMarker() {
  const el = document.getElementById("chartNow");
  if (!el || !state.series) return;
  const n = state.series.meta.frames.length;
  const xx = 26 + (state.series.idx / Math.max(1, n - 1)) * (264 - 26 - 4);
  el.setAttribute("x1", xx); el.setAttribute("x2", xx);
}

function mercCell([w, s, e, n], width, height, lng, lat) {
  const x = (R * lng * Math.PI) / 180;
  const y = R * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
  const col = Math.floor(((x - w) / (e - w)) * width);
  const row = Math.floor(((n - y) / (n - s)) * height);
  return col < 0 || row < 0 || col >= width || row >= height ? null : { col, row };
}

async function sample(l, lng, lat) {
  const m = state.meta[l.id];
  if (!state.grids[l.id]) {
    const buf = await fetch(DATA + l.values).then((r) => r.arrayBuffer());
    state.grids[l.id] = new Int16Array(buf);
  }
  const cell = mercCell(m.merc_bounds, m.grid.width, m.grid.height, lng, lat);
  if (!cell) return null;
  const raw = state.grids[l.id][cell.row * m.grid.width + cell.col];
  return raw === m.grid.nodata ? null : raw / m.grid.scale;
}

// ------------------------------------------------------------------ sources & build
async function openSources() {
  const body = $("sourcesBody");
  const [data, build] = await Promise.all([
    fetchJSON(DATA + "sources.json").catch(() => null),
    fetchJSON(DATA + "build.json").catch(() => null),
  ]);
  if (!data) {
    body.innerHTML = `<p class="status">sources.json not found. It is generated by the pipeline.</p>`;
  } else {
    const rows = data.sources.map((s) => `<tr>
      <td>${s.name}</td><td>${s.provider ?? "—"}</td><td>${s.version ?? "—"}</td>
      <td>${s.temporal_res ?? "—"}${s.coverage ? `<span class="sub">${s.coverage}</span>` : ""}</td>
      <td>${s.spatial_res ?? "—"}</td><td>${s.license ?? "—"}</td>
      <td>${s.retrieved_date ?? "—"}</td>
      <td><span class="pill ${s.status === "built" || s.status === "cached" ? "" : "warn"}">${statusWord(s.status)}</span></td></tr>`).join("");
    body.innerHTML = `<table><thead><tr><th>Dataset</th><th>Provider</th><th>Version</th><th>Time</th><th>Resolution</th>
      <th>License</th><th>File date</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>${buildInfo(build)}`;
  }
  $("sourcesDialog").showModal();
}

function buildInfo(b) {
  if (!b) return "";
  const tables = Object.entries(b.tables).map(([t, n]) => `${t} ${n.toLocaleString()}`).join(" · ");
  const v = b.validation;
  const issues = v.issues.length
    ? `<ul class="issues">${v.issues.map((i) => `<li><span class="pill ${i.level === "error" ? "warn" : ""}">${i.level}</span>
        ${i.table}: ${i.message} (${i.n.toLocaleString()} rows)</li>`).join("")}</ul>`
    : "";
  return `<h3 class="sub-head">Build</h3>
    <dl class="kv">
      <dt>Run</dt><dd><code>${b.run_id}</code></dd>
      <dt>Built</dt><dd>${b.built_at.replace("T", " ").replace("+00:00", " UTC")}</dd>
      <dt>Code</dt><dd><code>${b.code_version}</code></dd>
      <dt>Standard tables</dt><dd>${tables}</dd>
      <dt>Validation</dt><dd>${v.errors || v.warnings ? `${v.errors} error(s), ${v.warnings} warning(s)` : "All checks passed"}</dd>
    </dl>${issues}`;
}

function statusWord(s) {
  return { built: "Published", cached: "Published", missing: "Missing input", failed: "Build failed", "not built": "Not built" }[s] ?? s;
}

async function openChain() {
  const c = await fetchJSON(DATA + "analysis/chain_check.json").catch(() => null);
  const body = $("chainBody");
  if (!c?.ok) {
    body.innerHTML = `<p class="status">${c?.reason ?? "No chain check yet."}</p>`;
  } else {
    const rows = c.bins.map((b) => `<tr><td>${b.bin}</td><td>${b.assets.toLocaleString()}</td><td>${fmt(b.km)}</td>
      <td>${fmt(b.lst_heat_min)}–${fmt(b.lst_heat_max)}</td><td>${fmt(b.lst_base_mean)}</td><td>${fmt(b.lst_heat_mean)}</td>
      <td>${b.events_baseline}</td><td>${b.events_heatwave}</td>
      <td>${fmt(b.per_100km_day_baseline, 2)}</td><td>${fmt(b.per_100km_day_heatwave, 2)}</td></tr>`).join("");
    body.innerHTML = `<p class="lead">Road segments grouped by their mean hourly LST during the heat window
      (${shortDate(c.heatwave.start)}–${shortDate(c.heatwave.end)}), with 311 road requests matched to the same segments.
      Baseline: ${shortDate(c.baseline.start)}–${shortDate(c.baseline.end)}.</p>
      <table><thead>
        <tr><th rowspan="2">LST quintile</th><th rowspan="2">Segments</th><th rowspan="2">km</th><th rowspan="2">Heat-window LST range (°C)</th>
          <th colspan="2">Mean LST (°C)</th><th colspan="2">Requests</th><th colspan="2">Per 100 km per day</th></tr>
        <tr><th>Baseline</th><th>Heat</th><th>Baseline</th><th>Heat</th><th>Baseline</th><th>Heat</th></tr>
      </thead><tbody>${rows}</tbody></table>
      <p class="note">${c.note} ${c.assets_with_exposure.toLocaleString()} of ${c.assets_total.toLocaleString()} segments have hourly
      exposure; ${c.events_matched.toLocaleString()} requests in the two windows were matched to a segment.
      LST frames cover ${c.days_with_lst.baseline ?? 0} of ${c.days.baseline} baseline days and ${c.days_with_lst.heatwave ?? 0} of ${c.days.heatwave} heat-window days; rates use calendar days.</p>`;
  }
  $("chainDialog").showModal();
}

// ------------------------------------------------------------------ utils
function box(p, r) { return [[p.x - r, p.y - r], [p.x + r, p.y + r]]; }
function fmt(v, d = 1) { return v === null || v === undefined ? "—" : Number(v).toFixed(d); }
function fmtProp(v) {
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
  return String(v);
}
async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}
