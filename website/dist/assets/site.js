(function () {
  const body = document.body;
  const progressBar = document.querySelector('.reading-progress span');
  const navToggle = document.querySelector('.nav-toggle');
  const closeNav = document.querySelector('[data-close-nav]');
  const themeToggle = document.querySelector('[data-theme-toggle]');
  const themeToggleIcon = document.querySelector('.theme-toggle-icon');

  function getInitialTheme() {
    try {
      const saved = localStorage.getItem('di-theme');
      if (saved === 'light' || saved === 'dark') return saved;
    } catch (error) {
      return document.documentElement.dataset.theme || 'light';
    }
    return document.documentElement.dataset.theme || 'light';
  }

  function applyTheme(theme, persist) {
    const normalized = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = normalized;
    if (themeToggle) {
      themeToggle.setAttribute('aria-pressed', String(normalized === 'dark'));
      themeToggle.setAttribute(
        'aria-label',
        normalized === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
      );
    }
    if (themeToggleIcon) themeToggleIcon.textContent = normalized === 'dark' ? '☾' : '☀';
    if (persist) {
      try {
        localStorage.setItem('di-theme', normalized);
      } catch (error) {
        // Ignore storage failures; the visual toggle still works for this page.
      }
    }
  }

  function updateProgress() {
    if (!progressBar) return;
    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const percent = max > 0 ? Math.min(100, Math.max(0, (scrollTop / max) * 100)) : 0;
    progressBar.style.width = percent + '%';
  }

  function setNav(open) {
    body.classList.toggle('nav-open', open);
    if (navToggle) navToggle.setAttribute('aria-expanded', String(open));
  }

  function isTypingTarget(target) {
    if (!target) return false;
    const tag = target.tagName;
    return target.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
  }

  function copySectionLink(heading, button) {
    const url = new URL(window.location.href);
    url.hash = heading.id;
    const text = url.toString();
    const fallback = function () {
      window.prompt('Copy section link', text);
    };
    if (!navigator.clipboard) {
      fallback();
      return;
    }
    navigator.clipboard.writeText(text).then(function () {
      const original = button.textContent;
      button.textContent = 'Copied';
      window.setTimeout(function () {
        button.textContent = original;
      }, 1200);
    }).catch(fallback);
  }

  function initializeSections(notebook) {
    if (!notebook || notebook.dataset.sectionsReady === 'true') return [];
    const headingSelector = 'h1, h2, h3, h4, h5, h6';
    const sections = [];
    const stack = [];
    const flow = [];
    const usedIds = new Set(Array.from(document.querySelectorAll('[id]'), (node) => node.id));
    let nextBodyId = 1;
    let cellOrdinal = 0;

    function bodyId() {
      while (usedIds.has('di-section-body-' + nextBodyId)) nextBodyId += 1;
      const id = 'di-section-body-' + nextBodyId;
      usedIds.add(id);
      nextBodyId += 1;
      return id;
    }

    function splitMarkdownCell(cell) {
      const inner = cell.querySelector(':scope > .inner_cell');
      const rendered = inner && inner.querySelector(':scope > .text_cell_render');
      if (!cell.classList.contains('text_cell') || !rendered) return [{ node: cell }];
      const nodes = Array.from(rendered.childNodes);
      const headings = nodes.filter((node) => node.nodeType === 1 && node.matches(headingSelector));
      if (!headings.length) return [{ node: cell }];
      const parts = [];
      let cursor = 0;
      let leadingWhitespace = [];

      function addPart(content, heading) {
        const meaningful = heading || content.some((node) => node.nodeType !== 3 || node.textContent.trim());
        if (!meaningful) {
          if (parts.length) parts[parts.length - 1].content.push(...content);
          else leadingWhitespace.push(...content);
          return;
        }
        parts.push({ content: leadingWhitespace.concat(content), heading });
        leadingWhitespace = [];
      }

      headings.forEach((heading) => {
        const end = nodes.indexOf(heading);
        const previous = heading.previousElementSibling;
        const start = previous && previous.matches('p.section-break') ? nodes.indexOf(previous) : end;
        addPart(nodes.slice(cursor, start), null);
        addPart(nodes.slice(start, end + 1), heading);
        cursor = end + 1;
      });
      addPart(nodes.slice(cursor), null);

      // Reuse the first wrapper and move its descendants, keeping every original
      // ID. Later fragments need shallow wrappers, never cloned content or IDs.
      const cellTemplate = cell.cloneNode(false);
      const innerTemplate = inner.cloneNode(false);
      const renderedTemplate = rendered.cloneNode(false);
      return parts.map((part, index) => {
        let fragment = cell;
        let fragmentRendered = rendered;
        if (index > 0) {
          fragment = cellTemplate.cloneNode(false);
          const fragmentInner = innerTemplate.cloneNode(false);
          fragmentRendered = renderedTemplate.cloneNode(false);
          [fragment, fragmentInner, fragmentRendered].forEach((node) => node.removeAttribute('id'));
          fragmentInner.appendChild(fragmentRendered);
          fragment.appendChild(fragmentInner);
        }
        fragmentRendered.replaceChildren(...part.content);
        return { node: fragment, heading: part.heading };
      });
    }

    Array.from(notebook.childNodes).forEach((node) => {
      if (node.nodeType !== 1 || !node.classList.contains('cell')) {
        flow.push({ node });
        return;
      }
      const ordinal = String(cellOrdinal++);
      splitMarkdownCell(node).forEach((part) => {
        part.node.dataset.sourceCell = ordinal;
        flow.push(part);
      });
    });

    const fragment = document.createDocumentFragment();
    flow.forEach((part) => {
      if (!part.heading) {
        (stack.length ? stack[stack.length - 1].body : fragment).appendChild(part.node);
        return;
      }
      const heading = part.heading;
      const level = Number(heading.tagName.slice(1));
      while (stack.length && stack[stack.length - 1].level >= level) stack.pop();
      const parent = stack.length ? stack[stack.length - 1].body : fragment;
      const section = document.createElement('section');
      section.className = 'notebook-section';
      section.dataset.level = String(level);
      const sectionBody = document.createElement('div');
      sectionBody.className = 'section-body';
      sectionBody.id = bodyId();
      const title = heading.textContent.replace(/¶/g, '').trim();
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'section-toggle';
      toggle.dataset.pagefindIgnore = 'all';
      toggle.setAttribute('aria-controls', sectionBody.id);
      const icon = document.createElement('span');
      icon.className = 'section-toggle-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = '▾';
      toggle.appendChild(icon);
      heading.prepend(toggle);
      const count = document.createElement('button');
      count.type = 'button';
      count.className = 'section-hidden-count';
      count.dataset.pagefindIgnore = 'all';
      count.setAttribute('aria-controls', sectionBody.id);
      const record = { element: section, heading, level, body: sectionBody, toggle, count, title };
      toggle.addEventListener('click', () => setSectionExpanded(record, record.body.hidden));
      count.addEventListener('click', () => setSectionExpanded(record, true));
      [toggle, count].forEach((control) => control.addEventListener('keydown', (event) => {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        event.stopPropagation();
        setSectionExpanded(record, event.key === 'ArrowRight');
      }));
      section.append(part.node, count, sectionBody);
      parent.appendChild(section);
      sections.push(record);
      stack.push(record);
    });
    notebook.replaceChildren(fragment);
    sections.forEach((section) => {
      const cells = new Set(Array.from(section.body.querySelectorAll('[data-source-cell]'), (node) => node.dataset.sourceCell));
      if (cells.size) {
        section.count.textContent = cells.size + (cells.size === 1 ? ' cell hidden' : ' cells hidden');
        section.count.setAttribute('aria-label', 'Expand ' + section.title + ': ' + section.count.textContent);
      } else {
        section.toggle.remove();
        section.count.remove();
        section.toggle = null;
        section.count = null;
      }
      setSectionExpanded(section, true, false);
    });
    notebook.dataset.sectionsReady = 'true';
    return sections;
  }

  function setSectionExpanded(section, expanded, refreshProgress = true) {
    if (!section.toggle || !section.count) {
      section.body.hidden = false;
      return;
    }
    const focused = document.activeElement;
    if ((!expanded && section.body.contains(focused)) || (expanded && section.count.contains(focused))) {
      section.toggle.focus();
    }
    section.body.hidden = !expanded;
    section.count.hidden = expanded;
    section.toggle.setAttribute('aria-expanded', String(expanded));
    section.count.setAttribute('aria-expanded', String(expanded));
    section.toggle.setAttribute('aria-label', (expanded ? 'Collapse ' : 'Expand ') + section.title);
    if (refreshProgress) updateProgress();
  }

  const notebook = document.querySelector('.notebook-content');
  const sections = initializeSections(notebook);
  const sectionRecords = new Map(sections.map((section) => [section.element, section]));

  function revealFragment(hash, scroll) {
    if (!notebook || !hash || hash === '#') return;
    const rawId = hash.slice(1);
    let id = rawId;
    try { id = decodeURIComponent(rawId); } catch (error) { /* Keep malformed fragments harmless. */ }
    const target = document.getElementById(id) || document.getElementById(rawId);
    if (!target || !notebook.contains(target)) return;
    let section = target.closest('.notebook-section');
    while (section) {
      const record = sectionRecords.get(section);
      if (record) setSectionExpanded(record, true, false);
      section = section.parentElement && section.parentElement.closest('.notebook-section');
    }
    updateProgress();
    if (scroll) window.requestAnimationFrame(() => target.scrollIntoView({ block: 'start', behavior: 'auto' }));
  }

  window.addEventListener('hashchange', () => revealFragment(window.location.hash, true));
  document.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
    const link = event.target.closest && event.target.closest('a[href]');
    if (!link) return;
    let destination;
    try { destination = new URL(link.href, window.location.href); } catch (error) { return; }
    if (destination.origin === window.location.origin && destination.pathname === window.location.pathname && destination.search === window.location.search) {
      // A link to the current hash emits no hashchange, so reveal it explicitly.
      revealFragment(destination.hash, true);
    }
  });
  window.addEventListener('pageshow', (event) => {
    if (!event.persisted) return;
    sections.forEach((section) => setSectionExpanded(section, true, false));
    revealFragment(window.location.hash, true);
    updateProgress();
  });

  if (navToggle) {
    navToggle.addEventListener('click', () => setNav(!body.classList.contains('nav-open')));
  }

  if (closeNav) {
    closeNav.addEventListener('click', () => setNav(false));
  }

  if (themeToggle) {
    applyTheme(getInitialTheme(), false);
    themeToggle.addEventListener('click', () => {
      const current = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
      applyTheme(current === 'dark' ? 'light' : 'dark', true);
    });
  }

  document.querySelectorAll('.chapter-link').forEach((link) => {
    link.addEventListener('click', () => setNav(false));
  });

  sections.forEach(({ heading, title }) => {
    if (!heading.matches('h2[id], h3[id], h4[id]')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'section-copy';
    button.textContent = 'Copy link';
    button.setAttribute('aria-label', 'Copy link to ' + title);
    button.addEventListener('click', () => copySectionLink(heading, button));
    heading.appendChild(button);
  });

  window.addEventListener('keydown', (event) => {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isTypingTarget(event.target)) {
      return;
    }
    if (event.key === 'ArrowLeft') {
      const prev = document.querySelector('[data-prev-chapter]');
      if (prev) window.location.href = prev.href;
    }
    if (event.key === 'ArrowRight') {
      const next = document.querySelector('[data-next-chapter]');
      if (next) window.location.href = next.href;
    }
  });

  window.addEventListener('scroll', updateProgress, { passive: true });
  window.addEventListener('resize', updateProgress);
  revealFragment(window.location.hash, true);
  updateProgress();
})();
