// Run with Node 22+ and an existing Chrome remote-debugging session:
// CHROME_DEBUG_URL=http://127.0.0.1:9224 node tests/test_tex_references_browser.mjs
// Uses its own temporary about:blank tab; no site server or downloaded dependencies.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const html = fs.readFileSync(path.join(root, 'docs/problem.html'), 'utf8');
const script = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)]
    .map(match => match[1]).find(value => value.includes('function formatTeX'));
const formatter = script.slice(script.indexOf('function formatTeX'), script.indexOf('function initGiscus'));
assert.ok(formatter.includes('return formatted;'), 'The browser formatter must be available.');
assert.equal(typeof WebSocket, 'function', 'This test needs Node 22+ with its built-in WebSocket client.');
const debugURL = (process.env.CHROME_DEBUG_URL || 'http://127.0.0.1:9224').replace(/\/$/, '');
const response = await fetch(`${debugURL}/json/new?about:blank`, { method: 'PUT' });
assert.ok(response.ok, 'Chrome must expose its remote-debugging endpoint.');
const target = await response.json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
});
let sequence = 0;
const pending = new Map();
socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    const handler = pending.get(message.id);
    if (!handler) return;
    pending.delete(message.id);
    clearTimeout(handler.timeout);
    if (message.error) handler.reject(new Error(JSON.stringify(message.error)));
    else handler.resolve(message.result);
});
const call = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timeout = setTimeout(() => {
        pending.delete(id);
        reject(new Error(`Chrome timed out: ${method}`));
    }, 20000);
    pending.set(id, { resolve, reject, timeout });
    socket.send(JSON.stringify({ id, method, params }));
});
const evaluate = async expression => {
    const result = await call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
};

