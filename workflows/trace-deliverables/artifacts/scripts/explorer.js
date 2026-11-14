"use strict";
const MODEL = JSON.parse(document.getElementById("DATA").textContent);
const app = document.getElementById("app");
const esc = (value) => String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const storage = { get(key) { try { return localStorage.getItem(key); } catch (error) { return null; } }, set(key, value) { try { localStorage.setItem(key, value); } catch (error) { /* sandboxed */ } } };
const coreByKey = Object.fromEntries(MODEL.core.findings.map((finding) => [finding.key, finding]));
const TABS = [["out", "Outputs", Object.keys(MODEL.outputs).length], ["var", "Variables", Object.keys(MODEL.vars).length], ["protocol", "Protocol", MODEL.objectives.length],
  ["core", "CORE", MODEL.core.findings.length], ["checks", "Checks", null], ["gaps", "Gaps", MODEL.gaps.length]];

/* ------------------------------------------------------------ helpers */
const go = (hash) => { location.hash = hash; };
const varChip = (id, extra) => { const known = MODEL.vars[id]; return `<a class="chip adam" href="#var/${esc(id)}" title="${esc(known ? (known.label || known.role || "") : "not an ADaM variable of this run")}">${esc(id)}${extra || ""}</a>`; };
const sdtmChip = (ref) => `<a class="chip sdtm" href="#sdtm/${esc(ref)}" title="${esc((MODEL.sdtm[ref] || {}).label || "")}">${esc(ref)}</a>`;
const refChip = (ref) => (MODEL.vars[ref] ? varChip(ref) : sdtmChip(ref));
const outChip = (id) => `<a class="chip out" href="#out/${esc(id)}" title="${esc((MODEL.outputs[id] || {}).title || "planned, not produced")}">${esc(id)}</a>`;
const coreChip = (key) => { const finding = coreByKey[key]; return finding ? `<a class="chip" href="#core/${esc(key)}" title="${esc(finding.message)}">${esc(finding.rule)} · ${esc(finding.dataset || finding.std)}</a>` : ""; };
const objChip = (id) => `<a class="chip" href="#protocol/${esc(id)}">${esc(id.replace("_", " "))}</a>`;
const tag = (text, kind) => `<span class="tag ${kind || ""}">${esc(text)}</span>`;
const chips = (items, render, none) => (items && items.length ? items.map((item) => render(item)).join("") : `<span class="muted small">${none || "none"}</span>`);
const fmt = (value) => (typeof value === "number" ? (Number.isInteger(value) ? String(value) : String(+value.toPrecision(6))) : value == null ? "" : String(value));
const cite = (citation) => (citation ? `<div class="quote">p. ${esc(citation.page)} — “${esc(citation.quote)}”</div>` : "");

function commentStart(line) {
  let quote = null;
  for (let index = 0; index < line.length; index++) {
    const char = line[index];
    if (quote !== null) { if (char === "\\") index++; else if (char === quote) quote = null; }
    else if (char === '"' || char === "'" || char === "`") quote = char;
    else if (char === "#") return index;
  }
  return -1;
}
function highlight(line) {
  const start = commentStart(line);
  const code = start >= 0 ? line.slice(0, start) : line;
  let html = code.split(/("(?:[^"\\]|\\.)*"?|'(?:[^'\\]|\\.)*'?)/).map((part, index) => (index % 2 === 1
    ? `<span class="c-str">${esc(part)}</span>` : esc(part).replace(/\b([A-Za-z_.][\w.]*)(?=\()/g, '<span class="c-fn">$1</span>'))).join("");
  if (start >= 0) html += `<span class="c-com">${esc(line.slice(start)).replace(/(@(?:derive|tlf))/g, '<span class="c-tag">$1</span>')}</span>`;
  return html;
}
function codeBlock(file, start, end, hi, context) {
  const lines = (MODEL.programs[file] || "").split("\n");
  const from = Math.max(1, start - (context || 0)), to = Math.min(lines.length, end + (context || 0));
  let html = "";
  for (let number = from; number <= to; number++) {
    const cls = hi && hi.includes(number) ? "hi" : number >= start && number <= end && context ? "in" : "";
    html += `<div class="ln ${cls}"><span class="n">${number}</span><span class="t">${highlight(lines[number - 1] || "")}</span></div>`;
  }
  return `<pre class="code">${html}</pre>`;
}
function ardRows(output) { const ard = output.ard; if (!ard) return []; return ard.rows.map((row) => Object.fromEntries(ard.cols.map((col, index) => [col, row[index]]))); }
function groupText(row) { const parts = []; for (let index = 1; index < 6; index++) if (row["group" + index] != null) parts.push(`${row["group" + index]}=${row["group" + index + "_level"]}`); return parts.join(", "); }

/* ------------------------------------------------------------ chrome */
function chrome(active) {
  const study = MODEL.study || {};
  document.getElementById("study").textContent = [study.id, study.title].filter(Boolean).join(" · ");
  document.getElementById("nav").innerHTML = TABS.map(([key, label, count]) => `<a href="#${key}" class="${active === key ? "on" : ""}">${label}${count != null ? `<span class="count">${count}</span>` : ""}</a>`).join("");
}
function rail(groups, selected, placeholder, filterKey) {
  const filter = (storage.get(filterKey) || "").toLowerCase();
  let html = `<input placeholder="${esc(placeholder)}" value="${esc(filter)}" data-filter="${esc(filterKey)}">`;
  for (const group of groups) {
    const items = group.items.filter((item) => !filter || (item.id + " " + (item.sub || "")).toLowerCase().includes(filter));
    if (!items.length) continue;
    html += `<div class="group"><span>${esc(group.title)}</span><span>${items.length}</span></div>`;
    html += items.map((item) => `<div class="item ${item.id === selected ? "on" : ""}" data-go="${esc(item.href)}"><span>${esc(item.label || item.id)}</span><span class="sub">${esc(item.sub || "")}</span>${item.badge || ""}</div>`).join("");
  }
  return `<aside class="rail">${html}</aside>`;
}

