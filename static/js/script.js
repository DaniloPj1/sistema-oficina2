document.addEventListener('DOMContentLoaded', function() {

    // Ativar link do menu lateral e submenu
    const currentPage = window.location.pathname;
    const sidebarLinks = document.querySelectorAll('.sidebar-menu a');
    sidebarLinks.forEach(link => {
        const linkPath = link.getAttribute('href');
        if (linkPath === currentPage || (linkPath !== '/' && currentPage.startsWith(linkPath))) {
            link.classList.add('active');
            const parentSubmenu = link.closest('.submenu');
            if (parentSubmenu) {
                const parentLi = parentSubmenu.closest('.has-submenu');
                if (parentLi) {
                    parentLi.classList.add('open');
                    parentLi.querySelector('a').classList.add('active');
                }
            }
        }
    });

    // Lógica de Acordeão para Submenus
    document.querySelectorAll('.sidebar-menu .has-submenu > a').forEach(menuLink => {
        menuLink.addEventListener('click', function(event) {
            event.preventDefault();
            const parentLi = this.parentElement;
            parentLi.classList.toggle('open');
        });
    });

    // Relógio do Dashboard
    updateClock();
    setInterval(updateClock, 1000);

    // Lógica para Modais de Confirmação (Ex: Deleção)
    document.body.addEventListener('submit', function(event) {
        if (event.target.matches('.delete-form')) {
            if (!confirm('Você tem certeza que deseja deletar este item? Esta ação não pode ser desfeita.')) {
                event.preventDefault();
            }
        }
    });

    // Lógica para Modais genéricos
    document.body.addEventListener('click', function(e) {
        if (e.target.dataset.bsToggle === "modal") {
            e.preventDefault();
            const targetSelector = e.target.dataset.bsTarget;
            const target = document.querySelector(targetSelector);
            if (target) {
                target.style.display = 'block';
            }
        }
        if (e.target.dataset.bsDismiss === "modal" || e.target.classList.contains('btn-close')) {
            e.preventDefault();
            const modal = e.target.closest('.modal');
            if (modal) {
                modal.style.display = 'none';
            }
        }
    });
    window.addEventListener('click', function(e) {
        if (e.target.classList.contains('modal')) {
            e.target.style.display = 'none';
        }
    });

    // Lógica para o formulário de Ordem de Serviço
    const osForm = document.getElementById('os-form');
    if (osForm) {
        const clienteSelect = document.getElementById('cliente_id');
        const veiculoSelect = document.getElementById('veiculo_id');

        clienteSelect.addEventListener('change', function() {
            fetchVeiculos(this.value, veiculoSelect);
        });

        if (clienteSelect.value) {
            const selectedVeiculoId = veiculoSelect.dataset.selected;
            fetchVeiculos(clienteSelect.value, veiculoSelect, selectedVeiculoId);
        }

        veiculoSelect.addEventListener('change', function() {
            const km = this.options[this.selectedIndex]?.dataset.km || '';
            document.getElementById('km_entrada').value = km;
        });

        document.getElementById('add-produto')?.addEventListener('click', () => addItemRow('produtos'));
        document.getElementById('add-servico')?.addEventListener('click', () => addItemRow('servicos'));

        document.getElementById('produtos-list')?.addEventListener('click', handleRemove);
        document.getElementById('servicos-list')?.addEventListener('click', handleRemove);

        osForm.addEventListener('input', (e) => {
             if (e.target.matches('.produto-qtd, .produto-preco, .servico-preco, #desconto, #deslocamento')) {
                calculateTotals();
            }
        });

        osForm.addEventListener('change', (e) => {
            if (e.target.matches('.autofill-select')) {
                const select = e.target;
                const selectedOption = select.options[select.selectedIndex];
                const row = select.closest('.item-row, .servico-row');

                if (selectedOption.value) {
                    row.querySelector('.item-nome').value = selectedOption.dataset.nome || '';
                    row.querySelector('.item-preco').value = selectedOption.dataset.price || '0.00';
                    row.querySelector('.item-codigo').value = selectedOption.dataset.codigo || '';
                }
                calculateTotals();
            }
        });

        calculateTotals();
    }

    // Lógica para formulário de Cliente (PF/PJ)
    document.querySelectorAll('.client-form').forEach(form => {
        const tipoClienteRadios = form.querySelectorAll('input[name="tipo_cliente"]');
        tipoClienteRadios.forEach(radio => {
            radio.addEventListener('change', () => toggleClienteFields(form));
        });
        toggleClienteFields(form); // Initial check
    });

    // Lógica para busca de CEP
    document.body.addEventListener('blur', async (event) => {
        if (event.target.matches('input[name="cep"]')) {
            const cepInput = event.target;
            const form = cepInput.closest('form');
            const cep = cepInput.value.replace(/\D/g, '');
            if (cep.length === 8) {
                try {
                    const response = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
                    if (!response.ok) throw new Error('CEP não encontrado');
                    const data = await response.json();
                    if (data.erro) {
                        alert('CEP não encontrado.');
                    } else {
                        form.querySelector('input[name="rua"]').value = data.logradouro;
                        form.querySelector('input[name="bairro"]').value = data.bairro;
                        form.querySelector('input[name="cidade"]').value = data.localidade;
                        form.querySelector('input[name="uf"]').value = data.uf;
                        form.querySelector('input[name="numero"]').focus();
                    }
                } catch (error) {
                    console.error("Erro ao buscar CEP:", error);
                    alert('Erro ao buscar CEP.');
                }
            }
        }
    }, true);

    // Lógica para salvar cliente/veículo via modal da OS (AJAX)
    handleAjaxFormSubmit('novoClienteFormOS', 'clientes/salvar', (data) => {
        const clienteSelect = document.getElementById('cliente_id');
        const newOption = new Option(data.nome, data.id, true, true);
        clienteSelect.add(newOption);
        clienteSelect.dispatchEvent(new Event('change'));
        document.querySelector('#novoClienteModalOS .btn-close').click();
    });

    handleAjaxFormSubmit('novoVeiculoFormOS', 'veiculos/salvar', (data) => {
        const veiculoSelect = document.getElementById('veiculo_id');
        const displayText = `${data.marca} ${data.modelo} - Placa: ${data.placa}`;
        const newOption = new Option(displayText, data.id, true, true);
        newOption.dataset.km = data.km_atual || '';
        veiculoSelect.add(newOption);
        veiculoSelect.dispatchEvent(new Event('change'));
        document.querySelector('#novoVeiculoModalOS .btn-close').click();
    }, () => {
        const clienteId = document.getElementById('cliente_id').value;
        if (!clienteId) {
            alert("Por favor, selecione um cliente primeiro.");
            return null;
        }
        const formData = new FormData(document.getElementById('novoVeiculoFormOS'));
        formData.set('cliente_id', clienteId);
        return formData;
    });
});

