document.addEventListener('DOMContentLoaded', function () {
    const nomeProdutoInput = document.getElementById('nome_produto');
    const pluInput = document.getElementById('plu');
    const barcodeInput = document.getElementById('barcodeInput');
    const barcodeFormInput = document.getElementById('barcodeFormInput');
    const searchResultsContainer = document.getElementById('searchResults');
    const currentUserRole = document.getElementById('currentUserRole').value;
    const privilegedRoles = ['gerente', 'gerente_geral'];
    let searchTimeout;

    if (!nomeProdutoInput) return;

    // Função para travar/destravar campos
    const setFieldsReadOnly = (isReadOnly) => {
        if (!privilegedRoles.includes(currentUserRole)) {
            pluInput.readOnly = isReadOnly;
            // O campo de busca de barcode não é travado, pois pode ser usado para encontrar outro item
        }
    };

    const fetchSuggestions = (term) => {
        if (term.length < 3) {
            searchResultsContainer.innerHTML = '';
            searchResultsContainer.style.display = 'none';
            return;
        }
        fetch(`/api/buscar-catalogo?term=${term}`)
            .then(response => response.json())
            .then(data => {
                searchResultsContainer.innerHTML = '';
                if (data.length > 0) {
                    const list = document.createElement('div');
                    list.className = 'list-group';
                    data.forEach(item => {
                        const listItem = document.createElement('a');
                        listItem.href = '#';
                        listItem.className = 'list-group-item list-group-item-action';
                        listItem.textContent = `${item.nome} (PLU: ${item.plu || 'N/A'})`;
                        listItem.addEventListener('click', (e) => {
                            e.preventDefault();
                            nomeProdutoInput.value = item.nome;
                            pluInput.value = item.plu || '';
                            barcodeInput.value = item.barcode || '';
                            barcodeFormInput.value = item.barcode || '';
                            searchResultsContainer.style.display = 'none';
                            setFieldsReadOnly(true); // Trava os campos após a seleção
                        });
                        list.appendChild(listItem);
                    });
                    searchResultsContainer.appendChild(list);
                    searchResultsContainer.style.display = 'block';
                } else {
                    searchResultsContainer.style.display = 'none';
                }
            });
    };

    nomeProdutoInput.addEventListener('keyup', () => {
        setFieldsReadOnly(false); // Destrava os campos ao digitar um novo nome
        pluInput.value = ''; // Limpa o PLU para evitar inconsistência
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            fetchSuggestions(nomeProdutoInput.value);
        }, 300);
    });

    document.addEventListener('click', function(event) {
        if (!searchResultsContainer.contains(event.target) && event.target !== nomeProdutoInput) {
            searchResultsContainer.style.display = 'none';
        }
    });
});