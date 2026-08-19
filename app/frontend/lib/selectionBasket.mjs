export const SESSION_KEY = "devoteam-reference-pack-selection-v1";

export function selectReference(basket, reference) {
  if (basket.some((item) => item.reference_id === reference.reference_id)) return basket;
  return [...basket, {
    reference_id: reference.reference_id,
    display_title: reference.display_title || reference.mission_name || reference.project_title,
    mission_title: reference.mission_name || reference.project_title,
    client: reference.client || "",
    country: reference.country || "",
    period: reference.period || "",
    sector: reference.sector || "",
    offering: Array.isArray(reference.offerings) ? reference.offerings.join(", ") : String(reference.offering || ""),
  }];
}

export function removeReference(basket, referenceId) {
  return basket.filter((item) => item.reference_id !== referenceId);
}

export function moveReference(basket, referenceId, direction) {
  const index = basket.findIndex((item) => item.reference_id === referenceId);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= basket.length) return basket;
  const reordered = [...basket];
  [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
  return reordered;
}

export function clearBasket() {
  return [];
}

export function toggleReference(basket, reference) {
  return basket.some((item) => item.reference_id === reference.reference_id)
    ? removeReference(basket, reference.reference_id)
    : selectReference(basket, reference);
}

export function hydrateBasket(raw) {
  if (!raw) return [];
  try {
    const values = JSON.parse(raw);
    if (!Array.isArray(values)) return [];
    return values.reduce((basket, item) => {
      if (!item || typeof item.reference_id !== "string" || !/^[0-9a-f]{64}$/.test(item.reference_id)) return basket;
      return basket.some((current) => current.reference_id === item.reference_id) ? basket : [...basket, {
        reference_id: item.reference_id,
        display_title: String(item.display_title || item.mission_title || ""),
        mission_title: String(item.mission_title || item.display_title || ""),
        client: String(item.client || ""),
        country: String(item.country || ""),
        period: String(item.period || ""),
        sector: String(item.sector || ""),
        offering: String(item.offering || ""),
      }];
    }, []);
  } catch {
    return [];
  }
}
