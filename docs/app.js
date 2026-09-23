/**
 * Problem Hunting with LLMs - Main Application JavaScript
 */

// Utility functions

/**
 * Get URL parameters
 */
function getUrlParams() {
    return new URLSearchParams(window.location.search);
}

/**
 * Update URL without page reload
 */
function updateUrl(params) {
    const url = new URL(window.location);
    for (const [key, value] of Object.entries(params)) {
        if (value === null || value === undefined || value === '') {
            url.searchParams.delete(key);
        } else {
            url.searchParams.set(key, value);
        }
    }
    window.history.replaceState({}, '', url);
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Format TeX content for display
 * Preserves LaTeX while making it HTML-safe
 */
function formatTeXContent(text) {
    if (!text) return '';

    // First, escape HTML entities
    let formatted = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Convert double newlines to paragraph breaks
    formatted = formatted.split(/\n\n+/).map(para => {
        return '<p>' + para.replace(/\n/g, '<br>') + '</p>';
    }).join('');

    return formatted;
}

/**
 * Trigger MathJax to re-render
 */
function renderMath() {
    if (typeof MathJax !== 'undefined' && MathJax.typesetPromise) {
        MathJax.typesetPromise().catch(function(err) {
            console.warn('MathJax typeset error:', err);
        });
    }
}

/**
 * Debounce function for search inputs
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Sort problems by number
 */
function sortByNumber(a, b) {
    const numA = parseInt(a.number || a.id) || 0;
    const numB = parseInt(b.number || b.id) || 0;
    return numA - numB;
}

/**
 * Sort problems by score (descending)
 */
function sortByScore(a, b) {
    return (b.score || 0) - (a.score || 0);
}

/**
 * Get unique models from attacks
 */
function getMathematicalAttempts(attacks) {
    return (attacks || []).filter(a => a.entry_kind !== 'statement_only');
}

function getUniqueModels(attacks) {
    const attempts = getMathematicalAttempts(attacks);
    const authoredModels = new Set(attempts.filter(a => a.entry_kind !== 'reused_writeup').map(a => a.model));
    return [...new Set(attempts.flatMap(a => {
        if (a.entry_kind !== 'reused_writeup') return [a.model];
        const sourceModel = a.provenance.source_model.replace(/_/g, ' ');
        return authoredModels.has(a.model) ? [sourceModel] : [sourceModel, `${a.model} (collection)`];
    }))];
}

function getModelLabels(attacks) {
    const shorten = name => {
        if (/gpt[ _]6[ _]astra[ _]ultra/i.test(name)) {
            return name.includes('(collection)') ? 'GPT Astra Ultra (collection)' : 'GPT Astra Ultra';
        }
        if (/gpt[ _]pro/i.test(name)) return 'GPT Pro';
        if (/gpt[ _]5\.2/i.test(name)) return 'GPT 5.2';
        if (/codex/i.test(name)) return 'Codex';
        if (/claude|opus/i.test(name)) return 'Opus 4.5';
        if (/gemini/i.test(name)) return 'Gemini';
        return name;
    };
    return [...new Set(getUniqueModels(attacks).map(shorten))].sort((a, b) =>
        Number(b.startsWith('GPT Astra Ultra')) - Number(a.startsWith('GPT Astra Ultra')) || a.localeCompare(b)
    );
}

/**
 * Count problems with attacks
 */
function countWithAttacks(problems) {
    return Object.values(problems).filter(p => getMathematicalAttempts(p.attacks).length > 0).length;
}

/**
 * Format date string
 */
function formatDate(dateStr) {
    if (!dateStr) return '-';
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    } catch {
        return dateStr;
    }
}

/**
 * Get status class for styling
 */
function getStatusClass(status) {
    switch (status?.toLowerCase()) {
        case 'solved':
            return 'status-solved';
        case 'partial':
            return 'status-partial';
        case 'unresolved':
            return 'status-unresolved';
        default:
            return '';
    }
}

/**
 * Theme handling
 */
