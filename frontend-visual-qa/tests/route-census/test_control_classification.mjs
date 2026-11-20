import assert from "node:assert/strict";
import test from "node:test";
import { isWrappedControlElement } from "../../scripts/control_classification.mjs";

test("wrapped-control classification rejects semantic navigation containers", () => {
  assert.equal(isWrappedControlElement({ tagName: "DIV", className: "nav" }), false);
  assert.equal(isWrappedControlElement({ tagName: "DIV", className: "topic-nav" }), false);
  assert.equal(isWrappedControlElement({ tagName: "NAV", tabindex: "0", className: "nav" }), false);
  assert.equal(isWrappedControlElement({ tagName: "DIV", role: "navigation", tabindex: "0" }), false);
  assert.equal(isWrappedControlElement({ tagName: "DIV", className: "button" }), false);
});

test("wrapped-control classification accepts observable controls", () => {
  assert.equal(isWrappedControlElement({ tagName: "BUTTON" }), true);
  assert.equal(isWrappedControlElement({ tagName: "DIV", className: "menu-item", tabindex: "0" }), true);
  assert.equal(isWrappedControlElement({ tagName: "A", href: "/next", className: "link" }), true);
  assert.equal(isWrappedControlElement({ tagName: "A", href: "/next", className: "" }), false);
  assert.equal(isWrappedControlElement({ tagName: "DIV", role: "button" }), true);
  assert.equal(isWrappedControlElement({ tagName: "DIV", className: "button", tabindex: "0" }), true);
  assert.equal(isWrappedControlElement({ tagName: "BUTTON", className: "nav" }), true);
});

test("wrapped-control classification does not infer a control from class alone", () => {
  assert.equal(isWrappedControlElement({ tagName: "DIV", className: "menu-item" }), false);
  assert.equal(isWrappedControlElement({ tagName: "SPAN", className: "tab" }), false);
  assert.equal(isWrappedControlElement({ tagName: "DIV", className: "nav", tabindex: "-1" }), false);
});
