// Serializable browser observation: CSS boxes alone cannot prove glyph visibility.
// A finding is a partially painted vertical text fragment, not intentional ellipsis.
export function collectPaintedText({ limit = 1500 } = {}) {
  const issues = [], omissions = [];
  let examined = 0, truncated = false;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.nodeValue?.trim()) continue;
    const owner = node.parentElement;
    if (!owner || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(owner.tagName)) continue;
    const clips = [];
    let hidden = false, unsupported = false;
    for (let ancestor = owner; ancestor; ancestor = ancestor.parentElement) {
      const style = getComputedStyle(ancestor);
      if (style.display === 'none' || Number(style.opacity) === 0) hidden = true;
      // visibility can be explicitly restored by a descendant.
      if (ancestor === owner && style.visibility !== 'visible') hidden = true;
      if (style.clipPath !== 'none' || (style.clip && style.clip !== 'auto')) unsupported = true;
      if (['hidden', 'clip'].includes(style.overflowY)) clips.push(ancestor.getBoundingClientRect());
    }
    if (hidden) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    const rects = [...range.getClientRects()].filter(r => r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth);
    range.detach();
    if (!rects.length) continue;
    if (examined >= limit) { truncated = true; break; }
    examined++;
    const selector = owner.id ? `#${CSS.escape(owner.id)}` : owner.tagName.toLowerCase();
    if (unsupported) { omissions.push({ selector, reason: 'clip-path or legacy clip needs pixel inspection' }); continue; }
    // Scroll boundaries are intentional windows, not evidence of fixed-card clipping.
    const scrollOwner = [...ancestors(owner)].some(a => ['auto', 'scroll'].includes(getComputedStyle(a).overflowY) && a.scrollHeight > a.clientHeight);
    if (scrollOwner) { omissions.push({ selector, reason: 'scroll window needs journey inspection' }); continue; }
    for (const rect of rects) {
      let top = rect.top, bottom = rect.bottom;
      for (const clip of clips) { top = Math.max(top, clip.top); bottom = Math.min(bottom, clip.bottom); }
      const visible = Math.max(0, bottom - top);
      // Fully hidden lines are valid line-clamp/LOD candidates. Small font-metric
      // overhang is not half a line. Ratios use rendered CSS px, including transforms.
      if (visible > .75 && visible / rect.height < .8) {
        issues.push({ selector, type: 'partially-painted-text-line', severity: 'error',
          detail: `A text fragment paints ${visible.toFixed(2)} of ${rect.height.toFixed(2)} CSS px vertically. Inspect its crop; outer containment does not prove legibility.`,
          visibleHeight: visible, fragmentHeight: rect.height });
        break;
      }
    }
  }
  return { status: !examined ? 'unobserved' : truncated || omissions.length ? 'partial' : issues.length ? 'findings' : 'mechanical-pass', examined, truncated, omissions, issues };
  function* ancestors(element) { for (let a = element; a; a = a.parentElement) yield a; }
}
