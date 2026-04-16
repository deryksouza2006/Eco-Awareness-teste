import os
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash

try:
    import oracledb
except ImportError:
    oracledb = None

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'checkpoint2-eco-awareness')

DB_CONFIG = {
    'user': os.getenv('ORACLE_USER', 'seu_usuario'),
    'password': os.getenv('ORACLE_PASSWORD', 'sua_senha'),
    'dsn': os.getenv('ORACLE_DSN', 'localhost/XEPDB1'),
}

SCHEMA_SQL_FILE = os.path.join(os.path.dirname(__file__), 'schema.sql')


def get_connection():
    if oracledb is None:
        raise RuntimeError(
            'A biblioteca oracledb não está instalada. Execute: pip install oracledb'
        )
    return oracledb.connect(**DB_CONFIG)


def execute_schema():
    """Executa o script de criação e carga inicial no banco Oracle."""
    with open(SCHEMA_SQL_FILE, 'r', encoding='utf-8') as file:
        content = file.read()

    blocks = [block.strip() for block in content.split('/') if block.strip()]

    conn = get_connection()
    try:
        cursor = conn.cursor()
        for block in blocks:
            cursor.execute(block)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


PLSQL_CASHBACK = """
DECLARE
    CURSOR c_participantes IS
        SELECT ID, USUARIO_ID, VALOR_PAGO, TIPO
          FROM INSCRICOES
         WHERE STATUS = 'PRESENT'
         ORDER BY ID;

    v_id            INSCRICOES.ID%TYPE;
    v_usuario_id    INSCRICOES.USUARIO_ID%TYPE;
    v_valor_pago    INSCRICOES.VALOR_PAGO%TYPE;
    v_tipo          INSCRICOES.TIPO%TYPE;
    v_presencas     NUMBER;
    v_percentual    NUMBER(5,2);
    v_cashback      NUMBER(10,2);
    v_total_processados NUMBER := 0;
BEGIN
    OPEN c_participantes;

    LOOP
        FETCH c_participantes INTO v_id, v_usuario_id, v_valor_pago, v_tipo;
        EXIT WHEN c_participantes%NOTFOUND;

        SELECT COUNT(*)
          INTO v_presencas
          FROM INSCRICOES
         WHERE USUARIO_ID = v_usuario_id
           AND STATUS = 'PRESENT';

        IF v_presencas > 3 THEN
            v_percentual := 0.25;
        ELSIF UPPER(v_tipo) = 'VIP' THEN
            v_percentual := 0.20;
        ELSE
            v_percentual := 0.10;
        END IF;

        v_cashback := ROUND(v_valor_pago * v_percentual, 2);

        UPDATE USUARIOS
           SET SALDO = SALDO + v_cashback
         WHERE ID = v_usuario_id;

        INSERT INTO LOG_AUDITORIA (INSCRICAO_ID, MOTIVO)
        VALUES (
            v_id,
            'Cashback aplicado de R$ ' || TO_CHAR(v_cashback, 'FM9999990D00') ||
            ' | percentual: ' || TO_CHAR(v_percentual * 100, 'FM990D00') || '%' ||
            ' | presencas: ' || v_presencas
        );

        v_total_processados := v_total_processados + 1;
    END LOOP;

    CLOSE c_participantes;

    :total_processados := v_total_processados;
EXCEPTION
    WHEN OTHERS THEN
        IF c_participantes%ISOPEN THEN
            CLOSE c_participantes;
        END IF;
        RAISE;
END;
"""


def fetch_usuarios():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ID, NOME, EMAIL, PRIORIDADE, SALDO
              FROM USUARIOS
             ORDER BY ID
            """
        )
        rows = cursor.fetchall()
        return [
            {
                'id': row[0],
                'nome': row[1],
                'email': row[2],
                'prioridade': row[3],
                'saldo': float(row[4]) if isinstance(row[4], Decimal) else row[4],
            }
            for row in rows
        ]
    finally:
        conn.close()



def fetch_inscricoes():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT I.ID, U.NOME, I.STATUS, I.VALOR_PAGO, I.TIPO
              FROM INSCRICOES I
              JOIN USUARIOS U ON U.ID = I.USUARIO_ID
             ORDER BY I.ID
            """
        )
        rows = cursor.fetchall()
        return [
            {
                'id': row[0],
                'usuario_nome': row[1],
                'status': row[2],
                'valor_pago': float(row[3]) if isinstance(row[3], Decimal) else row[3],
                'tipo': row[4],
            }
            for row in rows
        ]
    finally:
        conn.close()



def fetch_logs(limit=20):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ID, INSCRICAO_ID, MOTIVO,
                   TO_CHAR(DATA, 'DD/MM/YYYY HH24:MI:SS') AS DATA_FORMATADA
              FROM LOG_AUDITORIA
             ORDER BY ID DESC
             FETCH FIRST :limit ROWS ONLY
            """,
            {'limit': limit},
        )
        rows = cursor.fetchall()
        return [
            {
                'id': row[0],
                'inscricao_id': row[1],
                'motivo': row[2],
                'data': row[3],
            }
            for row in rows
        ]
    finally:
        conn.close()


@app.route('/')
def index():
    error = None
    usuarios = []
    inscricoes = []
    logs = []

    try:
        usuarios = fetch_usuarios()
        inscricoes = fetch_inscricoes()
        logs = fetch_logs()
    except Exception as exc:
        error = str(exc)

    return render_template(
        'index.html',
        usuarios=usuarios,
        inscricoes=inscricoes,
        logs=logs,
        db_config=DB_CONFIG,
        error=error,
    )


@app.post('/setup')
def setup_database():
    try:
        execute_schema()
        flash('Banco preparado com sucesso. Tabelas criadas e dados inseridos.', 'success')
    except Exception as exc:
        flash(f'Erro ao preparar o banco: {exc}', 'error')
    return redirect(url_for('index'))


@app.post('/executar-cashback')
def executar_cashback():
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        total_processados = cursor.var(int)
        cursor.execute(PLSQL_CASHBACK, {'total_processados': total_processados})
        conn.commit()

        flash(
            f'Cashback processado com sucesso. Inscrições tratadas: {total_processados.getvalue()}.',
            'success',
        )
    except Exception as exc:
        if conn is not None:
            conn.rollback()

        if oracledb is not None and isinstance(exc, oracledb.DatabaseError):
            error, = exc.args
            flash(f'Erro Oracle {error.code}: {error.message}', 'error')
        else:
            flash(f'Erro ao executar cashback: {exc}', 'error')
    finally:
        if conn is not None:
            conn.close()

    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)
