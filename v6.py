import customtkinter as ctk
import serial
import serial.tools.list_ports
import threading
import time
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import filedialog, ttk, messagebox
from datetime import datetime
import openpyxl

# --- CONFIGURAÇÕES VISUAIS ---
THEME_CFG = {
    "Dark": {
        "bg": "#1e1e1e", "panel": "#2b2b2b", "text": "#e0e0e0", "text_dim": "#a0a0a0",
        "chart_bg": "#2b2b2b", "chart_grid": "#444444", "chart_line": "#2ecc71", "chart_axis": "#a0a0a0",
        "tree_bg": "#2b2b2b", "tree_fg": "#e0e0e0", "tree_field": "#2b2b2b", "tree_head_bg": "#444444",
        "tree_head_fg": "#ffffff"
    },
    "Light": {
        "bg": "#f0f0f0", "panel": "#ffffff", "text": "#333333", "text_dim": "#555555",
        "chart_bg": "#ffffff", "chart_grid": "#cccccc", "chart_line": "#27ae60", "chart_axis": "#333333",
        "tree_bg": "#ffffff", "tree_fg": "#333333", "tree_field": "#ffffff", "tree_head_bg": "#d0d0d0",
        "tree_head_fg": "#333333"
    }
}

COLOR_ACCENT = "#1f6aa5"
COLOR_SUCCESS = "#2cc985"
COLOR_WARNING = "#e67e22"
COLOR_DANGER = "#c0392b"

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")


class ThermalControlApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.current_theme = "Dark"
        self.serial_port = None
        self.is_connected = False
        self.monitoring = False  # Variável para controlar se registramos dados ou não
        self.thread = None
        self.start_time = None
        self.last_log_time = 0
        self.active_mode = 0

        # Variável nova para marcar o degrau
        self.next_event_marker = ""

        # --- NOVO: Guarda a última temperatura lida pelo sensor ---
        self.last_read_temp = None

        #Variável de segurança para o Modo Ventilação
        self.base_heat_confirmed = False

        # Dados
        self.full_data_log = []

        # Dados
        self.full_data_log = []
        self.display_data_x = []
        self.display_data_y = []
        self.display_data_setpoint = []

        # Config Janela
        self.withdraw()
        self.title("THERMAL CONTROL PRO v7.0")

        window_width = 1150
        window_height = 780
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        pos_x = (screen_width - window_width) // 2
        pos_y = (screen_height - window_height) // 2
        self.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")
        self.minsize(1000, 700)

        self.vcmd = (self.register(self.validate_number_input), '%P')

        self._setup_ui()
        self.apply_theme_colors()
        self._configure_table_columns(1)

        self.after(200, self.deiconify)
        self.after(500, self.auto_select_arduino)
        self.send_heartbeat()

        # ADICIONE ESTA LINHA NO FINAL (O atraso de 100ms garante que funcione após o geometry)
        self.after(100, lambda: self.state('zoomed'))

    def _setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- SIDEBAR COMPACTA ---
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Header
        header = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        header.pack(pady=(5, 5), padx=10, fill="x")
        ctk.CTkLabel(header, text="CONTROLE", font=("Roboto", 16, "bold")).pack(side="left")
        self.btn_theme = ctk.CTkButton(header, text="☀", width=30, command=self.toggle_theme,
                                       fg_color="transparent", border_width=1, text_color=COLOR_WARNING)
        self.btn_theme.pack(side="right")

        # CONEXÃO
        self._create_section_label("CONEXÃO")
        self.com_port_var = ctk.StringVar(value="Porta...")
        self.com_menu = ctk.CTkOptionMenu(self.sidebar, variable=self.com_port_var,
                                          values=self.get_com_ports(), fg_color=COLOR_ACCENT, height=22,
                                          font=("Arial", 11))
        self.com_menu.pack(pady=2, padx=15, fill="x")

        self.btn_connect = ctk.CTkButton(self.sidebar, text="CONECTAR", command=self.toggle_connection,
                                         fg_color=COLOR_SUCCESS, font=("Roboto", 11, "bold"), height=25)
        self.btn_connect.pack(pady=(2, 5), padx=15, fill="x")

        self._create_divider()

        # CONFIG
        self._create_section_label("CONFIGURAÇÃO")

        f1 = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        f1.pack(pady=1, padx=15, fill="x")
        ctk.CTkLabel(f1, text="Intervalo (s):", font=("Arial", 11)).pack(side="left")
        self.entry_interval = ctk.CTkEntry(f1, width=50, justify="center", height=22)
        self.entry_interval.pack(side="right")
        self.entry_interval.insert(0, "1.0")

        f2 = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        f2.pack(pady=1, padx=15, fill="x")
        ctk.CTkLabel(f2, text="Distúrbio (°C):", font=("Arial", 11)).pack(side="left")
        self.entry_dist = ctk.CTkEntry(f2, width=50, justify="center", height=22)
        self.entry_dist.pack(side="right")
        self.entry_dist.insert(0, "0.0")

        self.btn_dist = ctk.CTkButton(self.sidebar, text="Aplicar Dist.", command=self.send_disturbance,
                                      fg_color="#555555", height=22, font=("Arial", 10))
        self.btn_dist.pack(pady=2, padx=15, fill="x")

        self._create_divider()

        # MODO
        self._create_section_label("MODO")
        self.mode_var = ctk.StringVar(value="Só Aquecimento")
        self.mode_menu = ctk.CTkOptionMenu(self.sidebar, variable=self.mode_var,
                                           values=["Automático (Ambos)", "Só Aquecimento", "Só Ventilação"],
                                           command=self.change_control_mode, height=22, font=("Arial", 11))
        self.mode_menu.pack(pady=2, padx=15, fill="x")

        # Campo Lampada Base
        self.base_heat_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        ctk.CTkLabel(self.base_heat_frame, text="Lamp. Base (%):", font=("Arial", 11)).pack(side="left")
        self.entry_base_heat = ctk.CTkEntry(self.base_heat_frame, width=40, justify="center", height=22)
        self.entry_base_heat.pack(side="left", padx=(5, 5))
        self.entry_base_heat.insert(0, "50")
        self.btn_conf_base = ctk.CTkButton(self.base_heat_frame, text="OK", width=30, height=22,
                                           fg_color=COLOR_ACCENT, command=self.send_and_lock_base)
        self.btn_conf_base.pack(side="left")

        self._create_divider()

        # SETPOINT
        self._create_section_label("SETPOINT (°C)")
        self.entry_setpoint = ctk.CTkEntry(self.sidebar, placeholder_text="Ex: 30.0", justify="center", height=25)
        self.entry_setpoint.pack(pady=2, padx=15, fill="x")

        self.btn_set = ctk.CTkButton(self.sidebar, text="INICIAR", command=self.validate_and_send_setpoint,
                                     border_width=1, height=25, fg_color=COLOR_ACCENT)
        self.btn_set.pack(pady=2, padx=15, fill="x")

        self._create_divider()

        # PID
        self._create_section_label("PID")
        self.lbl_current_pid = ctk.CTkLabel(self.sidebar, text="PID Atual: -- / -- / --",
                                            font=("Arial", 9), text_color=COLOR_WARNING)
        self.lbl_current_pid.pack(pady=(0, 2))

        self.pid_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.pid_frame.pack(pady=1, padx=5)
        self.entry_kp = self._create_pid_block(self.pid_frame, "Kp", "40.0", 0)
        self.entry_ki = self._create_pid_block(self.pid_frame, "Ki", "1.0", 1)
        self.entry_kd = self._create_pid_block(self.pid_frame, "Kd", "10.0", 2)

        self.btn_pid = ctk.CTkButton(self.sidebar, text="Atualizar PID", command=self.validate_and_send_pid,
                                     border_width=1, border_color=COLOR_WARNING, text_color=COLOR_WARNING,
                                     fg_color="transparent", height=22, font=("Arial", 10))
        self.btn_pid.pack(pady=3, padx=15, fill="x")

        # EXPORTAÇÃO E STOP
        self.bottom_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.bottom_frame.pack(side="bottom", fill="x", padx=10, pady=10)

        ctk.CTkFrame(self.bottom_frame, height=1, fg_color="#3a3a3a").pack(fill="x", pady=(0, 5))

        self.export_grid = ctk.CTkFrame(self.bottom_frame, fg_color="transparent")
        self.export_grid.pack(fill="x", pady=(0, 5))

        self.btn_save_excel = ctk.CTkButton(self.export_grid, text="EXCEL", command=self.save_to_excel,
                                            fg_color="#27ae60", hover_color="#219150",
                                            height=25, width=80, font=("Arial", 10, "bold"), state="disabled")
        self.btn_save_excel.pack(side="left", padx=(0, 2), expand=True, fill="x")

        self.btn_save_img = ctk.CTkButton(self.export_grid, text="PNG", command=self.save_graph_image,
                                          fg_color="#8e44ad", hover_color="#732d91",
                                          height=25, width=80, font=("Arial", 10, "bold"), state="disabled")
        self.btn_save_img.pack(side="right", padx=(2, 0), expand=True, fill="x")

        self.btn_stop = ctk.CTkButton(self.bottom_frame, text="PARAR TUDO", command=self.stop_all_monitoring,
                                      fg_color=COLOR_DANGER, hover_color="#962d22",
                                      height=30, font=("Roboto", 11, "bold"))
        self.btn_stop.pack(fill="x")

        # --- DASHBOARD ---
        self.dashboard = ctk.CTkFrame(self, fg_color="transparent")
        self.dashboard.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.dashboard.grid_rowconfigure(1, weight=1)
        self.dashboard.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Cards
        self.card_temp, self.val_temp = self._create_metric_card_simple(self.dashboard, "TEMP. ATUAL", "---", 0, 0,
                                                                        COLOR_ACCENT)
        self.card_set, self.val_set = self._create_metric_card_simple(self.dashboard, "SETPOINT", "---", 0, 1,
                                                                      "default")
        self.card_lamp_frame, self.lbl_lamp_pct, self.lbl_lamp_volts = self._create_metric_card_complex(self.dashboard,
                                                                                                        "LÂMPADA (12V)",
                                                                                                        COLOR_WARNING,
                                                                                                        0, 2)
        self.card_fan_frame, self.lbl_fan_pct, self.lbl_fan_volts, self.lbl_fan_rpm = self._create_metric_card_fan(
            self.dashboard, "VENTOINHA (12V)", "#3498db", 0, 3)

        # Tabs
        self.tab_view = ctk.CTkTabview(self.dashboard)
        self.tab_view.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=(5, 0))

        # AUMENTO AGRESSIVO DA LARGURA DAS ABAS (Correção aqui)
        self.tab_view._segmented_button.configure(width=1000)

        self.tab_graph = self.tab_view.add("Gráfico")
        self.graph_container = ctk.CTkFrame(self.tab_graph, fg_color="transparent")
        self.graph_container.pack(fill="both", expand=True)
        self._init_matplotlib()

        self.tab_data = self.tab_view.add("Tabela")
        self.tree = ttk.Treeview(self.tab_data, show="headings", height=15)

        scrollbar = ttk.Scrollbar(self.tab_data, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # --- AJUSTE DINÂMICO DE COLUNAS ---
    def _configure_table_columns(self, mode):
        for col in self.tree["columns"]:
            self.tree.heading(col, text="")

        if mode == 1:
            cols = ("tempo", "temp", "set", "lamp_v", "event")
            names = ("Tempo(s)", "Temp(°C)", "Set(°C)", "Lamp(V)", "Eventos")
        elif mode == 2:
            cols = ("tempo", "temp", "set", "lamp_v", "fan_v", "rpm", "event")
            names = ("Tempo(s)", "Temp(°C)", "Set(°C)", "Lamp(V)", "Fan(V)", "RPM", "Eventos")
        else:
            cols = ("tempo", "temp", "set", "lamp_v", "fan_v", "rpm", "event")
            names = ("Tempo(s)", "Temp(°C)", "Set(°C)", "Lamp(V)", "Fan(V)", "RPM", "Eventos")

        self.tree["columns"] = cols
        for c, n in zip(cols, names):
            self.tree.heading(c, text=n)
            width = 120 if c == "event" else 80
            self.tree.column(c, width=width, anchor="center")

    # --- LÓGICA DE CONTROLE E UI ---

    def change_control_mode(self, choice):
        if not self.check_connection(): return

        map_modes = {"Automático (Ambos)": 0, "Só Aquecimento": 1, "Só Ventilação": 2}
        self.active_mode = map_modes.get(choice, 0)
        self._configure_table_columns(self.active_mode)

        # Envia modo ao Arduino
        self.serial_port.write(f"MODE:{self.active_mode}\n".encode())

        if self.active_mode == 2:  # Só Ventilação
            # Resetamos a confirmação para obrigar o usuário a dar "OK" novamente
            self.base_heat_confirmed = False

            # Mostra o frame
            self.base_heat_frame.pack(pady=2, padx=15, fill="x", after=self.mode_menu)

            # Destrava para edição
            self.entry_base_heat.configure(state="normal")
            self.btn_conf_base.configure(state="normal", text="OK", fg_color=COLOR_ACCENT)

            # Nota: NÃO enviamos o valor padrão automaticamente.
            # O usuário É OBRIGADO a clicar em OK para validar.

        else:
            self.base_heat_frame.pack_forget()  # Esconde
            self.base_heat_confirmed = True  # Nos outros modos, não precisa confirmar lâmpada

    def update_plot(self):
        colors = THEME_CFG[self.current_theme]
        self.ax.clear()

        self.ax.set_xlabel("Tempo (s)", color=colors["chart_axis"])
        self.ax.set_ylabel("Temperatura (°C)", color=colors["chart_axis"])

        self.ax.plot(self.display_data_x, self.display_data_y, color=colors["chart_line"], linewidth=1.5, label='Temp')
        self.ax.plot(self.display_data_x, self.display_data_setpoint, color=colors["chart_axis"], linestyle='--',
                     alpha=0.4, label='Set')

        if self.display_data_y:
            # Pega o MÍNIMO REAL dos dados coletados (ex: 28.5)
            y_min_data = min(self.display_data_y)
            y_max_data = max(self.display_data_y)

            # Considera o setpoint na escala também
            if self.display_data_setpoint:
                y_min_total = min(y_min_data, min(self.display_data_setpoint))
                y_max_total = max(y_max_data, max(self.display_data_setpoint))
            else:
                y_min_total = y_min_data
                y_max_total = y_max_data

            # Garante uma margem de visualização de +/- 1 grau
            self.ax.set_ylim(y_min_total - 1, y_max_total + 1)

        else:
            # Se não tem dados ainda, mostra uma escala "Aguardando..." (ex: 20 a 30)
            # NÃO MOSTRA 0
            self.ax.set_ylim(20, 30)

        self.ax.grid(True, linestyle=':', color=colors["chart_grid"], alpha=0.5)
        self.ax.set_facecolor(colors["chart_bg"])
        self.ax.spines['bottom'].set_color(colors["chart_axis"])
        self.ax.spines['left'].set_color(colors["chart_axis"])
        self.ax.tick_params(colors=colors["chart_axis"])

        legend = self.ax.legend(loc='upper right', facecolor=colors["panel"], labelcolor=colors["chart_axis"],
                                framealpha=0, fontsize=8)

        self.canvas.draw()

    def parse_float(self, val_str):
        if not val_str: return None
        try:
            return float(val_str.replace(',', '.'))
        except:
            return None

    def process_data(self, data):
        try:
            # 1. Leitura
            temp = float(data[1])
            setpoint = float(data[2])
            lamp_pwm = float(data[3])
            fan_pwm = float(data[4])
            rpm = int(data[6]) if len(data) > 6 else 0

            lamp_v = (lamp_pwm / 255.0) * 12.0
            fan_v = (fan_pwm / 255.0) * 12.0

            # Atualiza variável de validação e Cards (sempre visíveis)
            self.last_read_temp = temp
            self.update_cards(temp, setpoint, lamp_pwm, fan_pwm, rpm, lamp_v, fan_v)

            # --- FILTROS DE GRAVAÇÃO ---

            # Filtro 1: Se não estiver monitorando (aguardando os 2s ou parado), sai.
            if not self.monitoring:
                return

            # Filtro 2 (CRUCIAL): Se a temperatura for 0 ou erro, ignora para não estragar a escala.
            if temp <= 0.1:
                return

            # --- GRAVAÇÃO ---

            current_t = time.time()
            elapsed_time = current_t - self.start_time

            interval_setting = self.parse_float(self.entry_interval.get())
            if interval_setting is None or interval_setting < 0.1: interval_setting = 1.0

            if (current_t - self.last_log_time) >= interval_setting:
                self.last_log_time = current_t

                current_event = "-"
                if self.next_event_marker != "":
                    current_event = self.next_event_marker
                    self.next_event_marker = ""

                log_entry = {
                    "Tempo (s)": round(elapsed_time, 2),
                    "Temperatura (°C)": temp,
                    "Setpoint (°C)": setpoint,
                    "Tensão Lâmpada (V)": round(lamp_v, 2),
                    "Tensão Fan (V)": round(fan_v, 2),
                    "RPM": rpm,
                    "Eventos": current_event,
                    "Data/Hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                self.full_data_log.append(log_entry)

                vals = [f"{elapsed_time:.1f}", f"{temp:.1f}", f"{setpoint:.1f}", f"{lamp_v:.1f}"]
                if self.active_mode != 1:
                    vals.append(f"{fan_v:.1f}")
                    vals.append(f"{rpm}")
                vals.append(current_event)

                self.tree.insert("", "0", values=tuple(vals))

                self.display_data_x.append(elapsed_time)
                self.display_data_y.append(temp)
                self.display_data_setpoint.append(setpoint)

                self.update_plot()

        except Exception as e:
            print(f"Erro processamento: {e}")

    def save_to_excel(self):
        if not self.full_data_log: return
        filename = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if filename:
            try:
                df = pd.DataFrame(self.full_data_log)

                # Reorganiza para "Eventos" ficar no final ou visível
                # Filtra colunas baseado no modo, mas MANTÉM 'Eventos'
                if self.active_mode == 1:
                    df = df.drop(columns=["Tensão Fan (V)", "RPM"], errors='ignore')

                df.to_excel(filename, index=False)
                self.show_alert("SUCESSO", "Arquivo salvo!", False)
            except Exception as e:
                self.show_alert("ERRO", str(e), True)

    def toggle_theme(self):
        self.current_theme = "Light" if self.current_theme == "Dark" else "Dark"
        ctk.set_appearance_mode(self.current_theme)
        self.apply_theme_colors()

    def apply_theme_colors(self):
        colors = THEME_CFG[self.current_theme]
        self.configure(fg_color=colors["bg"])
        self.sidebar.configure(fg_color=colors["panel"])
        self.btn_set.configure(fg_color=COLOR_ACCENT, text_color="white")
        self.val_set.configure(text_color=colors["text_dim"])

        card_fg = colors["panel"]
        for w in [self.card_temp, self.card_set, self.card_lamp_frame, self.card_fan_frame]:
            w.configure(fg_color=card_fg)
            for child in w.winfo_children():
                if isinstance(child, ctk.CTkLabel) and getattr(child, "_font", [0, 0])[1] == 10:
                    child.configure(text_color=colors["text_dim"])

        self._style_treeview()
        if hasattr(self, 'fig'):
            self.fig.patch.set_facecolor(colors["panel"])
            self.ax.set_facecolor(colors["chart_bg"])
            self.ax.spines['bottom'].set_color(colors["chart_axis"])
            self.ax.spines['left'].set_color(colors["chart_axis"])
            self.ax.tick_params(colors=colors["chart_axis"])
            self.canvas.draw()

    def _style_treeview(self):
        style = ttk.Style()
        style.theme_use("clam")
        colors = THEME_CFG[self.current_theme]
        style.configure("Treeview", background=colors["tree_bg"], foreground=colors["tree_fg"],
                        fieldbackground=colors["tree_field"], borderwidth=0)
        style.configure("Treeview.Heading", background=colors["tree_head_bg"], foreground=colors["tree_head_fg"],
                        relief="flat")
        style.map("Treeview", background=[('selected', COLOR_ACCENT)], foreground=[('selected', 'white')])

    def _create_metric_card_simple(self, parent, title, value, row, col, color):
        if color == "default": color = "#a0a0a0"
        c = ctk.CTkFrame(parent)
        c.grid(row=row, column=col, sticky="nsew", padx=5)
        ctk.CTkLabel(c, text=title, font=("Arial", 10, "bold")).pack(pady=(15, 2))
        l = ctk.CTkLabel(c, text=value, font=("Arial", 22, "bold"), text_color=color)
        l.pack(pady=(0, 15))
        return c, l

    def _create_metric_card_complex(self, parent, title, color, row, col):
        c = ctk.CTkFrame(parent)
        c.grid(row=row, column=col, sticky="nsew", padx=5)
        ctk.CTkLabel(c, text=title, font=("Arial", 10, "bold")).pack(pady=(10, 0))
        lp = ctk.CTkLabel(c, text="0%", font=("Arial", 22, "bold"), text_color=color)
        lp.pack(pady=(2, 0))
        lv = ctk.CTkLabel(c, text="0.0 V", font=("Arial", 12))
        lv.pack(pady=(0, 10))
        return c, lp, lv

    def _create_metric_card_fan(self, parent, title, color, row, col):
        c = ctk.CTkFrame(parent)
        c.grid(row=row, column=col, sticky="nsew", padx=5)
        ctk.CTkLabel(c, text=title, font=("Arial", 10, "bold")).pack(pady=(8, 0))
        lp = ctk.CTkLabel(c, text="0%", font=("Arial", 20, "bold"), text_color=color)
        lp.pack(pady=(0, 0))
        d = ctk.CTkFrame(c, fg_color="transparent")
        d.pack(pady=(0, 5))
        lv = ctk.CTkLabel(d, text="0.0 V", font=("Arial", 11))
        lv.pack()
        lr = ctk.CTkLabel(d, text="0 RPM", font=("Arial", 11, "bold"), text_color="#888888")
        lr.pack()
        return c, lp, lv, lr

    def _create_section_label(self, text):
        ctk.CTkLabel(self.sidebar, text=text, font=("Roboto", 10, "bold"), text_color="#888888", anchor="w").pack(
            pady=(2, 0), padx=15, fill="x")

    def _create_divider(self):
        ctk.CTkFrame(self.sidebar, height=1, fg_color="#3a3a3a").pack(fill="x", pady=2, padx=10)

    def _create_pid_block(self, parent, label, default, col):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=0, column=col, padx=2)
        ctk.CTkLabel(f, text=label, font=("Arial", 10, "bold"), text_color="#888888").pack(pady=(0, 1))
        e = ctk.CTkEntry(f, width=45, justify="center", height=22)
        e.pack()
        e.insert(0, default)
        return e

    def _init_matplotlib(self):
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_container)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)

    def send_heartbeat(self):
        if self.is_connected and self.serial_port:
            try:
                self.serial_port.write(b"PING\n")
            except:
                pass
        self.after(1000, self.send_heartbeat)

    def update_cards(self, temp, setpoint, lamp_pwm, fan_pwm, rpm, lamp_v, fan_v):
        lamp_pct = int((lamp_pwm / 255) * 100)
        fan_pct = int((fan_pwm / 255) * 100)
        self.val_temp.configure(text=f"{temp:.1f} °C")
        self.val_set.configure(text=f"{setpoint:.1f} °C")
        self.lbl_lamp_pct.configure(text=f"{lamp_pct}%")
        self.lbl_lamp_volts.configure(text=f"{lamp_v:.1f} V")
        self.lbl_fan_pct.configure(text=f"{fan_pct}%")
        self.lbl_fan_volts.configure(text=f"{fan_v:.1f} V")
        self.lbl_fan_rpm.configure(text=f"{rpm} RPM")

    def toggle_connection(self):
        if not self.serial_port:
            try:
                self.serial_port = serial.Serial(self.com_menu.get(), 115200, timeout=1)
                self.is_connected = True
                self.monitoring = True
                self.start_time = time.time()

                # Limpa dados anteriores
                self.full_data_log = []
                self.display_data_x = []
                self.display_data_y = []
                self.display_data_setpoint = []
                for item in self.tree.get_children():
                    self.tree.delete(item)

                # Botão fica desabilitado e cinza indicando sucesso
                self.btn_connect.configure(text="SISTEMA CONECTADO", fg_color="#555555", state="disabled")

                # --- TRAVAMENTO IMEDIATO DO INTERVALO ---
                # Garante que desde o primeiro milissegundo o intervalo seja fixo
                self.entry_interval.configure(state="disabled")

                self.btn_save_excel.configure(state="disabled")
                self.btn_save_img.configure(state="disabled")

                self.thread = threading.Thread(target=self.read_serial_data, daemon=True)
                self.thread.start()

                self.after(200, lambda: self.change_control_mode(self.mode_var.get()))
                self.after(300, self.send_disturbance)
                self.after(400, self.validate_and_send_pid)
            except Exception as e:
                self.show_alert("FALHA", str(e), True)

    # CORREÇÃO PONTO 2 e 3: Função de Parada Total
    def stop_all_monitoring(self):
        # 1. Envia comando STOP para desligar componentes fisicos
        if self.serial_port:
            try:
                self.serial_port.write(b"STOP\n")
            except:
                pass

        # 2. Para de registrar dados
        self.monitoring = False

        # 3. Fecha a conexão serial (Resetando a interface para permitir reconexão)
        self.close_serial()

    def close_serial(self):
        self.is_connected = False
        self.monitoring = False
        if self.serial_port:
            try:
                self.serial_port.close()
            except:
                pass
        self.serial_port = None

        # Restaura botão CONECTAR
        self.btn_connect.configure(text="CONECTAR", fg_color=COLOR_SUCCESS, state="normal")

        # --- DESBLOQUEIA CAMPOS ---
        self.entry_setpoint.configure(state="normal")
        self.entry_interval.configure(state="normal")  # Destrava intervalo (pois desconectou)
        self.mode_menu.configure(state="normal")  # <--- DESTRAVA A MUDANÇA DE MODO

        # O botão da lâmpada base reativa se estivermos no modo ventilação
        if self.active_mode == 2:
            self.entry_base_heat.configure(state="normal")
            self.btn_conf_base.configure(state="normal")

        self.btn_set.configure(state="normal", fg_color=COLOR_ACCENT, text="INICIAR")

        if self.full_data_log:
            self.btn_save_excel.configure(state="normal")
            self.btn_save_img.configure(state="normal")

    def read_serial_data(self):
        while self.is_connected and self.serial_port:
            try:
                if self.serial_port.in_waiting:
                    line = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                    if line.startswith("DADOS"):
                        self.after(0, self.process_data, line.split(','))
            except:
                pass

    def send_disturbance(self):
        val = self.parse_float(self.entry_dist.get())
        if self.serial_port and val is not None:
            self.serial_port.write(f"DIST:{val}\n".encode())

    def send_and_lock_base(self, lock=True):
        val_f = self.parse_float(self.entry_base_heat.get())

        if val_f is not None:
            # Validação 10% a 100%
            if val_f < 10: val_f = 10
            if val_f > 100: val_f = 100

            # Atualiza visualmente
            current_state = self.entry_base_heat.cget("state")
            self.entry_base_heat.configure(state="normal")
            self.entry_base_heat.delete(0, "end")
            self.entry_base_heat.insert(0, str(int(val_f)))
            if current_state == "disabled": self.entry_base_heat.configure(state="disabled")

            # Envia ao Arduino
            val_pwm = int((val_f / 100.0) * 255)
            if self.serial_port:
                self.serial_port.write(f"BASE:{val_pwm}\n".encode())
                print(f"Lâmpada Base enviada: {val_pwm} PWM")  # Debug

            # Se foi confirmado pelo botão, trava e valida
            if lock:
                self.entry_base_heat.configure(state="disabled")
                self.btn_conf_base.configure(state="disabled", text="Def", fg_color="#555555")

                # --- NOVO: Marca como confirmado para permitir o INÍCIO ---
                self.base_heat_confirmed = True

    def validate_and_send_setpoint(self):
        # 1. Verifica conexão
        if not self.check_connection():
            return

            # 2. Valida input Setpoint
        val = self.parse_float(self.entry_setpoint.get())
        if val is None:
            self.show_alert("Atenção", "Informe o SETPOINT antes de iniciar.", True)
            self.entry_setpoint.focus()
            return

        # Validação do Modo Ventilação
        if self.active_mode == 2 and not self.base_heat_confirmed:
            self.show_alert("Configuração Pendente",
                            "No modo 'Só Ventilação', você DEVE definir e confirmar\n"
                            "o valor da Lâmpada Base antes de iniciar.\n\n"
                            "Defina o valor e clique no botão 'OK' ao lado.", True)
            return

        # 3. Validação de Limites (20-40)
        if val < 20 or val > 40:
            msg = (f"ATENÇÃO: {val}°C está fora da faixa ideal (20-40°C).\n"
                   "O sistema pode não ter potência suficiente.\n\n"
                   "Deseja continuar?")
            if not messagebox.askyesno("Limites", msg):
                return

        # 4. INÍCIO DO PROCESSO COM DELAY
        if self.serial_port:
            # RE-ENVIO DE SEGURANÇA (Garante o modo no Arduino)
            self.serial_port.write(f"MODE:{self.active_mode}\n".encode())
            time.sleep(0.1)

            # Envia Setpoint
            self.serial_port.write(f"SET:{val}\n".encode())

            # --- BLOQUEIOS DE INTERFACE (SEGURANÇA TOTAL) ---
            self.entry_setpoint.configure(state="disabled")
            self.mode_menu.configure(state="disabled")  # <--- BLOQUEIA A MUDANÇA DE MODO

            # Bloqueia também os controles da lâmpada base se estiverem visíveis
            self.entry_base_heat.configure(state="disabled")
            self.btn_conf_base.configure(state="disabled")

            self.btn_set.configure(state="disabled", fg_color=COLOR_WARNING, text="ESTABILIZANDO (2s)...")

            self.next_event_marker = f"INICIO (Set: {val})"

            self.after(2000, self.enable_monitoring_delayed)

    def enable_monitoring_delayed(self):
        # Ativa a gravação de dados após os 2 segundos
        self.monitoring = True

        # Atualiza o botão para o estado final "EM ANDAMENTO" (cinza escuro)
        self.btn_set.configure(text="EM ANDAMENTO", fg_color="#555555")

        print("Monitoramento iniciado após estabilização.")

    def validate_and_send_pid(self):
        if self.serial_port:
            kp = self.parse_float(self.entry_kp.get())
            ki = self.parse_float(self.entry_ki.get())
            kd = self.parse_float(self.entry_kd.get())
            if kp is not None:
                self.serial_port.write(f"PID:{kp}:{ki}:{kd}\n".encode())
                self.lbl_current_pid.configure(text=f"PID: {kp}/{ki}/{kd}")

    def save_graph_image(self):
        if self.full_data_log:
            f = filedialog.asksaveasfilename(defaultextension=".png")
            if f:
                self.fig.savefig(f)

    def get_com_ports(self):
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports] if ports else ["Nenhuma Porta"]

    def auto_select_arduino(self):
        for port in serial.tools.list_ports.comports():
            if "arduino" in port.description.lower() or "ch340" in port.description.lower():
                self.com_port_var.set(port.device)
                break

    def check_connection(self):
        if not self.serial_port:
            self.show_alert("Erro", "Conecte primeiro", True)
            return False
        return True

    def validate_number_input(self, n):
        return True

    def show_alert(self, t, m, e):
        if e:
            messagebox.showerror(t, m)
        else:
            messagebox.showinfo(t, m)


if __name__ == "__main__":
    app = ThermalControlApp()
    app.mainloop()