import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import queue
import zipfile
from datetime import datetime

import database as db
from sefaz import ConsultaSefaz, Documento
from licenca import verificar_ativacao, validar_chave, salvar_chave_local

# ---------------------------------------------------------------------------
# Paleta
# ---------------------------------------------------------------------------
BG       = '#1e1e2e'
SURFACE  = '#2a2a3e'
BORDER   = '#3a3a5c'
ACCENT   = '#7c6af7'
ACCENT_H = '#9d8fff'
TEXT     = '#cdd6f4'
SUBTEXT  = '#a6adc8'
GREEN    = '#a6e3a1'
RED      = '#f38ba8'
YELLOW   = '#f9e2af'
BLUE     = '#89b4fa'
ORANGE   = '#fab387'

UFS = ['AC','AL','AM','AP','BA','CE','DF','ES','GO','MA','MG','MS','MT',
       'PA','PB','PE','PI','PR','RJ','RN','RO','RR','RS','SC','SE','SP','TO']

STATUS_LABEL = {
    'pendente':   'Pendente',
    'entrada_ok': 'Entrada OK',
    'cancelada':  'Cancelada',
    'ignorada':   'Ignorada',
}
STATUS_COR = {
    'pendente':   TEXT,
    'entrada_ok': GREEN,
    'cancelada':  RED,
    'ignorada':   SUBTEXT,
}


def _so_digits(v: str) -> str:
    return ''.join(c for c in v if c.isdigit())


def _fmt_valor(v: str) -> str:
    if not v:
        return ''
    try:
        return f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    except Exception:
        return v


# ---------------------------------------------------------------------------
# Diálogo de ativação
# ---------------------------------------------------------------------------
class DialogoAtivacao(tk.Toplevel):
    def __init__(self, master, bloqueio=True):
        super().__init__(master)
        self.title('Ativação do Software')
        self.geometry('480x260')
        self.resizable(False, False)
        self.configure(bg=BG)
        self.grab_set()
        self.protocol('WM_DELETE_WINDOW', self._fechar)
        self._bloqueio = bloqueio
        self._ok = False

        ttk.Label(self, text='Provecta NF-e', font=('Segoe UI', 14, 'bold'),
                  background=BG, foreground=ACCENT).pack(pady=(24, 4))
        ttk.Label(self, text='Insira sua chave de ativação para continuar.',
                  background=BG, foreground=SUBTEXT, font=('Segoe UI', 10)).pack()

        frame = ttk.Frame(self, padding=(30, 16))
        frame.configure(style='TFrame')
        frame.pack(fill='x')

        ttk.Label(frame, text='Chave de Ativação', background=BG,
                  foreground=SUBTEXT, font=('Segoe UI', 9)).pack(anchor='w')
        self._chave_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self._chave_var, width=44,
                          font=('Consolas', 11))
        entry.pack(fill='x', pady=(4, 0))
        entry.bind('<Return>', lambda _: self._ativar())

        self._msg_var = tk.StringVar()
        self._msg_lbl = ttk.Label(frame, textvariable=self._msg_var,
                                   background=BG, foreground=RED,
                                   font=('Segoe UI', 9), wraplength=400)
        self._msg_lbl.pack(anchor='w', pady=(6, 0))

        btn_frame = ttk.Frame(self, padding=(30, 0))
        btn_frame.configure(style='TFrame')
        btn_frame.pack(fill='x')
        ttk.Button(btn_frame, text='Ativar', style='Primary.TButton',
                   command=self._ativar).pack(side='right')
        if not bloqueio:
            ttk.Button(btn_frame, text='Cancelar', style='Secondary.TButton',
                       command=self._fechar).pack(side='right', padx=(0, 8))

    def _ativar(self):
        chave = self._chave_var.get().strip()
        ok, msg = validar_chave(chave)
        if ok:
            salvar_chave_local(chave)
            self._ok = True
            self._msg_var.set(msg)
            self._msg_lbl.config(foreground=GREEN)
            self.after(1200, self.destroy)
        else:
            self._msg_var.set(msg)
            self._msg_lbl.config(foreground=RED)

    def _fechar(self):
        if self._bloqueio:
            if messagebox.askyesno('Sair', 'Sem ativação o software não funciona. Sair?',
                                   parent=self):
                self.master.destroy()
        else:
            self.destroy()


