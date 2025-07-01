import os
import json
import uuid
import re
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for, flash, 
                   jsonify, session, send_from_directory, send_file)
from werkzeug.utils import secure_filename
import zipfile
import io

# --- Configuração da Aplicação ---
app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_super_segura_e_avancada'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Funções Helper para Manipulação de Dados ---
DATA_DIR = 'data'

def get_data_path(filename):
    return os.path.join(DATA_DIR, filename)

def load_data(filename):
    """Carrega dados de um arquivo JSON."""
    filepath = get_data_path(filename)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_data(filename, data):
    """Salva dados em um arquivo JSON."""
    filepath = get_data_path(filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_config():
    """Carrega as configurações da oficina."""
    filepath = get_data_path('configuracao.json')
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Garante que a configuração da OS exista para compatibilidade
            if 'os_config' not in config:
                config['os_config'] = {
                    "exibir_logo": True, "exibir_data_hora": True, "exibir_endereco_cliente": True,
                    "exibir_contato_cliente": True, "exibir_cpf_cnpj": True, "exibir_veiculo_cor": True,
                    "exibir_veiculo_ano": True, "exibir_veiculo_km": True, "exibir_veiculo_combustivel": True,
                    "exibir_box": True, "exibir_mecanico": True, "exibir_condicoes_pagamento": True,
                    "texto_rodape": "ESTE DOCUMENTO NÃO VALE COMO RECIBO DE PAGAMENTO"
                }
                save_config(config)
            return config
    except (FileNotFoundError, json.JSONDecodeError):
        # Cria uma configuração padrão se o arquivo não existir ou for inválido
        default_config = {
            "nome_oficina": "Sua Oficina", "cnpj": "00.000.000/0001-00", "telefone": "(00) 00000-0000",
            "endereco": "Endereço Padrão, 123", "logo_path": None, "username": "admin", "password": "admin",
            "os_config": {
                "exibir_logo": True, "exibir_data_hora": True, "exibir_endereco_cliente": True,
                "exibir_contato_cliente": True, "exibir_cpf_cnpj": True, "exibir_veiculo_cor": True,
                "exibir_veiculo_ano": True, "exibir_veiculo_km": True, "exibir_veiculo_combustivel": True,
                "exibir_box": True, "exibir_mecanico": True, "exibir_condicoes_pagamento": True,
                "texto_rodape": "ESTE DOCUMENTO NÃO VALE COMO RECIBO DE PAGAMENTO"
            }
        }
        save_data('configuracao.json', default_config)
        return default_config

def save_config(config_data):
    """Salva as configurações da oficina."""
    save_data('configuracao.json', config_data)

# --- Funções de Utilitários ---
def generate_code(prefix, filename):
    """Gera um código sequencial para novos itens (Produtos, Serviços)."""
    data = load_data(filename)
    if not data:
        return f"{prefix}0001"

    codes = [int(re.sub(r'\D', '', item.get('codigo', f'{prefix}0000'))) for item in data]
    last_number = max(codes) if codes else 0
    new_number = last_number + 1
    return f"{prefix}{new_number:04d}"

def format_currency(value):
    """Formata um valor float para a moeda brasileira (R$)."""
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "R$ 0,00"

def find_by_id(filename, item_id):
    """Encontra um item pelo seu UUID em um arquivo JSON."""
    if not item_id: return None
    data = load_data(filename)
    for item in data:
        if item.get('id') == item_id:
            return item
    return None

# --- Funções de Validação ---
def validate_cpf(cpf):
    """Valida um CPF."""
    cpf = ''.join(re.findall(r'\d', str(cpf)))
    if not cpf or len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    if resto == 10: resto = 0
    if resto != int(cpf[9]): return False
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    if resto == 10: resto = 0
    if resto != int(cpf[10]): return False
    return True

def validate_cnpj(cnpj):
    """Valida um CNPJ."""
    cnpj = ''.join(re.findall(r'\d', str(cnpj)))
    if len(cnpj) != 14 or cnpj in [s * 14 for s in "0123456789"]:
        return False

    def validate_digit(digits, weights):
        soma = sum(int(d) * w for d, w in zip(digits, weights))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    digito1 = validate_digit(cnpj[:12], pesos1)
    if digito1 != int(cnpj[12]): return False

    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    digito2 = validate_digit(cnpj[:13], pesos2)
    if digito2 != int(cnpj[13]): return False

    return True

def validate_placa(placa):
    """Valida placas de veículo (padrão antigo e Mercosul)."""
    placa = str(placa).upper().strip().replace('-', '')
    padrao_antigo = re.compile(r"^[A-Z]{3}[0-9]{4}$")
    padrao_mercosul = re.compile(r"^[A-Z]{3}[0-9][A-Z][0-9]{2}$")
    return bool(padrao_antigo.match(placa) or padrao_mercosul.match(placa))

# --- Decorador de Autenticação ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash("Por favor, faça login para acessar esta página.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Context Processor para Injetar Dados em Todos os Templates ---
@app.context_processor
def inject_global_vars():
    config = get_config()
    return dict(
        nome_oficina=config.get('nome_oficina'),
        logo_path=config.get('logo_path'),
        format_currency=format_currency
    )

# --- Rotas de Autenticação ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        config = get_config()
        username = request.form['username']
        password = request.form['password']

        if username == config.get('username') and password == config.get('password'):
            session['logged_in'] = True
            flash("Login realizado com sucesso!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Credenciais inválidas. Tente novamente.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash("Você foi desconectado.", "info")
    return redirect(url_for('login'))

# --- Rotas Principais ---
@app.route('/')
@login_required
def dashboard():
    ordens = load_data('ordens.json')
    veiculos = load_data('veiculos.json')

    now = datetime.now()
    mes_atual = now.month
    ano_atual = now.year

    faturamento_mes = sum(
        float(o.get('total', 0)) for o in ordens 
        if o.get('status_pagamento') == 'Pago' and o.get('data_conclusao') and
           datetime.strptime(o.get('data_conclusao'), '%Y-%m-%d').month == mes_atual and
           datetime.strptime(o.get('data_conclusao'), '%Y-%m-%d').year == ano_atual
    )

    os_concluidas_mes = sum(
        1 for o in ordens
        if o.get('status') == 'Concluído' and o.get('data_conclusao') and
           datetime.strptime(o.get('data_conclusao'), '%Y-%m-%d').month == mes_atual and
           datetime.strptime(o.get('data_conclusao'), '%Y-%m-%d').year == ano_atual
    )

    os_abertas = sum(1 for o in ordens if o.get('status') not in ['Concluído', 'Cancelado'])

    veiculos_cadastrados = len(veiculos) 

    stats = {
        'faturamento_mes': faturamento_mes,
        'os_concluidas_mes': os_concluidas_mes,
        'os_abertas': os_abertas,
        'veiculos_cadastrados': veiculos_cadastrados
    }

    return render_template('dashboard.html', stats=stats)

# --- ROTAS DE CLIENTES ---
@app.route('/clientes')
@login_required
def clientes():
    query = request.args.get('q', '')
    clientes_data = load_data('clientes.json')

    if query:
        clientes_filtrados = [
            cliente for cliente in clientes_data if 
            query.lower() in cliente.get('nome', '').lower() or
            query.lower() in (cliente.get('cpf') or '').lower() or
            query.lower() in (cliente.get('cnpj') or '').lower() or
            query.lower() in (cliente.get('telefone') or '').lower()
        ]
    else:
        clientes_filtrados = clientes_data

    return render_template('clientes.html', clientes=clientes_filtrados, query=query)

@app.route('/clientes/detalhes/<item_id>')
@login_required
def detalhes_cliente(item_id):
    cliente = find_by_id('clientes.json', item_id)
    if not cliente:
        flash('Cliente não encontrado.', 'danger')
        return redirect(url_for('clientes'))

    veiculos = [v for v in load_data('veiculos.json') if v.get('cliente_id') == item_id]
    ordens = [o for o in load_data('ordens.json') if o.get('cliente_id') == item_id]

    for ordem in ordens:
        veiculo_os = find_by_id('veiculos.json', ordem.get('veiculo_id'))
        ordem['veiculo_placa'] = veiculo_os['placa'] if veiculo_os else 'N/A'

    return render_template('cliente_detalhes.html', cliente=cliente, veiculos=veiculos, ordens=ordens)

@app.route('/clientes/salvar', methods=['POST'])
@login_required
def salvar_cliente():
    item_id = request.form.get('id')
    tipo_cliente = request.form.get('tipo_cliente')
    cpf = request.form.get('cpf', '').strip()
    cnpj = request.form.get('cnpj', '').strip()

    clientes_data = load_data('clientes.json')

    if tipo_cliente == 'pf' and cpf:
        if any(c.get('cpf') == cpf and c.get('id') != item_id for c in clientes_data):
            error_message = f'Erro: CPF {cpf} já cadastrado.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': error_message}), 400
            flash(error_message, 'danger')
            return redirect(url_for('clientes'))

    elif tipo_cliente == 'pj' and cnpj:
        if any(c.get('cnpj') == cnpj and c.get('id') != item_id for c in clientes_data):
            error_message = f'Erro: CNPJ {cnpj} já cadastrado.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': error_message}), 400
            flash(error_message, 'danger')
            return redirect(url_for('clientes'))

    if (tipo_cliente == 'pf' and cpf and not validate_cpf(cpf)):
        error_message = 'CPF inválido.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': error_message}), 400
        flash(error_message, 'danger')
        return redirect(url_for('clientes'))
    elif (tipo_cliente == 'pj' and cnpj and not validate_cnpj(cnpj)):
        error_message = 'CNPJ inválido.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': error_message}), 400
        flash(error_message, 'danger')
        return redirect(url_for('clientes'))

    dados_cliente = {
        'tipo_cliente': tipo_cliente, 'nome': request.form['nome'],
        'nome_fantasia': request.form.get('nome_fantasia'),
        'cpf': cpf if tipo_cliente == 'pf' else '', 'rg': request.form.get('rg'),
        'cnpj': cnpj if tipo_cliente == 'pj' else '', 'ie': request.form.get('ie'),
        'telefone': request.form['telefone'], 'email': request.form['email'],
        'cep': request.form.get('cep'), 'rua': request.form.get('rua'),
        'numero': request.form.get('numero'), 'bairro': request.form.get('bairro'),
        'cidade': request.form.get('cidade'), 'uf': request.form.get('uf'),
        'status': request.form.get('status', 'Liberado')
    }

    if item_id:
        for i, cliente in enumerate(clientes_data):
            if cliente['id'] == item_id:
                clientes_data[i].update(dados_cliente)
                novo_cliente_obj = clientes_data[i]
                break
        flash('Cliente atualizado com sucesso!', 'success')
    else:
        dados_cliente['id'] = str(uuid.uuid4())
        dados_cliente['data_cadastro'] = datetime.now().strftime('%Y-%m-%d')
        clientes_data.append(dados_cliente)
        flash('Cliente cadastrado com sucesso!', 'success')
        novo_cliente_obj = dados_cliente

    save_data('clientes.json', clientes_data)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(novo_cliente_obj)

    next_url = request.args.get('next')
    return redirect(next_url) if next_url else redirect(url_for('clientes'))

