import os
from flask import Flask, jsonify, render_template
import oracledb

app = Flask(__name__)

def get_connection():
    user = os.getenv("ORACLE_USER")
    password = os.getenv("ORACLE_PASSWORD")
    dsn = os.getenv("ORACLE_DSN", "localhost:1521/XEPDB1")

    if not user or not password:
        raise RuntimeError("Defina ORACLE_USER e ORACLE_PASSWORD nas variáveis de ambiente.")

    return oracledb.connect(user=user, password=password, dsn=dsn)


PLSQL_CASHBACK = """
DECLARE
    CURSOR c_participantes IS
        SELECT ID, USUARIO_ID, VALOR_PAGO, TIPO
        FROM INSCRICOES
        WHERE STATUS = 'PRESENT'
        ORDER BY ID;

    v_id          INSCRICOES.ID%TYPE;
    v_usuario_id  INSCRICOES.USUARIO_ID%TYPE;
    v_valor_pago  INSCRICOES.VALOR_PAGO%TYPE;
    v_tipo        INSCRICOES.TIPO%TYPE;

    v_cashback    NUMBER(10,2);
    v_percentual  NUMBER(5,2);
    v_presencas   NUMBER;
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
           SET SALDO = NVL(SALDO, 0) + v_cashback
         WHERE ID = v_usuario_id;

        INSERT INTO LOG_AUDITORIA (INSCRICAO_ID, MOTIVO)
        VALUES (
            v_id,
            'Cashback aplicado ao usuário ' || v_usuario_id ||
            ' | inscrição ' || v_id ||
            ' | percentual ' || TO_CHAR(v_percentual * 100) || '%' ||
            ' | valor R$ ' || TO_CHAR(v_cashback, 'FM9999990D00')
        );
    END LOOP;

    CLOSE c_participantes;
END;
"""

RESET_SQL = """
BEGIN
    UPDATE USUARIOS
       SET SALDO =
           CASE ID
               WHEN 1 THEN 100
               WHEN 2 THEN 50
               WHEN 3 THEN 200
               ELSE NVL(SALDO, 0)
           END;

    DELETE FROM LOG_AUDITORIA;
END;
"""

def fetch_logs(cur):
    cur.execute("""
        SELECT ID,
               INSCRICAO_ID,
               MOTIVO,
               TO_CHAR(DATA, 'DD/MM/YYYY HH24:MI:SS') AS DATA_FMT
          FROM LOG_AUDITORIA
         ORDER BY ID DESC
    """)
    logs = []
    for row in cur.fetchall():
        logs.append({
            "id": row[0],
            "inscricao_id": row[1],
            "motivo": row[2],
            "data": row[3]
        })
    return logs

def fetch_usuarios(cur):
    cur.execute("""
        SELECT
            u.ID,
            u.NOME,
            u.EMAIL,
            u.PRIORIDADE,
            NVL(u.SALDO, 0) AS SALDO,
            NVL((
                SELECT COUNT(*)
                  FROM INSCRICOES i
                 WHERE i.USUARIO_ID = u.ID
                   AND i.STATUS = 'PRESENT'
            ), 0) AS PRESENCAS,
            MAX(CASE
                    WHEN i.STATUS = 'PRESENT' AND UPPER(i.TIPO) = 'VIP' THEN 'VIP'
                    ELSE 'NORMAL'
                END) AS TIPO_CASHBACK
        FROM USUARIOS u
        LEFT JOIN INSCRICOES i
               ON i.USUARIO_ID = u.ID
        GROUP BY u.ID, u.NOME, u.EMAIL, u.PRIORIDADE, u.SALDO
        ORDER BY u.ID
    """)
    usuarios = []
    for row in cur.fetchall():
        usuarios.append({
            "id": row[0],
            "nome": row[1],
            "email": row[2],
            "prioridade": row[3],
            "saldo": float(row[4]),
            "presencas": int(row[5]),
            "tipo_cashback": row[6] if row[6] else "NORMAL"
        })
    return usuarios

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/usuarios")
def usuarios():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                usuarios_data = fetch_usuarios(cur)
        return jsonify({"success": True, "usuarios": usuarios_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/processar-cashback", methods=["POST"])
def processar_cashback():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(PLSQL_CASHBACK)
                conn.commit()
                usuarios_data = fetch_usuarios(cur)
                logs = fetch_logs(cur)
        return jsonify({"success": True, "usuarios": usuarios_data, "logs": logs})
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/resetar", methods=["POST"])
def resetar():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(RESET_SQL)
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
