// feishu_dom_capture.js — Injectable DOM capture script for Feishu/Lark documents.
// Inject via chrome-devtools evaluate_script or Browser Use javascript_tool.
// After injection, call window.__feishuCapture.run() to execute the full pipeline.
// Result: window.__feishuCapture.manifest (JSON) and window.__feishuCapture.markdown (string).

(() => {
  'use strict';

  // ── Noise patterns (Feishu UI chrome that leaks into innerText) ──
  const NOISE_EXACT = new Set([
    'Unable to print', 'Group card (Log in to view)', 'Group card',
    'Copy', 'Code block', '代码块',
    'Plain Text', 'Shell', 'JSON', 'Bash', 'TypeScript', 'JavaScript',
  ]);
  const NOISE_RE = /^Unable to print|^Group card|^Modified [A-Z][a-z]+ \d+/;

  function stripNoise(s) {
    if (typeof s !== 'string') return s;
    return s
      .replace(/Unable to print[^\s]*(\d+%)?/g, '')
      .replace(/Group card \(Log in to view\)/g, '')
      .replace(/Group card/g, '')
      .replace(/Modified [A-Z][a-z]+ \d+/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function isNoise(text) {
    if (!text) return true;
    if (NOISE_EXACT.has(text)) return true;
    if (NOISE_RE.test(text)) return true;
    return false;
  }

  // ── Inline markdown: convert DOM inline tags to markdown syntax ──
  function inlineMarkdown(node) {
    let result = '';
    for (const child of node.childNodes) {
      if (child.nodeType === 3) {
        result += child.textContent;
      } else if (child.nodeType === 1) {
        const tag = child.tagName.toLowerCase();
        if (tag === 'br') { result += '\n'; continue; }
        const inner = inlineMarkdown(child);
        if (tag === 'b' || tag === 'strong') result += `**${inner}**`;
        else if (tag === 'i' || tag === 'em') result += `*${inner}*`;
        else if (tag === 'u') result += `<u>${inner}</u>`;
        else if (tag === 'code' && !child.parentElement?.querySelector('pre')) result += `\`${inner}\``;
        else if (tag === 'a' && child.getAttribute('href')) result += `[${inner}](${child.getAttribute('href')})`;
        else result += inner;
      }
    }
    return result.replace(/[​﻿]/g, '');
  }

  // ── Table / bullet helpers ──
  function isInsideTable(el) {
    return !!el.parentElement?.closest('.docx-table-block, .table-block');
  }

  function extractBullets(el, depth = 0) {
    const results = [];
    const listContent = el.querySelector(':scope > .list-wrapper, :scope > .list-content, :scope > .ace-line');
    let textNode = listContent;
    if (!textNode) {
      const aceLines = el.querySelectorAll('.ace-line');
      for (const a of aceLines) {
        if (a.closest('.docx-bullet-block, .docx-list-block') === el) { textNode = a; break; }
      }
    }
    if (textNode) {
      const text = inlineMarkdown(textNode).replace(/^[•◦·]\s*/, '').trim();
      if (text) results.push({ depth, text });
    }
    const allNested = el.querySelectorAll('.docx-bullet-block, .docx-list-block');
    const directChildren = Array.from(allNested).filter(b => {
      const parent = b.parentElement?.closest('.docx-bullet-block, .docx-list-block');
      return b !== el && parent === el;
    });
    directChildren.forEach(child => results.push(...extractBullets(child, depth + 1)));
    return results;
  }

  function extractTable(tableBlock) {
    const rows = [];
    tableBlock.querySelectorAll('tr, .docx-table-tr').forEach(rowEl => {
      const cells = Array.from(rowEl.querySelectorAll('td, .table-cell-block, .docx-table_cell-block, [class*="table-cell"]'))
        .map(c => (c.innerText || '').replace(/[​﻿\n]/g, ' ').trim());
      if (cells.length > 0) rows.push(cells);
    });
    return rows;
  }

  // ── Core capture ──
  const capturedBlocks = new Map();

  function captureVisibleBlocks() {
    const blocks = document.querySelectorAll('.block');
    let newCount = 0;
    for (const block of blocks) {
      const bid = block.getAttribute('data-block-id');
      if (!bid || capturedBlocks.has(bid)) continue;
      if (isInsideTable(block) && !block.className.includes('docx-table-block')) continue;
      const parentBullet = block.parentElement?.closest('.docx-bullet-block, .docx-list-block');
      if ((block.className.includes('docx-bullet-block') || block.className.includes('docx-list-block')) && parentBullet) continue;
      // Skip quote container child render units (they duplicate the container's content)
      if (block.className.includes('quote-container-render-unit')) continue;

      const cls = block.className || '';
      const text = (block.innerText || '').replace(/[​﻿]/g, '').trim();
      let type = 'text', payload = null;

      if (cls.includes('docx-heading1-block')) { type = 'h1'; payload = text; }
      else if (cls.includes('docx-heading2-block')) { type = 'h2'; payload = text; }
      else if (cls.includes('docx-heading3-block')) { type = 'h3'; payload = text; }
      else if (cls.includes('docx-heading4-block')) { type = 'h4'; payload = text; }
      else if (cls.includes('docx-table-block')) { type = 'table'; payload = extractTable(block); }
      else if (cls.includes('docx-bullet-block') || cls.includes('docx-list-block')) { type = 'bullets'; payload = extractBullets(block, 0); }
      else if (cls.includes('docx-code-block')) {
        type = 'code';
        const langEl = block.querySelector('[class*="lang"], [class*="language"]');
        payload = { lang: langEl?.innerText?.trim() || '', text };
      } else if (cls.includes('docx-quote_container-block') || cls.includes('docx-quote-block') || cls.includes('docx-callout-block')) {
        type = 'quote'; payload = inlineMarkdown(block).trim();
      } else if (cls.includes('docx-image-block') || cls.includes('docx-image')) {
        type = 'image';
        const img = block.querySelector('img');
        payload = { src: img?.src || '', alt: img?.alt || '' };
      } else if (cls.includes('docx-divider-block')) {
        type = 'divider'; payload = '---';
      } else {
        payload = inlineMarkdown(block).trim();
        if (!payload) continue;
      }

      capturedBlocks.set(bid, { id: bid, idNum: parseInt(bid, 10), type, payload });
      newCount++;
    }
    return { newCount, total: capturedBlocks.size };
  }

  // ── TOC-driven capture loop ──
  async function tocDrivenCapture() {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const tocItems = Array.from(document.querySelectorAll('.catalogue__list-item'));
    const scrollContainer = document.querySelector('.bear-web-x-container, .page-main, .content-scroller, [class*="docx-width"]');

    for (const item of tocItems) {
      const clickTarget = item.querySelector('a, button, [role="button"]') || item;
      clickTarget.click();
      await sleep(800);
      captureVisibleBlocks();
      if (scrollContainer) {
        for (let s = 0; s < 3; s++) {
          scrollContainer.scrollBy(0, scrollContainer.clientHeight * 0.6);
          await sleep(400);
          captureVisibleBlocks();
        }
      }
    }
    // Final sweep
    if (scrollContainer) {
      for (let s = 0; s < 8; s++) {
        scrollContainer.scrollBy(0, scrollContainer.clientHeight * 0.8);
        await sleep(500);
        captureVisibleBlocks();
      }
    }
  }

  // ── Image download via fetch + session cookie ──
  async function downloadImages(docName = 'doc') {
    const imageBlocks = Array.from(capturedBlocks.values()).filter(b => b.type === 'image' && b.payload?.src);
    const downloaded = [];
    for (let i = 0; i < imageBlocks.length; i++) {
      const src = imageBlocks[i].payload.src;
      if (src.startsWith('blob:') || src.startsWith('data:')) continue;
      try {
        const resp = await fetch(src, { credentials: 'include' });
        if (!resp.ok) { downloaded.push({ i, src: src.substring(0, 80), ok: false }); continue; }
        const contentType = resp.headers.get('content-type') || 'image/png';
        const blob = await resp.blob();
        const reader = new FileReader();
        const dataUrl = await new Promise(resolve => {
          reader.onloadend = () => resolve(reader.result);
          reader.readAsDataURL(blob);
        });
        const ext = contentType.includes('gif') ? 'gif' : contentType.includes('jpeg') ? 'jpg' : 'png';
        // Per-document naming: never share generic img-0.png across documents
        const safeName = docName.replace(/[^a-zA-Z0-9一-龥_-]/g, '').substring(0, 40);
        imageBlocks[i].payload.localName = `${safeName}-${i}.${ext}`;
        imageBlocks[i].payload.dataUrl = dataUrl;
        imageBlocks[i].payload.size = blob.size;
        downloaded.push({ i, ext, size: blob.size, ok: true });
      } catch (e) {
        downloaded.push({ i, error: e.message, ok: false });
      }
    }
    return downloaded;
  }

  // ── Clean + deduplicate + sort ──
  function cleanAndSort() {
    const all = Array.from(capturedBlocks.values());
    all.sort((a, b) => a.idNum - b.idNum);

    // Build covered-text set for dedup
    const coveredTexts = new Set();
    for (const b of all) {
      if (b.type === 'table' && Array.isArray(b.payload))
        b.payload.forEach(row => row.forEach(cell => { if (cell.trim()) coveredTexts.add(cell.trim()); }));
      if (b.type === 'bullets' && Array.isArray(b.payload))
        b.payload.forEach(item => { if (item.text?.trim()) coveredTexts.add(item.text.trim()); });
      if (b.type === 'quote' && typeof b.payload === 'string' && b.payload.trim())
        coveredTexts.add(stripNoise(b.payload));
    }

    const seenText = new Set();
    return all.filter(b => {
      // Drop aggregation artifacts (> 350 chars text blocks are page-main innerText lumps)
      if (b.type === 'text' && typeof b.payload === 'string' && b.payload.length > 350) return false;
      // Drop empty bullets
      if (b.type === 'bullets' && (!Array.isArray(b.payload) || b.payload.length === 0 || b.payload.every(it => !it.text?.trim()))) return false;

      const text = typeof b.payload === 'string' ? stripNoise(b.payload) : '';
      if (b.type === 'text' && (!text || text.length < 3)) return false;
      if (b.type === 'text' && isNoise(text)) return false;
      // Dedup: text covered by quote/table/bullets
      if (b.type === 'text' && coveredTexts.has(text)) return false;
      // Dedup by exact content
      let key = null;
      if (b.type === 'text' || b.type === 'quote') key = b.type + ':' + text;
      else if (b.type === 'bullets' && Array.isArray(b.payload)) key = 'bullets:' + b.payload.map(it => stripNoise(it.text)).join('|');
      else if (b.type === 'image' && b.payload?.src) key = 'image:' + b.payload.src;
      else if (b.type === 'code' && b.payload?.text) key = 'code:' + b.payload.text.trim();
      else if (b.type.startsWith('h')) key = b.type + ':' + b.payload;
      if (key && seenText.has(key)) return false;
      if (key) seenText.add(key);

      // Clean code-block noise
      if (b.type === 'code' && b.payload?.text) {
        let t = b.payload.text;
        t = t.split('\n').filter(l => !['Copy', 'Code block', '代码块'].includes(l.trim())).join('\n');
        t = t.replace(/^(plaintext|shell|bash|json|typescript|javascript|python)\s*\n/i, m => {
          if (!b.payload.lang) b.payload.lang = m.trim().toLowerCase();
          return '';
        });
        b.payload.text = t.trim();
      }
      return true;
    });
  }

  // ── Build manifest JSON ──
  function buildManifest(blocks, meta = {}) {
    const sections = [];
    let currentSection = null;
    const levelMap = { h1: 2, h2: 3, h3: 4, h4: 5 };

    for (const b of blocks) {
      if (levelMap[b.type]) {
        currentSection = { heading_level: levelMap[b.type], heading: (b.payload || '').trim(), body: [] };
        sections.push(currentSection);
        continue;
      }
      if (!currentSection) continue;

      const text = typeof b.payload === 'string' ? stripNoise(b.payload) : '';
      if (b.type === 'text' && text) currentSection.body.push(text);
      else if (b.type === 'quote' && text) currentSection.body.push('> ' + text);
      else if (b.type === 'bullets' && Array.isArray(b.payload)) {
        for (const item of b.payload) {
          const bt = stripNoise(item.text || '').replace(/^[•◦·]\s*/, '');
          if (bt) currentSection.body.push('  '.repeat(item.depth) + '- ' + bt);
        }
      } else if (b.type === 'code' && b.payload?.text) {
        const lang = (b.payload.lang || '').toLowerCase().replace(/[^a-z0-9]/g, '');
        currentSection.body.push('```' + lang + '\n' + b.payload.text + '\n```');
      } else if (b.type === 'table' && Array.isArray(b.payload) && b.payload.length > 0) {
        const rows = b.payload;
        currentSection.body.push('| ' + rows[0].join(' | ') + ' |');
        currentSection.body.push('|' + rows[0].map(() => '---').join('|') + '|');
        for (let i = 1; i < rows.length; i++) currentSection.body.push('| ' + rows[i].join(' | ') + ' |');
      } else if (b.type === 'image' && b.payload?.localName) {
        currentSection.body.push(`![${b.payload.alt || ''}](assets/${b.payload.localName})`);
      } else if (b.type === 'image' && b.payload?.src && !b.payload.src.startsWith('blob:')) {
        currentSection.body.push(`![${b.payload.alt || ''}](${b.payload.src})`);
      } else if (b.type === 'divider') {
        currentSection.body.push('---');
      }
    }

    return {
      title: meta.title || document.title.replace(/ - Feishu Docs$/, '').trim(),
      source: meta.source || location.href,
      author: meta.author || [],
      published: meta.published || '',
      created: new Date().toISOString().substring(0, 10),
      description: meta.description || '',
      tags: meta.tags || [],
      sections,
    };
  }

  // ── Public API ──
  window.__feishuCapture = {
    capturedBlocks,
    captureVisibleBlocks,
    tocDrivenCapture,
    downloadImages,
    cleanAndSort,
    buildManifest,
    stripNoise,
    inlineMarkdown,

    async run(meta = {}) {
      capturedBlocks.clear();
      captureVisibleBlocks();
      await tocDrivenCapture();
      const docName = meta.docName || meta.title || document.title.replace(/ - Feishu Docs$/, '').trim() || 'doc';
      const imgResults = await downloadImages(docName);
      const cleaned = cleanAndSort();
      const manifest = buildManifest(cleaned, meta);
      this.manifest = manifest;
      this.cleanedBlocks = cleaned;
      this.imageResults = imgResults;
      return {
        totalCaptured: capturedBlocks.size,
        afterClean: cleaned.length,
        sections: manifest.sections.length,
        images: imgResults.length,
        imagesOk: imgResults.filter(r => r.ok).length,
      };
    },
  };
})();