@app.route('/clientes/deletar/<item_id>', methods=['POST'])
@login_required
def deletar_cliente(item_id):
    clientes_data = load_data('clientes.json')
    clientes_data = [c for c in clientes_data if c['id'] != item_id]
    save_data('clientes.json', clientes_data)
    flash('Cliente deletado com sucesso!', 'success')
    return redirect(url_for('clientes'))

@app.route('/clientes/imprimir/<item_id>')
@login_required
def imprimir_ficha_cliente(item_id):
    cliente = find_by_id('clientes.json', item_id)
    config = get_config()
    if not cliente:
        flash('Cliente não encontrado.', 'danger')
        return redirect(url_for('clientes'))
    return render_template('cliente_print.html', cliente=cliente, config=config)

# --- CRUD VEÍCULOS ---
@app.route('/veiculos')
@login_required
def veiculos():
    query = request.args.get('q', '')
    veiculos_data = load_data('veiculos.json')
    clientes_data = load_data('clientes.json')

    if query:
        veiculos_filtrados = [
            v for v in veiculos_data if
            query.lower() in v.get('placa', '').lower() or
            query.lower() in v.get('marca', '').lower() or
            query.lower() in v.get('modelo', '').lower()
        ]
    else:
        veiculos_filtrados = veiculos_data

    for veiculo in veiculos_filtrados:
        cliente = find_by_id('clientes.json', veiculo.get('cliente_id'))
        veiculo['cliente_nome'] = cliente['nome'] if cliente else "Cliente não encontrado"

    return render_template('veiculos.html', veiculos=veiculos_filtrados, clientes=clientes_data, query=query)

