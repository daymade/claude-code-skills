/**
 * Classify whether an element itself is a wrapped-control candidate.
 *
 * Class-name inference is deliberately gated by an observable interaction signal:
 * a native control/link, an explicit interactive role, editable content, or a
 * nonnegative tabindex. Semantic navigation/menu containers are excluded even
 * when they are focusable for scrolling.
 *
 * Keep this function self-contained: visual_layout_audit.mjs serializes it into
 * the browser context, where module-scope constants do not exist.
 */
export function isWrappedControlElement({
  tagName = "",
  role = "",
  href = null,
  tabindex = null,
  className = "",
  contentEditable = "false",
} = {}) {
  const nativeControlTags = new Set(["BUTTON", "INPUT", "SELECT", "TEXTAREA", "SUMMARY"]);
  const interactiveRoles = new Set(["button", "tab", "menuitem", "switch", "checkbox", "radio", "link"]);
  const semanticContainerTags = new Set([
    "NAV", "MAIN", "HEADER", "FOOTER", "SECTION", "ARTICLE", "ASIDE", "UL", "OL", "DL",
  ]);
  const semanticContainerRoles = new Set([
    "navigation", "main", "banner", "contentinfo", "region", "list", "listitem", "group",
  ]);
  const semanticContainerClassParts = new Set([
    "nav", "navbar", "navigation", "menu", "toolbar", "breadcrumb", "breadcrumbs", "sidebar",
  ]);
  const controlClassParts = new Set([
    "btn", "button", "tab", "link", "chip", "toggle", "switch", "seg", "opt", "qbadge",
    "tier", "tag", "badge", "pill", "menuitem",
  ]);

  const classTokens = typeof className === "string"
    ? className.split(/\s+/).filter(Boolean)
    : [];
  const semanticParts = `${className || ""} ${role || ""}`
    .split(/\s+/)
    .filter(Boolean)
    .flatMap((token) => token.split(/[-_:]+/))
    .map((part) => part.toLowerCase())
    .filter(Boolean);
  const parsedTabIndex = (() => {
    if (tabindex === null || tabindex === undefined || tabindex === "") return null;
    const parsed = Number.parseInt(String(tabindex), 10);
    return Number.isInteger(parsed) ? parsed : null;
  })();

  const tag = String(tagName || "").toUpperCase();
  const normalizedRole = String(role || "").toLowerCase();
  const normalizedTokens = classTokens.map((token) => token.toLowerCase());
  const explicitMenuItem = normalizedTokens.includes("menu-item") || normalizedTokens.includes("menuitem");

  if (semanticContainerTags.has(tag) || semanticContainerRoles.has(normalizedRole)) return false;
  if (nativeControlTags.has(tag)) return true;
  if (interactiveRoles.has(normalizedRole)) return true;
  if (String(contentEditable).toLowerCase() === "true") return true;
  if (!explicitMenuItem && semanticParts.some((part) => semanticContainerClassParts.has(part))) return false;

  const hasHref = (tag === "A" || tag === "AREA") && Boolean(href);
  const focusable = hasHref || (parsedTabIndex ?? -1) >= 0;
  if (!focusable) return false;
  return explicitMenuItem
    || normalizedTokens.some((token) => (
      token === "segmented-control"
      || controlClassParts.has(token)
    ))
    || semanticParts.some((part) => controlClassParts.has(part));
}
