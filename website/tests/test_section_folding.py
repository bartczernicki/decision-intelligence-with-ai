"""Browser regressions for notebook sections using locally available tooling.

No packages are installed by these tests. Set PLAYWRIGHT_MODULE to an existing
Playwright index.mjs and CHROME_EXECUTABLE when automatic discovery is unsuitable.
"""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "src" / "build_website.py"
SPEC = importlib.util.spec_from_file_location("folding_build_website", SOURCE)
build_website = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_website)


def markdown_cell(content):
    return (
        '<div class="cell text_cell rendered"><div class="prompt input_prompt"></div>'
        '<div class="inner_cell"><div class="text_cell_render rendered_html">'
        + content
        + "</div></div></div>"
    )


def heading(level, anchor, title):
    return (
        '<p class="section-break" aria-hidden="true" data-pagefind-ignore="all">• · •</p>'
        f'<h{level} id="{anchor}">{title}'
        f'<a class="anchor-link" href="#{anchor}">¶</a></h{level}>'
    )


FIXTURE = "".join([
    markdown_cell(
        heading(2, "parent", "Parent")
        + '<p id="parent-body">Parent content in its heading cell.</p>'
        + heading(3, "child", "Child")
        + '<p id="child-body">Child content in the same original cell.</p>'
    ),
    '<div class="cell code_cell"><div class="input"><div class="inner_cell">'
    '<div class="input_area"><pre id="source-code">'
    + "\n".join(f"Console.WriteLine({i});" for i in range(45))
    + '</pre></div></div></div><div class="output_wrapper"><div class="output">'
    '<div class="output_area"><div class="output_markdown output_subarea">'
    '<h2 id="generated-heading">Generated output heading</h2>'
    '<p id="generated-output">Preserved generated output.</p>'
    '</div></div></div></div></div>',
    markdown_cell(
        heading(4, "deep", "Deep")
        + '<p id="deep-body">Nested body.</p><a id="deep-focus" href="#deep">Nested link</a>'
    ),
    markdown_cell(heading(3, "peer", "Peer") + '<p id="peer-body">Peer body.</p>'),
    markdown_cell(heading(2, "next", "Next") + '<p id="next-body">Next branch.</p>'),
    markdown_cell(heading(2, "empty", "Empty")),
    markdown_cell(heading(2, "encoded target", "Encoded") + '<p id="encoded-body">Encoded target.</p>'),
])
LEVELS_FIXTURE = markdown_cell("".join(
    heading(level, f"level-{level}", f"Level {level}") + f"<p>Body {level}.</p>"
    for level in (1, 3, 6, 2, 4, 5)
))