@app.route('/veiculos/detalhes/<item_id>')
@login_required
def detalhes_veiculo(item_id):
    veiculo = find_by_id('veiculos.json', item_id)
    if not veiculo:
        flash('Veículo não encontrado.', 'danger')
        return redirect(url_for('veiculos'))

    proprietario = find_by_id('clientes.json', veiculo.get('cliente_id'))
    ordens = [o for o in load_data('ordens.json') if o.get('veiculo_id') == item_id]

    return render_template('veiculo_detalhes.html', veiculo=veiculo, proprietario=proprietario, ordens=ordens)

@app.route('/veiculos/salvar', methods=['POST'])
@login_required
def salvar_veiculo():
    item_id = request.form.get('id')
    placa = request.form.get('placa', '').upper().replace('-', '')

    veiculos_data = load_data('veiculos.json')

    if any(v.get('placa') == placa and v.get('id') != item_id for v in veiculos_data):
        error_message = f'Erro: Placa {placa} já cadastrada.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': error_message}), 400
        flash(error_message, 'danger')
        return redirect(url_for('veiculos'))

    if not validate_placa(placa):
        error_message = 'Placa de veículo inválida.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': error_message}), 400
        flash(error_message, 'danger')
        return redirect(url_for('veiculos'))

    dados_veiculo = {
        'placa': placa, 'marca': request.form['marca'], 'modelo': request.form['modelo'],
        'ano': request.form['ano'], 'cor': request.form['cor'],
        'cliente_id': request.form['cliente_id'], 'km_atual': request.form.get('km_atual'),
        'combustivel': request.form.get('combustivel'), 'chassi': request.form.get('chassi'),
        'motor': request.form.get('motor')
    }

    if item_id:
        for i, veiculo in enumerate(veiculos_data):
            if veiculo['id'] == item_id:
                veiculos_data[i].update(dados_veiculo)
                novo_veiculo_obj = veiculos_data[i]
                break
        flash('Veículo atualizado com sucesso!', 'success')
    else:
        dados_veiculo['id'] = str(uuid.uuid4())
        veiculos_data.append(dados_veiculo)
        flash('Veículo cadastrado com sucesso!', 'success')
        novo_veiculo_obj = dados_veiculo

    save_data('veiculos.json', veiculos_data)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(novo_veiculo_obj)

    next_url = request.args.get('next')
    return redirect(next_url) if next_url else redirect(url_for('veiculos'))