function handleAjaxFormSubmit(formId, endpoint, onSuccess, getFormDataCallback = null) {
    const form = document.getElementById(formId);
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            let body;
            if (getFormDataCallback) {
                body = getFormDataCallback();
                if (body === null) return;
            } else {
                body = new FormData(form);
            }

            try {
                const response = await fetch(`/${endpoint}`, {
                    method: 'POST',
                    body: body,
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                const data = await response.json();
                if (response.ok) {
                    onSuccess(data);
                } else {
                    alert(data.message || 'Ocorreu um erro.');
                }
            } catch (error) {
                console.error('Erro na submissão do formulário:', error);
                alert('Ocorreu um erro de comunicação com o servidor.');
            }
        });
    }
}


function toggleClienteFields(form) {
    const tipo = form.querySelector('input[name="tipo_cliente"]:checked')?.value;
    const pfFields = form.querySelector('.pf-fields');
    const pjFields = form.querySelector('.pj-fields');

    if (pfFields && pjFields) {
        if (tipo === 'pf') {
            pfFields.style.display = 'block';
            pjFields.style.display = 'none';
        } else {
            pfFields.style.display = 'none';
            pjFields.style.display = 'block';
        }
    }
}


function updateClock() {
    const timeElement = document.getElementById('time');
    const dateElement = document.getElementById('date');
    if (timeElement && dateElement) {
        const now = new Date();
        const optionsDate = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        dateElement.textContent = now.toLocaleDateString('pt-BR', optionsDate);
        timeElement.textContent = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
}

function fetchVeiculos(clienteId, veiculoSelect, selectedVeiculoId = null) {
    veiculoSelect.innerHTML = '<option value="">Carregando...</option>';
    if (!clienteId) {
        veiculoSelect.innerHTML = '<option value="">Selecione um cliente primeiro</option>';
        return;
    }

    fetch(`/api/veiculos_do_cliente/${clienteId}`)
        .then(response => response.json())
        .then(data => {
            veiculoSelect.innerHTML = '<option value="">Selecione um veículo</option>';
            data.forEach(veiculo => {
                const option = document.createElement('option');
                option.value = veiculo.id;
                option.textContent = `${veiculo.marca} ${veiculo.modelo} - Placa: ${veiculo.placa}`;
                option.dataset.km = veiculo.km_atual || '';
                if (veiculo.id === selectedVeiculoId) {
                    option.selected = true;
                }
                veiculoSelect.appendChild(option);
            });
             if (selectedVeiculoId) {
                veiculoSelect.value = selectedVeiculoId;
                veiculoSelect.dispatchEvent(new Event('change', { bubbles: true }));
             }
        })
        .catch(error => {
            console.error('Erro ao buscar veículos:', error);
            veiculoSelect.innerHTML = '<option value="">Erro ao carregar veículos</option>';
        });
}


function addItemRow(type) {
    const list = document.getElementById(`${type}-list`);
    const template = document.getElementById(`${type}-template`);
    if (template) {
        const clone = template.content.cloneNode(true);
        list.appendChild(clone);
    }
}

function handleRemove(event) {
    if (event.target.classList.contains('remove-item')) {
        event.target.closest('.item-row, .servico-row').remove();
        calculateTotals();
    }
}

function calculateTotals() {
    let subtotalProdutos = 0;
    let subtotalServicos = 0;

    document.querySelectorAll('#produtos-list .item-row').forEach(row => {
        const priceInput = row.querySelector('.produto-preco');
        const qtyInput = row.querySelector('.produto-qtd');
        const priceElement = row.querySelector('.item-total-price');

        const price = parseFloat(priceInput.value.replace(',', '.') || 0);
        const quantity = parseInt(qtyInput.value || 0);

        const itemTotal = price * quantity;
        subtotalProdutos += itemTotal;
        priceElement.textContent = formatCurrency(itemTotal);
    });

    document.querySelectorAll('#servicos-list .servico-row').forEach(row => {
        const priceInput = row.querySelector('.servico-preco');
        const priceElement = row.querySelector('.item-total-price');

        const price = parseFloat(priceInput.value.replace(',', '.') || 0);

        subtotalServicos += price;
        priceElement.textContent = formatCurrency(price);
    });

    const desconto = parseFloat(document.getElementById('desconto').value.replace(',', '.') || 0);
    const deslocamento = parseFloat(document.getElementById('deslocamento').value.replace(',', '.') || 0);
    const total = subtotalProdutos + subtotalServicos + deslocamento - desconto;

    document.getElementById('subtotal-produtos-val').textContent = formatCurrency(subtotalProdutos);
    document.getElementById('subtotal-servicos-val').textContent = formatCurrency(subtotalServicos);
    document.getElementById('total-val').textContent = formatCurrency(total);

    document.getElementById('subtotal_produtos').value = subtotalProdutos.toFixed(2);
    document.getElementById('subtotal_servicos').value = subtotalServicos.toFixed(2);
    document.getElementById('total').value = total.toFixed(2);
}

function formatCurrency(value) {
    if (isNaN(value)) value = 0;
    return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

const reportForm = document.getElementById('report-form');
if (reportForm) {
    const reportTypeSelect = document.getElementById('tipo_relatorio');
    const clienteFilter = document.getElementById('cliente-filter');
    const veiculoFilter = document.getElementById('veiculo-filter');

    function toggleFilters() {
        const type = reportTypeSelect.value;
        clienteFilter.style.display = 'none';
        veiculoFilter.style.display = 'none';

        if (type === 'historico_cliente') {
            clienteFilter.style.display = 'block';
        } else if (type === 'servicos_veiculo') {
            veiculoFilter.style.display = 'block';
        }
    }
    reportTypeSelect.addEventListener('change', toggleFilters);
    toggleFilters();
}