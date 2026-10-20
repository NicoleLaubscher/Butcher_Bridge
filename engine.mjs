const DAY_MS = 86_400_000;

export const sampleState = {
  settings: {
    orderDate: "2026-09-10",
    waitDays: 5,
    product: "Beef mixed cuts"
  },
  demands: [
    { id: "d1", retailer: "Mamelodi Market", product: "Beef mixed cuts", quantity: 80, area: "Mamelodi", requiredDate: "2026-09-20", joinDays: 0, procurementCost: 460 },
    { id: "d2", retailer: "Atteridgeville Foods", product: "Beef mixed cuts", quantity: 65, area: "Atteridgeville", requiredDate: "2026-09-21", joinDays: 1, procurementCost: 420 },
    { id: "d3", retailer: "Soshanguve Butchery", product: "Beef mixed cuts", quantity: 60, area: "Soshanguve", requiredDate: "2026-09-22", joinDays: 2, procurementCost: 510 },
    { id: "d4", retailer: "Hammanskraal Foods", product: "Beef mixed cuts", quantity: 45, area: "Hammanskraal", requiredDate: "2026-09-24", joinDays: 4, procurementCost: 620 },
    { id: "d5", retailer: "Eersterust Butchery", product: "Beef mixed cuts", quantity: 35, area: "Eersterust", requiredDate: "2026-09-23", joinDays: 5, procurementCost: 360 }
  ],
  suppliers: [
    { id: "s1", name: "Mzansi Beef Co.", product: "Beef mixed cuts", areas: "All", capacity: 400, leadDays: 3, fixedCost: 520, variableCost: 1.10, tiers: "0:78.00; 150:74.00; 280:70.00" },
    { id: "s2", name: "Ubuntu Fresh Meats", product: "Beef mixed cuts", areas: "Mamelodi, Atteridgeville, Soshanguve, Eersterust", capacity: 250, leadDays: 2, fixedCost: 380, variableCost: 1.40, tiers: "0:77.00; 180:72.00" },
    { id: "s3", name: "City Abattoir", product: "Beef mixed cuts", areas: "All", capacity: 350, leadDays: 5, fixedCost: 450, variableCost: 0.85, tiers: "0:80.00; 200:71.50; 300:68.50" },
    { id: "s4", name: "Township Meat Hub", product: "Beef mixed cuts", areas: "All", capacity: 180, leadDays: 1, fixedCost: 300, variableCost: 1.80, tiers: "0:76.00; 120:73.00; 200:70.50" }
  ]
};

export function deepCopy(value) {
  return JSON.parse(JSON.stringify(value));
}

export function parseTiers(raw) {
  const text = String(raw ?? "").trim();
  if (!text) return { tiers: [], error: "Add at least one price tier." };

  const tiers = [];
  for (const part of text.split(/[;\n]+/).map((item) => item.trim()).filter(Boolean)) {
    const match = part.match(/^\s*(\d+(?:\.\d+)?)\s*(?::|@)\s*(\d+(?:\.\d+)?)\s*$/);
    if (!match) return { tiers: [], error: `Use min kg:price, for example 0:78.00 (problem: ${part}).` };
    const minQty = Number(match[1]);
    const price = Number(match[2]);
    if (minQty < 0 || price < 0) return { tiers: [], error: "Tier quantities and prices cannot be negative." };
    tiers.push({ minQty, price });
  }

  tiers.sort((a, b) => a.minQty - b.minQty);
  if (new Set(tiers.map((tier) => tier.minQty)).size !== tiers.length) {
    return { tiers: [], error: "Each tier must have a unique minimum quantity." };
  }
  return { tiers, error: null };
}

export function priceForQuantity(tiers, quantity) {
  let selected = null;
  for (const tier of tiers) {
    if (quantity >= tier.minQty) selected = tier;
  }
  return selected;
}

export function daysBetween(fromDate, toDate) {
  const start = new Date(`${fromDate}T00:00:00Z`).getTime();
  const end = new Date(`${toDate}T00:00:00Z`).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end)) return Number.NaN;
  return Math.floor((end - start) / DAY_MS);
}

export function addDays(date, days) {
  const parsed = new Date(`${date}T00:00:00Z`);
  parsed.setUTCDate(parsed.getUTCDate() + Number(days));
  return parsed.toISOString().slice(0, 10);
}

function numberValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function normalise(value) {
  return String(value ?? "").trim().toLocaleLowerCase();
}

function supplierServesArea(supplier, area) {
  const areas = String(supplier.areas ?? "")
    .split(",")
    .map(normalise)
    .filter(Boolean);
  return areas.includes("all") || areas.includes(normalise(area));
}