BROWSER_CHECKS = r"""
import { pathToFileURL } from 'node:url';
let incoming = '';
for await (const chunk of process.stdin) incoming += chunk;
const config = JSON.parse(incoming);
const { chromium } = await import(pathToFileURL(config.module).href);
const browser = await chromium.launch({
  headless: true,
  ...(config.executable ? { executablePath: config.executable } : {}),
});
const checks = [];
const errors = [];
const check = (name, passed, details = null) => checks.push({ name, passed, details });
const shell = fixture => `<!doctype html><html lang="en"><head><style>${config.css}</style></head>
<body><a class="skip-link" href="#main-content">Skip to content</a>
<div class="reading-progress"><span></span></div><main id="main-content" class="book-main">
<nav class="chapter-toc"><a id="toc-deep" href="#deep">Deep</a></nav>
<section class="notebook-content">${fixture}</section>
<a data-prev-chapter href="/previous.html">Previous</a>
<a data-next-chapter href="/next.html">Next</a></main></body></html>`;
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
context.setDefaultTimeout(5000);
context.setDefaultNavigationTimeout(5000);
await context.route('http://book.test/**', route => route.fulfill({
  contentType: 'text/html', body: shell(config.fixture),
}));
const page = await context.newPage();
page.on('pageerror', error => errors.push(error.message));
const settle = () => page.evaluate(() => new Promise(resolve =>
  requestAnimationFrame(() => requestAnimationFrame(resolve))));
const sectionInfo = id => page.evaluate(id => {
  const heading = document.getElementById(id);
  const section = heading.closest('.notebook-section');
  const own = selector => [...section.querySelectorAll(selector)].find(
    node => node.closest('.notebook-section') === section);
  const toggle = own('.section-toggle');
  const body = own('.section-body');
  const count = own('.section-hidden-count');
  return {
    expanded: toggle.getAttribute('aria-expanded'), hidden: body.hidden,
    controls: toggle.getAttribute('aria-controls'), bodyId: body.id,
    label: toggle.getAttribute('aria-label'), count: count?.textContent || '',
    countExpanded: count?.getAttribute('aria-expanded'),
    parent: section.parentElement.closest('.notebook-section')?.querySelector('h1,h2,h3,h4,h5,h6')?.id || null,
    ignored: Boolean(toggle.closest('[data-pagefind-ignore="all"]')),
    countIgnored: Boolean(count?.closest('[data-pagefind-ignore="all"]')),
    bodyIgnored: Boolean(body.closest('[data-pagefind-ignore="all"]')),
  };
}, id);
const button = async id => (await page.evaluateHandle(id => {
  const section = document.getElementById(id).closest('.notebook-section');
  return [...section.querySelectorAll('.section-toggle')].find(
    node => node.closest('.notebook-section') === section);
}, id)).asElement();
const toggle = async id => { await (await button(id)).click(); await settle(); };
const allExpanded = () => page.evaluate(() => [...document.querySelectorAll('.section-body')].every(
  node => !node.hidden));
const reset = async () => {
  await page.evaluate(() => dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })));
  await settle();
};
try {
  await page.goto('http://book.test/chapter.html');
  const sourceBefore = await page.locator('#source-code').textContent();
  await page.addScriptTag({ content: config.js });
  await settle();
  check('starts fully expanded', await allExpanded());
  check('only authored headings become sections', await page.locator('.notebook-section').count() === 7);
  check('empty section has no inactive folding controls', await page.locator('#empty').evaluate(heading => {
    const section = heading.closest('.notebook-section');
    return !section.querySelector('.section-toggle') && !section.querySelector('.section-hidden-count')
      && !section.querySelector('.section-body').hidden;
  }));
  check('generated output heading stays outside a section header', await page.locator('#generated-heading').evaluate(
    node => !node.querySelector('.section-toggle') && !node.closest('.section-header')));
  check('code and output survive sectionization',
    await page.locator('#source-code').textContent() === sourceBefore
    && await page.locator('#generated-output').textContent() === 'Preserved generated output.');
  const expectedParents = { parent: null, child: 'parent', deep: 'child', peer: 'parent', next: null, 'encoded target': null };
  for (const [id, expectedParent] of Object.entries(expectedParents)) {
    const info = await sectionInfo(id);
    check(`hierarchy ${id}`, info.parent === expectedParent, info);
    check(`ARIA controls and initial state ${id}`,
      info.expanded === 'true' && !info.hidden && info.controls === info.bodyId && Boolean(info.bodyId), info);
    check(`accessible label ${id}`, Boolean(info.label) && !info.label.includes('Copy link'), info);
    check(`Pagefind ignores controls but keeps body ${id}`,
      info.ignored && info.countIgnored && !info.bodyIgnored, info);
  }
  check('all fragments retain original source-cell identity', await page.evaluate(() =>
    [...document.querySelectorAll('.notebook-content .cell')].every(node => node.hasAttribute('data-source-cell'))));
  const expectedCounts = { parent: 4, child: 3, deep: 1, peer: 1, next: 1, 'encoded target': 1 };
  for (const [id, count] of Object.entries(expectedCounts)) {
    await toggle(id);
    const info = await sectionInfo(id);
    check(`distinct hidden source-cell count ${id}`,
      Number(info.count.match(/\d+/)?.[0]) === count && info.countExpanded === 'false', info);
    if (id === 'parent') {
      check('folding controls retain 44px targets', await page.locator('#parent').evaluate(heading => {
        const section = heading.closest('.notebook-section');
        const controls = [section.querySelector('.section-toggle'), section.querySelector('.section-hidden-count')];
        return controls.every(control => {
          const box = control.getBoundingClientRect();
          return box.width >= 44 && box.height >= 44;
        });
      }));
    }
    await toggle(id);
  }
  await toggle('child');
  await toggle('parent');
  check('parent closure retains child flag', (await sectionInfo('child')).hidden);
  await toggle('parent');
  check('parent reopening retains child fold', (await sectionInfo('child')).hidden
    && !(await sectionInfo('parent')).hidden && !await page.locator('#deep-body').isVisible());
  check('peer and following branches remain visible',
    await page.locator('#peer-body').isVisible() && await page.locator('#next-body').isVisible());
  check('same-cell child body follows its own section', !await page.locator('#child-body').isVisible()
    && await page.locator('#parent-body').isVisible());
  await toggle('child');
  await page.locator('#deep-focus').focus();
  await (await button('parent')).evaluate(node => node.click());
  check('closing parent promotes descendant focus to its caret', await (await button('parent')).evaluate(
    node => node === document.activeElement));
  await reset();
  check('cached page return starts expanded', await allExpanded());
  const parentButton = await button('parent');
  await parentButton.focus();
  await parentButton.press('Enter');
  check('Enter collapses exactly once', (await sectionInfo('parent')).hidden);
  await parentButton.press('Space');
  check('Space expands exactly once', !(await sectionInfo('parent')).hidden);
  const originalUrl = page.url();
  for (const key of ['ArrowLeft', 'ArrowLeft', 'ArrowRight', 'ArrowRight']) {
    await parentButton.press(key);
    await page.waitForTimeout(30);
  }
  check('caret arrows do not trigger chapter navigation', page.url() === originalUrl);
  check('caret arrows leave requested state', !(await sectionInfo('parent')).hidden);
  await page.locator('#toc-deep').click();
  await settle();
  await toggle('parent');
  await page.locator('#toc-deep').click();
  await settle();
  check('same-hash TOC click reveals section and ancestors', await page.locator('#deep-body').isVisible()
    && !(await sectionInfo('deep')).hidden && !(await sectionInfo('parent')).hidden);
  await page.evaluate(() => { location.hash = 'peer'; });
  await settle();
  await toggle('parent');
  await page.goBack();
  await settle();
  check('hash history back reveals target', page.url().endsWith('#deep')
    && await page.locator('#deep-body').isVisible());
  await toggle('parent');
  await page.goForward();
  await settle();
  check('hash history forward reveals target', page.url().endsWith('#peer')
    && await page.locator('#peer-body').isVisible());
  await page.evaluate(() => {
    const link = document.createElement('a');
    link.id = 'search-result'; link.href = '/chapter.html#deep'; link.textContent = 'Search result';
    document.querySelector('.chapter-toc').append(link);
  });
  await toggle('parent');
  await page.locator('#search-result').click();
  await settle();
  check('dynamic search-style link reveals target', await page.locator('#deep-body').isVisible());
  await toggle('encoded target');
  await page.evaluate(() => { location.hash = '#encoded%20target'; });
  await settle();
  check('encoded hash reveals its target section', (await sectionInfo('encoded target')).expanded
    && await page.locator('#encoded-body').isVisible());
  await toggle('child');
  await toggle('parent');
  const statesBeforePrint = await page.locator('.section-body').evaluateAll(nodes => nodes.map(node => node.hidden));
  await page.emulateMedia({ media: 'print' });
  await page.evaluate(() => dispatchEvent(new Event('beforeprint')));
  await settle();
  check('print shows nested collapsed content', await page.locator('#deep-body').isVisible()
    && await page.locator('#generated-output').isVisible());
  check('print hides carets', !await (await button('parent')).isVisible());
  await page.evaluate(() => dispatchEvent(new Event('afterprint')));
  await page.emulateMedia({ media: 'screen' });
  check('printing preserves screen fold states', JSON.stringify(statesBeforePrint)
    === JSON.stringify(await page.locator('.section-body').evaluateAll(nodes => nodes.map(node => node.hidden))));
  await reset();
  await page.evaluate(() => scrollTo(0, 300));
  await settle();
  await (await button('parent')).evaluate(node => node.click());
  await settle();
  check('folding recalculates reading progress', await page.evaluate(() => {
    const max = document.documentElement.scrollHeight - innerHeight;
    const expected = max > 0 ? Math.min(100, Math.max(0, scrollY / max * 100)) : 0;
    return Math.abs(parseFloat(document.querySelector('.reading-progress span').style.width) - expected) < 0.2;
  }));
  const levels = await context.newPage();
  await levels.setContent(shell(config.levels));
  await levels.addScriptTag({ content: config.js });
  check('all six heading levels are supported', await levels.locator('.notebook-section').count() === 6
    && await levels.locator('.section-toggle[aria-expanded="true"]').count() === 6);
  await levels.close();
  const nojsContext = await browser.newContext({ javaScriptEnabled: false });
  const nojs = await nojsContext.newPage();
  await nojs.setContent(shell(config.fixture));
  check('without JavaScript all authored content is readable', await nojs.locator('#parent-body').isVisible()
    && await nojs.locator('#deep-body').isVisible() && await nojs.locator('#generated-output').isVisible());
  check('without JavaScript no inactive carets are shown', await nojs.locator('.section-toggle').count() === 0);
  await nojsContext.close();
  await page.evaluate(() => document.activeElement?.blur());
  await page.keyboard.press('ArrowRight');
  await page.waitForURL('http://book.test/next.html');
  check('chapter arrows still work outside disclosures', page.url().endsWith('/next.html'));
} finally {
  await browser.close();
}
process.stdout.write(JSON.stringify({ checks, errors }));
"""


