document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('productSearchForm');
    const input = document.getElementById('productSearchInput');
    const button = document.getElementById('productSearchButton');
    const results = document.getElementById('searchResultsContainer');
    if (!form) return;
    let controller;
    let generation = 0;
    async function search() {
        const term = input.value.trim();
        if (!term) return;
        controller?.abort();
        controller = new AbortController();
        const current = ++generation;
        button.disabled = true;
        results.textContent = 'Consultando produtos…';
        try {
            const response = await fetch(`/api/produtos?term=${encodeURIComponent(term)}`, {signal: controller.signal});
            const data = await response.json();
            if (current !== generation) return;
            if (!response.ok) throw new Error(data.error || 'Sua sessão expirou ou a busca está indisponível.');
            results.replaceChildren();
            if (!data.products.length) {
                results.textContent = 'Produto não encontrado nessa base. Tente o nome e a marca ou outro código da embalagem. Nenhum item foi registrado.';
                return;
            }
            for (const item of data.products) {
                const card = document.createElement('article');
                card.className = 'lookup-result';
                const details = document.createElement('div');
                const name = document.createElement('strong');
                name.textContent = item.nome;
                const brand = document.createElement('small');
                brand.textContent = [item.marca, item.embalagem, item.barcode].filter(Boolean).join(' · ');
                brand.className = 'd-block text-muted mt-1';
                details.append(name, brand);
                const select = document.createElement('a');
                select.href = `/lotes/novo?selection=${encodeURIComponent(item.selection)}`;
                select.className = 'btn btn-outline-primary';
                select.textContent = 'Registrar lote →';
                card.append(details, select);
                results.append(card);
            }
        } catch (error) {
            if (current === generation && error.name !== 'AbortError') {
                results.textContent = error.message === 'Failed to fetch' ? 'Sem conexão. Tente novamente.' : error.message;
            }
        } finally {
            if (current === generation) button.disabled = false;
        }
    }
    form.addEventListener('submit', event => { event.preventDefault(); search(); });
    input.addEventListener('barcode-scanned', search);
    input.addEventListener('input', () => {
        controller?.abort();
        generation++;
        button.disabled = false;
    });
});