function evaluateSupplier(supplier, demands, settings, waitDays, collective = true) {
  const quantity = demands.reduce((total, row) => total + numberValue(row.quantity), 0);
  const parsed = parseTiers(supplier.tiers);
  const tier = priceForQuantity(parsed.tiers, quantity);
  const reasons = [];
  const missingAreas = [...new Set(demands.map((row) => row.area).filter((area) => !supplierServesArea(supplier, area)))];
  const capacity = numberValue(supplier.capacity);
  const leadDays = numberValue(supplier.leadDays);
  const latestArrivalDays = demands.length
    ? Math.min(...demands.map((row) => daysBetween(settings.orderDate, row.requiredDate)))
    : 0;
  const dispatchDelay = collective ? numberValue(waitDays) : Math.max(...demands.map((row) => numberValue(row.joinDays)), 0);
  const arrivalDays = dispatchDelay + leadDays;
  const slackDays = latestArrivalDays - arrivalDays;

  if (normalise(supplier.product) !== normalise(settings.product)) reasons.push("Product mismatch");
  if (parsed.error) reasons.push("Invalid price tiers");
  else if (!tier) reasons.push("No price tier for this quantity");
  if (capacity < quantity) reasons.push(`Capacity short by ${(quantity - capacity).toFixed(0)} kg`);
  if (missingAreas.length) reasons.push(`Area not served: ${missingAreas.join(", ")}`);
  if (slackDays < 0) reasons.push(`Late by ${Math.abs(slackDays)} day${Math.abs(slackDays) === 1 ? "" : "s"}`);

  const fixedCost = numberValue(supplier.fixedCost);
  const variableCost = numberValue(supplier.variableCost);
  const productCost = tier ? tier.price * quantity : null;
  const fulfilmentCost = fixedCost + variableCost * quantity;
  const totalCost = productCost == null ? null : productCost + fulfilmentCost;
  const landedPerKg = totalCost != null && quantity > 0 ? totalCost / quantity : null;
  const nextTier = parsed.tiers.find((candidate) => candidate.minQty > quantity) ?? null;

  return {
    supplier,
    feasible: reasons.length === 0,
    reasons,
    quantity,
    tier,
    nextTier,
    kgToNextTier: nextTier ? Math.max(0, nextTier.minQty - quantity) : 0,
    productCost,
    fulfilmentCost,
    logisticsPerKg: quantity ? fulfilmentCost / quantity : null,
    totalCost,
    landedPerKg,
    arrivalDays,
    arrivalDate: addDays(settings.orderDate, arrivalDays),
    slackDays,
    capacityUtilisation: capacity > 0 ? quantity / capacity : 0,
    fillRate: quantity > 0 ? Math.min(1, capacity / quantity) : 0
  };
}

function evaluateIndividual(demand, suppliers, settings) {
  const candidates = suppliers
    .filter((supplier) => normalise(supplier.product) === normalise(settings.product))
    .map((supplier) => evaluateSupplier(supplier, [demand], settings, 0, false))
    .filter((result) => result.feasible)
    .map((result) => {
      const procurementCost = numberValue(demand.procurementCost);
      const totalCost = result.totalCost + procurementCost;
      return {
        ...result,
        procurementCost,
        totalCost,
        landedPerKg: totalCost / numberValue(demand.quantity)
      };
    })
    .sort((a, b) => a.totalCost - b.totalCost);

  return {
    demand,
    best: candidates[0] ?? null,
    alternatives: candidates.length
  };
}

export function validateState(state) {
  const errors = [];
  if (!state?.settings?.orderDate || !Number.isFinite(new Date(`${state.settings.orderDate}T00:00:00Z`).getTime())) {
    errors.push({ scope: "settings", id: "orderDate", message: "Choose a valid order-opening date." });
  }
  if (!state?.settings?.product?.trim()) errors.push({ scope: "settings", id: "product", message: "Choose a product to analyse." });

  (state?.demands ?? []).forEach((row) => {
    if (!String(row.retailer ?? "").trim()) errors.push({ scope: "demand", id: row.id, message: "Retailer name is required." });
    if (!String(row.product ?? "").trim()) errors.push({ scope: "demand", id: row.id, message: "Product is required." });
    if (!(numberValue(row.quantity) > 0)) errors.push({ scope: "demand", id: row.id, message: "Demand must be greater than 0 kg." });
    if (!String(row.area ?? "").trim()) errors.push({ scope: "demand", id: row.id, message: "Service area is required." });
    if (!row.requiredDate || daysBetween(state.settings.orderDate, row.requiredDate) < 0) errors.push({ scope: "demand", id: row.id, message: "Required date must be on or after the order date." });
    if (numberValue(row.joinDays) < 0) errors.push({ scope: "demand", id: row.id, message: "Join days cannot be negative." });
    if (numberValue(row.procurementCost) < 0) errors.push({ scope: "demand", id: row.id, message: "Procurement cost cannot be negative." });
  });

  (state?.suppliers ?? []).forEach((row) => {
    if (!String(row.name ?? "").trim()) errors.push({ scope: "supplier", id: row.id, message: "Supplier name is required." });
    if (!String(row.product ?? "").trim()) errors.push({ scope: "supplier", id: row.id, message: "Product is required." });
    if (!String(row.areas ?? "").trim()) errors.push({ scope: "supplier", id: row.id, message: "Add a service area or All." });
    if (!(numberValue(row.capacity) > 0)) errors.push({ scope: "supplier", id: row.id, message: "Capacity must be greater than 0 kg." });
    if (numberValue(row.leadDays) < 0) errors.push({ scope: "supplier", id: row.id, message: "Lead time cannot be negative." });
    if (numberValue(row.fixedCost) < 0 || numberValue(row.variableCost) < 0) errors.push({ scope: "supplier", id: row.id, message: "Fulfilment costs cannot be negative." });
    const parsed = parseTiers(row.tiers);
    if (parsed.error) errors.push({ scope: "supplier", id: row.id, message: parsed.error });
  });
  return errors;
}

