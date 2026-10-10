/* Shared chart code for the dashboard, briefing and motion pages.
   Colours and type mirror core/design.py; see "Design system" in NOTES.md. */
const KD = (() => {
  const C = {
    navy: "#0f2a4a", blue: "#5b9bd5", red: "#c0392b", orange: "#e67e22", grey: "#95a5a6",
    band: "rgba(150,150,150,0.25)", grid: "#e6e6e6", text: "#363737", muted: "#757575", paper: "#ffffff",
  };
  const FONT = "Inter, 'Segoe UI', system-ui, -apple-system, Roboto, sans-serif";
  const CONFIG = { displayModeBar: false, responsive: true };

  /* Plotly renders a subset of HTML (links, styling) in every string it draws. Names,
     units and labels come from lake rows, so they are escaped before reaching it. */
  const esc = (text) => String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  };

  function layout(extra) {
    return Object.assign({
      font: { family: FONT, size: 12, color: C.text },
      paper_bgcolor: C.paper, plot_bgcolor: C.paper,
      margin: { l: 56, r: 24, t: 34, b: 36 },
      hovermode: "x unified",
      hoverlabel: { bgcolor: C.paper, bordercolor: C.grid, font: { family: FONT, size: 12, color: C.text } },
      legend: { orientation: "h", x: 0, y: 1.0, yanchor: "bottom", font: { size: 11.5 } },
      xaxis: { gridcolor: C.grid, linecolor: C.grid, tickcolor: C.grid, zeroline: false },
      yaxis: { gridcolor: C.grid, linecolor: C.grid, zeroline: false, automargin: true },
    }, extra);
  }

  function axisTitle(text, colour) {
    return { text: esc(text), font: { size: 11.5, color: colour || C.muted }, standoff: 6 };
  }

  function notes(list) {
    return (list || []).map((a, i) => {
      const low = a.text.startsWith("Low");
      return {
        x: a.x, y: a.y, xref: "x", yref: a.axis || "y", text: esc(a.text),
        showarrow: true, arrowhead: 0, arrowwidth: 1, arrowcolor: a.latest ? C.navy : C.muted,
        ax: a.latest ? -70 : (i % 2 ? 30 : -30), ay: a.latest ? -34 : (low ? 30 : -30),
        font: { size: 11, color: a.latest ? C.navy : C.text },
        bgcolor: "rgba(255,255,255,0.9)", borderpad: 2,
      };
    });
  }

  const fmt = (digits) => `,.${digits}f`;

  function seasonal(e) {
    const hover = `%{y:${fmt(e.digits)}}`;
    const data = [
      { x: e.x, y: e.band_min, mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
      { x: e.x, y: e.band_max, mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: C.band,
        name: esc(e.band_label), hoverinfo: "skip" },
      { x: e.x, y: e.median, mode: "lines", name: "Median", line: { color: C.orange, width: 1.5, dash: "dot" },
        hovertemplate: hover },
      { x: e.x, y: e.prior, mode: "lines", name: String(e.year - 1), line: { color: C.blue, width: 1.5 },
        hovertemplate: hover },
      { x: e.x, y: e.current, mode: "lines", name: String(e.year), line: { color: C.navy, width: 2.5 },
        hovertemplate: hover },
    ];
    /* Weekly series arrive with a value only on report days; the line joins them. */
    data.forEach((t) => { t.connectgaps = true; });
    return { data, layout: layout({
      xaxis: { type: "date", tickformat: "%b", dtick: "M1", hoverformat: "%-d %b", gridcolor: C.grid,
        linecolor: C.grid, range: [e.x[0], e.x[e.x.length - 1]] },
      yaxis: { title: axisTitle(e.unit), gridcolor: C.grid, zeroline: false, automargin: true,
        tickformat: fmt(e.digits > 1 ? 1 : 0) },
      annotations: notes(e.annotations),
    }) };
  }

  function trace(s, colour, axis, width) {
    return { x: s.x, y: s.y, mode: s.x.length < 16 ? "lines+markers" : "lines", name: esc(s.name), yaxis: axis,
      line: { color: colour, width: width }, marker: { size: 6, color: colour },
      hovertemplate: `%{y:${fmt(s.digits)}} ${esc(s.unit)}` };
  }

  function dual(e) {
    const [a, b] = e.series;
    const data = [trace(a, C.navy, "y", 2.2)];
    const extra = {
      yaxis: { title: axisTitle(`${a.name}, ${a.unit}`, C.navy), tickfont: { color: C.navy }, gridcolor: C.grid,
        zeroline: false, automargin: true },
      annotations: notes(e.annotations),
      margin: { l: 56, r: 56, t: 34, b: 36 },
    };
    if (b) {
      data.push(trace(b, C.blue, "y2", 1.8));
      extra.yaxis2 = { title: axisTitle(`${b.name}, ${b.unit}`, C.blue), tickfont: { color: C.blue },
        overlaying: "y", side: "right", showgrid: false, zeroline: false, automargin: true };
    }
    return { data, layout: layout(extra) };
  }

  function lines(e) {
    const colours = [C.navy, C.blue, C.grey];
    const data = e.series.map((s, i) => trace(s, colours[i % 3], "y", i ? 1.8 : 2.2));
    return { data, layout: layout({
      xaxis: { title: e.x_title ? axisTitle(e.x_title) : undefined, gridcolor: C.grid, linecolor: C.grid },
      yaxis: { title: axisTitle(e.series[0].unit), gridcolor: C.grid, zeroline: true, zerolinecolor: C.grid,
        automargin: true },
      showlegend: e.series.length > 1,
      annotations: notes(e.annotations),
    }) };
  }

  function bars(e) {
    const cats = e.categories.map(esc).reverse();
    const rev = (v) => v.slice().reverse();
    const hover = `%{x:${fmt(e.digits)}} ${esc(e.unit)}`;
    const data = [
      { type: "bar", orientation: "h", y: cats, x: rev(e.compare), name: esc(e.compare_name),
        marker: { color: C.blue }, hovertemplate: hover },
      { type: "bar", orientation: "h", y: cats, x: rev(e.values), name: esc(e.value_name),
        marker: { color: C.navy }, hovertemplate: hover },
    ];
    return { data, layout: layout({
      barmode: "group", bargap: 0.28, bargroupgap: 0.08, hovermode: "y unified",
      xaxis: { title: axisTitle(e.unit), gridcolor: C.grid, zeroline: true, zerolinecolor: C.grid },
      yaxis: { automargin: true, tickfont: { size: 11.5 } },
      legend: { orientation: "h", x: 0, y: 1.0, yanchor: "bottom", traceorder: "reversed", font: { size: 11.5 } },
      margin: { l: 56, r: 24, t: 34, b: 44 },
    }) };
  }

  const BUILDERS = { seasonal, dual, lines, bars };

  function render(node, exhibit) {
    const fig = BUILDERS[exhibit.kind](exhibit);
    if (exhibit.kind === "bars") node.style.height = Math.max(320, 30 * exhibit.categories.length + 90) + "px";
    Plotly.react(node, fig.data, fig.layout, CONFIG);
  }

  /* One exhibit: heading, stale flag, two-line takeaway, chart, source line. */
  function card(exhibit, options) {
    const opts = options || {};
    const box = el("article", "exhibit");
    box.id = "x-" + exhibit.id;
    const head = el("header");
    head.append(el(opts.heading || "h3", null, exhibit.title));
    if (exhibit.gap) head.append(el("span", "gap-flag", exhibit.gap));
    const take = el("div", "takeaway");
    exhibit.takeaway.forEach((line) => take.append(el("p", null, line)));
    const chart = el("div", "chart");
    const foot = el("p", "source", exhibit.source + (exhibit.note ? " · " + exhibit.note : ""));
    box.append(head, take, chart, foot);
    box.draw = () => render(chart, exhibit);
    return box;
  }

  function metaLine(node, meta) {
    const parts = [
      ["Pipeline as-of", meta.newest_run || "not recorded"],
      ["Oldest source", meta.oldest_run || "not recorded"],
      ["Built", meta.built_at],
      ["Stale exhibits", `${meta.stale} of ${meta.exhibits}`],
    ];
    parts.forEach(([label, value], i) => {
      if (i) node.append(" · ");
      node.append(label + " ");
      node.append(el("b", null, value));
    });
  }

  return { C, FONT, CONFIG, el, esc, layout, axisTitle, render, card, metaLine };
})();
