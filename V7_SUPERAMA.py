import customtkinter as ctk
import sqlite3
import threading
import time
import random
import datetime
import csv
from tkinter import messagebox
import uuid
import requests
from PIL import Image
import os
from dotenv import load_dotenv
import webbrowser

# Carrega as variáveis de ambiente do arquivo .env para a memória
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class SuperAppAMA(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SUPER APP AMA - Amigos Anônimos")
        self.geometry("1100x750")
        self.minsize(900, 600)

        self.usuario_logado = ""
        self.sessao_nome = ""
        self.sessao_id = ""
        self.sessao_turno = ""
        self.is_admin = False

        self.init_database()

        self.main_frames = {}
        self.content_frames = {}
        self.nav_buttons = {}

        self.build_root_screens()

        self.idle_timer = None
        self.is_screensaver_active = False
        self.bind_all("<Any-KeyPress>", self.reset_idle_timer)
        self.bind_all("<Any-Button>", self.reset_idle_timer)
        self.bind_all("<Motion>", self.reset_idle_timer)
        self.reset_idle_timer()

        self.sync_thread = threading.Thread(target=self.sync_worker, daemon=True)
        self.sync_thread.start()

        self.show_main_frame("login")

    def reset_idle_timer(self, event=None):
        if self.is_screensaver_active:
            self.is_screensaver_active = False
            self.screensaver_active = False
            self.show_main_frame("saas_layout")

        if self.idle_timer:
            self.after_cancel(self.idle_timer)

        self.idle_timer = self.after(600000, self.trigger_screensaver)

    def trigger_screensaver(self):
        if self.usuario_logado and not self.is_screensaver_active:
            self.is_screensaver_active = True
            self.show_main_frame("screensaver")
            self.screensaver_active = True

            self.dx = random.choice([-6, -5, -4, 4, 5, 6])
            self.dy = random.choice([-6, -5, -4, 4, 5, 6])
            self.animate_dvd()

    def init_database(self):
        self.conn = sqlite3.connect('ama_database.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS casos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_nuvem TEXT UNIQUE,
                status_sync INTEGER DEFAULT 0,
                plantonista TEXT,
                id_plantonista TEXT,
                turno TEXT,
                nome TEXT,
                idade TEXT,
                genero TEXT,
                idealizacao_suicida TEXT,
                canal TEXT,
                recorrencia TEXT,
                data_hora DATETIME,
                atendimento_real INTEGER
            )
        ''')
        
        # Migração segura para bases antigas sem a nova coluna
        self.cursor.execute("PRAGMA table_info(casos)")
        colunas = [col[1] for col in self.cursor.fetchall()]
        if "idealizacao_suicida" not in colunas:
            self.cursor.execute("ALTER TABLE casos ADD COLUMN idealizacao_suicida TEXT DEFAULT 'Não'")

        # Planilha de ponto dos plantonistas (um ponto por nome+ID+turno+dia)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS pontos_plantonistas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plantonista TEXT NOT NULL,
                id_plantonista TEXT NOT NULL,
                data_acesso TEXT NOT NULL,
                hora_acesso TEXT NOT NULL,
                turno TEXT NOT NULL,
                UNIQUE(plantonista, id_plantonista, data_acesso, turno)
            )
        ''')

        self.conn.commit()

    def registrar_ponto_plantonista(self, nome, identificacao, turno):
        data_hoje = datetime.datetime.now().strftime("%Y-%m-%d")
        hora_agora = datetime.datetime.now().strftime("%H:%M:%S")

        self.cursor.execute(
            """INSERT OR IGNORE INTO pontos_plantonistas
               (plantonista, id_plantonista, data_acesso, hora_acesso, turno)
               VALUES (?, ?, ?, ?, ?)""",
            (nome, identificacao, data_hoje, hora_agora, turno)
        )
        self.conn.commit()

        # Atualiza a planilha de ponto sempre que houver login
        self.exportar_planilha_ponto_csv()

    def exportar_planilha_ponto_csv(self):
        self.cursor.execute(
            """SELECT plantonista, id_plantonista, data_acesso, hora_acesso, turno
               FROM pontos_plantonistas
               ORDER BY data_acesso DESC, hora_acesso DESC"""
        )
        linhas = self.cursor.fetchall()

        with open("planilha_ponto_plantonistas.csv", "w", newline="", encoding="utf-8-sig") as arquivo:
            writer = csv.writer(arquivo)
            writer.writerow(["Plantonista", "ID", "Data do Acesso", "Hora do Acesso", "Turno"])
            writer.writerows(linhas)

    def show_main_frame(self, frame_name):
        for frame in self.main_frames.values():
            frame.pack_forget()
        self.main_frames[frame_name].pack(fill="both", expand=True)

    def show_content_frame(self, frame_name):
        for frame in self.content_frames.values():
            frame.pack_forget()

        self.content_frames[frame_name].pack(fill="both", expand=True)

        for name, btn in self.nav_buttons.items():
            if name == frame_name:
                btn.configure(fg_color="#1f538d", text_color="white", border_width=0)
            else:
                btn.configure(fg_color="transparent", text_color=("black", "white"), border_width=2)

        if frame_name == "dashboard":
            self.update_dashboard_metrics()

        # Mantém os botões de sessão com mesmo tamanho/posição em todas as abas
        self.bottom_bar.configure(height=70)
        self.btn_logout.configure(width=180, height=50, font=ctk.CTkFont(size=16, weight="bold"))
        self.btn_logout_vazio.configure(width=160, height=50, font=ctk.CTkFont(size=14, weight="bold"))

        # ROTEAMENTO CORRIGIDO: Salvar fica na esquerda, longe do perigo
        if frame_name == "insert":
            self.btn_salvar.pack(side="left")
        else:
            self.btn_salvar.pack_forget()

    def build_root_screens(self):
        self.carregar_assets()
        self.create_login_screen()
        self.create_screensaver()
        self.create_login_loading_screen()
        self.create_saas_layout()

    def create_login_loading_screen(self):
        frame = ctk.CTkFrame(self)
        self.main_frames["login_loading"] = frame

        container = ctk.CTkFrame(frame, fg_color="transparent")
        container.place(relx=0.5, rely=0.5, anchor="center")

        if hasattr(self, 'img_valida') and self.img_valida:
            ctk.CTkLabel(container, text="", image=self.logo_loading).pack(pady=(0, 20))

        ctk.CTkLabel(container, text="Autenticando Plantonista e Sincronizando...", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(0, 20))

        self.login_progress = ctk.CTkProgressBar(container, width=500, height=25, corner_radius=10)
        self.login_progress.pack()
        self.login_progress.set(0)

    def carregar_assets(self):
        try:
            base_img = Image.open("logo.png")

            self.logo_loading = ctk.CTkImage(light_image=base_img, dark_image=base_img, size=(150, 150))
            self.logo_login = ctk.CTkImage(light_image=base_img, dark_image=base_img, size=(100, 100))
            self.logo_sidebar = ctk.CTkImage(light_image=base_img, dark_image=base_img, size=(80, 80))

            from PIL import ImageTk
            icon = ImageTk.PhotoImage(base_img)
            self.iconphoto(False, icon)

            self.img_valida = True
        except Exception as e:
            self.img_valida = False
            print(f"[AVISO] Arquivo 'logo.png' não encontrado ou erro ao carregar: {e}")

    def sync_worker(self):

        endpoint = f"{SUPABASE_URL}/rest/v1/casos?on_conflict=id_nuvem"

        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates, return=minimal"
        }

        local_conn = sqlite3.connect('ama_database.db', timeout=10)
        local_cursor = local_conn.cursor()

        while True:
            time.sleep(10)

            try:
                # O SELECT AGORA PEDE EXATAMENTE 12 COLUNAS
                local_cursor.execute(
                    "SELECT id, id_nuvem, plantonista, id_plantonista, turno, nome, idade, genero, idealizacao_suicida, canal, recorrencia, data_hora, atendimento_real "
                    "FROM casos WHERE status_sync = 0"
                )
                pendentes = local_cursor.fetchall()

                if not pendentes:
                    continue

                print(f"[SYNC ALERTA] Tentando enviar {len(pendentes)} atendimento(s) retido(s) para a nuvem...")

                for caso in pendentes:
                    # O UNPACK AGORA RECEBE EXATAMENTE 12 VARIÁVEIS
                    caso_id, id_nuvem, plantonista, id_plantonista, turno, nome, idade, genero, idealizacao_suicida, canal, recorrencia, data_hora, atendimento_real = caso

                    payload = {
                        "id_nuvem": id_nuvem,
                        "plantonista": plantonista,
                        "id_plantonista": id_plantonista,
                        "turno": turno,
                        "nome": nome,
                        "idade": idade,
                        "genero": genero,
                        "idealizacao_suicida": idealizacao_suicida,
                        "canal": canal,
                        "recorrencia": recorrencia,
                        "data_hora": data_hora,
                        "atendimento_real": atendimento_real
                    }

                    response = requests.post(endpoint, headers=headers, json=payload)

                    if response.status_code in (200, 201):
                        local_cursor.execute("UPDATE casos SET status_sync = 1 WHERE id = ?", (caso_id,))
                        local_conn.commit()
                        print(f"[SYNC OK] Atendimento {id_nuvem[:8]}... salvo no Supabase com sucesso!")
                    else:
                        print(f"[SYNC FALHA] Erro {response.status_code} na nuvem. Motivo: {response.text}")

            except sqlite3.OperationalError as e:
                print(f"[SYNC ERRO DE BANCO] O banco local está desatualizado. Delete o arquivo ama_database.db! Erro: {e}")
            except Exception as e:
                print(f"[SYNC ERRO CRÍTICO] Falha interna no motor: {e}")

    def create_login_screen(self):
        frame = ctk.CTkFrame(self)
        self.main_frames["login"] = frame

        self.switch_theme_login = ctk.CTkSwitch(frame, text="Modo Escuro", font=ctk.CTkFont(size=16, weight="bold"), command=self.toggle_theme)
        self.switch_theme_login.place(relx=0.95, rely=0.05, anchor="ne")
        self.switch_theme_login.select()

        ctk.CTkLabel(frame, text="versão 1.5", font=ctk.CTkFont(size=14, weight="bold"), text_color=("gray40", "gray60")).place(relx=0.02, rely=0.98, anchor="sw")

        # Cartão ampliado para 700px para acomodar o logo sem esmagar o rodapé
        card = ctk.CTkFrame(frame, corner_radius=20, fg_color=("gray85", "gray15"), width=550, height=700)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        # Injeção do Logo Dinâmico com padding superior reduzido
        if hasattr(self, 'img_valida') and self.img_valida:
            ctk.CTkLabel(card, text="", image=self.logo_login).pack(pady=(20, 0))
            ctk.CTkLabel(card, text="AMA", font=ctk.CTkFont(size=44, weight="bold")).pack(pady=(5, 0))
        else:
            ctk.CTkLabel(card, text="AMA", font=ctk.CTkFont(size=44, weight="bold")).pack(pady=(30, 5))

        # Espaçamento inferior do subtítulo reduzido de 30 para 20
        ctk.CTkLabel(card, text="Amigos Anônimos", font=ctk.CTkFont(size=20, slant="italic"), text_color=("gray30", "gray70")).pack(pady=(0, 20))

        font_label = ctk.CTkFont(size=18, weight="bold")
        font_input = ctk.CTkFont(size=20)

        ctk.CTkLabel(card, text="1. Nome do Plantonista:", font=font_label).pack(anchor="w", padx=40, pady=(5, 5))
        self.entry_plantonista = ctk.CTkEntry(card, width=470, height=50, font=font_input)
        self.entry_plantonista.pack(padx=40)

        # ALTERAÇÃO: rótulo atualizado
        ctk.CTkLabel(card, text="2. Número de plantonista:", font=font_label).pack(anchor="w", padx=40, pady=(10, 5))
        self.entry_id = ctk.CTkEntry(card, width=470, height=50, font=font_input)
        self.entry_id.pack(padx=40)

        # ALTERAÇÃO: opções de turno atualizadas
        ctk.CTkLabel(card, text="3. Selecione o Turno:", font=font_label).pack(anchor="w", padx=40, pady=(10, 5))
        self.option_periodo = ctk.CTkOptionMenu(card, values=["P10", "P13", "P16", "P19"], width=250, height=50, font=font_input, dropdown_font=font_input)
        self.option_periodo.pack(anchor="w", padx=40)

        # Margens massivas removidas. O botão agora tem espaço para existir.
        self.btn_iniciar = ctk.CTkButton(card, text="INICIAR TURNO", width=470, height=70, font=ctk.CTkFont(size=24, weight="bold"), fg_color="#1f538d", hover_color="#14375e", command=self.process_login)
        self.btn_iniciar.pack(pady=(25, 20))

        self.entry_plantonista.bind("<Return>", self.process_login)
        self.entry_id.bind("<Return>", self.process_login)
        self.btn_iniciar.bind("<Return>", self.process_login)

    def create_screensaver(self):
        frame = ctk.CTkFrame(self)
        self.main_frames["screensaver"] = frame
        self.canvas = ctk.CTkCanvas(frame, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.dvd_text = self.canvas.create_text(100, 100, text="AMA", fill="#1f538d", font=("Arial", 40, "bold"))
        self.screensaver_active = False
        self.dx = 0
        self.dy = 0

    def process_login(self, event=None):
        plantonista = self.entry_plantonista.get().strip()
        identificacao = self.entry_id.get().strip()
        periodo = self.option_periodo.get()

        if not plantonista or not identificacao:
            return

        self.sessao_nome = plantonista
        self.sessao_id = identificacao
        self.sessao_turno = periodo

        self.is_admin = (plantonista.lower() == "adm" and identificacao == "000000")

        if not self.is_admin:
            self.registrar_ponto_plantonista(plantonista, identificacao, periodo)

        if self.is_admin:
            self.usuario_logado = "Administrador"
            self.lbl_user_status.configure(text="Plantonista Atual:\nAdministrador (ADM)")
        else:
            self.usuario_logado = f"{plantonista} (ID: {identificacao}) - {periodo}"
            self.lbl_user_status.configure(text=f"Plantonista: {self.usuario_logado}")

            # (Final da função process_login)
            self.usuario_logado = f"{self.sessao_nome} (ID: {self.sessao_id})"
            # Adicionamos um \n para forçar o nome do voluntário para a linha de baixo
            self.lbl_user_status.configure(text=f"Plantonista Atual:\n{self.usuario_logado}")

        # CHECAGEM DE SEGURANÇA AQUI
        self.avaliar_exibicao_botao_vazio()

        # CHECAGEM DE SEGURANÇA AQUI
        self.avaliar_exibicao_botao_vazio()

        self.progress_value = 0
        self.animate_progress_bar()

        self.show_main_frame("login_loading")

        self.login_progress.set(0)
        self.progress_value = 0.0
        self.animate_progress_bar()

    def animate_progress_bar(self):
        if self.progress_value < 1.0:
            self.progress_value += 0.04
            self.login_progress.set(self.progress_value)
            self.after(40, self.animate_progress_bar)
        else:
            self.show_main_frame("saas_layout")
            self.show_content_frame("dashboard")

    def process_logout(self):
        resposta = messagebox.askyesno("Encerrar Turno", "Tem certeza que deseja encerrar o turno e sair?", icon='warning')
        if resposta:
            self.sessao_nome = ""
            self.sessao_id = ""
            self.sessao_turno = ""
            self.usuario_logado = ""
            self.is_admin = False

            self.entry_plantonista.delete(0, "end")
            self.entry_id.delete(0, "end")

            self.show_main_frame("login")
            self.entry_plantonista.focus()

    def process_logout_vazio(self):
        if self.is_admin:
            messagebox.showwarning("Ação não permitida", "O perfil Administrador não registra encerramento de turno sem atendimento.")
            return

        resposta = messagebox.askyesno("Encerrar Sem Casos", "Confirma que não houve NENHUM atendimento neste turno e deseja encerrar?", icon='warning')

        if resposta:
            # Injeta o registro fantasma padronizado
            data_hora_atual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            novo_uuid = str(uuid.uuid4())

            self.cursor.execute(
                """INSERT INTO casos
                (id_nuvem, status_sync, plantonista, id_plantonista, turno, nome, idade, genero, idealizacao_suicida, canal, recorrencia, data_hora, atendimento_real)
                VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (novo_uuid, self.sessao_nome, self.sessao_id, self.sessao_turno,
                 "N/A", "N/A", "N/A", "Não", "Sistema", "Registro de Ponto", data_hora_atual)
            )
            self.conn.commit()

            # Limpa a sessão e volta pro login
            self.sessao_nome = ""
            self.sessao_id = ""
            self.sessao_turno = ""
            self.usuario_logado = ""
            self.is_admin = False

            self.entry_plantonista.delete(0, "end")
            self.entry_id.delete(0, "end")

            self.show_main_frame("login")
            self.entry_plantonista.focus()

    def avaliar_exibicao_botao_vazio(self):
        if self.is_admin:
            self.btn_logout_vazio.pack_forget()
            return

        hoje_str = datetime.datetime.now().strftime("%Y-%m-%d")
        # CORREÇÃO: Verificamos se existe algum atendimento real (atendimento_real = 1)
        self.cursor.execute(
            "SELECT COUNT(*) FROM casos WHERE id_plantonista = ? AND turno = ? AND substr(data_hora, 1, 10) = ? AND atendimento_real = 1",
            (self.sessao_id, self.sessao_turno, hoje_str)
        )
        qtd_atendimentos = self.cursor.fetchone()[0]

        if qtd_atendimentos > 0:
            self.btn_logout_vazio.pack_forget()
        else:
            self.btn_logout_vazio.pack(side="right")

    def animate_dvd(self):
        if not self.screensaver_active:
            return

        self.canvas.move(self.dvd_text, self.dx, self.dy)
        pos = self.canvas.bbox(self.dvd_text)

        width = self.canvas.winfo_width() or 1000
        height = self.canvas.winfo_height() or 700

        if pos[0] <= 0 or pos[2] >= width:
            self.dx *= -1
        if pos[1] <= 0 or pos[3] >= height:
            self.dy *= -1

        self.after(20, self.animate_dvd)

    def create_saas_layout(self):
        app_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frames["saas_layout"] = app_frame

        sidebar = ctk.CTkFrame(app_frame, width=320, corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ctk.CTkLabel(sidebar, text="APLICATIVO AMA", font=ctk.CTkFont(size=26, weight="bold")).pack(pady=(40, 10))

        if hasattr(self, 'img_valida') and self.img_valida:
            ctk.CTkLabel(sidebar, text="", image=self.logo_sidebar).pack(pady=(0, 30))
        else:
            ctk.CTkLabel(sidebar, text="", height=20).pack()

        btn_font = ctk.CTkFont(size=22, weight="bold")

        self.btn_nav_dashboard = ctk.CTkButton(sidebar, text="Informações", font=btn_font, height=60, command=lambda: self.show_content_frame("dashboard"))
        self.btn_nav_dashboard.pack(fill="x", padx=20, pady=(0, 15))

        self.btn_nav_insert = ctk.CTkButton(sidebar, text="Inserir Novo Caso", font=btn_font, height=60, command=lambda: self.show_content_frame("insert"))
        self.btn_nav_insert.pack(fill="x", padx=20, pady=15)

        self.btn_nav_view = ctk.CTkButton(sidebar, text="Ver Casos do Turno", font=btn_font, height=60, command=lambda: [self.load_and_show_cases(), self.show_content_frame("view")])
        self.btn_nav_view.pack(fill="x", padx=20, pady=15)

        self.btn_nav_turnos = ctk.CTkButton(sidebar, text="Meus Turnos", font=btn_font, height=60, command=lambda: [self.load_and_show_my_shifts(), self.show_content_frame("my_shifts")])
        self.btn_nav_turnos.pack(fill="x", padx=20, pady=15)

        self.nav_buttons = {
            "dashboard": self.btn_nav_dashboard,
            "insert": self.btn_nav_insert,
            "view": self.btn_nav_view,
            "my_shifts": self.btn_nav_turnos
        }

        # --- RODAPÉ DA BARRA LATERAL ---
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        # Aumentamos o pady inferior de 20 para 30 para desgrudar do chão da janela
        footer.pack(side="bottom", fill="x", pady=(10, 30), padx=20)

        self.switch_theme = ctk.CTkSwitch(footer, text="Modo Escuro", font=ctk.CTkFont(size=16), command=self.toggle_theme)
        self.switch_theme.pack(anchor="w", pady=(0, 25))
        self.switch_theme.select()

        self.lbl_user_status = ctk.CTkLabel(
            footer,
            text="Usuário: Não Logado",
            font=ctk.CTkFont(size=16, slant="italic"),
            anchor="w",
            text_color="gray60",
            wraplength=280,
            justify="left"
        )
        # Um único pack com margem superior para afastar do botão de tema escuro
        self.lbl_user_status.pack(fill="x", pady=(5, 0))

        right_panel = ctk.CTkFrame(app_frame, fg_color="transparent")
        right_panel.pack(side="right", fill="both", expand=True)

        self.content_area = ctk.CTkFrame(right_panel, corner_radius=0, fg_color="transparent")
        self.content_area.pack(side="top", fill="both", expand=True)

        # --- BARRA INFERIOR RESPONSIVA E SEPARADA ---
        self.bottom_bar = ctk.CTkFrame(right_panel, height=70, fg_color="transparent")
        self.bottom_bar.pack(side="bottom", fill="x", padx=30, pady=15)
        self.bottom_bar.pack_propagate(False)

        # Botões de Sessão (Alinhados à Direita)
        self.btn_logout = ctk.CTkButton(self.bottom_bar, text="ENCERRAR TURNO", font=ctk.CTkFont(size=16, weight="bold"), fg_color="#b22222", hover_color="#8b0000", width=180, height=50, command=self.process_logout)
        self.btn_logout.pack(side="right", padx=(15, 0))

        self.btn_logout_vazio = ctk.CTkButton(self.bottom_bar, text="ENCERRAR SEM ATENDIMENTO", font=ctk.CTkFont(size=14, weight="bold"), fg_color="#555555", hover_color="#333333", width=160, height=50, command=self.process_logout_vazio)
        self.btn_logout_vazio.pack(side="right")

        # Botão Salvar (Instanciado aqui, mas será alinhado à ESQUERDA pela função de controle)
        self.btn_salvar = ctk.CTkButton(self.bottom_bar, text="SALVAR ATENDIMENTO", font=ctk.CTkFont(size=18, weight="bold"), width=220, height=50, command=self.save_case)

        self.build_content_screens()

    def toggle_theme(self):
        modo_atual = ctk.get_appearance_mode()
        if modo_atual == "Dark":
            ctk.set_appearance_mode("Light")
        else:
            ctk.set_appearance_mode("Dark")

    def build_content_screens(self):
        self.create_dashboard_content()
        self.create_insert_content()
        self.create_view_cases_content()
        self.create_case_detail_content()

    def create_dashboard_content(self):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.content_frames["dashboard"] = frame

        ctk.CTkLabel(frame, text="Visão Geral", font=ctk.CTkFont(size=36, weight="bold"), anchor="w").pack(fill="x", padx=40, pady=(40, 10))
        ctk.CTkLabel(frame, text="Resumo rápido do seu plantão local.", font=ctk.CTkFont(size=18), text_color="gray50", anchor="w").pack(fill="x", padx=40)

        stats_frame = ctk.CTkFrame(frame, fg_color="transparent")
        stats_frame.pack(fill="x", padx=40, pady=40)

        card1 = ctk.CTkFrame(stats_frame, height=120)
        card1.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(card1, text="Seus Atendimentos (Hoje)", font=ctk.CTkFont(size=18)).pack(pady=(15, 5))
        self.lbl_dash_hoje = ctk.CTkLabel(card1, text="0", font=ctk.CTkFont(size=40, weight="bold"), text_color="#2ecc71")
        self.lbl_dash_hoje.pack()

        card2 = ctk.CTkFrame(stats_frame, height=120)
        card2.pack(side="left", fill="x", expand=True, padx=(10, 10))
        ctk.CTkLabel(card2, text="Seus Atendimentos (Total)", font=ctk.CTkFont(size=18)).pack(pady=(15, 5))
        self.lbl_dash_total_user = ctk.CTkLabel(card2, text="0", font=ctk.CTkFont(size=40, weight="bold"))
        self.lbl_dash_total_user.pack()

        card3 = ctk.CTkFrame(stats_frame, height=120)
        card3.pack(side="left", fill="x", expand=True, padx=(10, 0))
        ctk.CTkLabel(card3, text="Total Histórico (ONG)", font=ctk.CTkFont(size=18)).pack(pady=(15, 5))
        self.lbl_dash_total_ong = ctk.CTkLabel(card3, text="0", font=ctk.CTkFont(size=40, weight="bold"))
        self.lbl_dash_total_ong.pack()

        # O Atalho para o Painel Gerencial (posicionado mais acima)
        btn_abrir_web = ctk.CTkButton(
            frame,
            text="🌐 Acessar Painel Gerencial Completo (Web)",
            font=ctk.CTkFont(size=22, weight="bold"),
            height=72,
            fg_color="#1f538d",
            hover_color="#14375e",
            command=lambda: webbrowser.open("https://amadashboard.streamlit.app/")
        )
        btn_abrir_web.pack(pady=(5, 18), padx=40, fill="x")

        # Resumo por canal (usuário vs ONG)
        canais_frame = ctk.CTkFrame(frame)
        canais_frame.pack(fill="x", padx=40, pady=(0, 20))

        ctk.CTkLabel(
            canais_frame,
            text="Atendimentos por Canal",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=20, pady=(15, 10))

        header = ctk.CTkFrame(canais_frame, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(0, 5))
        ctk.CTkLabel(header, text="Canal", font=ctk.CTkFont(size=16, weight="bold"), width=180, anchor="w").pack(side="left")
        ctk.CTkLabel(header, text="Seus Atendimentos", font=ctk.CTkFont(size=16, weight="bold"), width=180, anchor="center").pack(side="left", padx=10)
        ctk.CTkLabel(header, text="Total ONG", font=ctk.CTkFont(size=16, weight="bold"), width=140, anchor="center").pack(side="left", padx=10)

        self.dashboard_channels = ["WhatsApp", "Presencial", "Telefone", "Instagram", "Facebook"]
        self.channel_labels_user = {}
        self.channel_labels_ong = {}

        for canal in self.dashboard_channels:
            row = ctk.CTkFrame(canais_frame, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=3)
            ctk.CTkLabel(row, text=canal, font=ctk.CTkFont(size=16), width=180, anchor="w").pack(side="left")

            lbl_user = ctk.CTkLabel(row, text="0", font=ctk.CTkFont(size=16, weight="bold"), width=180, anchor="center", text_color="#2ecc71")
            lbl_user.pack(side="left", padx=10)
            self.channel_labels_user[canal] = lbl_user

            lbl_ong = ctk.CTkLabel(row, text="0", font=ctk.CTkFont(size=16, weight="bold"), width=140, anchor="center")
            lbl_ong.pack(side="left", padx=10)
            self.channel_labels_ong[canal] = lbl_ong


    def update_dashboard_metrics(self):
        if not self.sessao_id:
            return
        hoje_str = datetime.datetime.now().strftime("%Y-%m-%d")

        # Busca puramente no banco local, sem requisições pesadas à API
        self.cursor.execute("SELECT COUNT(*) FROM casos")
        self.lbl_dash_total_ong.configure(text=str(self.cursor.fetchone()[0]))

        self.cursor.execute("SELECT COUNT(*) FROM casos WHERE id_plantonista = ?", (self.sessao_id,))
        self.lbl_dash_total_user.configure(text=str(self.cursor.fetchone()[0]))

        # Atualizado para contar apenas atendimentos reais (ignora os turnos vazios)
        self.cursor.execute(
            "SELECT COUNT(*) FROM casos WHERE id_plantonista = ? AND substr(data_hora, 1, 10) = ? AND atendimento_real = 1",
            (self.sessao_id, hoje_str)
        )
        self.lbl_dash_hoje.configure(text=str(self.cursor.fetchone()[0]))

        # Métricas por canal (somente atendimentos reais)
        self.cursor.execute(
            "SELECT canal, COUNT(*) FROM casos WHERE id_plantonista = ? AND atendimento_real = 1 GROUP BY canal",
            (self.sessao_id,)
        )
        por_canal_user = dict(self.cursor.fetchall())

        self.cursor.execute(
            "SELECT canal, COUNT(*) FROM casos WHERE atendimento_real = 1 GROUP BY canal"
        )
        por_canal_ong = dict(self.cursor.fetchall())

        for canal in self.dashboard_channels:
            self.channel_labels_user[canal].configure(text=str(por_canal_user.get(canal, 0)))
            self.channel_labels_ong[canal].configure(text=str(por_canal_ong.get(canal, 0)))

    def create_insert_content(self):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.content_frames["insert"] = frame

        ctk.CTkLabel(frame, text="Registrar Novo Atendimento", font=ctk.CTkFont(size=36, weight="bold"), anchor="w").pack(fill="x", padx=40, pady=(40, 20))

        form_bg = ctk.CTkScrollableFrame(frame, fg_color=("gray90", "gray13"), corner_radius=10)
        form_bg.pack(side="top", fill="both", expand=True, padx=40, pady=(0, 0))

        self.form_entries = {}
        font_label = ctk.CTkFont(size=22, weight="bold")
        font_input = ctk.CTkFont(size=22)

        header_nome = ctk.CTkFrame(form_bg, fg_color="transparent")
        header_nome.pack(fill="x", padx=20, pady=(15, 5))

        ctk.CTkLabel(header_nome, text="Nome do Atendido:", font=font_label).pack(side="left")

        self.anon_var = ctk.BooleanVar(value=False)
        self.chk_anon = ctk.CTkCheckBox(header_nome, text="Marcar como Anônimo", font=ctk.CTkFont(size=18), variable=self.anon_var, command=self.toggle_anonimo)
        self.chk_anon.pack(side="right")

        entry_nome = ctk.CTkEntry(form_bg, height=50, font=font_input)
        entry_nome.pack(fill="x", padx=20)
        self.form_entries["nome"] = entry_nome

        opcoes = {
            "idade": ["Não Informado", "Menos de 18 anos", "18 a 28 anos", "29 a 40 anos", "41 a 55 anos", "56 anos ou mais"],
            "genero": ["Não informado", "Masculino", "Feminino", "Não binário"],
            "idealizacao_suicida": ["Não", "Sim"],
            "canal": ["WhatsApp", "Presencial", "Telefone", "Instagram", "Facebook"],
            "recorrencia": ["Atendido Novo", "Atendido Antigo"]
        }
        titulos = {
            "idade": "Faixa Etária:",
            "genero": "Gênero:",
            "canal": "Canal de Atendimento:",
            "recorrencia": "Recorrência:",
            "idealizacao_suicida": "Idealização Suicida:"
        }

        for key in ["idade", "genero", "canal", "recorrencia", "idealizacao_suicida"]:
            ctk.CTkLabel(form_bg, text=titulos[key], font=font_label).pack(anchor="w", padx=20, pady=(15, 5))
            dropdown = ctk.CTkOptionMenu(form_bg, values=opcoes[key], height=50, font=font_input, dropdown_font=font_input)
            dropdown.pack(fill="x", padx=20)
            self.form_entries[key] = dropdown

    def toggle_anonimo(self):
        entry = self.form_entries["nome"]
        if self.anon_var.get():
            entry.delete(0, "end")
            entry.insert(0, "Anônimo")
            entry.configure(state="disabled", fg_color=("gray70", "gray30"))
        else:
            entry.configure(state="normal", fg_color=ctk.ThemeManager.theme["CTkEntry"]["fg_color"])
            entry.delete(0, "end")

    def toggle_anonimo_edit(self):
        entry = self.edit_entries["nome"]
        if self.edit_anon_var.get():
            entry.configure(state="normal", fg_color=ctk.ThemeManager.theme["CTkEntry"]["fg_color"])
            entry.delete(0, "end")
            entry.insert(0, "Anônimo")
            entry.configure(state="disabled", fg_color=("gray70", "gray30"))
        else:
            entry.configure(state="normal", fg_color=ctk.ThemeManager.theme["CTkEntry"]["fg_color"])
            if entry.get().strip() == "Anônimo":
                entry.delete(0, "end")

    def save_case(self):
        nome = self.form_entries["nome"].get().strip()

        if not nome:
            messagebox.showwarning(
                "Erro de Preenchimento",
                "O Nome do Atendido está vazio!\n\nPor favor, digite o nome ou marque a caixa 'Marcar como Anônimo' antes de salvar."
            )
            return

        data_hora_atual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        novo_uuid = str(uuid.uuid4())

        self.cursor.execute(
            """INSERT INTO casos
            (id_nuvem, status_sync, plantonista, id_plantonista, turno, nome, idade, genero, idealizacao_suicida, canal, recorrencia, data_hora, atendimento_real)
            VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (novo_uuid, self.sessao_nome, self.sessao_id, self.sessao_turno, nome,
             self.form_entries["idade"].get(), self.form_entries["genero"].get(), self.form_entries["idealizacao_suicida"].get(),
             self.form_entries["canal"].get(), self.form_entries["recorrencia"].get(), data_hora_atual)
        )
        self.conn.commit()

        # DESTRÓI O BOTÃO IMEDIATAMENTE APÓS O PRIMEIRO CASO
        self.avaliar_exibicao_botao_vazio()

        messagebox.showinfo("Sucesso", "Atendimento salvo localmente!\nSincronização em andamento.")

        self.form_entries["nome"].configure(state="normal", fg_color=ctk.ThemeManager.theme["CTkEntry"]["fg_color"])
        self.form_entries["nome"].delete(0, "end")
        self.chk_anon.deselect()

        for key in ["idade", "genero", "canal", "recorrencia", "idealizacao_suicida"]:
            valores = self.form_entries[key].cget("values")
            self.form_entries[key].set(valores[0])

    def create_view_cases_content(self):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.content_frames["view"] = frame

        ctk.CTkLabel(frame, text="Histórico de Casos do Turno", font=ctk.CTkFont(size=36, weight="bold"), anchor="w").pack(fill="x", padx=40, pady=(40, 20))

        self.cases_scroll = ctk.CTkScrollableFrame(frame, fg_color=("gray90", "gray13"))
        self.cases_scroll.pack(fill="both", expand=True, padx=40, pady=(0, 10))

    def load_and_show_cases(self):
        for widget in self.cases_scroll.winfo_children():
            widget.destroy()

        if self.is_admin:
            self.cursor.execute(
                "SELECT id, nome, canal, data_hora FROM casos WHERE atendimento_real = 1 ORDER BY id DESC"
            )
            casos = self.cursor.fetchall()
            empty_text = "Nenhum atendimento registrado no banco."
        else:
            self.cursor.execute(
                "SELECT id, nome, canal, data_hora FROM casos WHERE id_plantonista = ? AND turno = ? ORDER BY id DESC",
                (self.sessao_id, self.sessao_turno)
            )
            casos = self.cursor.fetchall()
            empty_text = "Nenhum atendimento registrado neste turno."

        if not casos:
            ctk.CTkLabel(self.cases_scroll, text=empty_text, font=ctk.CTkFont(size=22), text_color="gray50").pack(pady=40)
        else:
            for caso in casos:
                case_id, nome, canal, data_hora = caso
                row = ctk.CTkFrame(self.cases_scroll, fg_color=("gray85", "gray20"), height=70)
                row.pack(fill="x", pady=5, padx=10)
                row.pack_propagate(False)

                ctk.CTkLabel(row, text=f"#{case_id}", font=ctk.CTkFont(size=20)).pack(side="left", padx=15)
                ctk.CTkLabel(row, text=nome, font=ctk.CTkFont(size=22, weight="bold")).pack(side="left", padx=15)

                # NOVO: Os dois botões lado a lado diretamente na lista
                btn_detalhes = ctk.CTkButton(row, text="Ver Detalhes", width=110, font=ctk.CTkFont(size=14, weight="bold"), command=lambda cid=case_id: self.show_case_details(cid))
                btn_detalhes.pack(side="right", padx=(5, 15))

                btn_retificar = ctk.CTkButton(row, text="Retificar", width=100, font=ctk.CTkFont(size=14, weight="bold"), fg_color="#b8860b", hover_color="#8b6508", command=lambda cid=case_id: self.load_edit_form(cid))
                btn_retificar.pack(side="right", padx=5)

                hora_formatada = data_hora[-8:-3]
                ctk.CTkLabel(row, text=f"Via {canal} às {hora_formatada}", font=ctk.CTkFont(size=18), text_color="gray60").pack(side="right", padx=15)

        self.show_content_frame("view")

    def create_case_detail_content(self):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.content_frames["case_detail"] = frame

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=40, pady=(40, 20))

        ctk.CTkButton(header, text="← Voltar", width=120, height=40, font=ctk.CTkFont(size=18, weight="bold"), command=lambda: self.show_content_frame("view")).pack(side="left")
        ctk.CTkLabel(header, text="Detalhes do Atendimento", font=ctk.CTkFont(size=36, weight="bold")).pack(side="left", padx=30)

        self.detail_scroll = ctk.CTkScrollableFrame(frame, fg_color=("gray90", "gray13"), corner_radius=10)
        self.detail_scroll.pack(fill="both", expand=True, padx=40, pady=(0, 40))

    def show_case_details(self, case_id):
        for widget in self.detail_scroll.winfo_children():
            widget.destroy()

        # O botão de retificar foi removido daqui porque agora mora na lista de casos
        header = self.content_frames["case_detail"].winfo_children()[0]
        for child in header.winfo_children():
            if isinstance(child, ctk.CTkButton) and child.cget("text") == "Retificar Registro":
                child.destroy()

        self.cursor.execute(
            "SELECT plantonista, turno, nome, idade, genero, idealizacao_suicida, canal, recorrencia, data_hora, status_sync FROM casos WHERE id = ?",
            (case_id,)
        )
        caso = self.cursor.fetchone()
        if not caso:
            return

        plantonista, turno, nome, idade, genero, idealizacao_suicida, canal, recorrencia, data_hora, status_sync = caso

        campos = [
            ("Data e Hora", data_hora),
            ("Plantonista Responsável", f"{plantonista} (Turno {turno})"),
            ("Nome do Atendido", nome),
            ("Faixa Etária", idade),
            ("Identidade de Gênero", genero),
            ("Idealização Suicida", idealizacao_suicida),
            ("Canal de Contato", canal),
            ("Histórico", recorrencia),
            ("Status do Servidor", "Sincronizado na Nuvem" if status_sync == 1 else "Pendente (Salvo apenas neste PC)")
        ]

        for titulo, valor in campos:
            linha = ctk.CTkFrame(self.detail_scroll, fg_color="transparent")
            linha.pack(fill="x", pady=15, padx=20)
            ctk.CTkLabel(linha, text=f"{titulo}:", font=ctk.CTkFont(size=20, weight="bold"), text_color="gray50", width=250, anchor="w").pack(side="left")
            cor_texto = "orange" if titulo == "Status do Servidor" and status_sync == 0 else ("black", "white")
            ctk.CTkLabel(linha, text=valor, font=ctk.CTkFont(size=22), text_color=cor_texto, anchor="w").pack(side="left", fill="x", expand=True)

        self.show_content_frame("case_detail")

    def create_my_shifts_content(self):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.content_frames["my_shifts"] = frame

        ctk.CTkLabel(frame, text="Meus Turnos", font=ctk.CTkFont(size=36, weight="bold"), anchor="w").pack(fill="x", padx=40, pady=(40, 10))
        ctk.CTkLabel(frame, text="Histórico dos seus acessos por turno (P10, P13, P16, P19).", font=ctk.CTkFont(size=18), text_color="gray50", anchor="w").pack(fill="x", padx=40)

        self.my_shifts_scroll = ctk.CTkScrollableFrame(frame, fg_color=("gray90", "gray13"))
        self.my_shifts_scroll.pack(fill="both", expand=True, padx=40, pady=(20, 10))

    def load_and_show_my_shifts(self):
        for widget in self.my_shifts_scroll.winfo_children():
            widget.destroy()

        if not self.sessao_id:
            ctk.CTkLabel(self.my_shifts_scroll, text="Faça login para visualizar seus turnos.", font=ctk.CTkFont(size=22), text_color="gray50").pack(pady=40)
            self.show_content_frame("my_shifts")
            return

        if self.is_admin:
            self.cursor.execute(
                """SELECT plantonista, id_plantonista, data_acesso, hora_acesso, turno
                   FROM pontos_plantonistas
                   ORDER BY data_acesso DESC, hora_acesso DESC"""
            )
            turnos = self.cursor.fetchall()
            empty_text = "Nenhum turno registrado no banco."
        else:
            self.cursor.execute(
                """SELECT plantonista, id_plantonista, data_acesso, hora_acesso, turno
                   FROM pontos_plantonistas
                   WHERE id_plantonista = ?
                   ORDER BY data_acesso DESC, hora_acesso DESC""",
                (self.sessao_id,)
            )
            turnos = self.cursor.fetchall()
            empty_text = "Nenhum turno registrado para este ID."

        if not turnos:
            ctk.CTkLabel(self.my_shifts_scroll, text=empty_text, font=ctk.CTkFont(size=22), text_color="gray50").pack(pady=40)
        else:
            header = ctk.CTkFrame(self.my_shifts_scroll, fg_color=("gray85", "gray20"), height=50)
            header.pack(fill="x", padx=10, pady=(5, 8))
            header.pack_propagate(False)
            ctk.CTkLabel(header, text="Plantonista", font=ctk.CTkFont(size=16, weight="bold"), width=190, anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(header, text="ID", font=ctk.CTkFont(size=16, weight="bold"), width=100, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(header, text="Data", font=ctk.CTkFont(size=16, weight="bold"), width=120, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(header, text="Hora Início", font=ctk.CTkFont(size=16, weight="bold"), width=115, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(header, text="Turno Realizado", font=ctk.CTkFont(size=16, weight="bold"), width=130, anchor="w").pack(side="left", padx=4)

            for plantonista, id_plantonista, data_acesso, hora_acesso, turno in turnos:
                row = ctk.CTkFrame(self.my_shifts_scroll, fg_color=("gray85", "gray20"), height=56)
                row.pack(fill="x", padx=10, pady=4)
                row.pack_propagate(False)

                ctk.CTkLabel(row, text=plantonista, font=ctk.CTkFont(size=15), width=190, anchor="w").pack(side="left", padx=8)
                ctk.CTkLabel(row, text=id_plantonista, font=ctk.CTkFont(size=15), width=100, anchor="w").pack(side="left", padx=4)
                ctk.CTkLabel(row, text=data_acesso, font=ctk.CTkFont(size=15), width=120, anchor="w").pack(side="left", padx=4)
                ctk.CTkLabel(row, text=hora_acesso, font=ctk.CTkFont(size=15), width=115, anchor="w").pack(side="left", padx=4)
                ctk.CTkLabel(row, text=turno, font=ctk.CTkFont(size=15, weight="bold"), width=130, anchor="w", text_color="#2ecc71").pack(side="left", padx=4)

        self.show_content_frame("my_shifts")

    def build_content_screens(self):
        # Substitua a sua função build_content_screens atual por esta, adicionando a linha abaixo:
        self.create_dashboard_content()
        self.create_insert_content()
        self.create_view_cases_content()
        self.create_case_detail_content()
        self.create_my_shifts_content()
        self.create_edit_case_content()  # NOVA

    def create_edit_case_content(self):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.content_frames["edit_case"] = frame

        ctk.CTkLabel(frame, text="Retificar Atendimento", font=ctk.CTkFont(size=36, weight="bold"), anchor="w").pack(fill="x", padx=40, pady=(40, 20))

        bottom_bar = ctk.CTkFrame(frame, fg_color="transparent")
        bottom_bar.pack(side="bottom", fill="x", padx=40, pady=(10, 30))

        ctk.CTkButton(bottom_bar, text="CANCELAR", height=60, width=200, fg_color="gray40", hover_color="gray30", font=ctk.CTkFont(size=22, weight="bold"), command=lambda: self.show_content_frame("view")).pack(side="left")
        self.btn_salvar_edicao = ctk.CTkButton(bottom_bar, text="SALVAR RETIFICAÇÃO", height=60, width=350, fg_color="#b8860b", hover_color="#8b6508", font=ctk.CTkFont(size=26, weight="bold"), command=self.save_edited_case)
        self.btn_salvar_edicao.pack(side="right")

        form_bg = ctk.CTkScrollableFrame(frame, fg_color=("gray90", "gray13"), corner_radius=10)
        form_bg.pack(side="top", fill="both", expand=True, padx=40, pady=(0, 0))

        self.edit_entries = {}
        font_label = ctk.CTkFont(size=22, weight="bold")
        font_input = ctk.CTkFont(size=22)

        header_nome_edit = ctk.CTkFrame(form_bg, fg_color="transparent")
        header_nome_edit.pack(fill="x", padx=20, pady=(15, 5))

        ctk.CTkLabel(header_nome_edit, text="Nome do Atendido:", font=font_label).pack(side="left")

        self.edit_anon_var = ctk.BooleanVar(value=False)
        self.chk_anon_edit = ctk.CTkCheckBox(
            header_nome_edit,
            text="Marcar como Anônimo",
            font=ctk.CTkFont(size=18),
            variable=self.edit_anon_var,
            command=self.toggle_anonimo_edit
        )
        self.chk_anon_edit.pack(side="right")

        entry_nome = ctk.CTkEntry(form_bg, height=50, font=font_input)
        entry_nome.pack(fill="x", padx=20)
        self.edit_entries["nome"] = entry_nome

        ctk.CTkLabel(form_bg, text="Data e Hora do Registro (AAAA-MM-DD HH:MM:SS):", font=font_label).pack(anchor="w", padx=20, pady=(15, 5))
        entry_data_hora = ctk.CTkEntry(form_bg, height=50, font=font_input)
        entry_data_hora.pack(fill="x", padx=20)
        self.edit_entries["data_hora"] = entry_data_hora

        opcoes = {
            "idade": ["Não Informado", "Menos de 18 anos", "18 a 28 anos", "29 a 40 anos", "41 a 55 anos", "56 anos ou mais"],
            "genero": ["Não informado", "Masculino", "Feminino", "Não binário"],
            "idealizacao_suicida": ["Não", "Sim"],
            "canal": ["WhatsApp", "Presencial", "Telefone", "Instagram", "Facebook"],
            "recorrencia": ["Atendido Novo", "Atendido Antigo"]
        }
        titulos = {
            "idade": "Faixa Etária:",
            "genero": "Gênero:",
            "canal": "Canal de Atendimento:",
            "recorrencia": "Recorrência:",
            "idealizacao_suicida": "Idealização Suicida:"
        }

        for key in ["idade", "genero", "canal", "recorrencia", "idealizacao_suicida"]:
            ctk.CTkLabel(form_bg, text=titulos[key], font=font_label).pack(anchor="w", padx=20, pady=(15, 5))
            dropdown = ctk.CTkOptionMenu(form_bg, values=opcoes[key], height=50, font=font_input, dropdown_font=font_input)
            dropdown.pack(fill="x", padx=20)
            self.edit_entries[key] = dropdown

    def load_edit_form(self, case_id):
        """Nova lógica de roteamento: busca os dados direto do banco usando apenas o case_id"""
        self.cursor.execute(
            "SELECT id_nuvem, nome, idade, genero, idealizacao_suicida, canal, recorrencia, data_hora FROM casos WHERE id = ?",
            (case_id,)
        )
        caso = self.cursor.fetchone()
        if not caso:
            return

        id_nuvem, nome, idade, genero, idealizacao_suicida, canal, recorrencia, data_hora = caso

        self.current_edit_id = case_id
        self.current_edit_nuvem_id = id_nuvem

        self.edit_entries["nome"].configure(state="normal", fg_color=ctk.ThemeManager.theme["CTkEntry"]["fg_color"])
        self.edit_entries["nome"].delete(0, "end")

        self.edit_entries["nome"].insert(0, nome)
        if nome == "Anônimo":
            self.edit_anon_var.set(True)
            self.edit_entries["nome"].configure(state="disabled", fg_color=("gray70", "gray30"))
        else:
            self.edit_anon_var.set(False)
            self.edit_entries["nome"].configure(state="normal", fg_color=ctk.ThemeManager.theme["CTkEntry"]["fg_color"])
        self.edit_entries["data_hora"].delete(0, "end")
        self.edit_entries["data_hora"].insert(0, data_hora)
        self.edit_entries["idade"].set(idade)
        self.edit_entries["genero"].set(genero)
        self.edit_entries["idealizacao_suicida"].set(idealizacao_suicida)
        self.edit_entries["canal"].set(canal)
        self.edit_entries["recorrencia"].set(recorrencia)

        self.show_content_frame("edit_case")

    def save_edited_case(self):
        nome = self.edit_entries["nome"].get().strip()
        data_hora_editada = self.edit_entries["data_hora"].get().strip()

        if not nome:
            messagebox.showwarning("Erro", "O Nome não pode ficar vazio.")
            return

        try:
            datetime.datetime.strptime(data_hora_editada, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            messagebox.showwarning("Erro", "Data/Hora inválida. Use o formato: AAAA-MM-DD HH:MM:SS")
            return

        # Atualiza o banco local e reseta o status_sync para 0 para forçar a re-sincronização
        self.cursor.execute(
            """UPDATE casos
               SET nome = ?, data_hora = ?, idade = ?, genero = ?, idealizacao_suicida = ?, canal = ?, recorrencia = ?, status_sync = 0
               WHERE id = ?""",
            (nome, data_hora_editada, self.edit_entries["idade"].get(), self.edit_entries["genero"].get(),
             self.edit_entries["idealizacao_suicida"].get(), self.edit_entries["canal"].get(), self.edit_entries["recorrencia"].get(), self.current_edit_id)
        )
        self.conn.commit()

        messagebox.showinfo("Sucesso", "Atendimento retificado com sucesso!\nA alteração será enviada para a nuvem.")

        # Recarrega a lista e volta para a tela de visualização
        self.load_and_show_cases()


if __name__ == "__main__":
    app = SuperAppAMA()
    app.mainloop()