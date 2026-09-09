document.addEventListener('DOMContentLoaded', () => {
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
    const frequency = document.getElementById('frequency');
    const weekday = document.getElementById('weekday');
    if (frequency && weekday) {
        const update = () => { weekday.disabled = frequency.value !== 'weekly'; };
        frequency.addEventListener('change', update);
        update();
    }
});
