# Eco-Awareness 2026 - Checkpoint 2

Projeto completo em Flask + Oracle para o desafio **Programa de Cashback Progressivo**.

## O que o projeto entrega

- Backend em **Python Flask**
- Interface web em **HTML + CSS**
- Integração com **Oracle Database**
- Uso obrigatório de **CURSOR EXPLÍCITO em bloco anônimo PL/SQL**
- **Commit / Rollback** no backend
- **Tratamento de erro Oracle** com `oracledb.DatabaseError`
- Persistência de auditoria na tabela `LOG_AUDITORIA`

## Estrutura

```text
eco_awareness_checkpoint2/
├── app.py
├── schema.sql
├── requirements.txt
├── README.md
├── templates/
│   └── index.html
└── static/
    └── style.css
```

## Regras de negócio implementadas

O sistema processa apenas inscrições com `STATUS = 'PRESENT'`.

Dentro do loop do cursor explícito:

1. Faz uma contagem de presenças do usuário
2. Define o percentual de cashback:
   - Mais de 3 presenças: **25%**
   - Ingresso VIP: **20%**
   - Demais casos: **10%**
3. Atualiza o saldo do usuário
4. Registra log na tabela `LOG_AUDITORIA`

## Como executar

### 1. Instale as dependências

```bash
pip install -r requirements.txt
```

### 2. Configure as variáveis de ambiente do Oracle

No Windows PowerShell:

```powershell
$env:ORACLE_USER="SEU_USUARIO"
$env:ORACLE_PASSWORD="SUA_SENHA"
$env:ORACLE_DSN="localhost/XEPDB1"
```

No Linux/macOS:

```bash
export ORACLE_USER="SEU_USUARIO"
export ORACLE_PASSWORD="SUA_SENHA"
export ORACLE_DSN="localhost/XEPDB1"
```

> Ajuste o DSN para o Oracle XE ou o ambiente usado na sua faculdade.

### 3. Rode a aplicação

```bash
python app.py
```

### 4. Acesse no navegador

```text
http://127.0.0.1:5000
```

## Fluxo de uso

1. Clique em **Preparar banco** para criar as tabelas e inserir dados de teste
2. Clique em **Executar cashback** para rodar o bloco PL/SQL com cursor explícito
3. Veja os saldos atualizados e os logs de auditoria na tela

## Observações importantes

- O script `schema.sql` já faz o **drop seguro** das tabelas.
- O backend captura exceções Oracle e exibe o código do erro.
- O `commit` acontece só quando o processamento é concluído com sucesso.
- Em caso de falha, o sistema executa `rollback`.

## Trecho principal do requisito técnico

No arquivo `app.py`, a variável `PLSQL_CASHBACK` contém o bloco anônimo com:

- `CURSOR c_participantes IS ...`
- `OPEN`
- `FETCH`
- `EXIT WHEN ...%NOTFOUND`
- `CLOSE`

Isso atende ao requisito de uso de **cursor explícito sem procedure e sem trigger**.
