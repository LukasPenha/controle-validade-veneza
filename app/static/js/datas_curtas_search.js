document.addEventListener('DOMContentLoaded', function () {
    const searchInput = document.getElementById('productSearchInput');
    const resultsContainer = document.getElementById('searchResultsContainer');
    let searchTimeout;

    const fetchProducts = (term) => {
        if (term.length < 3) {
            resultsContainer.innerHTML = '<p class="text-center text-muted">Digite pelo menos 3 caracteres para buscar.</p>';
            return;
        }

        resultsContainer.innerHTML = '<p class="text-center text-muted">Buscando no catálogo...</p>';

        fetch(`/api/buscar-produtos-catalogo?term=${term}`)
            .then(response => response.json())
            .then(data => {
                resultsContainer.innerHTML = '';
                if (data.length > 0) {
                    const list = document.createElement('ul');
                    list.className = 'list-group';
                    data.forEach(item => {
                        const listItem = document.createElement('li');
                        listItem.className = 'list-group-item d-flex justify-content-between align-items-center';
                        listItem.innerHTML = `
                            <div>
                                <strong>${item.nome}</strong><br>
                                <small class="text-muted">PLU: ${item.plu || 'N/A'} | Cód. Barras: ${item.barcode || 'N/A'}</small>
                            </div>
                            <a href="/cadastrar-rebaixa/${item.id}" class="btn btn-sm btn-primary">
                                Selecionar
                            </a>
                        `;
                        list.appendChild(listItem);
                    });
                    resultsContainer.appendChild(list);
                } else {
                    resultsContainer.innerHTML = '<p class="text-center text-muted">Nenhum item encontrado no catálogo.</p>';
                }
            })
            .catch(() => {
                resultsContainer.innerHTML = '<p class="text-center text-danger">Ocorreu um erro na busca.</p>';
            });
    };

    searchInput.addEventListener('keyup', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            fetchProducts(searchInput.value);
        }, 300); // 300ms delay
    });
});