# ---------------------------------------------------------------------------
# Viewer XML
# ---------------------------------------------------------------------------
class ViewerXML(tk.Toplevel):
    def __init__(self, master, nsu: str, xml_raw: str):
        super().__init__(master)
        self.title(f'XML — NSU {nsu}')
        self.geometry('960x640')
        self.configure(bg=BG)

        try:
            from lxml import etree
            root = etree.fromstring(xml_raw.encode())
            pretty = etree.tostring(root, pretty_print=True, encoding='unicode')
        except Exception:
            pretty = xml_raw

        self._pretty = pretty
        self._nsu = nsu

        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill='x')
        ttk.Button(toolbar, text='Salvar XML', style='Secondary.TButton',
                   command=self._salvar).pack(side='left')
        ttk.Button(toolbar, text='Copiar tudo', style='Secondary.TButton',
                   command=self._copiar).pack(side='left', padx=(6, 0))

        txt = scrolledtext.ScrolledText(self, bg=SURFACE, fg=TEXT,
                                         font=('Consolas', 9), wrap='none',
                                         relief='flat', borderwidth=0)
        txt.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        txt.insert('end', pretty)
        txt.config(state='disabled')
        self._txt = txt

    def _salvar(self):
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension='.xml',
            initialfile=f'NSU-{self._nsu}.xml',
            filetypes=[('XML', '*.xml'), ('Todos', '*.*')],
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self._pretty)

    def _copiar(self):
        self.clipboard_clear()
        self.clipboard_append(self._pretty)


