// Collapse writeups at section boundaries, leaving complete statements and math intact.
(function () {
    const statementLabel = /^(?:(?:formal restatement|restatement|statement|target)\b|problem(?:\s*$|\s*\(|\s+and\b|\s+statement\b|\s+setup\b|\s+formulation\b|\s*:))/i;
    const objectiveLabel = /^(?:round[-\s–]*\d+\s+)?objective\b/i;
    const numberedSection = /^(?:OUTPUT\s+)?\d+[.)]\s+/i;
    const paragraphSection = /^(?:(?:quick\s+)?(?:literature|context)|attack plan|work|(?:adversarial\s+)?verification|final|sources|references|completion|(?:round[-\s–]*\d+\s+)?foundation|new insight)\b/i;

    function sections(content) {
        return [...content.querySelectorAll('h2, h3, h4, h5, h6, p')].flatMap(node => {
            // Paragraph headings occur in older fragments. Do not interpret list
            // items or quoted examples as sections of the enclosing writeup.
            if (node.closest('blockquote, li, pre, table')) return [];
            const text = node.textContent.trim().replace(/^\\item\s*/, '').replace(/\s+/g, ' ');
            const heading = /^H[2-6]$/.test(node.tagName);
            const label = text.replace(numberedSection, '').replace(/^[“‘"']\s*/, '');
            // A numbered sentence may be a list item within the statement.
            // Only known section labels can end a prose-format preview.
            const marker = statementLabel.exec(label) || objectiveLabel.exec(label) || paragraphSection.exec(label);
            if (!heading && (!marker || (!numberedSection.test(text)
                && marker[0] !== marker[0].toUpperCase()
                && !/^formal restatement\b/i.test(label)
                && !node.firstElementChild?.matches('strong, em, b, i')))) return [];
            return [{ node, label, level: heading ? Number(node.tagName[1]) : 3,
                statement: statementLabel.test(label),
                objective: objectiveLabel.test(label),
                numbered: numberedSection.test(text) }];
        });
    }

    function openingSection(content) {
        const headings = sections(content);
        const start = headings.find(section => section.statement)
            || headings.find(section => section.objective)
            || headings.find(section => section.numbered);
        if (!start) return null;
        const next = headings.slice(headings.indexOf(start) + 1)
            .find(section => section.level <= start.level);
        return { ...start, end: next?.node || null };
    }

    function copyStatement(content, section) {
        const range = document.createRange();
        // A heading contains only the label; a paragraph can contain both the
        // label and the statement, so retain that paragraph in full.
        if (/^H[2-6]$/.test(section.node.tagName)) range.setStartAfter(section.node);
        else range.setStartBefore(section.node);
        if (section.end) range.setEndBefore(section.end);
        else range.setEnd(content, content.childNodes.length);
        const copy = range.cloneContents();
        // The additional statement must not advance MathJax's equation counter
        // and renumber the original attempts. Explicit tags remain as supplied.
        const walker = document.createTreeWalker(copy, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
            walker.currentNode.textContent = walker.currentNode.textContent.replace(
                /\\(begin|end)\{(equation|align|alignat|flalign|gather|multline)\}/g,
                '\\$1{$2*}'
            );
        }
        return copy;
    }

    function initAttemptPreviews(container, statementTarget) {
        const entries = [...container.querySelectorAll('.attempt')].map(attempt => {
            const content = attempt.querySelector('.attempt-content');
            return { attempt, content, section: openingSection(content) };
        });

        // Some later rounds only restate their own objective. Show the original
        // question once above all attempts, using an explicitly labelled source
        // section. Ranked catalog pages already supply their own statement.
        if (statementTarget && !statementTarget.querySelector('.writeup-statement')) {
            const candidates = entries.filter(entry => entry.section?.statement && entry.section.end);
            const source = candidates.find(entry => /^formal restatement\b/i.test(entry.section.label)) || candidates[0];
            if (source) {
                const statement = document.createElement('div');
                statement.className = 'writeup-statement tex-content';
                statement.append(copyStatement(source.content, source.section));
                const attribution = document.createElement('p');
                attribution.className = 'status-note';
                attribution.append('Restatement from ');
                const link = document.createElement('a');
                link.href = `#attempt-${entries.indexOf(source) + 1}`;
                link.textContent = source.attempt.querySelector('h3').textContent;
                attribution.append(link, '.');
                statement.append(attribution);
                statementTarget.prepend(statement);
            }
        }

        entries.forEach(({ attempt, content, section }, index) => {
            attempt.id = `attempt-${index + 1}`;
            if (content.querySelector('.attempt-read-more') || attempt.dataset.statementOnly === 'true' || !section?.end) return;
            const remainder = document.createElement('div');
            remainder.className = 'attempt-remainder';
            remainder.id = `attempt-remainder-${index + 1}`;
            const range = document.createRange();
            range.setStartBefore(section.end);
            range.setEnd(content, content.childNodes.length);
            remainder.append(range.extractContents());

            const preview = document.createElement('div');
            preview.className = 'attempt-preview';
            while (content.firstChild) preview.append(content.firstChild);
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'attempt-read-more';
            button.setAttribute('aria-controls', remainder.id);
            const title = attempt.querySelector('h3').textContent;
            const setExpanded = expanded => {
                remainder.hidden = !expanded;
                button.setAttribute('aria-expanded', String(expanded));
                button.textContent = expanded ? 'Read less' : 'Read more';
                button.setAttribute('aria-label', `${button.textContent}: ${title}`);
            };
            setExpanded(false);
            button.addEventListener('click', () => setExpanded(remainder.hidden));
            content.append(preview, button, remainder);
        });
    }

    window.ProblemHunting.initAttemptPreviews = initAttemptPreviews;
})();
