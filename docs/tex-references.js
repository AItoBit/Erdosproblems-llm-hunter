// Resolve source references within their own writeup (and imported source version).
(function () {
    function initTeXReferences(container) {
        const maps = new Map();
        const keyFor = node => `${node.dataset.texScope || '0'}:${node.dataset.texLabel || node.dataset.texReference}`;
        container.querySelectorAll('.attempt').forEach((attempt, index) => {
            const targets = new Map();
            attempt.querySelectorAll('.tex-label').forEach((label, number) => {
                label.id = `tex-label-${index + 1}-${number + 1}`;
                label.tabIndex = -1;
                const block = label.closest('.theorem, .lemma, .proposition, .corollary, .claim, .definition, .remark');
                const heading = block?.querySelector('strong')?.textContent || '';
                const name = label.dataset.texLabelKind === 'math' ? null : heading.match(/\[([\s\S]+)\]:?\s*$/)?.[1];
                targets.set(keyFor(label), { label, name });
            });
            maps.set(attempt, targets);
        });

        document.querySelectorAll('.tex-reference').forEach(link => {
            let attempt = link.closest('.attempt');
            if (!attempt) {
                // A copied problem statement refers back to its original writeup.
                const source = link.closest('.writeup-statement')?.querySelector('.status-note a[href^="#attempt-"]');
                attempt = source ? document.getElementById(source.hash.slice(1)) : null;
            }
            const target = maps.get(attempt)?.get(keyFor(link));
            if (!target) {
                link.removeAttribute('href');
                link.title = `Reference ${link.dataset.texReference}: target not present in this writeup`;
                return;
            }
            link.href = `#${target.label.id}`;
            link.title = `View ${link.dataset.texReference} in this writeup`;
            if (target.name && !/[\\$]/.test(target.name)) {
                link.textContent = link.dataset.texReferenceKind === 'eqref' ? `(${target.name})` : target.name;
            }
            if (!link.dataset.texReferenceReady) {
                link.dataset.texReferenceReady = 'true';
                link.addEventListener('click', () => {
                    const remainder = target.label.closest('.attempt-remainder');
                    if (remainder?.hidden) {
                        attempt.querySelector('.attempt-read-more')?.click();
                    }
                });
            }
        });
    }
    window.ProblemHunting.initTeXReferences = initTeXReferences;
})();