# ---------------------------------------------------------------------------
# App principal
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Provecta NF-e — Distribuição DFe')
        self.geometry('1280x780')
        self.minsize(960, 600)
        self.configure(bg=BG)

        db.inicializar()

        self._consulta = ConsultaSefaz()
        self._fila: queue.Queue = queue.Queue()
        self._item_para_nsu: dict[str, str] = {}   # tree item_id → nsu
        self._total_novos = 0

        self._aplicar_tema()
        self._construir_ui()
        self._carregar_banco()
        self._processar_fila()
        self._verificar_licenca()

    # -----------------------------------------------------------------------
    # Tema
    # -----------------------------------------------------------------------
    def _aplicar_tema(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background=BG, foreground=TEXT, font=('Segoe UI', 10))
        s.configure('TFrame', background=BG)
        s.configure('Surface.TFrame', background=SURFACE)
        s.configure('TLabel', background=BG, foreground=TEXT)
        s.configure('Sub.TLabel', background=SURFACE, foreground=SUBTEXT, font=('Segoe UI', 9))
        s.configure('SubBG.TLabel', background=BG, foreground=SUBTEXT, font=('Segoe UI', 9))
        s.configure('Title.TLabel', background=BG, foreground=TEXT, font=('Segoe UI', 13, 'bold'))
        s.configure('Accent.TLabel', background=BG, foreground=ACCENT, font=('Segoe UI', 11, 'bold'))
        s.configure('AccentS.TLabel', background=SURFACE, foreground=ACCENT, font=('Segoe UI', 10, 'bold'))

        for name, bg in [('Custom.TEntry', SURFACE)]:
            s.configure(name, fieldbackground=bg, foreground=TEXT,
                        insertcolor=TEXT, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER)

        s.configure('TCombobox', fieldbackground=SURFACE, background=SURFACE,
                    foreground=TEXT, selectbackground=ACCENT, arrowcolor=TEXT)
        s.map('TCombobox', fieldbackground=[('readonly', SURFACE)])
        s.configure('TCheckbutton', background=BG, foreground=TEXT)

        for name, bg, fg, hbg in [
            ('Primary.TButton',   ACCENT,   'white', ACCENT_H),
            ('Danger.TButton',    '#e05c6b', 'white', RED),
            ('Secondary.TButton', BORDER,   TEXT,    SURFACE),
            ('Success.TButton',   '#2d5a3d', GREEN,   '#3a7a52'),
        ]:
            s.configure(name, background=bg, foreground=fg,
                        font=('Segoe UI', 10, 'bold' if name != 'Secondary.TButton' else 'normal'),
                        borderwidth=0, padding=(10, 5))
            s.map(name, background=[('active', hbg), ('disabled', BORDER)])

        s.configure('Treeview', background=SURFACE, fieldbackground=SURFACE,
                    foreground=TEXT, rowheight=26, borderwidth=0)
        s.configure('Treeview.Heading', background=BORDER, foreground=TEXT,
                    font=('Segoe UI', 9, 'bold'), borderwidth=0)
        s.map('Treeview', background=[('selected', ACCENT)],
              foreground=[('selected', 'white')])

        s.configure('Horizontal.TProgressbar', background=ACCENT,
                    troughcolor=BORDER, borderwidth=0, thickness=5)
        s.configure('TSeparator', background=BORDER)

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------
    def _construir_ui(self):
        header = ttk.Frame(self, padding=(20, 12, 20, 8))
        header.pack(fill='x')
        ttk.Label(header, text='Provecta NF-e', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='  Distribuição DFe', style='Accent.TLabel').pack(side='left')
        self._lbl_licenca = ttk.Label(header, text='', style='SubBG.TLabel')
        self._lbl_licenca.pack(side='right')

        ttk.Separator(self, orient='horizontal').pack(fill='x', padx=20)

        corpo = ttk.Frame(self, padding=(16, 12))
        corpo.pack(fill='both', expand=True)
        corpo.columnconfigure(1, weight=1)
        corpo.rowconfigure(0, weight=1)

        self._painel_config(corpo)
        self._painel_direito(corpo)
        self._barra_status()

    def _painel_config(self, parent):
        f = ttk.Frame(parent, style='Surface.TFrame', padding=(14, 14))
        f.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        f.configure(width=290)

        def lbl(text):
            ttk.Label(f, text=text, style='Sub.TLabel', background=SURFACE).pack(
                anchor='w', pady=(0, 2))

        ttk.Label(f, text='Configuração', style='AccentS.TLabel',
                  background=SURFACE).pack(anchor='w', pady=(0, 12))

        # Certificado
        lbl('Certificado (.pfx)')
        row = ttk.Frame(f, style='Surface.TFrame')
        row.pack(fill='x', pady=(0, 10))
        self._cert_var = tk.StringVar()
        ttk.Entry(row, textvariable=self._cert_var, style='Custom.TEntry').pack(
            side='left', fill='x', expand=True)
        ttk.Button(row, text='…', style='Secondary.TButton', width=3,
                   command=self._sel_cert).pack(side='left', padx=(4, 0))

        # Senha
        lbl('Senha do Certificado')
        self._senha_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._senha_var, show='•',
                  style='Custom.TEntry').pack(fill='x', pady=(0, 10))

        # CNPJ
        lbl('CNPJ')
        self._cnpj_var = tk.StringVar()
        self._cnpj_var.trace_add('write', self._fmt_cnpj)
        ttk.Entry(f, textvariable=self._cnpj_var, style='Custom.TEntry').pack(
            fill='x', pady=(0, 10))

        # UF
        lbl('UF')
        self._uf_var = tk.StringVar(value='SP')
        ttk.Combobox(f, textvariable=self._uf_var, values=UFS,
                     state='readonly', width=8).pack(anchor='w', pady=(0, 10))

        # NSU
        lbl('NSU Inicial')
        self._nsu_var = tk.StringVar(value='0')
        ttk.Entry(f, textvariable=self._nsu_var, style='Custom.TEntry',
                  width=16).pack(anchor='w', pady=(0, 10))

        # Ambiente
        self._homolog = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text='Homologação', variable=self._homolog).pack(
            anchor='w', pady=(0, 10))

        ttk.Separator(f, orient='horizontal').pack(fill='x', pady=(2, 10))

        # Pasta saída
        lbl('Pasta de saída (XMLs)')
        row2 = ttk.Frame(f, style='Surface.TFrame')
        row2.pack(fill='x', pady=(0, 14))
        self._pasta_var = tk.StringVar(
            value=os.path.join(os.path.expanduser('~'), 'Downloads', 'NFe'))
        ttk.Entry(row2, textvariable=self._pasta_var, style='Custom.TEntry').pack(
            side='left', fill='x', expand=True)
        ttk.Button(row2, text='…', style='Secondary.TButton', width=3,
                   command=self._sel_pasta).pack(side='left', padx=(4, 0))

        ttk.Separator(f, orient='horizontal').pack(fill='x', pady=(2, 10))

        self._btn_ini = ttk.Button(f, text='▶  Iniciar Consulta',
                                    style='Primary.TButton', command=self._iniciar)
        self._btn_ini.pack(fill='x', pady=(0, 6))

        self._btn_parar = ttk.Button(f, text='■  Parar', style='Danger.TButton',
                                      command=self._parar, state='disabled')
        self._btn_parar.pack(fill='x', pady=(0, 6))

        ttk.Button(f, text='Reativar licença', style='Secondary.TButton',
                   command=lambda: self._abrir_ativacao(bloqueio=False)).pack(fill='x')

    def _painel_direito(self, parent):
        right = ttk.Frame(parent)
        right.grid(row=0, column=1, sticky='nsew')
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=3)
        right.rowconfigure(2, weight=1)

        # ── Toolbar de ações ─────────────────────────────────────────────
        toolbar = ttk.Frame(right, style='Surface.TFrame', padding=(8, 6))
        toolbar.grid(row=0, column=0, sticky='ew', pady=(0, 6))

        # Filtro de status
        ttk.Label(toolbar, text='Filtro:', style='Sub.TLabel',
                  background=SURFACE).pack(side='left', padx=(0, 4))
        self._filtro_var = tk.StringVar(value='todos')
        filtro_opts = [('Todos', 'todos'), ('Pendente', 'pendente'),
                       ('Entrada OK', 'entrada_ok'), ('Cancelada', 'cancelada'),
                       ('Ignorada', 'ignorada')]
        cb = ttk.Combobox(toolbar, textvariable=self._filtro_var,
                          values=[v for _, v in filtro_opts],
                          state='readonly', width=12)
        cb.pack(side='left', padx=(0, 8))
        cb.bind('<<ComboboxSelected>>', lambda _: self._aplicar_filtro())

        # Busca
        ttk.Label(toolbar, text='Busca:', style='Sub.TLabel',
                  background=SURFACE).pack(side='left', padx=(0, 4))
        self._busca_var = tk.StringVar()
        self._busca_var.trace_add('write', lambda *_: self._aplicar_filtro())
        ttk.Entry(toolbar, textvariable=self._busca_var, style='Custom.TEntry',
                  width=22).pack(side='left', padx=(0, 10))

        # Botões de ação em lote
        ttk.Button(toolbar, text='✔ Entrada (sel.)', style='Success.TButton',
                   command=lambda: self._marcar_lote('entrada_ok')).pack(side='left', padx=(0, 4))
        ttk.Button(toolbar, text='Ignorar (sel.)', style='Secondary.TButton',
                   command=lambda: self._marcar_lote('ignorada')).pack(side='left', padx=(0, 4))
        ttk.Button(toolbar, text='⬇ Exportar (sel.)', style='Secondary.TButton',
                   command=self._exportar_selecionados).pack(side='left', padx=(0, 4))
        ttk.Button(toolbar, text='⬇ Exportar todos', style='Secondary.TButton',
                   command=self._exportar_todos).pack(side='left', padx=(0, 4))

        self._lbl_sel = ttk.Label(toolbar, text='', style='Sub.TLabel',
                                   background=SURFACE)
        self._lbl_sel.pack(side='right', padx=(0, 6))

        # ── Tabela ──────────────────────────────────────────────────────
        tf = ttk.Frame(right, style='Surface.TFrame', padding=2)
        tf.grid(row=1, column=0, sticky='nsew', pady=(0, 8))
        tf.columnconfigure(0, weight=1)
        tf.rowconfigure(0, weight=1)

        colunas = ('nsu', 'tipo', 'status', 'data', 'emitente', 'destinatario', 'valor', 'chave')
        self._tree = ttk.Treeview(tf, columns=colunas, show='headings',
                                   selectmode='extended')

        def col(c, label, w, anchor='w'):
            self._tree.heading(c, text=label,
                               command=lambda: self._ordenar(c))
            self._tree.column(c, width=w, anchor=anchor, minwidth=30)

        col('nsu',          'NSU',          80,  'center')
        col('tipo',         'Tipo',         120)
        col('status',       'Status',       100)
        col('data',         'Data',         90,  'center')
        col('emitente',     'Emitente',     170)
        col('destinatario', 'Destinatário', 150)
        col('valor',        'Valor (R$)',   100, 'e')
        col('chave',        'Chave de Acesso', 360)

        for st, cor in STATUS_COR.items():
            self._tree.tag_configure(st, foreground=cor)

        vsb = ttk.Scrollbar(tf, orient='vertical', command=self._tree.yview)
        hsb = ttk.Scrollbar(tf, orient='horizontal', command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky='nsew', padx=(6, 0), pady=6)
        vsb.grid(row=0, column=1, sticky='ns', pady=6)
        hsb.grid(row=1, column=0, sticky='ew', padx=(6, 0))

        self._tree.bind('<Double-1>', self._abrir_xml_duplo)
        self._tree.bind('<<TreeviewSelect>>', self._on_selecao)
        self._tree.bind('<Button-3>', self._menu_contexto)

        # ── Log ─────────────────────────────────────────────────────────
        lf = ttk.Frame(right, style='Surface.TFrame', padding=(8, 6))
        lf.grid(row=2, column=0, sticky='nsew')
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(1, weight=1)
        ttk.Label(lf, text='Log', style='AccentS.TLabel',
                  background=SURFACE).grid(row=0, column=0, sticky='w', pady=(0, 4))
        ttk.Button(lf, text='Limpar log', style='Secondary.TButton',
                   command=self._limpar_log).grid(row=0, column=1, sticky='e')

        self._log = scrolledtext.ScrolledText(
            lf, state='disabled', height=7,
            bg=BG, fg=SUBTEXT, font=('Consolas', 9),
            relief='flat', borderwidth=0, wrap='word')
        self._log.grid(row=1, column=0, columnspan=2, sticky='nsew')
        for tag, cor in [('erro', RED), ('ok', GREEN), ('aviso', YELLOW), ('info', BLUE)]:
            self._log.tag_config(tag, foreground=cor)

    def _barra_status(self):
        bar = ttk.Frame(self, padding=(16, 4))
        bar.pack(fill='x', side='bottom')
        self._status_var = tk.StringVar(value='Pronto')
        ttk.Label(bar, textvariable=self._status_var, style='SubBG.TLabel').pack(side='left')
        self._stats_var = tk.StringVar(value='')
        ttk.Label(bar, textvariable=self._stats_var, style='SubBG.TLabel').pack(side='left', padx=(20, 0))
        self._progress = ttk.Progressbar(bar, mode='indeterminate', length=140,
                                          style='Horizontal.TProgressbar')
        self._progress.pack(side='right')

    # -----------------------------------------------------------------------
    # Licença
    # -----------------------------------------------------------------------
    def _verificar_licenca(self):
        ok, msg = verificar_ativacao()
        if ok:
            self._lbl_licenca.config(text=f'Licença: {msg}', foreground=GREEN)
        else:
            self._abrir_ativacao(bloqueio=True)

    def _abrir_ativacao(self, bloqueio=False):
        dlg = DialogoAtivacao(self, bloqueio=bloqueio)
        self.wait_window(dlg)
        if dlg._ok:
            ok, msg = verificar_ativacao()
            self._lbl_licenca.config(text=f'Licença: {msg}', foreground=GREEN)

    # -----------------------------------------------------------------------
    # Carregar banco
    # -----------------------------------------------------------------------
    def _carregar_banco(self):
        rows = db.listar_documentos()
        for row in rows:
            self._inserir_linha_tree(
                nsu=row['nsu'], tipo=row['tipo'],
                status=row['status'],
                data=row['data_emissao'] or '',
                emitente=row['emitente'] or '',
                destinatario=row['destinatario'] or '',
                valor=_fmt_valor(row['valor']),
                chave=row['chave'] or '',
            )
        self._atualizar_stats()

    # -----------------------------------------------------------------------
    # Eventos de UI
    # -----------------------------------------------------------------------
    def _sel_cert(self):
        p = filedialog.askopenfilename(
            title='Selecionar certificado',
            filetypes=[('PFX', '*.pfx'), ('Todos', '*.*')])
        if p:
            self._cert_var.set(p)

    def _sel_pasta(self):
        p = filedialog.askdirectory(title='Pasta de saída')
        if p:
            self._pasta_var.set(p)

    def _fmt_cnpj(self, *_):
        val = _so_digits(self._cnpj_var.get())[:14]
        fmt = val
        if len(val) >= 3:  fmt = f'{val[:2]}.{val[2:]}'
        if len(val) >= 6:  fmt = f'{val[:2]}.{val[2:5]}.{val[5:]}'
        if len(val) >= 9:  fmt = f'{val[:2]}.{val[2:5]}.{val[5:8]}/{val[8:]}'
        if len(val) >= 13: fmt = f'{val[:2]}.{val[2:5]}.{val[5:8]}/{val[8:12]}-{val[12:]}'
        self._cnpj_var.trace_remove('write', self._cnpj_var.trace_info()[0][1])
        self._cnpj_var.set(fmt)
        self._cnpj_var.trace_add('write', self._fmt_cnpj)

    def _validar(self) -> bool:
        if not self._cert_var.get() or not os.path.isfile(self._cert_var.get()):
            messagebox.showerror('Erro', 'Certificado não encontrado.')
            return False
        if not self._senha_var.get():
            messagebox.showerror('Erro', 'Informe a senha do certificado.')
            return False
        if len(_so_digits(self._cnpj_var.get())) != 14:
            messagebox.showerror('Erro', 'CNPJ inválido (14 dígitos).')
            return False
        try:
            int(self._nsu_var.get())
        except ValueError:
            messagebox.showerror('Erro', 'NSU deve ser um número inteiro.')
            return False
        ok, _ = verificar_ativacao()
        if not ok:
            messagebox.showerror('Licença inválida', 'Ative o software antes de consultar.')
            return False
        return True

    def _iniciar(self):
        if not self._validar():
            return
        self._btn_ini.config(state='disabled')
        self._btn_parar.config(state='normal')
        self._progress.start(12)
        self._status_var.set('Consultando…')
        self._total_novos = 0
        self._consulta.consultar_async(
            uf=self._uf_var.get(),
            certificado=self._cert_var.get(),
            senha=self._senha_var.get(),
            cnpj=_so_digits(self._cnpj_var.get()),
            nsu_inicial=int(self._nsu_var.get()),
            homologacao=self._homolog.get(),
            pasta_saida=self._pasta_var.get(),
            on_log=lambda m: self._fila.put(('log', m)),
            on_documento=lambda d: self._fila.put(('doc', d)),
            on_finalizado=lambda s: self._fila.put(('fim', s)),
        )

    def _parar(self):
        self._consulta.parar()
        self._btn_parar.config(state='disabled')

    # -----------------------------------------------------------------------
    # Tabela — inserção e seleção
    # -----------------------------------------------------------------------
    def _inserir_linha_tree(self, nsu, tipo, status, data, emitente,
                             destinatario, valor, chave) -> str:
        tag = status if status in STATUS_COR else 'pendente'
        item_id = self._tree.insert('', 0, values=(
            nsu, tipo, STATUS_LABEL.get(status, status),
            data, emitente[:40], destinatario[:35], valor, chave,
        ), tags=(tag,))
        self._item_para_nsu[item_id] = nsu
        return item_id

    def _on_selecao(self, _=None):
        n = len(self._tree.selection())
        self._lbl_sel.config(text=f'{n} selecionado(s)' if n else '')

    def _abrir_xml_duplo(self, event):
        item = self._tree.identify_row(event.y)
        if not item:
            return
        nsu = self._item_para_nsu.get(item)
        if not nsu:
            return
        row = db.buscar_por_nsu(nsu)
        if row and row['xml_raw']:
            ViewerXML(self, nsu, row['xml_raw'])

    # -----------------------------------------------------------------------
    # Menu de contexto (botão direito)
    # -----------------------------------------------------------------------
    def _menu_contexto(self, event):
        item = self._tree.identify_row(event.y)
        if not item:
            return
        if item not in self._tree.selection():
            self._tree.selection_set(item)

        menu = tk.Menu(self, tearoff=0, bg=SURFACE, fg=TEXT,
                       activebackground=ACCENT, activeforeground='white',
                       font=('Segoe UI', 10), bd=0)

        menu.add_command(label='✔  Marcar entrada feita',
                         command=lambda: self._marcar_lote('entrada_ok'))
        menu.add_command(label='↩  Reverter para pendente',
                         command=lambda: self._marcar_lote('pendente'))
        menu.add_command(label='✖  Ignorar',
                         command=lambda: self._marcar_lote('ignorada'))
        menu.add_separator()
        menu.add_command(label='👁  Ver XML',
                         command=lambda: self._ver_xml_item(item))
        menu.add_command(label='💾  Exportar XML(s) selecionados',
                         command=self._exportar_selecionados)
        menu.add_separator()
        menu.add_command(label='📋  Copiar chave de acesso',
                         command=lambda: self._copiar_chave(item))

        menu.tk_popup(event.x_root, event.y_root)

    def _ver_xml_item(self, item_id: str):
        nsu = self._item_para_nsu.get(item_id)
        if not nsu:
            return
        row = db.buscar_por_nsu(nsu)
        if row and row['xml_raw']:
            ViewerXML(self, nsu, row['xml_raw'])
        else:
            messagebox.showinfo('Sem XML', 'XML não disponível para este documento.')

    def _copiar_chave(self, item_id: str):
        nsu = self._item_para_nsu.get(item_id)
        if not nsu:
            return
        row = db.buscar_por_nsu(nsu)
        if row and row['chave']:
            self.clipboard_clear()
            self.clipboard_append(row['chave'])

    # -----------------------------------------------------------------------
    # Ações em lote
    # -----------------------------------------------------------------------
    def _nsus_selecionados(self) -> list[str]:
        return [self._item_para_nsu[i] for i in self._tree.selection()
                if i in self._item_para_nsu]

    def _marcar_lote(self, novo_status: str):
        nsus = self._nsus_selecionados()
        if not nsus:
            messagebox.showinfo('Aviso', 'Selecione ao menos um documento.')
            return
        db.atualizar_status_lote(nsus, novo_status)
        self._recarregar_tree()
        self._log_ui(f'Status "{STATUS_LABEL[novo_status]}" aplicado a {len(nsus)} doc(s).', 'ok')

    def _exportar_selecionados(self):
        nsus = self._nsus_selecionados()
        if not nsus:
            messagebox.showinfo('Aviso', 'Selecione ao menos um documento.')
            return
        self._exportar_nsus(nsus)

    def _exportar_todos(self):
        nsus = list(self._item_para_nsu.values())
        if not nsus:
            messagebox.showinfo('Aviso', 'Nenhum documento na tabela.')
            return
        if not messagebox.askyesno('Confirmar', f'Exportar {len(nsus)} documento(s)?'):
            return
        self._exportar_nsus(nsus)

    def _exportar_nsus(self, nsus: list[str]):
        if len(nsus) == 1:
            row = db.buscar_por_nsu(nsus[0])
            if not row or not row['xml_raw']:
                messagebox.showinfo('Sem XML', 'XML não disponível.')
                return
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension='.xml',
                initialfile=f'NSU-{nsus[0]}.xml',
                filetypes=[('XML', '*.xml')])
            if path:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(row['xml_raw'])
                self._log_ui(f'Exportado: {os.path.basename(path)}', 'ok')
        else:
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension='.zip',
                initialfile=f'NFe_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip',
                filetypes=[('ZIP', '*.zip')])
            if not path:
                return
            salvos = 0
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for nsu in nsus:
                    row = db.buscar_por_nsu(nsu)
                    if row and row['xml_raw']:
                        zf.writestr(f'NSU-{nsu}.xml', row['xml_raw'])
                        salvos += 1
            self._log_ui(f'Exportados {salvos} XMLs → {os.path.basename(path)}', 'ok')

    # -----------------------------------------------------------------------
    # Filtro e ordenação
    # -----------------------------------------------------------------------
    def _aplicar_filtro(self):
        self._recarregar_tree()

    def _recarregar_tree(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._item_para_nsu.clear()

        rows = db.listar_documentos(
            status_filtro=self._filtro_var.get(),
            busca=self._busca_var.get(),
        )
        for row in rows:
            self._inserir_linha_tree(
                nsu=row['nsu'], tipo=row['tipo'],
                status=row['status'],
                data=row['data_emissao'] or '',
                emitente=row['emitente'] or '',
                destinatario=row['destinatario'] or '',
                valor=_fmt_valor(row['valor']),
                chave=row['chave'] or '',
            )
        self._atualizar_stats()

    _sort_rev: dict = {}

    def _ordenar(self, coluna: str):
        rev = self._sort_rev.get(coluna, False)
        items = [(self._tree.set(i, coluna), i) for i in self._tree.get_children('')]
        try:
            items.sort(key=lambda x: float(x[0].replace('.', '').replace(',', '.')), reverse=rev)
        except Exception:
            items.sort(key=lambda x: x[0].lower(), reverse=rev)
        for idx, (_, i) in enumerate(items):
            self._tree.move(i, '', idx)
        self._sort_rev[coluna] = not rev

    # -----------------------------------------------------------------------
    # Log
    # -----------------------------------------------------------------------
    def _log_ui(self, msg: str, tag: str = 'info'):
        self._log.config(state='normal')
        self._log.insert('end', msg + '\n', tag)
        self._log.see('end')
        self._log.config(state='disabled')

    def _limpar_log(self):
        self._log.config(state='normal')
        self._log.delete('1.0', 'end')
        self._log.config(state='disabled')

    def _atualizar_stats(self):
        stats = db.estatisticas()
        partes = [f'Total: {stats["total"]}']
        for k in ('pendente', 'entrada_ok', 'cancelada', 'ignorada'):
            if stats.get(k, 0):
                partes.append(f'{STATUS_LABEL[k]}: {stats[k]}')
        self._stats_var.set('  |  '.join(partes))

    # -----------------------------------------------------------------------
    # Fila de eventos (thread → UI)
    # -----------------------------------------------------------------------
    def _processar_fila(self):
        try:
            while True:
                tipo, dado = self._fila.get_nowait()
                if tipo == 'log':
                    tag = ('erro' if '[ERRO' in dado
                           else 'ok' if 'Salvo:' in dado
                           else 'aviso' if '[AVISO]' in dado
                           else 'info')
                    self._log_ui(dado, tag)
                elif tipo == 'doc':
                    self._on_novo_doc(dado)
                elif tipo == 'fim':
                    self._on_fim(dado)
        except queue.Empty:
            pass
        self.after(100, self._processar_fila)

    def _on_novo_doc(self, doc: Documento):
        inseriu = db.salvar_documento(doc)
        if not inseriu:
            return  # NSU duplicado, ignora

        self._total_novos += 1

        # Determina status inicial
        if doc.tipo_evento in ('110111', '110112'):
            status_inicial = 'cancelada'
        else:
            status_inicial = 'pendente'

        self._inserir_linha_tree(
            nsu=doc.nsu, tipo=doc.tipo,
            status=status_inicial,
            data=doc.data_emissao,
            emitente=doc.emitente,
            destinatario=doc.destinatario,
            valor=_fmt_valor(doc.valor),
            chave=doc.chave,
        )

        # Se for cancelamento, atualiza itens já na tabela
        if doc.chave_ref:
            self._atualizar_status_tree_por_chave(doc.chave_ref, 'cancelada')

        self._atualizar_stats()

    def _atualizar_status_tree_por_chave(self, chave: str, novo_status: str):
        for item_id, nsu in self._item_para_nsu.items():
            vals = self._tree.item(item_id, 'values')
            if vals and vals[7] == chave:
                lista = list(vals)
                lista[2] = STATUS_LABEL.get(novo_status, novo_status)
                self._tree.item(item_id, values=lista, tags=(novo_status,))

    def _on_fim(self, status: str):
        self._btn_ini.config(state='normal')
        self._btn_parar.config(state='disabled')
        self._progress.stop()
        msgs = {
            'ok':     (f'Concluído — {self._total_novos} novo(s) documento(s)', 'ok'),
            'parado': ('Consulta interrompida', 'aviso'),
            'erro':   ('Falha na consulta — veja o log', 'erro'),
        }
        msg, tag = msgs.get(status, ('Finalizado', 'info'))
        self._status_var.set(msg)
        self._log_ui(f'─── {msg} ───', tag)
        self._atualizar_stats()


if __name__ == '__main__':
    app = App()
    app.mainloop()
