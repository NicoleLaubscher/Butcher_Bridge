import { analyseScenario, buildTradeoff, deepCopy, parseTiers, recommendedWindow, sampleState, validateState } from "./engine.mjs";

const STORAGE_KEY = "butcherbridge-scenario-v1";
const currency = new Intl.NumberFormat("en-ZA", { style: "currency", currency: "ZAR", minimumFractionDigits: 2 });
const number = new Intl.NumberFormat("en-ZA", { maximumFractionDigits: 0 });
const dateFormat = new Intl.DateTimeFormat("en-ZA", { day: "2-digit", month: "short", timeZone: "UTC" });
let state = loadState();
let lastResult = null;

const elements = {
  demandBody: document.querySelector("#demand-body"),
  supplierBody: document.querySelector("#supplier-body"),
  productSelect: document.querySelector("#product-select"),
  orderDate: document.querySelector("#order-date"),
  waitDays: document.querySelector("#wait-days"),
  waitOutput: document.querySelector("#wait-output"),
  validationBanner: document.querySelector("#validation-banner"),
  kpiGrid: document.querySelector("#kpi-grid"),
  feasibilityBody: document.querySelector("#feasibility-body"),
  individualBody: document.querySelector("#individual-body"),
  recommendationChip: document.querySelector("#recommendation-chip"),
  emptyResults: document.querySelector("#empty-results"),
  resultsContent: document.querySelector("#results-content"),
  savingsBadge: document.querySelector("#savings-badge"),
  comparisonBars: document.querySelector("#comparison-bars"),
  comparisonDetail: document.querySelector("#comparison-detail"),
  tierProgress: document.querySelector("#tier-progress"),
  tierStatus: document.querySelector("#tier-status"),
  orderSummary: document.querySelector("#order-summary"),
  tradeoffChart: document.querySelector("#tradeoff-chart"),
  tradeoffInsight: document.querySelector("#tradeoff-insight"),
  toast: document.querySelector("#toast")
};

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved?.settings && Array.isArray(saved.demands) && Array.isArray(saved.suppliers)) return saved;
  } catch {}
  return deepCopy(sampleState);
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function safe(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function uid(prefix) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function asMoney(value) {
  return value == null || !Number.isFinite(value) ? "—" : currency.format(value);
}

function asPercent(value, digits = 0) {
  return value == null || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function asDate(value) {
  if (!value) return "—";
  return dateFormat.format(new Date(`${value}T00:00:00Z`));
}

function demandRow(row) {
  return `<tr data-id="${safe(row.id)}">
    <td><input aria-label="Retailer name" data-field="retailer" value="${safe(row.retailer)}"></td>
    <td><input aria-label="Demand product" data-field="product" value="${safe(row.product)}"></td>
    <td><input aria-label="Demand kilograms" data-field="quantity" type="number" min="0" step="1" value="${safe(row.quantity)}"></td>
    <td><input aria-label="Retailer area" data-field="area" value="${safe(row.area)}"></td>
    <td><input aria-label="Required date" data-field="requiredDate" type="date" value="${safe(row.requiredDate)}"></td>
    <td><input aria-label="Days until demand joins" data-field="joinDays" type="number" min="0" step="1" value="${safe(row.joinDays)}"><span class="metric-sub">days</span></td>
    <td><input class="money-input" aria-label="Individual trip and administration cost" data-field="procurementCost" type="number" min="0" step="10" value="${safe(row.procurementCost)}"><span class="metric-sub">ZAR / order</span></td>
    <td><button class="remove-row" data-remove="demand" aria-label="Remove ${safe(row.retailer)}">×</button></td>
  </tr>`;
}

function supplierRow(row) {
  return `<tr data-id="${safe(row.id)}">
    <td><input aria-label="Supplier name" data-field="name" value="${safe(row.name)}"></td>
    <td><input aria-label="Supplier product" data-field="product" value="${safe(row.product)}"></td>
    <td><input class="area-input" aria-label="Supplier service areas" data-field="areas" value="${safe(row.areas)}"></td>
    <td><input aria-label="Supplier capacity kilograms" data-field="capacity" type="number" min="0" step="1" value="${safe(row.capacity)}"></td>
    <td><input aria-label="Supplier lead time days" data-field="leadDays" type="number" min="0" step="1" value="${safe(row.leadDays)}"><span class="metric-sub">days</span></td>
    <td><input class="money-input" aria-label="Fixed fulfilment cost" data-field="fixedCost" type="number" min="0" step="10" value="${safe(row.fixedCost)}"></td>
    <td><input class="money-input" aria-label="Variable fulfilment cost per kilogram" data-field="variableCost" type="number" min="0" step="0.1" value="${safe(row.variableCost)}"></td>
    <td><input class="tier-input" aria-label="Price tiers" data-field="tiers" value="${safe(row.tiers)}"></td>
    <td><button class="remove-row" data-remove="supplier" aria-label="Remove ${safe(row.name)}">×</button></td>
  </tr>`;
}

function renderInputs() {
  elements.orderDate.value = state.settings.orderDate;
  elements.waitDays.value = state.settings.waitDays;
  elements.waitOutput.textContent = `${state.settings.waitDays} day${Number(state.settings.waitDays) === 1 ? "" : "s"}`;
  elements.demandBody.innerHTML = state.demands.map(demandRow).join("");
  elements.supplierBody.innerHTML = state.suppliers.map(supplierRow).join("");
  renderProductOptions();
}

function renderProductOptions() {
  const products = [...new Set([...state.demands, ...state.suppliers].map((row) => String(row.product ?? "").trim()).filter(Boolean))];
  if (!products.includes(state.settings.product) && products.length) state.settings.product = products[0];
  elements.productSelect.innerHTML = products.map((product) => `<option ${product === state.settings.product ? "selected" : ""}>${safe(product)}</option>`).join("");
}

function renderValidation(errors) {
  document.querySelectorAll("tr.row-error").forEach((row) => row.classList.remove("row-error"));
  for (const error of errors) document.querySelector(`tr[data-id="${CSS.escape(error.id)}"]`)?.classList.add("row-error");
  elements.validationBanner.hidden = errors.length === 0;
  elements.validationBanner.innerHTML = errors.length ? `<strong>${errors.length} input${errors.length === 1 ? " needs" : "s need"} attention.</strong> ${safe(errors[0].message)}${errors.length > 1 ? " Check the highlighted rows." : ""}` : "";
}

function kpiCard(label, value, note, tone = "") {
  return `<article class="kpi ${tone}"><span class="kpi-label">${safe(label)}</span><strong>${value}</strong><small>${safe(note)}</small></article>`;
}

function renderKpis(result) {
  const kpis = result.kpis;
  elements.kpiGrid.innerHTML = [
    kpiCard("Committed demand", `${number.format(kpis.committedDemand)} kg`, `${result.includedDemands.length} retailers in window`, "good"),
    kpiCard("Collective landed cost", asMoney(kpis.collectiveLandedPerKg), "per kilogram", kpis.collectiveLandedPerKg ? "good" : "warn"),
    kpiCard("Logistics cost", asMoney(kpis.logisticsPerKg), "per kilogram", ""),
    kpiCard("Feasible alternatives", number.format(kpis.feasibleAlternatives), `${result.supplierResults.length} quotations tested`, kpis.feasibleAlternatives ? "good" : "warn"),
    kpiCard("Fill · on-time", `${asPercent(kpis.fillRate)} · ${asPercent(kpis.onTimeRate)}`, "best collective option", kpis.fillRate === 1 && kpis.onTimeRate === 1 ? "good" : "warn"),
    kpiCard("Trips avoided", number.format(kpis.procurementTripsAvoided), "one consolidated order", kpis.procurementTripsAvoided ? "good" : "")
  ].join("");
}

function renderComparison(result) {
  const individual = result.individualLandedPerKg;
  const collective = result.bestCollective?.landedPerKg ?? null;
  const max = Math.max(individual ?? 0, collective ?? 0, 1);
  const savingPositive = (result.collectiveSavings ?? 0) >= 0;
  elements.savingsBadge.className = `savings-badge ${savingPositive ? "" : "negative"}`;
  elements.savingsBadge.textContent = result.collectiveSavings == null
    ? "Comparison unavailable"
    : `${savingPositive ? "Save" : "Costs"} ${asMoney(Math.abs(result.collectiveSavings))}`;
  elements.comparisonBars.innerHTML = `
    <div class="bar-row"><span>Individual</span><div class="bar-track"><div class="bar-fill" style="width:${individual == null ? 0 : individual / max * 100}%"></div></div><strong>${asMoney(individual)}/kg</strong></div>
    <div class="bar-row collective"><span>Collective</span><div class="bar-track"><div class="bar-fill" style="width:${collective == null ? 0 : collective / max * 100}%"></div></div><strong>${asMoney(collective)}/kg</strong></div>`;
  elements.comparisonDetail.innerHTML = `
    <div><span>Best collective supplier</span><strong>${safe(result.bestCollective?.supplier.name ?? "No feasible supplier")}</strong></div>
    <div><span>Total collective cost</span><strong>${asMoney(result.bestCollective?.totalCost)}</strong></div>
    <div><span>Difference vs individual</span><strong>${result.collectiveSavingsPct == null ? "—" : `${result.collectiveSavingsPct >= 0 ? "−" : "+"}${Math.abs(result.collectiveSavingsPct * 100).toFixed(1)}%`}</strong></div>`;
}

function renderTier(result) {
  const best = result.bestCollective;
  if (!best) {
    elements.tierProgress.innerHTML = `<div class="tier-note">No collective tier is feasible for the current window.</div>`;
    elements.orderSummary.innerHTML = `<div><span>Visible demand</span><strong>${number.format(result.totalDemand)} kg</strong></div><div><span>Pending</span><strong>${number.format(result.pendingDemand)} kg</strong></div>`;
    elements.tierStatus.style.background = "var(--red)";
    return;
  }
  const target = best.nextTier?.minQty ?? result.totalDemand;
  const percentage = Math.min(100, target ? result.totalDemand / target * 100 : 100);
  elements.tierProgress.innerHTML = `
    <div class="tier-amounts"><strong>${number.format(result.totalDemand)} kg</strong><span>${best.nextTier ? `${number.format(best.kgToNextTier)} kg to next tier` : "best quoted tier reached"}</span></div>
    <div class="progress-track"><div class="progress-fill" style="width:${percentage}%"></div></div>
    <p class="tier-note">Applied quote: ${number.format(best.tier.minQty)}+ kg at ${asMoney(best.tier.price)}/kg${best.nextTier ? ` · next tier ${number.format(best.nextTier.minQty)}+ kg at ${asMoney(best.nextTier.price)}/kg` : ""}.</p>`;
  elements.orderSummary.innerHTML = `
    <div><span>Demand visible</span><strong>${asPercent(result.kpis.demandVisibility)}</strong></div>
    <div><span>Pending demand</span><strong>${number.format(result.pendingDemand)} kg</strong></div>
    <div><span>Earliest need</span><strong>${asDate(result.earliestRequiredDate)}</strong></div>
    <div><span>Delivery buffer</span><strong>${best.slackDays} day${Math.abs(best.slackDays) === 1 ? "" : "s"}</strong></div>`;
  elements.tierStatus.style.background = best.nextTier ? "var(--sand)" : "var(--green-2)";
}

function renderFeasibility(result) {
  elements.feasibilityBody.innerHTML = result.supplierResults.map((item) => {
    const best = result.bestCollective?.supplier.id === item.supplier.id;
    const areaOk = !item.reasons.some((reason) => reason.startsWith("Area"));
    const capacityOk = !item.reasons.some((reason) => reason.startsWith("Capacity"));
    const arrivalOk = item.slackDays >= 0;
    const decision = item.feasible ? "Feasible" : item.reasons.join(" · ");
    return `<tr>
      <td><span class="supplier-name">${safe(item.supplier.name)}</span>${best ? '<span class="best-label">Best</span>' : ""}</td>
      <td>${number.format(item.quantity)} / ${number.format(Number(item.supplier.capacity))} kg<span class="metric-sub">${capacityOk ? `${(item.capacityUtilisation * 100).toFixed(0)}% utilised` : "insufficient"}</span></td>
      <td>${areaOk ? "Covered" : "Not covered"}<span class="metric-sub">${safe(item.supplier.areas)}</span></td>
      <td>${asDate(item.arrivalDate)}<span class="metric-sub">${arrivalOk ? `${item.slackDays} day buffer` : `${Math.abs(item.slackDays)} day late`}</span></td>
      <td>${item.tier ? `${number.format(item.tier.minQty)}+ kg` : "—"}<span class="metric-sub">${item.tier ? `${asMoney(item.tier.price)}/kg` : "no tier"}</span></td>
      <td>${asMoney(item.logisticsPerKg)}</td>
      <td><strong>${asMoney(item.landedPerKg)}</strong></td>
      <td><span class="decision-status ${item.feasible ? "pass" : "fail"}">${item.feasible ? "●" : "×"} ${safe(decision)}</span></td>
    </tr>`;
  }).join("") || `<tr><td colspan="8">No quotations match this product.</td></tr>`;
}

function renderIndividuals(result) {
  elements.individualBody.innerHTML = result.individualResults.map((item) => `<tr>
    <td class="supplier-name">${safe(item.demand.retailer)}</td>
    <td>${number.format(Number(item.demand.quantity))} kg</td>
    <td>${safe(item.best?.supplier.name ?? "No feasible supplier")}</td>
    <td>${item.best?.tier ? `${asMoney(item.best.tier.price)}/kg` : "—"}</td>
    <td>${asMoney(Number(item.demand.procurementCost))}</td>
    <td><strong>${asMoney(item.best?.landedPerKg)}</strong></td>
    <td>${asDate(item.best?.arrivalDate)}</td>
  </tr>`).join("");
}

function renderTradeoff() {
  const points = buildTradeoff(state, state.settings.product, 14);
  const recommendation = recommendedWindow(points);
  const validCosts = points.map((point) => point.landedPerKg).filter((value) => value != null);
  const min = validCosts.length ? Math.min(...validCosts) : 0;
  const max = validCosts.length ? Math.max(...validCosts) : 1;
  const scale = (value) => value == null ? 0 : 34 + ((max - value) / Math.max(1, max - min)) * 115;
  elements.tradeoffChart.innerHTML = `<span class="chart-axis">lower landed cost →</span>` + points.map((point) => {
    const classes = [point.waitDays === Number(state.settings.waitDays) ? "selected" : "", point.waitDays === recommendation?.waitDays ? "recommended" : "", point.landedPerKg == null ? "blocked" : ""].filter(Boolean).join(" ");
    const tip = point.landedPerKg == null ? `Day ${point.waitDays}: no feasible collective option` : `Day ${point.waitDays}: ${asMoney(point.landedPerKg)}/kg · ${number.format(point.totalDemand)} kg · ${point.slackDays} day buffer`;
    return `<div class="chart-col ${classes}"><span class="chart-tip">${safe(tip)}</span><div class="chart-bar" style="height:${scale(point.landedPerKg)}px"></div><label>${point.waitDays}</label></div>`;
  }).join("");

  const current = points[Number(state.settings.waitDays)];
  elements.tradeoffInsight.innerHTML = recommendation ? `
    <div><span class="card-kicker">MODEL INSIGHT</span><h3>${recommendation.waitDays === Number(state.settings.waitDays) ? "This window is the lowest-cost feasible point." : `A ${recommendation.waitDays}-day window gives the lowest feasible cost.`}</h3><p>The model only recommends options that cover all visible demand, serve every included area, remain within capacity, and arrive by the earliest required date.</p></div>
    <div class="insight-stats"><div><span>Recommended cost</span><strong>${asMoney(recommendation.landedPerKg)}/kg</strong></div><div><span>Delivery buffer</span><strong>${recommendation.slackDays} days</strong></div><div><span>Visible demand</span><strong>${number.format(recommendation.totalDemand)} kg</strong></div><div><span>Current window</span><strong>${current?.landedPerKg == null ? "Blocked" : asMoney(current.landedPerKg) + "/kg"}</strong></div></div>` : `
    <div><span class="card-kicker">MODEL INSIGHT</span><h3>No feasible window yet.</h3><p>Increase supplier capacity, broaden service coverage, shorten lead time, or extend retailer required dates.</p></div>`;
}

function renderResults(scroll = false) {
  const errors = validateState(state);
  renderValidation(errors);
  const productErrors = errors.filter((error) => error.scope === "settings");
  if (productErrors.length) return;
  lastResult = analyseScenario(state);
  elements.waitOutput.textContent = `${state.settings.waitDays} day${Number(state.settings.waitDays) === 1 ? "" : "s"}`;
  elements.emptyResults.hidden = lastResult.totalDemand > 0;
  elements.resultsContent.hidden = lastResult.totalDemand === 0;
  if (lastResult.totalDemand === 0) {
    elements.recommendationChip.className = "recommendation-chip blocked";
    elements.recommendationChip.textContent = "No demand is visible in the selected window.";
    renderTradeoff();
    return;
  }
  if (lastResult.bestCollective) {
    elements.recommendationChip.className = "recommendation-chip";
    elements.recommendationChip.textContent = `${lastResult.bestCollective.supplier.name} is feasible at ${asMoney(lastResult.bestCollective.landedPerKg)}/kg with a ${lastResult.bestCollective.slackDays}-day delivery buffer.`;
  } else {
    elements.recommendationChip.className = "recommendation-chip blocked";
    elements.recommendationChip.textContent = "No quotation satisfies every capacity, area, tier, and deadline constraint.";
  }
  renderKpis(lastResult);
  renderComparison(lastResult);
  renderTier(lastResult);
  renderFeasibility(lastResult);
  renderIndividuals(lastResult);
  renderTradeoff();
  if (scroll) document.querySelector("#results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function updateTableRow(event, collectionName) {
  const input = event.target.closest("input[data-field]");
  if (!input) return;
  const rowId = input.closest("tr")?.dataset.id;
  const row = state[collectionName].find((item) => item.id === rowId);
  if (!row) return;
  const numeric = ["quantity", "joinDays", "procurementCost", "capacity", "leadDays", "fixedCost", "variableCost"].includes(input.dataset.field);
  row[input.dataset.field] = numeric ? Number(input.value) : input.value;
  saveState();
  renderProductOptions();
  renderResults();
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => elements.toast.classList.remove("show"), 2400);
}

elements.demandBody.addEventListener("input", (event) => updateTableRow(event, "demands"));
elements.supplierBody.addEventListener("input", (event) => updateTableRow(event, "suppliers"));
document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-remove]");
  if (!button) return;
  const rowId = button.closest("tr")?.dataset.id;
  const collection = button.dataset.remove === "demand" ? "demands" : "suppliers";
  state[collection] = state[collection].filter((row) => row.id !== rowId);
  saveState();
  renderInputs();
  renderResults();
});

