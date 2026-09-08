// Serialize this function through the existing browser harness. It observes
// rendered text; it does not decide whether the text deserves to be present.
export function collectAttentionInventory({ limit = 2000 } = {}) {
  const selector = (el) => {
    if (el === document.documentElement) return "html";
    const parts = [];
    for (let node = el; node && node !== document.body; node = node.parentElement) {
      const siblings = [...node.parentElement.children].filter((other) => other.tagName === node.tagName);
      parts.unshift(`${node.tagName.toLowerCase()}:nth-of-type(${siblings.indexOf(node) + 1})`);
    }
    return `body${parts.length ? " > " + parts.join(" > ") : ""}`;
  };
  const rect = (r) => ({ x: r.x, y: r.y, width: r.width, height: r.height });
  const visible = (el, box) => {
    if (box.width <= 1 || box.height <= 1 || box.bottom <= 0 || box.right <= 0 || box.top >= innerHeight || box.left >= innerWidth) return false;
    for (let node = el; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.display === "none" || ["hidden", "collapse"].includes(style.visibility) || Number(style.opacity) === 0) return false;
      const parent = node.getBoundingClientRect();
      // Include partly visible scroll-edge text; exclude text entirely outside
      // its clipping ancestor, including the common 1px accessible-only label.
      const clipsX = ["hidden", "clip", "scroll", "auto"].includes(style.overflowX);
      const clipsY = ["hidden", "clip", "scroll", "auto"].includes(style.overflowY);
      if ((style.clipPath !== "none" || style.clip !== "auto") && (parent.width <= 1 || parent.height <= 1)) return false;
      if (clipsX && (box.right <= parent.left || box.left >= parent.right)) return false;
      if (clipsY && (box.bottom <= parent.top || box.top >= parent.bottom)) return false;
    }
    return true;
  };
  const items = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let eligible = 0;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.nodeValue.replace(/\s+/g, " ").trim();
    const el = node.parentElement;
    if (!text || !el || el.closest("script,style,template,noscript,textarea,option")) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    const box = range.getBoundingClientRect();
    if (!visible(el, box)) continue;
    eligible += 1;
    if (items.length >= limit) continue;
    const container = el.closest("button,a,label,[role=tab],header,footer,nav,p,th,td") || (el === document.body ? el : el.parentElement) || el;
    const style = getComputedStyle(el);
    items.push({ id: `text-${items.length + 1}`, text, selector: selector(el), containerSelector: selector(container), tag: el.tagName.toLowerCase(), role: el.getAttribute("role"), rect: rect(box), lineBoxes: [...range.getClientRects()].map(rect), fontSize: parseFloat(style.fontSize), position: getComputedStyle(container).position });
  }
  const byText = new Map();
  for (const item of items) {
    if ([...item.text].length < 2) continue;
    const group = byText.get(item.text) || [];
    group.push(item.id);
    byText.set(item.text, group);
  }
  const repeats = [...byText.values()].filter((ids) => ids.length > 1);
  const echoes = [];
  const containers = new Map();
  for (const item of items) {
    const group = containers.get(item.containerSelector) || [];
    group.push(item);
    containers.set(item.containerSelector, group);
  }
  for (const group of containers.values()) {
    for (let a = 0; a < group.length; a += 1) for (let b = a + 1; b < group.length; b += 1) {
      const first = group[a], second = group[b];
      if (first.text !== second.text && Math.min([...first.text].length, [...second.text].length) >= 2 && (first.text.includes(second.text) || second.text.includes(first.text))) echoes.push([first.id, second.id]);
    }
  }
  const opaqueSurfaces = [...document.querySelectorAll("body *")].filter((el) => (el.tagName === "IFRAME" || el.shadowRoot !== null) && visible(el, el.getBoundingClientRect())).map((el) => selector(el));
  return { scope: "first_viewport_light_dom_text", inputValuesIncluded: false, pseudoContentIncluded: false, occlusionEvaluated: false, opaqueSurfaces, truncated: eligible > items.length, eligibleTextNodes: eligible, items, repeats, labelEchoes: echoes, necessityVerdict: "not_evaluated" };
}
