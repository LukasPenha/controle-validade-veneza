document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('input[type="file"][data-max-bytes]').forEach(input => {
        const validate = () => {
            const limit = Number(input.dataset.maxBytes);
            input.setCustomValidity(input.files[0]?.size > limit
                ? `Escolha uma foto de até ${limit / (1024 * 1024)} MB.` : '');
        };
        input.addEventListener('change', validate);
        validate();
    });
    document.querySelectorAll('table').forEach(table => {
        if (!table.closest('.table-responsive')) {
            const wrapper = document.createElement('div');
            wrapper.className = 'table-responsive';
            wrapper.setAttribute('tabindex', '0');
            wrapper.setAttribute('aria-label', 'Tabela: deslize para consultar todas as colunas');
            table.before(wrapper);
            wrapper.append(table);
        }
    });
    const sidebar = document.getElementById('sidebarMenu');
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && sidebar?.classList.contains('show')) {
            bootstrap.Collapse.getOrCreateInstance(sidebar).hide();
            document.querySelector('[data-bs-target="#sidebarMenu"]').focus();
        }
    });
    document.addEventListener('click', event => {
        if (window.innerWidth < 768 && sidebar?.classList.contains('show') &&
            !sidebar.contains(event.target) && !event.target.closest('[data-bs-target="#sidebarMenu"]')) {
            bootstrap.Collapse.getOrCreateInstance(sidebar).hide();
        }
    });
    // Troca de status: confirma antes de enviar e desfaz a escolha se a pessoa cancelar.
    document.querySelectorAll('form.js-status-form select').forEach(select => {
        const original = select.value;
        select.addEventListener('change', () => {
            if (confirm(select.form.dataset.confirm)) {
                select.form.submit();
            } else {
                select.value = original;
            }
        });
    });
    const frequency = document.getElementById('frequency');
    const weekday = document.getElementById('weekday');
    if (frequency && weekday) {
        const update = () => { weekday.disabled = frequency.value !== 'weekly'; };
        frequency.addEventListener('change', update);
        update();
    }
});