@app.route('/veiculos/deletar/<item_id>', methods=['POST'])
@login_required
def deletar_veiculo(item_id):
    veiculos_data = load_data('veiculos.json')
    veiculos_data = [v for v in veiculos_data if v['id'] != item_id]
    save_data('veiculos.json', veiculos_data)
    flash('Veículo deletado com sucesso!', 'success')
    return redirect(url_for('veiculos'))

@app.route('/veiculos/imprimir/<item_id>')
@login_required
def imprimir_ficha_veiculo(item_id):
    veiculo = find_by_id('veiculos.json', item_id)
    config = get_config()
    if not veiculo:
        flash('Veículo não encontrado.', 'danger')
        return redirect(url_for('veiculos'))

    proprietario = find_by_id('clientes.json', veiculo.get('cliente_id'))
    ordens = [o for o in load_data('ordens.json') if o.get('veiculo_id') == item_id]

    return render_template('veiculo_print.html', veiculo=veiculo, proprietario=proprietario, ordens=ordens, config=config)


# --- CRUD Produtos ---
@app.route('/produtos')
@login_required
def produtos():
    lista_produtos = load_data('produtos.json')
    return render_template('produtos.html', produtos=lista_produtos)

@app.route('/produtos/novo', methods=['POST'])
@login_required
def novo_produto():
    produtos_data = load_data('produtos.json')
    novo = {
        'id': str(uuid.uuid4()), 'codigo': generate_code('P', 'produtos.json'),
        'nome': request.form['nome'], 'descricao': request.form['descricao'],
        'preco': float(request.form['preco'].replace(',', '.')), 'estoque': int(request.form['estoque'])
    }
    produtos_data.append(novo)
    save_data('produtos.json', produtos_data)
    flash('Produto cadastrado com sucesso!', 'success')
    return redirect(url_for('produtos'))

@app.route('/produtos/editar/<item_id>', methods=['POST'])
@login_required
def editar_produto(item_id):
    produtos_data = load_data('produtos.json')
    for produto in produtos_data:
        if produto['id'] == item_id:
            produto['nome'] = request.form['nome']
            produto['descricao'] = request.form['descricao']
            produto['preco'] = float(request.form['preco'].replace(',', '.'))
            produto['estoque'] = int(request.form['estoque'])
            break
    save_data('produtos.json', produtos_data)
    flash('Produto atualizado com sucesso!', 'success')
    return redirect(url_for('produtos'))

@app.route('/produtos/deletar/<item_id>', methods=['POST'])
@login_required
def deletar_produto(item_id):
    produtos_data = load_data('produtos.json')
    produtos_data = [p for p in produtos_data if p['id'] != item_id]
    save_data('produtos.json', produtos_data)
    flash('Produto deletado com sucesso!', 'success')
    return redirect(url_for('produtos'))

# --- CRUD Serviços ---
@app.route('/servicos')
@login_required
def servicos():
    lista_servicos = load_data('servicos.json')
    return render_template('servicos.html', servicos=lista_servicos)