def browser_tools():
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required for section browser checks.")
    explicit_module = os.environ.get("PLAYWRIGHT_MODULE")
    modules = ([Path(explicit_module)] if explicit_module else []) + [
        SOURCE.parents[2] / "node_modules" / "playwright" / "index.mjs",
        *sorted((Path.home() / ".npm" / "_npx").glob("*/node_modules/playwright/index.mjs")),
    ]
    module = next((path for path in modules if path.is_file()), None)
    if module is None:
        raise unittest.SkipTest("Install Playwright separately or set PLAYWRIGHT_MODULE to run browser checks.")
    executable = os.environ.get("CHROME_EXECUTABLE")
    if not executable:
        chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        executable = str(chrome) if chrome.is_file() else shutil.which("chromium") or shutil.which("google-chrome")
    return node, module, executable


class SectionFoldingBrowserTests(unittest.TestCase):
    def test_emitted_sections_are_accessible_nested_and_navigable(self):
        node, module, executable = browser_tools()
        result = subprocess.run(
            [node, "--input-type=module", "-e", BROWSER_CHECKS],
            input=json.dumps({
                "module": str(module), "executable": executable,
                "js": build_website.SITE_JS, "css": build_website.SITE_CSS,
                "fixture": FIXTURE, "levels": LEVELS_FIXTURE,
            }),
            text=True, capture_output=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["errors"], [])
        self.assertGreater(len(report["checks"]), 35)
        for check in report["checks"]:
            with self.subTest(check=check["name"]):
                self.assertTrue(check["passed"], check["details"])


if __name__ == "__main__":
    unittest.main()