/* ------------------------------------------------------------ outputs */
function outputStatus(output) {
  const checks = output.checks || {}, problems = [];
  const reconciliation = checks.reconciliation, denominators = checks.denominators, recompute = checks.recompute;
  if (reconciliation && reconciliation.unmatched && reconciliation.unmatched.length) problems.push("unmatched numbers");
  if (denominators && denominators.status === "fail") problems.push("big N");
  if (recompute && recompute.mismatches && recompute.mismatches.length) problems.push("recompute");
  return problems;
}
function renderOutputs(id) {
  const ids = Object.keys(MODEL.outputs);
  id = id || ids[0];
  const byType = {};
  for (const outputId of ids) { const output = MODEL.outputs[outputId]; (byType[output.type] = byType[output.type] || []).push({ id: outputId, href: "#out/" + outputId, sub: output.title,
    badge: outputStatus(output).length ? tag("!", "bad") : "" }); }
  const groups = Object.keys(byType).map((type) => ({ title: type + "s", items: byType[type] }));
  app.innerHTML = `<div class="layout">${rail(groups, id, "filter outputs…", "f-out")}<main id="main"></main></div>`;
  const output = MODEL.outputs[id];
  const main = document.getElementById("main");
  if (!output) { main.innerHTML = `<div class="empty">No output ${esc(id)}.</div>`; return; }
  const analysis = MODEL.analyses[output.analysis] || {};
  const checks = output.checks || {};
  const reconciliation = checks.reconciliation || {}, denominators = checks.denominators || {}, recompute = checks.recompute || {};
  const problems = outputStatus(output);
  let html = `<h2>${esc(output.id)}</h2><p class="lead">${esc(output.title)}</p>
    <div class="meta"><span>analysis <b>${esc(output.analysis || "—")}</b></span><span>method <b>${esc(analysis.method || (output.spec || {}).methods || "—")}</b></span>
    <span>analysis set <b>${esc((analysis.analysisSet || {}).label || "—")}</b> ${esc((analysis.analysisSet || {}).condition || "")}</span>
    <span>records <b>${esc((analysis.dataSubset || {}).label || "—")}</b></span><span>program <b>${esc(output.program || "—")}</b></span></div>`;
  html += `<div class="pill-row">${problems.length ? tag("checks: " + problems.join(", "), "bad") : tag("checks pass", "good")}
    ${reconciliation.checked != null ? tag(`${reconciliation.checked} numbers reconciled to the ARD`, reconciliation.unmatched && reconciliation.unmatched.length ? "bad" : "good") : ""}
    ${denominators.status ? tag(`big N ${denominators.status}`, denominators.status === "pass" ? "good" : denominators.status === "fail" ? "bad" : "") : ""}
    ${recompute.statistics != null ? tag(`${recompute.recomputed}/${recompute.statistics} statistics recomputed${recompute.mismatches && recompute.mismatches.length ? `, ${recompute.mismatches.length} mismatch` : ""}`, recompute.mismatches && recompute.mismatches.length ? "bad" : recompute.recomputed ? "good" : "") : ""}
    ${output.core.length ? tag(`${output.core.length} CORE finding(s) on its inputs`, "warn") : ""}</div>`;
  html += `<h3>Why this output exists</h3><div class="card"><div class="body">${whyOutput(output)}</div></div>`;
  html += `<h3>Display — click a number to trace it</h3><div class="split"><div class="card"><div class="head"><b>${esc(output.id)}</b><span class="muted">${esc(output.type)}</span></div><div class="display" id="display"></div></div>
    <div class="trace" id="trace">${traceIntro(output)}</div></div>`;
  html += `<h3>Inputs</h3><div class="card"><div class="body"><div class="small muted">ADaM variables the program declares (@tlf uses=)</div>${chips(output.uses, varChip)}
    <div class="small muted" style="margin-top:8px">Analysis set flag · grouping · record subset</div>${chips([(analysis.analysisSet || {}).var].concat((analysis.groupings || []).map((grouping) => grouping.var), (analysis.dataSubset || {}).vars || []).filter(Boolean), refChip)}</div></div>`;
  if (output.core.length) html += `<h3>CORE findings on the data behind it</h3><div class="card"><div class="body">${output.core.map(coreChip).join("")}</div></div>`;
  html += `<h3>Analysis Results Data (${output.ard ? output.ard.rows.length : 0} rows)</h3><div class="card" style="max-height:420px;overflow:auto" id="ardtable">${ardTable(output, [])}</div>`;
  if (output.program) html += `<h3>Program — ${esc(output.program)}</h3><div class="card" style="max-height:520px;overflow:auto">${codeBlock(output.program, 1, (MODEL.programs[output.program] || "").split("\n").length, [], 0)}</div>`;
  main.innerHTML = html;
  mountDisplay(output);
}
function whyOutput(output) {
  const plan = output.plan || {};
  let html = "";
  for (const objectiveId of output.objectives) {
    const objective = MODEL.objectives.find((item) => item.id === objectiveId);
    if (objective) html += `<div><a href="#protocol/${esc(objective.id)}">${esc(objective.level || objective.id)}</a> — ${esc(objective.text)}${cite(objective.cite)}</div>`;
  }
  for (const endpointId of output.endpoints) {
    const endpoint = MODEL.endpoints[endpointId];
    if (endpoint) html += `<div style="margin-top:6px"><a href="#protocol/${esc(endpoint.objective)}">${esc(endpoint.level || endpointId)}</a> — ${esc(endpoint.text)}${cite(endpoint.cite)}</div>`;
  }
  if (!html) html = `<div class="muted">No protocol objective or endpoint: ${output.rule ? "required by <b>" + esc(output.rule) + "</b>" : "supportive output"}.</div>`;
  html += `<div class="meta" style="margin-top:8px"><span>plan <b>${esc(plan.candidate_id || "not in the plan")}</b></span><span>category <b>${esc(plan.category || "—")}</b></span><span>priority <b>${esc(plan.priority || "—")}</b></span></div>`;
  if (plan.notes && plan.notes.length) html += `<div class="small muted">${plan.notes.map(esc).join(" · ")}</div>`;
  return html;
}
/* Displays are written by AI-authored programs: keep table markup only - no scripts, handlers, links, embeds or external URLs. */
const SAFE_TAGS = new Set(["table", "caption", "colgroup", "col", "thead", "tbody", "tfoot", "tr", "th", "td", "div", "span", "p", "br", "hr",
  "h1", "h2", "h3", "h4", "h5", "h6", "b", "i", "em", "strong", "u", "sup", "sub", "small", "ul", "ol", "li", "pre", "code"]);
