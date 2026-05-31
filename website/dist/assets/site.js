(function () {
  const body = document.body;
  const progressBar = document.querySelector('.reading-progress span');
  const navToggle = document.querySelector('.nav-toggle');
  const closeNav = document.querySelector('[data-close-nav]');
  const themeToggle = document.querySelector('[data-theme-toggle]');
  const themeToggleLabel = document.querySelector('[data-theme-toggle-label]');
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
    if (themeToggle) themeToggle.setAttribute('aria-pressed', String(normalized === 'dark'));
    if (themeToggleLabel) themeToggleLabel.textContent = normalized === 'dark' ? 'Dark mode' : 'Light mode';
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

  document.querySelectorAll('.notebook-content h2[id], .notebook-content h3[id], .notebook-content h4[id]').forEach((heading) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'section-copy';
    button.textContent = 'Copy link';
    button.setAttribute('aria-label', 'Copy link to ' + heading.textContent.replace('¶', '').trim());
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
  updateProgress();
})();