document.querySelector("#add-demand").addEventListener("click", () => {
  state.demands.push({ id: uid("d"), retailer: "New retailer", product: state.settings.product, quantity: 50, area: "", requiredDate: state.settings.orderDate, joinDays: 0, procurementCost: 0 });
  saveState(); renderInputs(); renderResults();
  elements.demandBody.lastElementChild?.querySelector("input")?.focus();
});

document.querySelector("#add-supplier").addEventListener("click", () => {
  state.suppliers.push({ id: uid("s"), name: "New supplier", product: state.settings.product, areas: "All", capacity: 300, leadDays: 3, fixedCost: 0, variableCost: 0, tiers: "0:0" });
  saveState(); renderInputs(); renderResults();
  elements.supplierBody.lastElementChild?.querySelector("input")?.focus();
});

elements.orderDate.addEventListener("change", () => { state.settings.orderDate = elements.orderDate.value; saveState(); renderResults(); });
elements.productSelect.addEventListener("change", () => { state.settings.product = elements.productSelect.value; saveState(); renderResults(); });
elements.waitDays.addEventListener("input", () => {
  state.settings.waitDays = Number(elements.waitDays.value);
  saveState(); renderResults();
});
document.querySelector("#run-analysis").addEventListener("click", () => {
  const errors = validateState(state);
  renderResults(errors.length === 0);
  showToast(errors.length ? "Please fix the highlighted inputs." : "Scenario recalculated.");
});
document.querySelector("#reset-data").addEventListener("click", () => {
  if (!window.confirm("Restore the example scenario? Your current browser data will be replaced.")) return;
  state = deepCopy(sampleState); saveState(); renderInputs(); renderResults(); showToast("Example scenario restored.");
});
document.querySelector("#export-scenario").addEventListener("click", () => {
  const payload = { exportedAt: new Date().toISOString(), scenario: state, currentAnalysis: lastResult };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `butcherbridge-scenario-${state.settings.orderDate}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
  showToast("Scenario exported as JSON.");
});

renderInputs();
renderResults();
