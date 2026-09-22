#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf2epub_gui — interface gráfica (tkinter) para o conversor pdf2epub.

Reutiliza o motor de pdf2epub.py (import convert/PDFError).
Não duplica lógica de conversão.

Uso:
    python pdf2epub_gui.py
"""
from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pdf2epub
from pdf2epub import PDFError

LINGUAS = ["pt", "pt-BR", "en", "es", "fr", "de", "it", "nl", "ru"]


class _Cancelado(Exception):
    pass


def _parse_drop(dados):
    # tkinterdnd2 entrega '{C:/a b.pdf} {C:/c.pdf}' ou separado por espaços
    partes = re.findall(r"\{([^}]+)\}|(\S+)", dados)
    ficheiros = []
    for brace, plain in partes:
        ficheiros.append(brace or plain)
    return ficheiros


class App:
    def __init__(self, root):
        self.root = root
        root.title("pdf2epub — Conversor PDF para EPUB")
        root.geometry("720x620")
        root.minsize(640, 560)

        self.pdfs = []          # lista de caminhos
        self.msg_queue = queue.Queue()
        self.worker = None
        self.cancel_event = threading.Event()
        self.convertendo = False
        self.ultima_pasta = None  # para o botão "Abrir pasta"

        self._construir_ui()
        self._atualizar_botoes()
        self.root.after(120, self._poll_queue)

    # ---------- UI ----------
    def _construir_ui(self):
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(0, weight=1)

        # Lista de PDFs
        ttk.Label(frm, text="PDFs a converter:").grid(row=0, column=0, sticky="w")
        self.lista = tk.Listbox(frm, height=7, selectmode=tk.EXTENDED)
        self.lista.grid(row=1, column=0, sticky="nsew", pady=(2, 4))
        frm.rowconfigure(1, weight=0)

        bl = ttk.Frame(frm)
        bl.grid(row=2, column=0, sticky="w", pady=(0, 6))
        ttk.Button(bl, text="Adicionar…", command=self.adicionar).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bl, text="Remover", command=self.remover).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bl, text="Limpar", command=self.limpar).pack(side=tk.LEFT)
        ttk.Label(bl, text="  (também pode arrastar PDFs para a janela, se suportado)").pack(side=tk.LEFT, padx=(8, 0))

        # Botão "Detalhes" (metadados e divisão ocultos por defeito)
        self.det_aberto = False
        det_bar = ttk.Frame(frm)
        det_bar.grid(row=3, column=0, sticky="w", pady=(0, 6))
        self.btn_detalhes = ttk.Button(det_bar, text="Detalhes \u25b8",
                                       command=self.alternar_detalhes)
        self.btn_detalhes.pack(side=tk.LEFT)
        ttk.Label(det_bar, text="  Metadados e divisão do EPUB").pack(
            side=tk.LEFT, padx=(8, 0))

        self.det = ttk.Frame(frm)
        self.det.grid(row=4, column=0, sticky="ew")
        self.det.columnconfigure(0, weight=1)

        # Metadados
        meta = ttk.LabelFrame(self.det, text="Metadados (em branco = usar os do PDF)", padding=8)
        meta.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        meta.columnconfigure(1, weight=1)
        ttk.Label(meta, text="Título:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.ent_titulo = ttk.Entry(meta)
        self.ent_titulo.grid(row=0, column=1, sticky="ew")
        ttk.Label(meta, text="Autor:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(4, 0))
        self.ent_autor = ttk.Entry(meta)
        self.ent_autor.grid(row=1, column=1, sticky="ew", pady=(4, 0))
        ttk.Label(meta, text="Língua:").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=(4, 0))
        self.cmb_lingua = ttk.Combobox(meta, values=LINGUAS, width=12)
        self.cmb_lingua.set("pt")
        self.cmb_lingua.grid(row=2, column=1, sticky="w", pady=(4, 0))

        # Opções de divisão
        div = ttk.LabelFrame(self.det, text="Divisão (documentos sem títulos)", padding=8)
        div.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.var_nao_dividir = tk.BooleanVar(value=False)
        ttk.Checkbutton(div, text="Não dividir documentos sem títulos",
                        variable=self.var_nao_dividir).pack(anchor="w")
        linha = ttk.Frame(div)
        linha.pack(anchor="w", pady=(4, 0))
        ttk.Label(linha, text="Páginas por ficheiro:").pack(side=tk.LEFT, padx=(0, 6))
        self.spin_pag = ttk.Spinbox(linha, from_=1, to=5000, width=8)
        self.spin_pag.set("300")
        self.spin_pag.pack(side=tk.LEFT)

        # Pasta de saída
        out = ttk.LabelFrame(frm, text="Pasta de saída (vazio = ao lado de cada PDF)", padding=8)
        out.grid(row=5, column=0, sticky="ew", pady=(0, 6))
        out.columnconfigure(0, weight=1)
        self.ent_saida = ttk.Entry(out)
        self.ent_saida.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        bo = ttk.Frame(out)
        bo.grid(row=0, column=1, sticky="e")
        ttk.Button(bo, text="Procurar…", command=self.escolher_pasta).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bo, text="Limpar", command=lambda: self.ent_saida.delete(0, tk.END)).pack(side=tk.LEFT)

        # Progresso
        prog = ttk.Frame(frm)
        prog.grid(row=6, column=0, sticky="ew", pady=(0, 4))
        prog.columnconfigure(0, weight=1)
        self.lbl_estado = ttk.Label(prog, text="Pronto.")
        self.lbl_estado.grid(row=0, column=0, sticky="w")
        self.barra = ttk.Progressbar(prog, mode="determinate", maximum=100)
        self.barra.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        # Botões principais
        bp = ttk.Frame(frm)
        bp.grid(row=7, column=0, sticky="ew", pady=(0, 6))
        self.btn_converter = ttk.Button(bp, text="Converter", command=self.iniciar)
        self.btn_converter.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_cancelar = ttk.Button(bp, text="Cancelar", command=self.cancelar, state=tk.DISABLED)
        self.btn_cancelar.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_abrir = ttk.Button(bp, text="Abrir pasta", command=self.abrir_pasta, state=tk.DISABLED)
        self.btn_abrir.pack(side=tk.LEFT)

        # Log
        ttk.Label(frm, text="Registo:").grid(row=8, column=0, sticky="w")
        self.log = ScrolledText(frm, height=10, wrap=tk.WORD, state=tk.DISABLED)
        self.log.grid(row=9, column=0, sticky="nsew", pady=(2, 0))
        frm.rowconfigure(9, weight=1)

        # DnD opcional
        try:
            from tkinterdnd2 import DND_FILES  # type: ignore
            self.lista.drop_target_register(DND_FILES)
            self.lista.bind("<<Drop>>", self._on_drop)
            self.root.drop_target_register(DND_FILES)
            self.root.bind("<<Drop>>", self._on_drop)
        except Exception:
            pass  # sem tkinterdnd2: só diálogo de ficheiros

        self.det.grid_remove()

    def alternar_detalhes(self):
        if self.det_aberto:
            self.det.grid_remove()
            self.btn_detalhes.configure(text="Detalhes \u25b8")
        else:
            self.det.grid()
            self.btn_detalhes.configure(text="Detalhes \u25be")
        self.det_aberto = not self.det_aberto

    # ---------- lista ----------
    def adicionar(self):
        fich = filedialog.askopenfilenames(
            title="Escolher PDFs",
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")])
        for f in fich:
            self._juntar(f)

    def _juntar(self, caminho):
        caminho = os.path.abspath(caminho)
        if not caminho.lower().endswith(".pdf"):
            return
        if caminho not in self.pdfs:
            self.pdfs.append(caminho)
            self.lista.insert(tk.END, caminho)
        self._atualizar_botoes()

    def _on_drop(self, event):
        for f in _parse_drop(event.data):
            if os.path.isfile(f):
                self._juntar(f)
        return "break"

    def remover(self):
        sel = sorted(self.lista.curselection(), reverse=True)
        for i in sel:
            self.lista.delete(i)
            del self.pdfs[i]
        self._atualizar_botoes()

    def limpar(self):
        if self.convertendo:
            return
        self.pdfs.clear()
        self.lista.delete(0, tk.END)
        self._atualizar_botoes()

    def escolher_pasta(self):
        pasta = filedialog.askdirectory(title="Escolher pasta de saída")
        if pasta:
            self.ent_saida.delete(0, tk.END)
            self.ent_saida.insert(0, pasta)

    # ---------- log / estado (thread-safe via queue) ----------
    def _escrever_log(self, texto):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, texto + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _poll_queue(self):
        try:
            while True:
                ev = self.msg_queue.get_nowait()
                tipo = ev[0]
                if tipo == "log":
                    self._escrever_log(ev[1])
                elif tipo == "ficheiro":
                    _, idx, total, nome = ev
                    self.lbl_estado.configure(text="%d de %d — %s" % (idx, total, nome))
                    self.barra["value"] = 0
                elif tipo == "progresso":
                    _, pag, total = ev
                    if total > 0:
                        self.barra["value"] = 100.0 * pag / total
                elif tipo == "fim":
                    _, ok, erros = ev
                    self.convertendo = False
                    self._atualizar_botoes()
                    self.barra["value"] = 100 if ok else self.barra["value"]
                    if erros == 0:
                        self.lbl_estado.configure(text="Concluído: %d ficheiro(s)." % ok)
                    else:
                        self.lbl_estado.configure(
                            text="Concluído: %d ok, %d com erro." % (ok, erros))
                    if self.ultima_pasta:
                        self.btn_abrir.configure(state=tk.NORMAL)
                elif tipo == "cancelado":
                    self.convertendo = False
                    self._atualizar_botoes()
                    self.lbl_estado.configure(text="Cancelado pelo utilizador.")
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _atualizar_botoes(self):
        if self.convertendo:
            self.btn_converter.configure(state=tk.DISABLED)
            self.btn_cancelar.configure(state=tk.NORMAL)
        else:
            self.btn_cancelar.configure(state=tk.DISABLED)
            self.btn_converter.configure(
                state=tk.NORMAL if self.pdfs else tk.DISABLED)

    # ---------- conversão ----------
    def iniciar(self):
        if self.convertendo or not self.pdfs:
            return
        try:
            chunk = int(self.spin_pag.get())
            if chunk < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Opção inválida",
                                 "«Páginas por ficheiro» tem de ser um número >= 1.")
            return
        out_dir = self.ent_saida.get().strip() or None
        if out_dir and not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Pasta de saída", "Não foi possível criar a pasta:\n%s" % e)
                return

        titulo = self.ent_titulo.get().strip() or None
        autor = self.ent_autor.get().strip() or None
        lingua = self.cmb_lingua.get().strip() or "pt"
        nao_dividir = bool(self.var_nao_dividir.get())

        self.cancel_event.clear()
        self.convertendo = True
        self._atualizar_botoes()
        self.btn_abrir.configure(state=tk.DISABLED)
        self._escrever_log("A iniciar conversão de %d ficheiro(s)…" % len(self.pdfs))

        pdfs = list(self.pdfs)
        opts_base = dict(titulo=titulo, autor=autor, lingua=lingua,
                         chunk_paginas=chunk, nao_dividir=nao_dividir)
        self.worker = threading.Thread(
            target=self._trabalhar,
            args=(pdfs, out_dir, opts_base),
            daemon=True)
        self.worker.start()

    def _trabalhar(self, pdfs, out_dir, opts_base):
        q = self.msg_queue
        ok = 0
        erros = 0
        total = len(pdfs)
        for idx, pdf in enumerate(pdfs, start=1):
            if self.cancel_event.is_set():
                q.put(("cancelado",))
                return
            nome = os.path.basename(pdf)
            q.put(("ficheiro", idx, total, nome))
            q.put(("log", "— [%d/%d] %s" % (idx, total, pdf)))
            if out_dir:
                destino = os.path.join(
                    out_dir, os.path.splitext(nome)[0] + ".epub")
            else:
                destino = os.path.splitext(pdf)[0] + ".epub"

            opts = SimpleNamespace(**opts_base)

            def progress_cb(pag, tot, msg, _idx=idx, _tot=total):
                if self.cancel_event.is_set():
                    raise _Cancelado()
                # mensagens com nº de página são só progresso; o resto vai para o log
                if msg.startswith("A ler páginas:") or msg.startswith("A converter página"):
                    q.put(("progresso", pag, tot))
                else:
                    q.put(("log", "  " + msg))
                    if tot:
                        q.put(("progresso", pag, tot))

            try:
                pdf2epub.convert(pdf, destino, opts, progress_cb=progress_cb)
            except _Cancelado:
                q.put(("log", "Cancelado pelo utilizador."))
                q.put(("cancelado",))
                return
            except PDFError as e:
                erros += 1
                q.put(("log", "ERRO em %s: %s" % (nome, e)))
                continue
            except Exception as e:  # noqa: BLE001 — continuar para o próximo PDF
                erros += 1
                q.put(("log", "ERRO em %s: %s: %s" % (nome, type(e).__name__, e)))
                continue
            ok += 1
            self.ultima_pasta = os.path.dirname(os.path.abspath(destino))
            q.put(("log", "OK: %s" % destino))
            q.put(("progresso", 1, 1))
        q.put(("fim", ok, erros))

    def cancelar(self):
        if self.convertendo:
            self.cancel_event.set()
            self._escrever_log("A cancelar…")

    def abrir_pasta(self):
        pasta = self.ultima_pasta or self.ent_saida.get().strip()
        if not pasta or not os.path.isdir(pasta):
            messagebox.showinfo("Abrir pasta", "Nenhuma pasta de saída disponível.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(pasta)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", pasta])
            else:
                subprocess.Popen(["xdg-open", pasta])
        except Exception as e:
            messagebox.showerror("Abrir pasta", "Não foi possível abrir:\n%s" % e)


def main():
    try:
        from tkinterdnd2 import TkinterDnD  # type: ignore
        root = TkinterDnD.Tk()
    except Exception:
        root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