@app.route('/servicos/novo', methods=['POST'])
@login_required
def novo_servico():
    servicos_data = load_data('servicos.json')
    novo = {
        'id': str(uuid.uuid4()), 'codigo': generate_code('S', 'servicos.json'),
        'nome': request.form['nome'], 'descricao': request.form['descricao'],
        'preco': float(request.form['preco'].replace(',', '.'))
    }
    servicos_data.append(novo)
    save_data('servicos.json', servicos_data)
    flash('Serviço cadastrado com sucesso!', 'success')
    return redirect(url_for('servicos'))

@app.route('/servicos/editar/<item_id>', methods=['POST'])
@login_required
def editar_servico(item_id):
    servicos_data = load_data('servicos.json')
    for servico in servicos_data:
        if servico['id'] == item_id:
            servico['nome'] = request.form['nome']
            servico['descricao'] = request.form['descricao']
            servico['preco'] = float(request.form['preco'].replace(',', '.'))
            break
    save_data('servicos.json', servicos_data)
    flash('Serviço atualizado com sucesso!', 'success')
    return redirect(url_for('servicos'))

@app.route('/servicos/deletar/<item_id>', methods=['POST'])
@login_required
def deletar_servico(item_id):
    servicos_data = load_data('servicos.json')
    servicos_data = [s for s in servicos_data if s['id'] != item_id]
    save_data('servicos.json', servicos_data)
    flash('Serviço deletado com sucesso!', 'success')
    return redirect(url_for('servicos'))

# --- CRUD Mecânicos ---
@app.route('/mecanicos')
@login_required
def mecanicos():
    lista_mecanicos = load_data('mecanicos.json')
    return render_template('mecanicos.html', mecanicos=lista_mecanicos)

@app.route('/mecanicos/novo', methods=['POST'])
@login_required
def novo_mecanico():
    mecanicos_data = load_data('mecanicos.json')
    novo = {'id': str(uuid.uuid4()), 'nome': request.form['nome'], 'especialidade': request.form['especialidade']}
    mecanicos_data.append(novo)
    save_data('mecanicos.json', mecanicos_data)
    flash('Mecânico cadastrado com sucesso!', 'success')
    return redirect(url_for('mecanicos'))

@app.route('/mecanicos/editar/<item_id>', methods=['POST'])
@login_required
def editar_mecanico(item_id):
    mecanicos_data = load_data('mecanicos.json')
    for mecanico in mecanicos_data:
        if mecanico['id'] == item_id:
            mecanico['nome'] = request.form['nome']
            mecanico['especialidade'] = request.form['especialidade']
            break
    save_data('mecanicos.json', mecanicos_data)
    flash('Mecânico atualizado com sucesso!', 'success')
    return redirect(url_for('mecanicos'))

@app.route('/mecanicos/deletar/<item_id>', methods=['POST'])
@login_required
def deletar_mecanico(item_id):
    mecanicos_data = load_data('mecanicos.json')
    mecanicos_data = [m for m in mecanicos_data if m['id'] != item_id]
    save_data('mecanicos.json', mecanicos_data)
    flash('Mecânico deletado com sucesso!', 'success')
    return redirect(url_for('mecanicos'))

# --- Ordens de Serviço (Avançado) ---
@app.route('/ordens')
@login_required
def ordens():
    ordens_data = load_data('ordens.json')
    for ordem in ordens_data:
        cliente = find_by_id('clientes.json', ordem.get('cliente_id'))
        veiculo = find_by_id('veiculos.json', ordem.get('veiculo_id'))
        ordem['cliente_nome'] = cliente['nome'] if cliente else 'N/A'
        ordem['veiculo_placa'] = veiculo['placa'] if veiculo else 'N/A'
    return render_template('ordens.html', ordens=ordens_data)

@app.route('/ordens/form', methods=['GET'])
@app.route('/ordens/form/<item_id>', methods=['GET'])
@login_required
def ordem_form(item_id=None):
    ordem = find_by_id('ordens.json', item_id) if item_id else {}
    title = f"Editar Ordem de Serviço #{ordem.get('numero_os')}" if item_id else "Nova Ordem de Serviço"

    clientes = load_data('clientes.json')
    veiculos = load_data('veiculos.json')
    mecanicos = load_data('mecanicos.json')
    produtos = load_data('produtos.json')
    servicos = load_data('servicos.json')

    return render_template('ordem_form.html', 
                           ordem=ordem, title=title,
                           clientes=clientes, veiculos=veiculos, mecanicos=mecanicos,
                           produtos=produtos, servicos=servicos)