const SAFE_ATTRIBUTES = new Set(["class", "colspan", "rowspan", "align", "valign", "width", "data-ard", "title", "style"]);
function sanitize(html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  const clean = (node) => {
    for (const child of [...node.children]) {
      if (SAFE_TAGS.has(child.tagName.toLowerCase()) === false) { child.remove(); continue; }
      for (const attribute of [...child.attributes]) {
        const value = attribute.value.toLowerCase();
        if (SAFE_ATTRIBUTES.has(attribute.name.toLowerCase()) === false || /url\s*\(|javascript:|expression\s*\(/.test(value)) child.removeAttribute(attribute.name);
      }
      clean(child);
    }
  };
  clean(template.content);
  return template.innerHTML;
}
function mountDisplay(output) {
  const host = document.getElementById("display");
  if (output.png) { host.innerHTML = `<img src="${esc(output.png)}" alt="${esc(output.title)}">`; }
  if (!output.html) { if (!output.png) host.innerHTML = '<div class="empty">No rendered display.</div>'; return; }
  const container = document.createElement("div");
  host.appendChild(container);
  const shadow = container.attachShadow({ mode: "open" });
  const body = output.html.replace(/^[\s\S]*?<body[^>]*>/i, "").replace(/<\/body>[\s\S]*$/i, "");
  const style = (output.html.match(/<style[^>]*>([\s\S]*?)<\/style>/i) || [, ""])[1].replace(/@import|url\s*\(|expression\s*\(|<\//gi, "");
  shadow.innerHTML = `<style>${style} [data-ard]{cursor:pointer} [data-ard]:hover{outline:1px solid #1f7a6d} .sel{background:#fdf0c8 !important;outline:2px solid #1f7a6d}</style>${sanitize(body)}`;
  shadow.addEventListener("click", (event) => {
    const cell = event.target.closest("[data-ard]");
    if (!cell) return;
    shadow.querySelectorAll(".sel").forEach((node) => node.classList.remove("sel"));
    cell.classList.add("sel");
    const indexes = cell.getAttribute("data-ard").split(",").map(Number);
    document.getElementById("trace").innerHTML = traceCell(output, cell.textContent.trim(), indexes);
    document.getElementById("ardtable").innerHTML = ardTable(output, indexes);
    const row = document.querySelector("#ardtable tr.sel"); if (row) row.scrollIntoView({ block: "nearest" });
  });
}
function traceIntro(output) {
  return `<div class="card"><div class="head"><b>Trace</b></div><div class="body muted small">Click any number in the display. Its chain appears here:
    <div class="chain" style="margin-top:8px"><div class="step"><div class="k">cell</div><div>the value shown</div></div><div class="step"><div class="k">ARD rows</div><div>data-ard → the statistics it was rendered from</div></div>
    <div class="step"><div class="k">analysis</div><div>${esc(output.analysis || "—")} (ARS)</div></div><div class="step"><div class="k">ADaM</div><div>the variables, flags and groups each row reads</div></div>
    <div class="step"><div class="k">program</div><div>the @derive lines that build them</div></div><div class="step"><div class="k">SDTM</div><div>the columns they come from</div></div></div></div></div>`;
}
function traceCell(output, text, indexes) {
  const rows = ardRows(output), resolve = output.resolve || {}, analysis = MODEL.analyses[output.analysis] || {};
  const picked = indexes.map((index) => rows[index]).filter(Boolean);
  const adam = new Set();
  for (const row of picked) {
    if (resolve[row.variable]) adam.add(resolve[row.variable]);
    for (let index = 1; index < 6; index++) if (row["group" + index] && resolve[row["group" + index]]) adam.add(resolve[row["group" + index]]);
  }
  if ((analysis.analysisSet || {}).var) adam.add(analysis.analysisSet.var);
  ((analysis.dataSubset || {}).vars || []).forEach((ref) => adam.add(ref));
  const unresolved = picked.filter((row) => row.variable && !resolve[row.variable]).map((row) => row.variable);
  let html = `<div class="card"><div class="head"><b>Trace of “${esc(text)}”</b>${unresolved.length ? tag("gap: " + unresolved.join(", "), "bad") : tag("resolves to SDTM", "good")}</div><div class="body"><div class="chain">`;
  html += `<div class="step"><div class="k">ARD rows</div><div>${picked.map((row, position) => `<div class="mono small"><b>#${indexes[position]}</b> ${esc(row.variable || "")}${row.variable_level != null && row.variable_level !== "" ? "=" + esc(row.variable_level) : ""} · ${esc(row.stat_name)} = <b>${esc(fmt(row.stat))}</b> <span class="muted">${esc(groupText(row))}${row.filter ? " · where " + esc(row.filter) : ""}${row.context ? " · " + esc(row.context) : ""}</span></div>`).join("") || '<span class="muted">none</span>'}</div></div>`;
  html += `<div class="step"><div class="k">analysis</div><div class="small">${esc(output.analysis)} · ${esc(analysis.method || "")}<br><span class="muted">set ${esc((analysis.analysisSet || {}).label || "")} (${esc((analysis.analysisSet || {}).condition || "")}) · ${esc((analysis.dataSubset || {}).label || "")}</span></div></div>`;
  const sdtm = new Set(), programs = [];
  for (const ref of adam) {
    const variable = MODEL.vars[ref]; if (!variable) continue;
    variable.sources.forEach((source) => { if (!MODEL.vars[source]) sdtm.add(source); else (MODEL.vars[source].sources || []).forEach((upstream) => { if (!MODEL.vars[upstream]) sdtm.add(upstream); }); });
    const label = variable.program && variable.lines ? `${variable.program}:${variable.lines[0]}–${variable.lines[1]}` : null;
    if (label && !programs.some((entry) => entry.includes(">" + label + "<"))) programs.push(`<a href="#var/${esc(ref)}" class="chip">${esc(label)}</a>`);
  }
  html += `<div class="step"><div class="k">ADaM</div><div>${chips([...adam], varChip)}</div></div>`;
  html += `<div class="step"><div class="k">program</div><div>${programs.join("") || '<span class="muted small">none</span>'}</div></div>`;
  html += `<div class="step"><div class="k">SDTM</div><div>${chips([...sdtm].sort(), sdtmChip)}</div></div>`;
  const core = output.core.filter((key) => coreByKey[key].impact.adam.concat(coreByKey[key].impact.downstream).some((ref) => adam.has(ref)));
  if (core.length) html += `<div class="step"><div class="k">CORE</div><div>${core.map(coreChip).join("")}</div></div>`;
  return html + "</div></div></div>";
}
function ardTable(output, selected) {
  if (!output.ard) return '<div class="empty">No ARD.</div>';
  const cols = output.ard.cols, limit = 400;
  const first = selected.length ? Math.max(0, Math.min(...selected) - 20) : 0;
  const rows = output.ard.rows.slice(first, first + limit);
  return `<table class="grid"><tr><th>#</th>${cols.map((col) => `<th>${esc(col)}</th>`).join("")}</tr>${rows.map((row, offset) => `<tr class="${selected.includes(first + offset) ? "sel" : ""}"><td class="num">${first + offset}</td>${row.map((value) => `<td class="${typeof value === "number" ? "num" : ""}">${esc(fmt(value))}</td>`).join("")}</tr>`).join("")}</table>
    ${output.ard.rows.length > limit ? `<div class="muted small" style="padding:8px">Showing rows ${first}–${first + rows.length - 1} of ${output.ard.rows.length}; click a cell to jump.</div>` : ""}`;
}

/* ------------------------------------------------------------ variables */
function renderVars(id) {
  const first = MODEL.datasets.length && MODEL.datasets[0].vars.length ? MODEL.datasets[0].name + "." + MODEL.datasets[0].vars[0] : "";
  id = id || first;
  const groups = MODEL.datasets.map((dataset) => ({ title: dataset.name, items: dataset.vars.map((name) => { const variable = MODEL.vars[dataset.name + "." + name] || {};
    return { id: dataset.name + "." + name, label: name, href: "#var/" + dataset.name + "." + name, sub: variable.label || variable.role || "", badge: (variable.flags || []).length ? tag("!", "warn") : "" }; }) }));
  app.innerHTML = `<div class="layout">${rail(groups, id, "filter variables…", "f-var")}<main id="main"></main></div>`;
  const variable = MODEL.vars[id], main = document.getElementById("main");
  if (!variable) { main.innerHTML = `<div class="empty">No ADaM variable ${esc(id)}.</div>`; return; }
  let html = `<h2><span class="ds">${esc(variable.ds)}.</span>${esc(variable.name)}</h2><p class="lead">${esc(variable.label || variable.role || "")}</p>
    <div class="meta"><span>origin <b>${esc(variable.origin || "—")}</b></span><span>program <b>${esc(variable.program || "—")}</b></span><span>spec <b>${esc(variable.inSpec ? variable.role || "yes" : "not in the ADaM spec")}</b></span><span>data <b>${variable.inData ? "present" : "missing"}</b></span></div>`;
  if (variable.method) html += `<div class="small" style="margin:6px 0 12px">${esc(variable.method)}</div>`;
  for (const flag of variable.flags || []) html += `<div class="banner">${esc(flag)}</div>`;
  html += `<h3>Lineage</h3><div class="card"><div class="flow">`;
  const sdtmFound = new Set(variable.found || []);
  html += `<div class="col"><h4>COMES FROM</h4>${variable.sources.map((source) => { const adam = !!MODEL.vars[source]; const found = adam || sdtmFound.has(source);
    return `<a class="box ${adam ? "adam" : "sdtm"} ${found ? "" : "dashed"}" href="#${adam ? "var" : "sdtm"}/${esc(source)}">${esc(source)}<small>${esc(adam ? MODEL.vars[source].label || "ADaM" : (MODEL.sdtm[source] || {}).label || "SDTM")}${found ? "" : " · declared, not named in the traced code"}</small></a>`; }).join("") || '<span class="muted small">no declared source</span>'}
    ${variable.deps.filter((dep) => !variable.sources.includes(dep)).map((dep) => `<a class="box adam dashed" href="#var/${esc(dep)}">${esc(dep)}<small>read on the assigning line</small></a>`).join("")}</div>`;
  html += `<div class="col"><h4>BUILT BY</h4>${(variable.steps || []).map((step) => `<div class="box code" data-scroll="step-${step.s}">${esc(step.file.split("/")[1])}:${step.s}${step.e !== step.s ? "–" + step.e : ""}<small>${esc(step.kind === "primary" ? "the @derive block" : step.note || "builds " + (step.target || "") )}</small></div>`).join("") || '<span class="muted small">no program lines</span>'}</div>`;
  html += `<div class="col"><h4>THIS VARIABLE</h4><div class="box self">${esc(variable.name)}<small>${esc(variable.ds)} · ${esc(variable.origin || "")}</small></div></div>`;
  html += `<div class="col"><h4>READ BY</h4>${variable.usedBy.slice(0, 12).map((user) => `<a class="box adam" href="#var/${esc(user)}">${esc(user)}<small>${esc((MODEL.vars[user] || {}).label || "")}</small></a>`).join("")}
    ${variable.usedBy.length > 12 ? `<div class="muted small">+ ${variable.usedBy.length - 12} more ADaM variables</div>` : ""}
    <div style="margin-top:6px">${chips(variable.outputs, outChip, "no output reads it")}</div></div>`;
  html += `</div></div>`;
  html += `<h3>Derivation code — assigning lines highlighted</h3>`;
  for (const step of variable.steps || []) {
    html += `<div class="card" id="step-${step.s}"><div class="head">${tag(step.kind === "primary" ? "PRIMARY" : "UPSTREAM", step.kind === "primary" ? "acc" : "")}<b class="mono">${esc(step.file.split("/")[1])}</b><span class="muted mono">lines ${step.s}–${step.e}</span><span class="muted">${esc(step.kind === "primary" ? "" : step.note || "builds `" + (step.target || "") + "`")}</span></div>
      ${codeBlock(step.file, step.s, step.e, step.kind === "primary" ? variable.hi || [] : [], step.kind === "primary" ? 2 : 0)}</div>`;
  }
  html += `<h3>Where it goes</h3><div class="card"><div class="body"><div class="cols2"><div><div class="small muted">Outputs</div>${chips(variable.outputs, outChip)}<div class="small muted" style="margin-top:8px">Analyses</div>${chips(variable.analyses, (analysis) => `<span class="chip static">${esc(analysis)}</span>`)}</div>
    <div><div class="small muted">Endpoints</div>${chips(variable.endpoints, (endpoint) => objChip(endpoint))}<div class="small muted" style="margin-top:8px">Objectives</div>${chips(variable.objectives, objChip)}</div></div></div></div>`;
  if (variable.core.length) html += `<h3>CORE findings on its sources</h3><div class="card"><div class="body">${variable.core.map(coreChip).join("")}</div></div>`;
  html += profileHtml(variable);
  main.innerHTML = html;
  main.querySelectorAll("[data-scroll]").forEach((node) => node.addEventListener("click", () => { const target = document.getElementById(node.dataset.scroll); if (target) target.scrollIntoView({ behavior: "smooth" }); }));
}
function profileHtml(variable) {
  const profile = variable.profile;
  if (!profile) return "";
  let html = `<h3>Data profile</h3><div class="tiles"><div class="tile"><div class="v">${esc(profile.n)}</div><div class="l">records</div></div><div class="tile"><div class="v">${esc(profile.nmiss)}</div><div class="l">missing</div></div><div class="tile"><div class="v">${esc(profile.nuniq)}</div><div class="l">distinct values</div></div>
    ${profile.summary ? Object.entries(profile.summary).map(([key, value]) => `<div class="tile"><div class="v" style="font-size:16px">${esc(fmt(value))}</div><div class="l">${esc(key)}</div></div>`).join("") : ""}</div>`;
  if (profile.levels) {
    const max = Math.max(...profile.levels.map((level) => level.n), 1);
    html += `<div class="card"><div class="body bars">${profile.levels.map((level) => `<div class="r"><span class="mono small">${esc(level.v)}</span><span><span class="b" style="display:block;width:${(100 * level.n / max).toFixed(1)}%"></span></span><span class="mono small">${esc(level.n)}</span></div>`).join("")}${profile.levelsMore ? `<div class="muted small">+ ${esc(profile.levelsMore)} more values</div>` : ""}</div></div>`;
  }
  const byArm = profile.byArm;
  if (byArm && byArm.arms && byArm.arms.length) {
    html += `<h3>By treatment arm</h3><div class="card" style="overflow:auto"><table class="grid"><tr><th></th>${byArm.arms.map((arm) => `<th>${esc(arm)}</th>`).join("")}</tr>`;
    if (byArm.kind === "cat") html += byArm.rows.map((row) => `<tr><td class="mono">${esc(row.v)}</td>${row.cells.map((cell) => `<td class="num">${esc(cell)}</td>`).join("")}</tr>`).join("");
    else { const keys = ["n", "mean", "sd", "median", "min", "max"].filter((key) => byArm.cells.some((cell) => cell && cell[key] != null));
      html += keys.map((key) => `<tr><td class="mono">${key}</td>${byArm.cells.map((cell) => `<td class="num">${esc(fmt((cell || {})[key]))}</td>`).join("")}</tr>`).join(""); }
    html += "</table></div>";
  }
  if (profile.examples && profile.examples.length) {
    const keys = (MODEL.datasets.find((dataset) => dataset.name === variable.ds) || {}).keys || [];
    html += `<h3>Example records</h3><div class="card"><table class="grid"><tr>${keys.map((key) => `<th>${esc(key)}</th>`).join("")}<th>${esc(variable.name)}</th></tr>${profile.examples.map((example) => `<tr>${example.k.map((value) => `<td class="mono">${esc(value)}</td>`).join("")}<td class="mono"><b>${esc(example.v)}</b></td></tr>`).join("")}</table></div>`;
  }
  return html;
}

/* ------------------------------------------------------------ SDTM column */
function renderSdtm(ref) {
  chrome("var");
  const column = MODEL.sdtm[ref] || { usedBy: [], readBy: [], core: [] };
  const domain = ref.split(".")[0];
  app.innerHTML = `<div class="single"><h2><span class="ds">${esc(domain)}.</span>${esc(ref.split(".")[1] || "")}</h2><p class="lead">${esc(column.label || "SDTM column")} · ${esc((MODEL.domains[domain] || {}).label || "")}</p>
    <h3>Declared as the source of</h3><div class="card"><div class="body">${chips(column.usedBy, varChip)}</div></div>
    <h3>Named in the code that builds</h3><div class="card"><div class="body">${chips(column.readBy, varChip)}</div></div>
    <h3>Outputs downstream</h3><div class="card"><div class="body">${chips([...new Set([...column.usedBy, ...column.readBy].flatMap((id) => (MODEL.vars[id] || {}).outputs || []))].sort(), outChip)}</div></div>
    <h3>CORE findings on this column</h3><div class="card"><div class="body">${chips(column.core, coreChip)}</div></div></div>`;
}

/* ------------------------------------------------------------ protocol */
function renderProtocol(focus) {
  let html = `<div class="single"><h2>Protocol → outputs</h2><p class="lead">Each objective and endpoint of the digitized protocol (USDM), the protocol page it was read from, and the outputs planned for it.</p>`;
  for (const objective of MODEL.objectives) {
    html += `<div class="card" id="p-${esc(objective.id)}" style="${focus === objective.id ? "outline:2px solid var(--accent)" : ""}"><div class="head">${tag(objective.level || "Objective", "acc")}<b>${esc(objective.id)}</b></div><div class="body">${esc(objective.text)}${cite(objective.cite)}
      <div style="margin-top:6px">${chips(objective.outputs, (id) => (MODEL.outputs[id] ? outChip(id) : `<span class="chip static muted">${esc(id)}</span>`), "no output planned for the objective itself")}</div>`;
    for (const endpointId of objective.endpoints) {
      const endpoint = MODEL.endpoints[endpointId];
      html += `<div style="margin:12px 0 0 14px;padding-left:12px;border-left:2px solid var(--line)">${tag(endpoint.level || "Endpoint")} <b class="small">${esc(endpointId)}</b> ${esc(endpoint.purpose || "")}<div>${esc(endpoint.text)}</div>${cite(endpoint.cite)}<div>${chips(endpoint.outputs, (id) => (MODEL.outputs[id] ? outChip(id) : `<span class="chip static">${esc(id)}</span>`), "no output planned")}</div></div>`;
    }
    html += "</div></div>";
  }
  html += `<h3>TLF plan (${MODEL.plan.length} entries)</h3><div class="card" style="overflow:auto"><table class="grid"><tr><th>Output</th><th>Title</th><th>Status</th><th>Traces to</th><th>Produced</th></tr>
    ${MODEL.plan.map((entry) => `<tr><td>${MODEL.outputs[entry.id] ? outChip(entry.id) : `<span class="mono small">${esc(entry.id)}</span>`}</td><td>${esc(entry.title)}</td><td>${tag(entry.status, entry.status === "planned" ? "good" : "warn")}${entry.reason ? `<div class="small muted">${esc(entry.reason)}</div>` : ""}</td>
    <td>${(entry.traces.objective_ids || []).concat(entry.traces.endpoint_ids || []).map(objChip).join("")}${entry.traces.regulatory_rule ? `<span class="small muted">${esc(entry.traces.regulatory_rule)}</span>` : ""}</td><td>${entry.produced ? tag("yes", "good") : tag("no", entry.status === "planned" ? "bad" : "")}</td></tr>`).join("")}</table></div></div>`;
  app.innerHTML = html;
  if (focus) { const target = document.getElementById("p-" + focus) || [...document.querySelectorAll("[id^=p-]")].find((node) => node.textContent.includes(focus)); if (target) target.scrollIntoView(); }
}

/* ------------------------------------------------------------ CORE */
function renderCore(key) {
  if (key && coreByKey[key]) return renderFinding(coreByKey[key]);
  const filter = storage.get("f-core-std") || "all", impactOnly = storage.get("f-core-impact") === "1";
  let html = `<div class="single"><h2>CDISC CORE</h2><p class="lead">Every finding, the reviewer's disposition, and what it touches downstream: SDTM column → ADaM variables built from it → outputs.</p><div class="tiles">`;
  for (const [standard, info] of Object.entries(MODEL.core.standards)) html += `<div class="tile"><div class="v">${esc(info.findings)}</div><div class="l">${esc(standard.toUpperCase())} ${esc(info.version || "")} findings · ${esc(info.issues)} issues · ${esc(info.rules)} rules · ${esc(info.runtime || "")}</div></div>`;
  html += `</div><div class="pill-row">${["all"].concat(Object.keys(MODEL.core.standards)).map((standard) => `<a data-std="${standard}" class="${filter === standard ? "on" : ""}">${standard}</a>`).join("")}<a data-impact="1" class="${impactOnly ? "on" : ""}">reaches an output</a></div>`;
  const findings = MODEL.core.findings.filter((finding) => (filter === "all" || finding.std === filter) && (!impactOnly || finding.impact.outputs.length))
    .sort((left, right) => right.impact.outputs.length - left.impact.outputs.length || (+right.issues || 0) - (+left.issues || 0));
  html += `<div class="card" style="overflow:auto"><table class="grid"><tr><th>Rule</th><th>Dataset</th><th>Message</th><th>Issues</th><th>Subjects</th><th>Disposition</th><th>ADaM</th><th>Outputs</th></tr>
    ${findings.slice(0, 600).map((finding) => `<tr class="click" data-go="#core/${esc(finding.key)}"><td class="mono">${esc(finding.rule)}</td><td class="mono">${esc(finding.dataset)}</td><td>${esc(finding.message)}</td><td class="num">${esc(finding.issues)}</td><td class="num">${esc(finding.subjects)}</td>
    <td>${finding.disposition ? tag(finding.disposition, finding.disposition === "fix" ? "bad" : "") : '<span class="muted small">—</span>'}</td><td class="num">${finding.impact.adam.length}</td><td class="num">${finding.impact.outputs.length}</td></tr>`).join("")}</table>
    ${findings.length > 600 ? `<div class="muted small" style="padding:8px">${findings.length - 600} more — filter to narrow.</div>` : ""}</div></div>`;
  app.innerHTML = html;
  app.querySelectorAll("[data-std]").forEach((node) => node.addEventListener("click", () => { storage.set("f-core-std", node.dataset.std); renderCore(); }));
  app.querySelectorAll("[data-impact]").forEach((node) => node.addEventListener("click", () => { storage.set("f-core-impact", impactOnly ? "0" : "1"); renderCore(); }));
}
function renderFinding(finding) {
  const impact = finding.impact;
  let html = `<div class="single"><a href="#core">← all findings</a><h2>${esc(finding.rule)} <span class="ds">· ${esc(finding.dataset)} · ${esc(finding.std.toUpperCase())}</span></h2><p class="lead">${esc(finding.message)}</p>
    <div class="meta"><span>issues <b>${esc(finding.issues)}</b></span><span>subjects <b>${esc(finding.subjects)}</b></span><span>variables <b>${esc(finding.variables.join(", ") || "—")}</b></span></div>
    <div class="banner ${finding.disposition === "fix" ? "bad" : finding.disposition ? "good" : ""}"><b>Disposition: ${esc(finding.disposition || "none recorded")}</b>${finding.justification ? " — " + esc(finding.justification) : ""}</div>
    <h3>What it touches</h3><div class="card"><div class="flow">
    <div class="col"><h4>SDTM COLUMNS</h4>${chips(impact.sdtm, sdtmChip, finding.std === "sdtmig" ? "no flagged column feeds the ADaM" : "—")}</div>
    <div class="col"><h4>ADAM VARIABLES BUILT FROM THEM</h4>${chips(impact.adam, varChip)}</div>
    <div class="col"><h4>DOWNSTREAM ADAM</h4>${chips(impact.downstream.slice(0, 40), varChip)}${impact.downstream.length > 40 ? `<div class="muted small">+${impact.downstream.length - 40} more</div>` : ""}</div>
    <div class="col"><h4>OUTPUTS</h4>${chips(impact.outputs, outChip)}</div></div></div>`;
  if (finding.examples.length) {
    const columns = [...new Set(finding.examples.flatMap((example) => Object.keys(example.values)))];
    html += `<h3>Example issues</h3><div class="card" style="overflow:auto"><table class="grid"><tr><th>USUBJID</th><th>SEQ</th><th>row</th>${columns.map((column) => `<th>${esc(column)}</th>`).join("")}</tr>
      ${finding.examples.map((example) => `<tr><td class="mono">${esc(example.subject)}</td><td class="num">${esc(example.seq)}</td><td class="num">${esc(example.row)}</td>${columns.map((column) => `<td class="mono">${esc(example.values[column])}</td>`).join("")}</tr>`).join("")}</table></div>`;
  }
  app.innerHTML = html + "</div>";
}

/* ------------------------------------------------------------ checks + gaps */
function renderChecks() {
  const summary = MODEL.checks.summary || {}, coverage = MODEL.checks.coverage || {};
  const outputs = Object.values(MODEL.outputs);
  const reconciled = outputs.reduce((total, output) => total + (((output.checks || {}).reconciliation || {}).checked || 0), 0);
  const unmatched = outputs.reduce((total, output) => total + ((((output.checks || {}).reconciliation || {}).unmatched) || []).length, 0);
  let html = `<div class="single"><h2>Checks</h2><p class="lead">Deterministic checks of this run, per output. Every number in a display is matched to its ARD row; the ARD is then checked against ADaM independently of the programs.</p>
    <div class="tiles"><div class="tile"><div class="v">${esc(reconciled)}</div><div class="l">displayed numbers reconciled</div></div><div class="tile"><div class="v">${unmatched}</div><div class="l">unmatched</div></div>
    <div class="tile"><div class="v">${esc(summary.denominatorsPassed ?? "—")}/${esc((summary.denominatorsPassed || 0) + (summary.denominatorsFailed || 0) + (summary.denominatorsNotChecked || 0))}</div><div class="l">big-N checks passed</div></div>
    <div class="tile"><div class="v">${esc(coverage.recomputed ?? "—")}</div><div class="l">of ${esc(coverage.statistics ?? "—")} statistics recomputed · ${esc(coverage.mismatches ?? 0)} mismatches</div></div>
    <div class="tile"><div class="v">${MODEL.gaps.length}</div><div class="l">traceability gaps</div></div></div>`;
  for (const warning of (MODEL.checks.warnings || []).concat(MODEL.checks.consistency || [])) html += `<div class="banner">${esc(typeof warning === "string" ? warning : JSON.stringify(warning))}</div>`;
  html += `<h3>Per output</h3><div class="card" style="overflow:auto"><table class="grid"><tr><th>Output</th><th>Title</th><th>Numbers reconciled</th><th>Big N</th><th>Recomputed</th><th>Not independently checked</th><th>CORE on inputs</th></tr>
    ${outputs.map((output) => { const checks = output.checks || {}, reconciliation = checks.reconciliation || {}, denominators = checks.denominators || {}, recompute = checks.recompute || {};
      return `<tr><td>${outChip(output.id)}</td><td class="small">${esc(output.title)}</td><td>${reconciliation.checked != null ? tag(`${reconciliation.checked}${(reconciliation.unmatched || []).length ? ", " + reconciliation.unmatched.length + " unmatched" : ""}`, (reconciliation.unmatched || []).length ? "bad" : "good") : "—"}</td>
      <td>${denominators.status ? tag(denominators.status, denominators.status === "pass" ? "good" : denominators.status === "fail" ? "bad" : "") : "—"}<div class="small muted mono">${esc(denominators.analysisSet || "")}</div></td>
      <td>${recompute.statistics != null ? tag(`${recompute.recomputed}/${recompute.statistics}`, (recompute.mismatches || []).length ? "bad" : recompute.recomputed ? "good" : "") : "—"}</td>
      <td class="small muted">${esc(Object.keys(recompute.notChecked || {}).join("; "))}</td><td class="num">${output.core.length}</td></tr>`; }).join("")}</table></div>`;
  const populations = MODEL.checks.populations || {};
  if (Object.keys(populations).length) {
    const arms = [...new Set(Object.values(populations).flatMap((population) => Object.keys(population.byArm || {})))];
    html += `<h3>Population counts (derive-adam)</h3><div class="card"><table class="grid"><tr><th>Flag</th><th>Total</th>${arms.map((arm) => `<th>${esc(arm)}</th>`).join("")}</tr>${Object.entries(populations).map(([flag, population]) => `<tr><td>${varChip("ADSL." + flag)}</td><td class="num">${esc(population.total)}</td>${arms.map((arm) => `<td class="num">${esc((population.byArm || {})[arm] ?? "")}</td>`).join("")}</tr>`).join("")}</table></div>`;
  }
  html += `<h3>Runs that produced this package</h3><div class="card"><table class="grid"><tr><th>Workflow</th><th>Outcome</th><th>Run</th><th>At</th></tr>${(MODEL.study.history || []).map((run) => `<tr><td>${esc(run.workflow)}</td><td>${tag(run.outcome)}</td><td class="mono small">${esc(run.runId)}</td><td class="small">${esc(run.at)}</td></tr>`).join("")}</table></div></div>`;
  app.innerHTML = html;
}
function renderGaps() {
  const link = (gap) => (MODEL.outputs[gap.ref] ? outChip(gap.ref) : MODEL.vars[gap.ref] ? varChip(gap.ref) : `<span class="mono">${esc(gap.ref)}</span>`);
  app.innerHTML = `<div class="single"><h2>Gaps</h2><p class="lead">Links that should exist and do not. An empty list means every output traces to ADaM, every ADaM variable to its program lines and sources, and every planned output was produced.</p>
    ${MODEL.gaps.length ? `<div class="card"><table class="grid"><tr><th>Kind</th><th>Where</th><th>What</th></tr>${MODEL.gaps.map((gap) => `<tr><td>${tag(gap.kind, "warn")}</td><td>${link(gap)}</td><td>${esc(gap.message)}</td></tr>`).join("")}</table></div>` : '<div class="banner good">No traceability gaps.</div>'}</div>`;
}

/* ------------------------------------------------------------ router */
function route() {
  const hash = decodeURIComponent(location.hash.slice(1));
  const [view, ...rest] = hash.split("/");
  const id = rest.join("/");
  const active = TABS.some(([key]) => key === view) ? view : "out";
  chrome(active);
  if (view === "var") renderVars(id);
  else if (view === "sdtm") renderSdtm(id);
  else if (view === "protocol") renderProtocol(id);
  else if (view === "core") renderCore(id);
  else if (view === "checks") renderChecks();
  else if (view === "gaps") renderGaps();
  else renderOutputs(id);
  if (!["out", "var", ""].includes(view)) window.scrollTo(0, 0);
  const selected = document.querySelector(".rail .item.on"); if (selected) selected.scrollIntoView({ block: "nearest" });
}
app.addEventListener("click", (event) => { const target = event.target.closest("[data-go]"); if (target) go(target.dataset.go); });
app.addEventListener("input", (event) => {
  const input = event.target.closest("input[data-filter]"); if (!input) return;
  storage.set(input.dataset.filter, input.value);
  const position = input.selectionStart; route();
  const again = document.querySelector(`input[data-filter="${input.dataset.filter}"]`); if (again) { again.focus(); again.setSelectionRange(position, position); }
});
document.getElementById("theme").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "light" : "dark"; storage.set("theme", document.documentElement.dataset.theme);
});
if (storage.get("theme")) document.documentElement.dataset.theme = storage.get("theme");
window.addEventListener("hashchange", route);
route();
