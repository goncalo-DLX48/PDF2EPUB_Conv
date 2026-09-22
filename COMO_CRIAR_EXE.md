# Criar pdf2epub.exe com PyInstaller (opcional)

A GUI (`pdf2epub_gui.py`) usa apenas tkinter + PyMuPDF, por isso pode ser
empacotada num `.exe` único sem consola.

## 1. Instalar o PyInstaller

```bat
pip install pyinstaller
```

## 2. Gerar o executável (uma pasta, sem consola)

Na pasta `pdf2epub`, correr:

```bat
pyinstaller --onefile --windowed --name pdf2epub-gui pdf2epub_gui.py
```

O executável sai em `dist\pdf2epub-gui.exe`.

## 3. Notas

- `--windowed` esconde a consola; o log aparece dentro da janela.
- O `pdf2epub.py` é incluído automaticamente como import; mantenha os dois
  ficheiros na mesma pasta ao regenerar.
- Se usar arrastar-e-soltar com `tkinterdnd2`, acrescente
  `--collect-all tkinterdnd2` e instale `pip install tkinterdnd2`.
  Sem esse pacote a GUI continua a funcionar (só via botões/diálogos).
- Para incluir ícone próprio: `--icon icone.ico`.
- O antivirus do Windows pode pedir confirmação na primeira execução de
  um `.exe` gerado localmente — é normal.

## 4. Testar

```bat
dist\pdf2epub-gui.exe
```

Abrir a janela, adicionar 2 PDFs e carregar em Converter.