function getStoredTheme() {
    try {
        return localStorage.getItem('theme');
    } catch {
        return null;
    }
}

function getPreferredTheme() {
    const stored = getStoredTheme();
    if (stored === 'light' || stored === 'dark') return stored;
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return 'dark';
    }
    return 'light';
}

function updateThemeToggle(theme) {
    const toggle = document.getElementById('theme-toggle');
    if (!toggle) return;
    toggle.textContent = theme === 'dark' ? 'Dark' : 'Light';
    toggle.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
    toggle.setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`);
}

function updateGiscusTheme(theme) {
    const frame = document.querySelector('iframe.giscus-frame');
    if (!frame || !frame.contentWindow) return;
    frame.contentWindow.postMessage(
        { giscus: { setConfig: { theme: theme === 'dark' ? 'dark' : 'light' } } },
        'https://giscus.app'
    );
}

function applyTheme(theme, persist) {
    const nextTheme = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', nextTheme);
    if (persist) {
        try {
            localStorage.setItem('theme', nextTheme);
        } catch {
            // Ignore storage errors
        }
    }
    updateThemeToggle(nextTheme);
    updateGiscusTheme(nextTheme);
}

function initThemeToggle() {
    const toggle = document.getElementById('theme-toggle');
    if (!toggle) return;

    const initialTheme = getPreferredTheme();
    applyTheme(initialTheme, false);

    toggle.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
        const next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next, true);
    });

    if (window.matchMedia) {
        const media = window.matchMedia('(prefers-color-scheme: dark)');
        if (media.addEventListener) {
            media.addEventListener('change', (event) => {
                if (getStoredTheme()) return;
                applyTheme(event.matches ? 'dark' : 'light', false);
            });
        }
    }
}

/**
 * Get review label for display
 */
function getReviewLabel(review) {
    const status = (review && review.status ? review.status : '').toLowerCase();
    switch (status) {
        case 'flagged':
        case 'incorrect':
        case 'known':
        case 'technicality':
        case 'trivial':
        case 'partial':
        case 'plausible':
        case 'accepted':
            return status;
        default:
            return 'unreviewed';
    }
}

/**
 * Get review class for styling
 */
function getReviewClass(review) {
    if (!review || !review.status) return 'review-unreviewed';
    return `review-${review.status.toLowerCase()}`;
}

function normalizeReviewHandle(handle) {
    if (handle === null || handle === undefined) return '';
    let cleaned = String(handle).trim();
    if (!cleaned) return '';
    if (cleaned.startsWith('@')) cleaned = cleaned.slice(1);
    cleaned = cleaned.replace(/[^A-Za-z0-9-]/g, '');
    return cleaned;
}

function getReviewHandles(review) {
    if (!review || !review.reviewed_by) return [];
    const raw = review.reviewed_by;
    let items = [];
    if (Array.isArray(raw)) {
        items = raw;
    } else if (raw !== null && raw !== undefined) {
        const text = String(raw).trim();
        if (text) items = text.split(',');
    }

    const handles = [];
    const seen = new Set();
    items.forEach((item) => {
        const normalized = normalizeReviewHandle(item);
        if (!normalized) return;
        const key = normalized.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        handles.push(normalized);
    });
    return handles;
}

function formatReviewHandles(review) {
    const handles = getReviewHandles(review);
    if (handles.length === 0) return '';
    return handles.map((handle) => `@${handle}`).join(', ');
}

function formatReviewHandleLinks(review) {
    const handles = getReviewHandles(review);
    if (handles.length === 0) return '';
    return handles
        .map((handle) => `<a href="https://github.com/${handle}" target="_blank" rel="noopener">@${handle}</a>`)
        .join(', ');
}

/**
 * Format completion percentage for display.
 */
function formatCompletion(value) {
    if (value === null || value === undefined) return '';
    const num = Number(value);
    if (!Number.isFinite(num)) return '';
    const rounded = Math.round(num * 10) / 10;
    if (Math.abs(rounded - Math.round(rounded)) < 1e-9) {
        return `${Math.round(rounded)}%`;
    }
    return `${rounded}%`;
}

/**
 * Keep the database's mathematical status separate from claims by LLMs.
 */
function getProblemStatus(problem) {
    return problem.status || 'not available';
}

function getProblemStatusClass(problem) {
    return problem.is_solved ? 'problem-status-solved' : 'problem-status-open';
}

function getCompletionSourceLabel(problem) {
    if (!formatCompletion(problem.completion)) return '';
    if (problem.completion_source === 'database') return 'Resolved in Tao\'s database';
    if (!getMathematicalAttempts(problem.attacks).length &&
        (problem.attacks || []).some(a => a.entry_kind === 'statement_only')) {
        return 'Statement only; awaiting a mathematical attempt';
    }
    return 'LLM estimate';
}

function formatStatusSync(sync) {
    if (!sync || !sync.checked_at) return '';
    const checkedDate = escapeHtml(String(sync.checked_at).slice(0, 10));
    const commit = /^[a-f0-9]{40}$/i.test(sync.source_commit || '') ? sync.source_commit : '';
    const sourceUrl = commit
        ? `https://github.com/teorth/erdosproblems/commit/${commit}`
        : 'https://github.com/teorth/erdosproblems';
    return `Problem status and formalization data checked ${checkedDate} against ` +
        `<a href="${sourceUrl}" target="_blank" rel="noopener">Tao's database${commit ? ` (${commit.slice(0, 7)})` : ''}</a>.`;
}