@app.route('/ordens/salvar', methods=['POST'])
@login_required
def salvar_ordem():
    def safe_float(s, default=0.0):
        if not s:
            return default
        try:
            return float(str(s).replace(',', '.'))
        except (ValueError, TypeError):
            return default

    ordens_data = load_data('ordens.json')
    item_id = request.form.get('id')

    produtos_selecionados = []
    prod_nomes = request.form.getlist('produto_nome')
    prod_precos = request.form.getlist('produto_preco')
    prod_qtds = request.form.getlist('produto_qtd')
    prod_codigos = request.form.getlist('produto_codigo')

    for i, nome in enumerate(prod_nomes):
        if not nome or not prod_precos[i] or not prod_qtds[i]:
            continue
        produtos_selecionados.append({
            'codigo': prod_codigos[i], 'nome': nome,
            'preco': safe_float(prod_precos[i]), 'quantidade': int(prod_qtds[i])
        })

    servicos_selecionados = []
    serv_nomes = request.form.getlist('servico_nome')
    serv_precos = request.form.getlist('servico_preco')
    serv_codigos = request.form.getlist('servico_codigo')

    for i, nome in enumerate(serv_nomes):
        if not nome or not serv_precos[i]:
            continue
        servicos_selecionados.append({
            'codigo': serv_codigos[i], 'nome': nome, 'preco': safe_float(serv_precos[i])
        })

    dados_ordem = {
        'cliente_id': request.form['cliente_id'], 'veiculo_id': request.form['veiculo_id'],
        'mecanico_id': request.form['mecanico_id'],
        'problema_relatado': request.form['problema_relatado'],
        'diagnostico_tecnico': request.form.get('diagnostico_tecnico'),
        'data_entrada': request.form.get('data_entrada'),
        'data_saida': request.form.get('data_saida'),
        'data_entrada': request.form.get('data_entrada'),
        'data_saida': request.form.get('data_saida'),
        'km_entrada': request.form.get('km_entrada'),
        'produtos': produtos_selecionados, 'servicos': servicos_selecionados,
        'subtotal_produtos': safe_float(request.form.get('subtotal_produtos', 0)),
        'subtotal_servicos': safe_float(request.form.get('subtotal_servicos', 0)),
        'desconto': safe_float(request.form.get('desconto', 0)),
        'deslocamento': safe_float(request.form.get('deslocamento', 0)),
        'total': safe_float(request.form.get('total', 0)),
        'status': request.form['status'],
        'forma_pagamento': request.form.get('forma_pagamento'),
        'status_pagamento': request.form.get('status_pagamento'),
        'condicoes_pagamento': request.form.get('condicoes_pagamento'),
        'box': request.form.get('box'),
        'data_conclusao': None
    }

    status_atual = dados_ordem['status']
    if status_atual in ['Concluído', 'Finalizado']:
        dados_ordem['data_conclusao'] = datetime.now().strftime('%Y-%m-%d')
    else:
        dados_ordem['data_conclusao'] = None

    if item_id: # Edição
        for i, o in enumerate(ordens_data):
            if o['id'] == item_id:
                if status_atual in ['Concluído', 'Finalizado'] and not o.get('data_conclusao'):
                     dados_ordem['data_conclusao'] = datetime.now().strftime('%Y-%m-%d')
                else:
                     dados_ordem['data_conclusao'] = o.get('data_conclusao')

                if status_atual not in ['Concluído', 'Finalizado']:
                    dados_ordem['data_conclusao'] = None

                ordens_data[i].update(dados_ordem)
                break
        flash('Ordem de Serviço atualizada com sucesso!', 'success')
    else: # Novo
        dados_ordem['id'] = str(uuid.uuid4())
        dados_ordem['numero_os'] = (max([int(o.get('numero_os', 0)) for o in ordens_data]) + 1) if ordens_data else 1
        dados_ordem['data_abertura'] = datetime.now().strftime('%Y-%m-%d')
        ordens_data.append(dados_ordem)
        flash('Ordem de Serviço criada com sucesso!', 'success')

    save_data('ordens.json', ordens_data)
    return redirect(url_for('ordens'))


@app.route('/ordens/deletar/<item_id>', methods=['POST'])
@login_required
def deletar_ordem(item_id):
    ordens_data = load_data('ordens.json')
    ordens_data = [o for o in ordens_data if o['id'] != item_id]
    save_data('ordens.json', ordens_data)
    flash('Ordem de Serviço deletada com sucesso!', 'success')
    return redirect(url_for('ordens'))

@app.route('/ordens/imprimir/<item_id>')
@login_required
def imprimir_ordem(item_id):
    ordem = find_by_id('ordens.json', item_id)
    if not ordem:
        flash('Ordem de Serviço não encontrada.', 'danger')
        return redirect(url_for('ordens'))

    config = get_config()
    cliente = find_by_id('clientes.json', ordem.get('cliente_id'))
    veiculo = find_by_id('veiculos.json', ordem.get('veiculo_id'))
    mecanico = find_by_id('mecanicos.json', ordem.get('mecanico_id'))

    now = datetime.now()

    return render_template('ordem_print.html', 
                           ordem=ordem, config=config, cliente=cliente, 
                           veiculo=veiculo, mecanico=mecanico, now=now)

