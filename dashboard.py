import streamlit as st
from supabase import create_client, Client
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Gestão AMA", page_icon="🔒", layout="wide")

# ==========================================
# 1. SISTEMA DE BLINDAGEM (LOGIN)
# ==========================================
def check_password():
    """Retorna True se o usuário inseriu a senha correta."""
    def password_entered():
        if st.session_state["senha_digitada"] == st.secrets["PAINEL_PASSWORD"]:
            st.session_state["senha_correta"] = True
            del st.session_state["senha_digitada"]  # Apaga a senha da memória por segurança
        else:
            st.session_state["senha_correta"] = False

    if "senha_correta" not in st.session_state:
        # Primeira visita: Pede a senha
        st.markdown("### 🔒 Acesso Restrito - Diretoria AMA")
        st.text_input("Insira a Senha Mestra:", type="password", on_change=password_entered, key="senha_digitada")
        return False
    elif not st.session_state["senha_correta"]:
        # Errou a senha: Pede de novo
        st.markdown("### 🔒 Acesso Restrito - Diretoria AMA")
        st.text_input("Senha incorreta. Tente novamente:", type="password", on_change=password_entered, key="senha_digitada")
        st.error("Acesso Negado.")
        return False
    
    return True # Senha correta, libera o código abaixo

# Se a função acima retornar False, o comando st.stop() mata o site inteiro aqui mesmo.
if not check_password():
    st.stop()

# ==========================================
# 2. MOTOR DE DADOS E MATEMÁTICA BOOLEANA
# ==========================================
@st.cache_resource
def init_connection() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

@st.cache_data(ttl=60)
def load_data():
    response = supabase.table("casos").select("*").execute()
    if not response.data:
        return pd.DataFrame()
    
    df = pd.DataFrame(response.data)
    df['data_hora'] = pd.to_datetime(df['data_hora'])
    df['data'] = df['data_hora'].dt.date
    # Garante que a coluna nova seja tratada como número
    if 'atendimento_real' in df.columns:
        df['atendimento_real'] = pd.to_numeric(df['atendimento_real'], errors='coerce').fillna(1)
    return df

df_raw = load_data()

if df_raw.empty:
    st.warning("O banco de dados está vazio ou aguardando sincronização.")
    st.stop()

# --- A SEPARAÇÃO CIRÚRGICA ---
# df_real: Filtra matematicamente APENAS onde atendimento_real é 1 (Pacientes)
if 'atendimento_real' in df_raw.columns:
    df_real = df_raw[df_raw['atendimento_real'] == 1]
else:
    df_real = df_raw # Fallback caso a coluna falhe na nuvem

# turnos_realizados: Agrupa tudo (0 e 1) para saber quantas vezes a cadeira foi ocupada
turnos_realizados = df_raw.groupby(['data', 'turno', 'plantonista']).size().reset_index(name='qtd_registros')

# ==========================================
# 3. INTERFACE GERENCIAL (DASHBOARD)
# ==========================================
st.sidebar.header("Filtros de Análise")
data_min, data_max = df_raw['data'].min(), df_raw['data'].max()

data_inicio, data_fim = st.sidebar.date_input("Período:", [data_min, data_max], min_value=data_min, max_value=data_max)

lista_plantonistas = ["Todos"] + list(df_raw['plantonista'].unique())
plantonista_selecionado = st.sidebar.selectbox("Plantonista:", lista_plantonistas)

# Aplica filtros
mascara_data = (df_real['data'] >= data_inicio) & (df_real['data'] <= data_fim)
df_filtrado = df_real[mascara_data]

mascara_data_turnos = (turnos_realizados['data'] >= data_inicio) & (turnos_realizados['data'] <= data_fim)
turnos_filtrados = turnos_realizados[mascara_data_turnos]

if plantonista_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado['plantonista'] == plantonista_selecionado]
    turnos_filtrados = turnos_filtrados[turnos_filtrados['plantonista'] == plantonista_selecionado]

st.title("📈 Centro de Inteligência AMA")
st.markdown("Visão executiva isolada por barreira criptográfica.")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total de Atendimentos Reais", len(df_filtrado))
col2.metric("Turnos de Plantão", len(turnos_filtrados))
media_por_turno = len(df_filtrado) / len(turnos_filtrados) if len(turnos_filtrados) > 0 else 0
col3.metric("Média (Atendimentos/Turno)", f"{media_por_turno:.1f}")
col4.metric("Voluntários Ativos", df_filtrado['plantonista'].nunique())

st.divider()

if not df_filtrado.empty:
    st.subheader("Curva de Demanda Diária")
    demanda_diaria = df_filtrado.groupby('data').size().reset_index(name='atendimentos')
    st.plotly_chart(px.line(demanda_diaria, x='data', y='atendimentos', markers=True, color_discrete_sequence=['#1f538d']), use_container_width=True)

    col_graf1, col_graf2, col_graf3 = st.columns(3)
    with col_graf1: st.plotly_chart(px.pie(df_filtrado, names='canal', title="Canais", hole=0.4), use_container_width=True)
    with col_graf2: st.plotly_chart(px.pie(df_filtrado, names='idade', title="Faixa Etária", hole=0.4), use_container_width=True)
    with col_graf3: st.plotly_chart(px.pie(df_filtrado, names='recorrencia', title="Retenção", hole=0.4), use_container_width=True)

    st.subheader("Registro de Operações Clínicas")
    st.dataframe(df_filtrado[['id', 'data_hora', 'plantonista', 'turno', 'nome', 'canal']].sort_values(by='id', ascending=False), use_container_width=True, hide_index=True)
else:
    st.info("Nenhum dado clínico registrado no período filtrado.")