function formatFormalization(formalization, label) {
    if (!formalization || !formalization.state) return '';
    const stateLabel = { yes: 'formalized', no: 'not formalized', unformalized: 'not formalized' };
    let state = escapeHtml(stateLabel[formalization.state] || formalization.state);
    if (formalization.url && /^https?:\/\//i.test(formalization.url)) {
        const url = escapeHtml(formalization.url).replace(/"/g, '&quot;');
        state = `<a href="${url}" target="_blank" rel="noopener">${state}</a>`;
    }
    return `<li><strong>${escapeHtml(label)} formalization:</strong> ${state}</li>`;
}

/**
 * Initialize collapsible sections
 */
function initCollapsibles() {
    document.querySelectorAll('.collapsible-header').forEach(header => {
        header.addEventListener('click', () => {
            const content = header.nextElementSibling;
            if (content && content.classList.contains('collapsible-content')) {
                content.classList.toggle('collapsed');
                header.classList.toggle('expanded');
            }
        });
    });
}

/**
 * Smooth scroll to element
 */
function scrollToElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

/**
 * Copy text to clipboard
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (err) {
        console.error('Failed to copy:', err);
        return false;
    }
}

/**
 * Show a temporary message
 */
function showMessage(message, duration = 3000) {
    const existing = document.querySelector('.temp-message');
    if (existing) existing.remove();

    const div = document.createElement('div');
    div.className = 'temp-message';
    div.textContent = message;
    div.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 10px 20px;
        background: #333;
        color: white;
        border-radius: 4px;
        z-index: 1000;
    `;
    document.body.appendChild(div);

    setTimeout(() => div.remove(), duration);
}

// Export for use in other scripts
window.ProblemHunting = {
    getUrlParams,
    updateUrl,
    escapeHtml,
    formatTeXContent,
    renderMath,
    debounce,
    sortByNumber,
    sortByScore,
    getUniqueModels,
    getModelLabels,
    getMathematicalAttempts,
    countWithAttacks,
    formatDate,
    getStatusClass,
    getReviewLabel,
    getReviewClass,
    getReviewHandles,
    formatReviewHandles,
    formatReviewHandleLinks,
    formatCompletion,
    getProblemStatus,
    getProblemStatusClass,
    getCompletionSourceLabel,
    formatStatusSync,
    formatFormalization,
    initThemeToggle,
    initCollapsibles,
    scrollToElement,
    copyToClipboard,
    showMessage
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    initThemeToggle();
    initCollapsibles();
});
