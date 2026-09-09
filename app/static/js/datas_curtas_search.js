document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('productSearchInput');
    const results = document.getElementById('searchResultsContainer');
    if (!input || !results) return;
    let timer, controller;
    let generation = 0;
    const message = text => { results.textContent = text; };
    input.addEventListener('input', () => {
        clearTimeout(timer);
        controller?.abort();
        const current = ++generation;
        const term = input.value.trim();
        if (!term) { message('Digite um nome ou leia um código para começar.'); return; }
        timer = setTimeout(async () => {
            controller = new AbortController();
            message('Buscando no catálogo…');
            try {
                const response = await fetch(`/api/catalogo?term=${encodeURIComponent(term)}`, {signal:controller.signal});
                if (!response.ok || response.redirected) throw new Error('lookup');
                const data = await response.json();
                if (current !== generation) return;
                results.replaceChildren();
                if (!data.length) { message('Produto não encontrado. Use “Cadastrar novo produto” para adicioná-lo ao catálogo.'); return; }
                const list = document.createElement('div');
                list.className = 'list-group';
                data.forEach(item => {
                    const link = document.createElement('a');
                    link.className = 'list-group-item list-group-item-action py-3';
                    link.href = `/cadastrar-rebaixa/${encodeURIComponent(item.id)}`;
                    const name = document.createElement('strong');
                    name.textContent = item.nome;
                    const details = document.createElement('small');
                    details.className = 'd-block text-muted mt-1';
                    details.textContent = `PLU ${item.plu || '—'} · Código ${item.barcode || '—'} · Selecionar →`;
                    link.append(name, details);
                    list.append(link);
                });
                results.append(list);
            } catch (error) {
                if (error.name !== 'AbortError' && current === generation) message('Não foi possível buscar. Confira a conexão e se sua sessão continua ativa.');
            }
        }, 250);
    });
});
