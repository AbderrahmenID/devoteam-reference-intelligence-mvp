import test from "node:test";
import assert from "node:assert/strict";

import { clearBasket, hydrateBasket, moveReference, removeReference, selectReference, toggleReference } from "../lib/selectionBasket.mjs";

const id = (character) => character.repeat(64);
const reference = (character, title) => ({
  reference_id: id(character),
  display_title: `Display ${title}`,
  mission_name: title,
  project_title: title,
  client: `Client ${character}`,
  country: "Tunisie",
  period: "2021–2023",
});

test("select and deselect a reference without duplicates", () => {
  const selected = selectReference([], reference("a", "Mission A"));
  assert.equal(selected.length, 1);
  assert.equal(selected[0].display_title, "Display Mission A");
  assert.equal(selected[0].mission_title, "Mission A");
  assert.deepEqual(selectReference(selected, reference("a", "Mission A")), selected);
  assert.deepEqual(toggleReference(selected, reference("a", "Mission A")), []);
});

test("selection order survives pagination and session hydration", () => {
  let basket = selectReference([], reference("a", "Page one"));
  basket = selectReference(basket, reference("b", "Page two"));
  basket = selectReference(basket, reference("c", "Page three"));
  const hydrated = hydrateBasket(JSON.stringify(basket));
  assert.deepEqual(hydrated.map((item) => item.reference_id), [id("a"), id("b"), id("c")]);
});

test("remove and clear basket are explicit", () => {
  const basket = [reference("a", "A"), reference("b", "B")].reduce(selectReference, []);
  assert.deepEqual(removeReference(basket, id("a")).map((item) => item.reference_id), [id("b")]);
  assert.deepEqual(clearBasket(), []);
});

test("selected references can be reordered without changing membership", () => {
  const basket = [reference("a", "A"), reference("b", "B"), reference("c", "C")].reduce(selectReference, []);
  const moved = moveReference(basket, id("b"), -1);
  assert.deepEqual(moved.map((item) => item.reference_id), [id("b"), id("a"), id("c")]);
  assert.deepEqual(moveReference(moved, id("b"), -1), moved);
});

test("invalid or duplicate session values are discarded", () => {
  const valid = selectReference([], reference("a", "A"))[0];
  assert.equal(hydrateBasket(JSON.stringify([valid, valid, { reference_id: "../escape" }])).length, 1);
});
