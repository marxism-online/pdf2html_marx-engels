(function () {
    // Split body's direct child nodes at <!--nextpage--> comments
    const bodyNodes = Array.from(document.body.childNodes);

    let hasMarker = false;
    const pages = [];
    let current = [];

    for (const node of bodyNodes) {
        if (node.nodeType === Node.COMMENT_NODE && node.nodeValue.trim() === 'nextpage') {
            hasMarker = true;
            pages.push(current);
            current = [];
        } else {
            current.push(node);
        }
    }
    pages.push(current);

    if (!hasMarker) return; // not a paginated document — do nothing

    const total = pages.length;

    // Wrap each page group in a <div>
    document.body.innerHTML = '';
    const pageDivs = pages.map((nodes, i) => {
        const div = document.createElement('div');
        div.className = 'pager-page';
        nodes.forEach(n => div.appendChild(n));
        return div;
    });
    pageDivs.forEach(div => document.body.appendChild(div));

    // --- Navigation bar ---
    const nav = document.createElement('div');
    nav.id = 'pager-nav';
    nav.innerHTML = `
        <button id="pager-prev" title="Предыдущая страница (←)">&#9664;</button>
        <span id="pager-label">
            Страница&nbsp;<input id="pager-input" type="number" min="1" max="${total}" value="1">&nbsp;из&nbsp;${total}
        </span>
        <button id="pager-next" title="Следующая страница (→)">&#9654;</button>
    `;
    document.body.insertBefore(nav, document.body.firstChild);

    const prevBtn = document.getElementById('pager-prev');
    const nextBtn = document.getElementById('pager-next');
    const pageInput = document.getElementById('pager-input');

    let currentPage = 0;

    function showPage(n) {
        n = Math.max(0, Math.min(total - 1, n));
        currentPage = n;
        pageDivs.forEach((div, i) => {
            div.style.display = i === n ? '' : 'none';
        });
        pageInput.value = n + 1;
        prevBtn.disabled = n === 0;
        nextBtn.disabled = n === total - 1;
        window.scrollTo(0, 0);
        // Reflect in URL hash so browser history works
        history.replaceState(null, '', '#p' + (n + 1));
    }

    prevBtn.addEventListener('click', () => showPage(currentPage - 1));
    nextBtn.addEventListener('click', () => showPage(currentPage + 1));

    pageInput.addEventListener('change', () => {
        showPage(parseInt(pageInput.value, 10) - 1);
    });
    pageInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') showPage(parseInt(pageInput.value, 10) - 1);
    });

    document.addEventListener('keydown', e => {
        if (e.target === pageInput) return;
        if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') showPage(currentPage - 1);
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') showPage(currentPage + 1);
    });

    // Restore page from hash on load
    const hashMatch = location.hash.match(/^#p(\d+)$/);
    showPage(hashMatch ? parseInt(hashMatch[1], 10) - 1 : 0);
})();
