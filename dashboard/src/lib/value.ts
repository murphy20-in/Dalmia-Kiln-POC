// Illustrative value model for the Roadmap page. Pure: the client's inputs in, rupees out.
export interface ValueInputs {
  clinkerTpd: number; // clinker tonnes per day
  contributionPerT: number; // ₹ contribution margin per tonne
  runningDays: number; // kiln running days per year
  stoppageHours: number; // unplanned stoppage hours per year
  depositSharePct: number; // % of those hours that are deposit / ring / coating related
  convertiblePct: number; // % of those that early detection could turn into planned stops
  downtimeSavedPct: number; // % of downtime saved when a stop is planned instead of unplanned
  heatKcalPerKg: number; // specific heat consumption, kcal per kg clinker
  fuelPerMkcal: number; // ₹ per million kcal of fuel heat
  efficiencyGainPct: number; // % heat-consumption improvement from optimised operation
}

export interface ValueOutputs {
  hoursRecovered: number;
  productionProtected: number; // ₹/yr
  fuelSaving: number; // ₹/yr
  total: number; // ₹/yr
}

export function computeValue(i: ValueInputs): ValueOutputs {
  const hoursRecovered = i.stoppageHours * (i.depositSharePct / 100) * (i.convertiblePct / 100) * (i.downtimeSavedPct / 100);
  const productionProtected = hoursRecovered * (i.clinkerTpd / 24) * i.contributionPerT;
  const annualHeatMkcal = (i.clinkerTpd * i.runningDays * 1000 * i.heatKcalPerKg) / 1e6; // t → kg, kcal → Mkcal
  const fuelSaving = annualHeatMkcal * i.fuelPerMkcal * (i.efficiencyGainPct / 100);
  return { hoursRecovered, productionProtected, fuelSaving, total: productionProtected + fuelSaving };
}