@app.route('/api/veiculos_do_cliente/<cliente_id>')
@login_required
def veiculos_do_cliente(cliente_id):
    """API para buscar veículos de um cliente específico."""
    todos_veiculos = load_data('veiculos.json')
    veiculos_cliente = [v for v in todos_veiculos if v.get('cliente_id') == cliente_id]
    return jsonify(veiculos_cliente)

# --- Financeiro ---
@app.route('/financeiro')
@login_required
def financeiro():
    contas = load_data('contas.json')
    ordens = load_data('ordens.json')

    contas_pagar = [c for c in contas if c.get('tipo') == 'Pagar']
    contas_receber_os = [o for o in ordens if o.get('status') in ['Concluído', 'Finalizado'] and o.get('status_pagamento') != 'Pago']

    for o in contas_receber_os:
        cliente = find_by_id('clientes.json', o.get('cliente_id'))
        o['cliente_nome'] = cliente['nome'] if cliente else 'N/A'

    return render_template('financeiro.html', contas_pagar=contas_pagar, contas_receber_os=contas_receber_os)

@app.route('/financeiro/nova_conta', methods=['POST'])
@login_required
def nova_conta():
    contas = load_data('contas.json')
    nova = {
        'id': str(uuid.uuid4()), 'descricao': request.form['descricao'],
        'valor': float(request.form['valor'].replace(',', '.')), 'data_vencimento': request.form['data_vencimento'],
        'status': 'Pendente', 'tipo': 'Pagar'
    }
    contas.append(nova)
    save_data('contas.json', contas)
    flash('Conta a pagar cadastrada com sucesso!', 'success')
    next_url = request.args.get('next')
    return redirect(next_url) if next_url else redirect(url_for('financeiro'))

@app.route('/financeiro/pagar_conta/<item_id>', methods=['POST'])
@login_required
def pagar_conta(item_id):
    contas = load_data('contas.json')
    for conta in contas:
        if conta['id'] == item_id:
            conta['status'] = 'Pago'
            break
    save_data('contas.json', contas)
    flash('Conta marcada como paga!', 'success')
    return redirect(url_for('financeiro'))

@app.route('/financeiro/pagar_os/<item_id>', methods=['POST'])
@login_required
def pagar_os(item_id):
    ordens = load_data('ordens.json')
    for ordem in ordens:
        if ordem['id'] == item_id:
            ordem['status_pagamento'] = 'Pago'
            ordem['forma_pagamento'] = request.form.get('forma_pagamento', ordem.get('forma_pagamento', 'N/A'))
            if not ordem.get('data_conclusao'):
                ordem['data_conclusao'] = datetime.now().strftime('%Y-%m-%d')
            break
    save_data('ordens.json', ordens)
    flash('Ordem de Serviço marcada como paga!', 'success')
    return redirect(url_for('financeiro'))

# --- Relatórios ---
@app.route('/relatorios', methods=['GET', 'POST'])
@login_required
def relatorios():
    dados = None
    if request.method == 'POST':
        tipo_relatorio = request.form.get('tipo_relatorio')
        data_inicio = request.form.get('data_inicio')
        data_fim = request.form.get('data_fim')
        cliente_id = request.form.get('cliente_id')
        veiculo_id = request.form.get('veiculo_id')

        dados = gerar_dados_relatorio(tipo_relatorio, data_inicio, data_fim, cliente_id, veiculo_id)

    clientes = load_data('clientes.json')
    veiculos = load_data('veiculos.json')

    return render_template('relatorios.html', 
                           show_results=request.method == 'POST',
                           dados=dados,
                           clientes=clientes,
                           veiculos=veiculos,
                           form_data=request.form)


def gerar_dados_relatorio(tipo, inicio, fim, cliente_id=None, veiculo_id=None):
    if not (inicio and fim): return {'items': [], 'total_geral': 0}
    ordens = load_data('ordens.json')
    dt_inicio = datetime.strptime(inicio, '%Y-%m-%d')
    dt_fim = datetime.strptime(fim, '%Y-%m-%d')

    resultados = []
    total_geral = 0

    for ordem in ordens:
        data_os_str = ordem.get('data_conclusao') or ordem.get('data_abertura')
        data_os = datetime.strptime(data_os_str, '%Y-%m-%d')

        if not (dt_inicio <= data_os <= dt_fim): continue

        add = False
        if tipo == 'faturamento' and ordem.get('status_pagamento') == 'Pago':
            add = True
        elif tipo == 'servicos_veiculo' and veiculo_id and ordem.get('veiculo_id') == veiculo_id:
            add = True
        elif tipo == 'historico_cliente' and cliente_id and ordem.get('cliente_id') == cliente_id:
            add = True

        if add:
            resultados.append(ordem)
            total_geral += float(ordem.get('total', 0))

    for r in resultados:
        cliente = find_by_id('clientes.json', r.get('cliente_id'))
        veiculo = find_by_id('veiculos.json', r.get('veiculo_id'))
        r['cliente_nome'] = cliente['nome'] if cliente else 'N/A'
        r['veiculo_placa'] = veiculo['placa'] if veiculo else 'N/A'

    return {'items': resultados, 'total_geral': total_geral}

