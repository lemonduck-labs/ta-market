// JavaScript port of tamarket/scenario.py: arithmetic on a council's own inputs, never a
// forecast. Must give exactly the outputs in scenario_cases.json (tests/test_spec_js.py checks
// it with node). Plain numbers in, plain numbers out; the rounding is stated in the cases file.

export const TYPES = ["bed_and_breakfast", "nightly_paid_self_contained", "hostels", "private_sector_leased", "la_ha_stock", "other"];
export const MAX_LEASE_YEARS = 30;
const NUMBERS = ["price_gap_per_household_year", "setup_cost_per_household", "void_cost_per_household_year", "lease_term_years"];
export const FIELDS = ["households_moved", "from_type", "to_type", ...NUMBERS, "households_on_from_type"];
const REQUIRED = FIELDS.slice(0, -1);
const isNum = (v) => typeof v === "number" && Number.isFinite(v);

export const wholePounds = (x) => Math.sign(x) * Math.floor(Math.abs(x) + 0.5) + 0;        // + 0 turns -0 into 0
export const twoPlaces = (x) => (Math.sign(x) * Math.floor(Math.abs(x) * 100 + 0.5)) / 100 + 0;

export function validateScenario(inputs) {
  if (inputs === null || typeof inputs !== "object" || Array.isArray(inputs)) return [{ field: "inputs", error: "must be an object" }];
  const errs = [], err = (field, error) => errs.push({ field, error });
  const oneOf = "must be one of: " + TYPES.join(", ");
  for (const f of REQUIRED) {
    if (!(f in inputs)) { err(f, "required"); continue; }
    const v = inputs[f];
    if (f === "households_moved") {
      if (!isNum(v)) err(f, "must be a number");
      else if (!Number.isInteger(v)) err(f, "must be a whole number");
      else if (v < 1) err(f, "must be at least 1");
    } else if (f === "from_type" || f === "to_type") {
      if (typeof v !== "string" || !TYPES.includes(v)) err(f, oneOf);
      else if (f === "to_type" && v === inputs.from_type) err(f, "must differ from from_type");
    } else if (!isNum(v)) err(f, "must be a number");
    else if ((f === "setup_cost_per_household" || f === "void_cost_per_household_year") && v < 0) err(f, "must be 0 or more");
    else if (f === "lease_term_years" && !(v > 0)) err(f, "must be more than 0");
    else if (f === "lease_term_years" && v > MAX_LEASE_YEARS) err(f, `must be ${MAX_LEASE_YEARS} or less`);
  }
  if ("households_on_from_type" in inputs) {
    const cap = inputs.households_on_from_type;
    if (!isNum(cap)) err("households_on_from_type", "must be a number");
    else if (cap < 0) err("households_on_from_type", "must be 0 or more");
    else if (isNum(inputs.households_moved) && inputs.households_moved > cap) err("households_moved", "must not be more than households_on_from_type");
  }
  for (const f of Object.keys(inputs).filter((k) => !FIELDS.includes(k)).sort()) err(f, "not an input");
  return errs;
}

export function evaluateScenario(inputs) {
  const errors = validateScenario(inputs);
  if (errors.length) return { errors };
  const h = inputs.households_moved, g = inputs.price_gap_per_household_year, s = inputs.setup_cost_per_household,
    v = inputs.void_cost_per_household_year, t = inputs.lease_term_years;
  const perHousehold = g - v;
  const payback = perHousehold > 0 ? twoPlaces(s / perHousehold) : null;
  const notes = [];
  if (g < 0) notes.push("negative_gap");
  if (payback === null) notes.push("never_recovered");
  else if (payback > t) notes.push("not_recovered_in_term");
  return {
    results: {
      gross_difference_per_year: wholePounds(h * g),
      void_cost_per_year: wholePounds(h * v),
      net_difference_per_year: wholePounds(h * (g - v)),
      set_up_cost: wholePounds(h * s),
      net_difference_over_term: wholePounds(t * h * (g - v) - h * s),
      payback_years: payback,
      recovered_within_term: payback !== null && payback <= t,
    },
    notes,
  };
}
