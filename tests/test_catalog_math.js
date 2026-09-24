const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const context = vm.createContext({ window: { ProblemHunting: {} } });
vm.runInContext(fs.readFileSync(path.join(root, 'docs/catalog-math.js'), 'utf8'), context);
const prepare = context.window.ProblemHunting.catalogMath;
const tex = String.raw;

assert.equal(prepare('H^(2i)(X_bar,Q_l(i))^Gal(k_bar/k)'),
    tex`\(H^{2 i}(\overline{X},Q_{l}(i))^{\operatorname{Gal}(\overline{k} / k)}\)`);
assert.equal(prepare('zeta(s)=sum_{n>=1} n^(-s)'), tex`\(\zeta(s) = \sum_{n \ge 1} n^{-s}\)`);
assert.equal(prepare('0<Re(s)<1'), tex`\(0 < \operatorname{Re}(s) < 1\)`);
assert.equal(prepare('NP subseteq BQP'), tex`\(\mathrm{NP} \subseteq \mathrm{BQP}\)`);
assert.equal(prepare('C-infinity(R^3 x [0,infinity))'), tex`\(C^{\infty}(R^{3} x [0,\infty))\)`);
assert.equal(prepare('|u(x,t)|^2'), tex`\(|u(x,t)|^{2}\)`);
for (const plain of [
    'For every smooth geometrically irreducible projective variety.',
    'Fefferman statement (A), sections 3-4, reviewed 2026-09-24.',
    'The l-adic cycle-class map over a finitely generated field.',
    'https://example.org/a?x=2', '`Q_l`', tex`$Q_\ell$`, tex`\(x^2\)`,
    'H^(unfinished prose', 'Q_',
]) assert.equal(prepare(plain), plain);

const records = JSON.parse(fs.readFileSync(path.join(root, 'lists/top500-v22.json'), 'utf8')).records;
let withMath = 0;
for (const record of records) {
    const before = record.exactTarget;
    const output = prepare(before);
    assert.equal(record.exactTarget, before, 'The canonical catalog statement stays unchanged.');
    assert.ok(output.length >= before.length / 2, record.problemId);
    assert.doesNotMatch(output, /\[object Object\]/, record.problemId);
    assert.equal((output.match(/undefined/g) || []).length, (before.match(/undefined/g) || []).length, record.problemId);
    if (output.includes('\\(')) withMath++;
}
assert.ok(withMath > 300, 'Catalog formatting must cover the collection, not only Tate.');
console.log(`Catalog notation tests passed; ${withMath}/500 statements contain rendered math.`);
