// Run with: node tests/test_open_problem_detail.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'docs/problem.html'), 'utf8');
const scripts = Array.from(html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g), m => m[1]);
for (const script of scripts) new vm.Script(script);
const detailScript = scripts.find(script => script.includes('function initGiscus'));
const ranked = (id, rank) => ({
    id, rank, title: `Title ${rank}`, collection: 'ranked',
    domain_label: 'Algebra & geometry', status: 'open', llm_status: 'none',
    exact_target: 'For every n < 10, prove the stated inequality.',
    status_qualification: 'Bounded review; still open.', status_reviewed_at: '2026-09-22',
    sources: [{ citation: 'Definition <source>', url: 'https://example.org/?x=1&y=2', role: 'formal_statement' }],
    attacks: []
});
const records = {
    'problem.z-first': ranked('problem.z-first', 1),
    'problem.a-second': ranked('problem.a-second', 2),
    'mo:42': { id: 'mo:42', collection: 'mo', rank: null }
};

function render(query, open = records) {
    const elements = new Map();
    function element(id) {
        if (!elements.has(id)) elements.set(id, {
            innerHTML: '', textContent: '', style: {}, hidden: false, children: [],
            appendChild(child) { this.children.push(child); },
            querySelector(selector) { return element(`${id} ${selector}`); }
        });
        return elements.get(id);
    }
    const callbacks = [];
    const document = {
        addEventListener(name, callback) { if (name === 'DOMContentLoaded') callbacks.push(callback); },
        getElementById: element,
        querySelector: element,
        documentElement: { getAttribute() { return 'light'; } },
        createElement() { return { dataset: {} }; }
    };
    const context = vm.createContext({
        document, URLSearchParams, console,
        window: { location: { search: query }, OPEN_PROBLEMS_DATA: open,
            OPEN_PROBLEMS_CATALOG: { edition_date: '2026-09-22' } },
        moProblems: { '42': { id: '42', title: 'Legacy question', score: 5, link: 'https://mathoverflow.net/questions/42', attacks: [] } },
        erdosProblems: { '1': { number: '1', status: 'open', llm_status: 'unresolved', problem_url: 'https://www.erdosproblems.com/1', attacks: [] } }
    });
    vm.runInContext(fs.readFileSync(path.join(root, 'docs/app.js'), 'utf8'), context);
    vm.runInContext(fs.readFileSync(path.join(root, 'docs/catalog-math.js'), 'utf8'), context);
    callbacks.length = 0;
    vm.runInContext(detailScript, context);
    callbacks[0]();
    return { element, context };
}

let page = render('?type=open_problems&id=problem.z-first');
assert.equal(page.element('page-title').textContent, 'Title 1');
assert.match(page.element('problem-meta').innerHTML, /Problem Status:/);
assert.doesNotMatch(page.element('problem-meta').innerHTML, /Problem ID:|Catalog status:/);
assert.match(page.element('problem-meta').innerHTML, /No attempts yet/);
assert.match(page.element('problem-links').innerHTML, /\$n &lt; 10\$/);
assert.match(page.element('problem-links').innerHTML, /Definition &lt;source&gt;/);
assert.match(page.element('problem-links').innerHTML, /x=1&amp;y=2/);
assert.equal(page.element('prev-problem').style.visibility, 'hidden');
assert.equal(page.element('next-problem').href, 'problem.html?type=open_problems&id=problem.a-second');
assert.match(page.element('attempts-container').innerHTML, /No LLM attempts yet/);
assert.notEqual(page.element('llm-attempts-section').style.display, 'none');
assert.equal(page.element('.giscus').children[0].dataset.term, 'OpenProblem-problem.z-first');
const reviewURL = new URL(page.context.getReviewIssueUrl('open_problems', 'problem.z-first'));
assert.equal(reviewURL.searchParams.get('problem_type'), 'Open Problems');
assert.equal(reviewURL.searchParams.get('problem_id'), 'problem.z-first');

page = render('?type=open_problems&id=problem.a-second');
assert.equal(page.element('prev-problem').href, 'problem.html?type=open_problems&id=problem.z-first');
assert.equal(page.element('next-problem').style.visibility, 'hidden');

page = render('?type=open_problems&id=mo%3A42');
assert.match(page.element('problem-meta').innerHTML, /MathOverflow subset/);
assert.equal(page.element('.giscus').children[0].dataset.term, 'MO-42');
page = render('?type=erdos&id=1');
assert.equal(page.element('page-title').textContent, 'Erdos Problem #1');
assert.equal(page.element('.giscus').children[0].dataset.term, 'Erdos-1');

for (const id of ['problem.missing', '__proto__', 'constructor']) {
    assert.match(render(`?type=open_problems&id=${id}`).element('problem-meta').innerHTML, /Problem not found/);
}
assert.match(render('?type=open_problems&id=problem.z-first', null).element('problem-meta').innerHTML, /Error loading Top Open Problems data/);
const unsafeSource = { ...records['problem.z-first'], sources: [
    { citation: '<img src=x onerror=alert(1)>', url: 'javascript:alert(1)' },
    { citation: 'Quoted URL', url: 'https://example.org/" onmouseover="alert(1)' }
] };
page = render('?type=open_problems&id=problem.z-first', { 'problem.z-first': unsafeSource });
assert.doesNotMatch(page.element('problem-links').innerHTML, /href="javascript:|<img| onmouseover="/);
assert.match(page.element('problem-links').innerHTML, /&quot;/);

const tate = JSON.parse(fs.readFileSync(path.join(root, 'lists/top500-v22.json'), 'utf8')).records
    .find(record => record.problemId === 'problem.tate-conjecture-for-abelian-varieties-and-higher-dimensional-varieties');
const tateProblem = { ...ranked(tate.problemId, tate.releaseRank), exact_target: tate.exactTarget };
page = render(`?type=open_problems&id=${tate.problemId}`, { [tate.problemId]: tateProblem });
const statement = page.element('problem-links').innerHTML;
assert.match(statement, /class="problem-statement-text tex-content"/);
assert.match(statement, /\\overline\{X\}/);
assert.match(statement, /Q_\{l\}/);
assert.match(statement, /\^\{\\operatorname\{Gal\}\(\\overline\{k\} \/ k\)\}/);
assert.doesNotMatch(statement, /X_bar|H\^\(2i\)|Q_l/);
assert.doesNotMatch(page.element('problem-meta').innerHTML, /Problem ID:|Catalog status:/);
console.log('Ranked definitions, citations, stable navigation, empty attempts, review links and legacy detail routes passed.');