try {
    await evaluate(`window.ProblemHunting = {};\n${formatter}\n${fs.readFileSync(path.join(root, 'docs/attempt-previews.js'), 'utf8')}\n${fs.readFileSync(path.join(root, 'docs/tex-references.js'), 'utf8')}`);
    const result = await evaluate(`(() => {
        const tex = String.raw;
        const source = tex\`\\section{Formal restatement}
Use Lemma~\\ref{shared} and equation \\eqref{eq:inside}.
\\begin{equation}a=b\\label{eq:opening}\\end{equation}

\\section{Work}
\\begin{lemma}[First named result]\\label{shared}
An equation within this lemma has its own identity:
\\begin{equation}x=1\\label{eq:inside}\\end{equation}
\\end{lemma}
\\ref{absent} remains a readable reference.
\`;
        const other = tex\`\\section{Formal restatement}
Use Lemma~\\ref{shared}.

\\section{Work}
\\begin{lemma}[Second named result]\\label{shared}Different claim.\\end{lemma}
\`;
        const collection = tex\`% BEGIN REUSED SOURCE: version-one.tex
\\begin{lemma}[Version one]\\label{shared}First imported claim.\\end{lemma}
See \\ref{shared}.
% END REUSED SOURCE: version-one.tex
% BEGIN REUSED SOURCE: version-two.tex
\\begin{lemma}[Version two]\\label{shared}Second imported claim.\\end{lemma}
See \\ref{shared}.
% END REUSED SOURCE: version-two.tex
\`;
        const payload = '"/><img src=x onerror="window.referencePayloadExecuted=true">';
        const untrusted = tex\`\\label{\` + payload + '}Reference ' + tex\`\\ref{\` + payload + '}';
        const host = document.createElement('main');
        const statement = document.createElement('section');
        document.body.append(statement, host);
        for (const [index, raw] of [source, other, collection, untrusted].entries()) {
            const attempt = document.createElement('article');
            attempt.className = 'attempt';
            attempt.innerHTML = '<h3>Writeup ' + (index + 1) + '</h3><div class="attempt-content">'
                + formatTeX(raw, index === 2) + '</div>';
            host.append(attempt);
        }
        ProblemHunting.initAttemptPreviews(host, statement);
        ProblemHunting.initTeXReferences(host);

        const attempts = [...host.querySelectorAll('.attempt')];
        const linkedTarget = link => link.getAttribute('href') ? document.getElementById(link.hash.slice(1)) : null;
        const links = [...document.querySelectorAll('.tex-reference')].map(link => {
            const target = linkedTarget(link);
            return {
                key: link.dataset.texReference,
                caption: link.textContent,
                sourceAttempt: attempts.indexOf(link.closest('.attempt')),
                targetAttempt: attempts.indexOf(target?.closest('.attempt')),
                sourceScope: link.dataset.texScope,
                targetScope: target?.dataset.texScope,
                targetKey: target?.dataset.texLabel,
                href: link.getAttribute('href')
            };
        });
        const copied = statement.querySelector('.tex-reference');
        const destination = linkedTarget(copied);
        const collapsedBeforeClick = destination.closest('.attempt-remainder').hidden;
        copied.click();
        const expandedAfterClick = !destination.closest('.attempt-remainder').hidden;
        const IDs = [...document.querySelectorAll('[id]')].map(node => node.id);
        return {
            links,
            copied: {
                belongsToOriginal: destination.closest('.attempt') === attempts[0],
                collapsedBeforeClick, expandedAfterClick,
                accessibleExpanded: attempts[0].querySelector('.attempt-read-more').getAttribute('aria-expanded')
            },
            originalEquationNumbered: attempts[0].textContent.includes('\\\\begin{equation}'),
            copiedEquationNumbered: statement.textContent.includes('\\\\begin{equation}'),
            copiedEquationStarred: statement.textContent.includes('\\\\begin{equation*}'),
            duplicateIDs: IDs.filter((id, index) => IDs.indexOf(id) !== index),
            security: {
                injectedElements: attempts[3].querySelectorAll('img, [onerror]').length,
                executed: window.referencePayloadExecuted === true,
                textPreserved: attempts[3].textContent.includes(payload)
            }
        };
    })()`);

    for (const link of result.links.filter(link => link.key !== 'absent')) {
        assert.ok(link.href, `Missing target for ${link.key}`);
        assert.equal(link.targetKey, link.key, 'A reference must target its actual source label.');
        assert.equal(link.targetScope, link.sourceScope, 'Imported versions must not share reference targets.');
        if (link.sourceAttempt !== -1) assert.equal(link.targetAttempt, link.sourceAttempt, 'Other writeups must not capture a reference.');
    }
    assert.deepEqual(result.links.filter(link => link.sourceAttempt === 2).map(link => link.caption), ['Version one', 'Version two']);
    assert.equal(result.links.find(link => link.sourceAttempt === 0 && link.key === 'shared').caption, 'First named result');
    assert.equal(result.links.find(link => link.sourceAttempt === 1 && link.key === 'shared').caption, 'Second named result');
    for (const link of result.links.filter(link => link.key === 'eq:inside')) {
        assert.equal(link.caption, '(eq:inside)', 'An equation must not inherit the enclosing theorem name or an invented number.');
    }
    const absent = result.links.find(link => link.key === 'absent');
    assert.equal(absent.caption, 'absent');
    assert.equal(absent.href, null, 'An unavailable source target must not acquire a guessed link.');
    assert.deepEqual(result.copied, { belongsToOriginal: true, collapsedBeforeClick: true, expandedAfterClick: true, accessibleExpanded: 'true' });
    assert.equal(result.originalEquationNumbered, true, 'The original numbered equation must remain numbered.');
    assert.equal(result.copiedEquationNumbered, false, 'A copied statement must not increment equation numbering.');
    assert.equal(result.copiedEquationStarred, true, 'The statement copy must retain its equation.');
    assert.deepEqual(result.duplicateIDs, []);
    assert.equal(result.links.filter(link => link.sourceAttempt === 3).length, 1, 'The untrusted label must be exercised as a reference.');
    assert.deepEqual(result.security, { injectedElements: 0, executed: false, textPreserved: true });
    console.log('Browser reference isolation, equation captions, copied statements, expansion and escaping passed.');
} finally {
    await call('Page.close').catch(() => {});
    socket.close();
}