export function analyseScenario(state, product = state.settings.product, waitDays = state.settings.waitDays) {
  const settings = { ...state.settings, product };
  const includedDemands = state.demands.filter((row) =>
    normalise(row.product) === normalise(product) && numberValue(row.joinDays) <= numberValue(waitDays)
  );
  const pendingDemands = state.demands.filter((row) =>
    normalise(row.product) === normalise(product) && numberValue(row.joinDays) > numberValue(waitDays)
  );
  const totalDemand = includedDemands.reduce((sum, row) => sum + numberValue(row.quantity), 0);
  const pendingDemand = pendingDemands.reduce((sum, row) => sum + numberValue(row.quantity), 0);

  const supplierResults = state.suppliers
    .filter((supplier) => normalise(supplier.product) === normalise(product))
    .map((supplier) => evaluateSupplier(supplier, includedDemands, settings, waitDays, true))
    .sort((a, b) => {
      if (a.feasible !== b.feasible) return a.feasible ? -1 : 1;
      return (a.landedPerKg ?? Number.POSITIVE_INFINITY) - (b.landedPerKg ?? Number.POSITIVE_INFINITY);
    });
  const feasibleSuppliers = supplierResults.filter((result) => result.feasible);
  const bestCollective = feasibleSuppliers[0] ?? null;

  const individualResults = includedDemands.map((demand) => evaluateIndividual(demand, state.suppliers, settings));
  const individualCoveredQuantity = individualResults.reduce((sum, result) => sum + (result.best ? numberValue(result.demand.quantity) : 0), 0);
  const individualTotalCost = individualResults.reduce((sum, result) => sum + (result.best?.totalCost ?? 0), 0);
  const individualComplete = includedDemands.length > 0 && individualResults.every((result) => result.best);
  const individualLandedPerKg = individualComplete && totalDemand > 0 ? individualTotalCost / totalDemand : null;
  const collectiveSavings = individualComplete && bestCollective ? individualTotalCost - bestCollective.totalCost : null;
  const collectiveSavingsPct = collectiveSavings != null && individualTotalCost > 0 ? collectiveSavings / individualTotalCost : null;

  const bestPartialFill = supplierResults.reduce((best, result) => Math.max(best, result.fillRate), 0);
  const earliestRequiredDate = includedDemands.length
    ? includedDemands.map((row) => row.requiredDate).sort()[0]
    : null;
  const tierProgress = bestCollective?.nextTier
    ? Math.min(1, totalDemand / bestCollective.nextTier.minQty)
    : bestCollective ? 1 : 0;

  return {
    product,
    waitDays: numberValue(waitDays),
    includedDemands,
    pendingDemands,
    totalDemand,
    pendingDemand,
    earliestRequiredDate,
    supplierResults,
    feasibleSuppliers,
    bestCollective,
    individualResults,
    individualCoveredQuantity,
    individualTotalCost,
    individualComplete,
    individualLandedPerKg,
    collectiveSavings,
    collectiveSavingsPct,
    tierProgress,
    kpis: {
      committedDemand: totalDemand,
      demandVisibility: totalDemand + pendingDemand > 0 ? totalDemand / (totalDemand + pendingDemand) : 0,
      feasibleAlternatives: feasibleSuppliers.length,
      collectiveLandedPerKg: bestCollective?.landedPerKg ?? null,
      logisticsPerKg: bestCollective?.logisticsPerKg ?? null,
      fillRate: bestCollective ? 1 : bestPartialFill,
      onTimeRate: bestCollective ? 1 : 0,
      procurementTripsAvoided: bestCollective ? Math.max(0, includedDemands.length - 1) : 0
    }
  };
}

export function buildTradeoff(state, product = state.settings.product, maxWait = 14) {
  return Array.from({ length: maxWait + 1 }, (_, waitDays) => {
    const result = analyseScenario(state, product, waitDays);
    return {
      waitDays,
      totalDemand: result.totalDemand,
      landedPerKg: result.bestCollective?.landedPerKg ?? null,
      feasibleAlternatives: result.feasibleSuppliers.length,
      slackDays: result.bestCollective?.slackDays ?? null,
      supplier: result.bestCollective?.supplier.name ?? null
    };
  });
}

export function recommendedWindow(points) {
  return points
    .filter((point) => point.landedPerKg != null && point.totalDemand > 0)
    .sort((a, b) => a.landedPerKg - b.landedPerKg || b.slackDays - a.slackDays || a.waitDays - b.waitDays)[0] ?? null;
}
