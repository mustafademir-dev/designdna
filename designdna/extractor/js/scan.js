(opts) => {
  // DesignDNA tek-geçişli sayfa tarayıcısı. page.evaluate(scan.js, opts) ile çalışır.
  // opts: { viewport: {width, height}, properties: [...STYLE_PROPERTIES] }
  const r2 = (x) => Math.round(x * 100) / 100;
  const vw = opts.viewport.width;
  const vh = opts.viewport.height;
  const props = opts.properties;

  try { window.scrollTo(0, 0); } catch (e) { /* yoksay */ }
  for (const old of document.querySelectorAll('[data-designdna-idx]')) {
    old.removeAttribute('data-designdna-idx');
  }

  const classString = (el) => {
    const c = el.getAttribute('class');
    return c ? c : '';
  };
  const describe = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    const cls = classString(el).split(/\s+/).filter(Boolean);
    if (cls.length) s += '.' + cls.join('.');
    return s;
  };

  // ------------------------------------------------------------ overlay temizliği
  const removed = [];
  const hiddenEls = [];
  try {
    const protectedSet = new Set();
    for (const h of document.querySelectorAll('header, nav, [role="banner"]')) {
      protectedSet.add(h);
      for (let a = h.parentElement; a; a = a.parentElement) protectedSet.add(a);
      for (const d of h.querySelectorAll('*')) protectedSet.add(d);
    }
    const KEY = /cookie|consent|gdpr/;
    const body = document.body;
    if (body) {
      for (const el of body.querySelectorAll('*')) {
        if (protectedSet.has(el)) continue;
        if (hiddenEls.some((h) => h.contains(el))) continue;
        const cs = getComputedStyle(el);
        if (cs.display === 'none') continue;
        let hide = false;
        const meta = (el.id || '') + ' ' + classString(el) + ' ' + (el.getAttribute('aria-label') || '');
        if (KEY.test(meta.toLowerCase())) {
          hide = true;
        } else if (
          ['fixed', 'sticky', 'absolute'].includes(cs.position) ||
          el.getAttribute('role') === 'dialog' ||
          el.getAttribute('aria-modal') === 'true'
        ) {
          const txt = el.textContent || '';
          if (txt.length < 400 && KEY.test(txt.toLowerCase())) hide = true;
        }
        if (!hide && cs.position === 'fixed') {
          const rect = el.getBoundingClientRect();
          const ix = Math.max(0, Math.min(rect.right, vw) - Math.max(rect.left, 0));
          const iy = Math.max(0, Math.min(rect.bottom, vh) - Math.max(rect.top, 0));
          if (ix * iy > 0.3 * vw * vh) hide = true;
        }
        if (hide) {
          hiddenEls.push(el);
          removed.push(describe(el));
        }
      }
    }
    for (const el of hiddenEls) el.style.setProperty('display', 'none', 'important');
  } catch (e) { /* overlay temizliği başarısız olursa taramaya devam et */ }

  // ------------------------------------------------------------ element gezintisi
  const SKIP = new Set(['head', 'script', 'style', 'link', 'meta', 'title', 'noscript', 'template', 'base']);
  const elements = [];
  const gradients = [];

  const splitTop = (s) => {
    const parts = [];
    let depth = 0;
    let cur = '';
    for (const ch of s) {
      if (ch === '(') depth++;
      if (ch === ')') depth--;
      if (ch === ',' && depth === 0) { parts.push(cur.trim()); cur = ''; } else cur += ch;
    }
    if (cur.trim()) parts.push(cur.trim());
    return parts;
  };
  const COLOR_RE = /(?:rgba?|hsla?|oklch|oklab|lab|lch|color)\([^)]*\)|#[0-9a-fA-F]{3,8}\b/g;

  const walk = (el, depth, parentIdx) => {
    const tag = el.tagName.toLowerCase();
    if (SKIP.has(tag)) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none') return;
    let myIdx = parentIdx;
    const rect = el.getBoundingClientRect();
    const visible =
      cs.visibility !== 'hidden' && !(parseFloat(cs.opacity) <= 0) && rect.width >= 2 && rect.height >= 2;
    if (visible) {
      const idx = elements.length;
      const x = r2(rect.left + window.scrollX);
      const y = r2(rect.top + window.scrollY);
      const w = r2(rect.width);
      const h = r2(rect.height);
      let textLength = 0;
      for (const n of el.childNodes) {
        if (n.nodeType === 3) textLength += n.textContent.trim().length;
      }
      const styles = {};
      for (const p of props) styles[p] = cs.getPropertyValue(p);
      const inVp = x < vw && x + w > 0 && y < vh && y + h > 0;
      const role = el.getAttribute('role');
      elements.push({
        idx,
        parent_idx: parentIdx,
        depth,
        tag,
        id: el.id || '',
        classes: Array.from(el.classList || []),
        role: role ? role.toLowerCase() : null,
        input_type: tag === 'input' ? String(el.type || 'text').toLowerCase() : null,
        href: tag === 'a' && el.hasAttribute('href'),
        text_length: textLength,
        bbox: { x, y, width: w, height: h },
        area: r2(w * h),
        in_viewport: inVp,
        styles,
      });
      el.setAttribute('data-designdna-idx', String(idx));
      myIdx = idx;

      const bgi = styles['background-image'];
      if (bgi && bgi.indexOf('gradient(') !== -1) {
        for (const part of splitTop(bgi)) {
          const m = /^(?:repeating-)?(linear|radial)-gradient\(/.exec(part);
          if (m) {
            gradients.push({
              kind: m[1],
              value: part,
              element_idx: idx,
              area: r2(w * h),
              colors: part.match(COLOR_RE) || [],
            });
          }
        }
      }
    }
    if (tag === 'svg') return;
    for (const c of el.children) walk(c, depth + 1, myIdx);
  };
  walk(document.documentElement, 0, null);

  // ------------------------------------------------------------ stylesheet okuma
  const customProps = [];
  const fontFaces = [];
  const mediaQueries = [];
  const seenMedia = new Set();
  const fontLinks = new Set();
  let hasScheme = false;
  const FONT_HOSTS = ['fonts.googleapis.com', 'fonts.bunny.net', 'use.typekit.net', 'fonts.gstatic.com'];
  const isFontHost = (u) => FONT_HOSTS.some((h) => (u || '').indexOf(h) !== -1);
  const ROOT_SEL = /^(:root|html|body)(?![\w-])/;

  const toPx = (v, unit) => (unit === 'px' ? v : v * 16);
  const parseMedia = (cond) => {
    const q = { condition: cond, min_width: null, max_width: null, prefers_color_scheme: null };
    let m = /\(\s*min-width\s*:\s*([\d.]+)(px|em|rem)\s*\)/.exec(cond);
    if (m) q.min_width = toPx(parseFloat(m[1]), m[2]);
    m = /\(\s*max-width\s*:\s*([\d.]+)(px|em|rem)\s*\)/.exec(cond);
    if (m) q.max_width = toPx(parseFloat(m[1]), m[2]);
    m = /\(\s*width\s*>=\s*([\d.]+)(px|em|rem)\s*\)/.exec(cond);
    if (m && q.min_width === null) q.min_width = toPx(parseFloat(m[1]), m[2]);
    m = /\(\s*width\s*<=\s*([\d.]+)(px|em|rem)\s*\)/.exec(cond);
    if (m && q.max_width === null) q.max_width = toPx(parseFloat(m[1]), m[2]);
    m = /prefers-color-scheme\s*:\s*(dark|light)/.exec(cond);
    if (m) q.prefers_color_scheme = m[1];
    return q;
  };

  const readRules = (rules, media) => {
    for (const rule of rules) {
      try {
        const t = rule.constructor && rule.constructor.name;
        if (rule.type === 1 || t === 'CSSStyleRule') {
          const sel = rule.selectorText || '';
          const rootish = sel.split(',').some((p) => {
            const s = p.trim();
            return ROOT_SEL.test(s) || s.indexOf('[data-theme') !== -1;
          });
          if (rootish) {
            for (let i = 0; i < rule.style.length; i++) {
              const name = rule.style[i];
              if (name.startsWith('--')) {
                customProps.push({
                  name,
                  value: rule.style.getPropertyValue(name).trim(),
                  selector: sel,
                  media: media,
                });
              }
            }
          }
          if (rule.cssRules && rule.cssRules.length) readRules(rule.cssRules, media);
        } else if (rule.type === 4 || t === 'CSSMediaRule') {
          const cond = (rule.media && rule.media.mediaText) || rule.conditionText || '';
          if (/prefers-color-scheme/.test(cond)) hasScheme = true;
          if (!seenMedia.has(cond)) {
            seenMedia.add(cond);
            mediaQueries.push(parseMedia(cond));
          }
          readRules(rule.cssRules, cond);
        } else if (rule.type === 5 || t === 'CSSFontFaceRule') {
          const st = rule.style;
          const family = st.getPropertyValue('font-family').trim().replace(/^["']|["']$/g, '');
          const src = [];
          const re = /url\(\s*["']?([^"')]+?)["']?\s*\)/g;
          let mm;
          const srcText = st.getPropertyValue('src');
          while ((mm = re.exec(srcText)) !== null) src.push(mm[1]);
          fontFaces.push({
            family,
            src,
            weight: st.getPropertyValue('font-weight').trim() || null,
            style: st.getPropertyValue('font-style').trim() || null,
          });
        } else if (rule.type === 3 || t === 'CSSImportRule') {
          if (isFontHost(rule.href)) fontLinks.add(rule.href);
        } else if (rule.cssRules && rule.cssRules.length) {
          // @supports, @layer vb.
          readRules(rule.cssRules, media);
        }
      } catch (e) { /* tek bir kural okunamazsa devam et */ }
    }
  };
  for (const sheet of document.styleSheets) {
    try {
      readRules(sheet.cssRules, null);
    } catch (e) { /* cross-origin stylesheet */ }
  }
  for (const l of document.querySelectorAll('link[rel~="stylesheet"][href]')) {
    const href = l.getAttribute('href') || '';
    if (isFontHost(href)) fontLinks.add(l.href || href);
  }

  const root = document.documentElement;
  const pageHeight = Math.max(root.scrollHeight, document.body ? document.body.scrollHeight : 0);
  return {
    elements,
    custom_properties: customProps,
    font_faces: fontFaces,
    font_links: Array.from(fontLinks).sort(),
    media_queries: mediaQueries,
    gradients,
    has_color_scheme_query: hasScheme,
    removed_overlays: removed,
    page_height: r2(pageHeight),
  };
}