# --- Configurações ---
@app.route('/configuracoes', methods=['GET', 'POST'])
@login_required
def configuracoes():
    config = get_config()
    if request.method == 'POST':
        config['nome_oficina'] = request.form['nome_oficina']
        config['cnpj'] = request.form['cnpj']
        config['telefone'] = request.form['telefone']
        config['endereco'] = request.form['endereco']
        config['username'] = request.form['username']

        if request.form.get('password'):
            config['password'] = request.form['password']

        if 'logo' in request.files:
            file = request.files['logo']
            if file.filename != '':
                if config.get('logo_path'): # Remove o logo antigo se existir
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], config['logo_path']))
                    except OSError:
                        pass # Ignora se o arquivo não for encontrado

                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(save_path)
                config['logo_path'] = unique_filename

        save_config(config)
        flash('Configurações salvas com sucesso!', 'success')
        return redirect(url_for('configuracoes'))

    return render_template('configuracoes.html', config=config)

@app.route('/configuracoes_os', methods=['GET', 'POST'])
@login_required
def configuracoes_os():
    config = get_config()
    if request.method == 'POST':
        os_config = config.get('os_config', {})

        possible_keys = [
            'exibir_logo', 'exibir_data_hora', 'exibir_endereco_cliente',
            'exibir_contato_cliente', 'exibir_cpf_cnpj', 'exibir_veiculo_cor',
            'exibir_veiculo_ano', 'exibir_veiculo_km', 'exibir_veiculo_combustivel',
            'exibir_box', 'exibir_mecanico', 'exibir_condicoes_pagamento'
        ]
        for key in possible_keys:
            os_config[key] = key in request.form

        os_config['texto_rodape'] = request.form.get('texto_rodape', '')

        config['os_config'] = os_config
        save_config(config)
        flash('Configurações da O.S. salvas com sucesso!', 'success')
        return redirect(url_for('configuracoes_os'))

    return render_template('configuracoes_os.html', config=config)

# --- Backup e Restauração ---
@app.route('/backup', methods=['GET', 'POST'])
@login_required
def backup():
    if request.method == 'POST':
        if 'backup_file' not in request.files or not request.files['backup_file'].filename:
            flash('Nenhum arquivo selecionado para restauração.', 'danger')
            return redirect(request.url)

        file = request.files['backup_file']
        if file and file.filename.endswith('.zip'):
            try:
                with zipfile.ZipFile(file, 'r') as zip_ref:
                    expected_files = {f"{f}.json" for f in ['clientes', 'veiculos', 'produtos', 'servicos', 'ordens', 'contas', 'mecanicos', 'configuracao']}
                    zip_files = set(os.path.basename(info.filename) for info in zip_ref.infolist())

                    if not expected_files.issubset(zip_files):
                         flash('Arquivo de backup inválido ou corrompido. Faltam arquivos essenciais.', 'danger')
                         return redirect(url_for('backup'))

                    zip_ref.extractall(DATA_DIR)
                flash('Restauração concluída com sucesso! Os dados foram substituídos.', 'success')
            except Exception as e:
                flash(f'Ocorreu um erro durante a restauração: {e}', 'danger')
            return redirect(url_for('dashboard'))
        else:
            flash('Formato de arquivo inválido. Por favor, envie um arquivo .zip.', 'warning')

    return render_template('backup.html')

@app.route('/backup/download')
@login_required
def download_backup():
    """Cria um zip da pasta 'data' e o oferece para download."""
    data = io.BytesIO()
    with zipfile.ZipFile(data, mode='w', compression=zipfile.ZIP_DEFLATED) as z:
        for filename in os.listdir(DATA_DIR):
            if filename.endswith('.json'):
                z.write(os.path.join(DATA_DIR, filename), arcname=filename)

    data.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(data, mimetype='application/zip', as_attachment=True, download_name=f'backup_oficina_{timestamp}.zip')

# --- Servir arquivos estáticos e uploads ---
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)