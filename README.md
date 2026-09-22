# pdf2epub — Conversor de PDF (texto) para EPUB 3

`pdf2epub` é um conversor genérico que transforma qualquer PDF baseado em
**texto** (não digitalizado) num **EPUB 3**, respeitando tanto quanto possível
a formatação original. A **primeira página do PDF é automaticamente usada como
capa** do EPUB.

> PDF digitalizado (imagem) não tem texto extraível e não pode ser convertido
> sem antes passar por OCR. Ver [Limitações](#limitações).

---

## Índice

1. [Funcionalidades](#funcionalidades)
2. [Instalação](#instalação)
3. [Como usar](#como-usar)
   - [Linha de comandos](#linha-de-comandos)
   - [Modo arrastar-e-soltar (Windows)](#modo-arrastar-e-soltar-windows)
   - [Opções](#opções)
   - [Exemplos](#exemplos)
4. [Como funciona (internamente)](#como-funciona-internamente)
5. [Estrutura do EPUB gerado](#estrutura-do-epub-gerado)
6. [Qualidade e validação](#qualidade-e-validação)
7. [Limitações e dicas](#limitações-e-dicas)
8. [Resolução de problemas](#resolução-de-problemas)

---

## Funcionalidades

- **Capa automática** — a 1.ª página do PDF é renderizada como imagem e fica
  definida como capa do EPUB (metadado `cover-image` + página `cover.xhtml`).
- **Reconstrução de parágrafos** — o texto é extraído linha a linha e voltado a
  agrupar em parágrafos coerentes, inclusive quando um parágrafo continua de
  uma página para a seguinte.
- **Limpeza de "mobiliário" da página** — são removidos automaticamente:
  - cabeçalhos correntes (linhas repetidas no topo das páginas, ex.: título do
    livro);
  - rodapés correntes;
  - números de página (numeração árabe ou romana, no topo ou no rodapé).
- **Deteção de títulos** — capítulos, partes e secções são identificados por
  tipografia (negrito, tamanho de letra, centragem, espaço em branco à volta).
  Cada título detectado gera:
  - uma divisão do conteúdo em ficheiros;
  - uma entrada no índice navegável do EPUB.
  Títulos consecutivos (ex.: "Primeira parte" seguida de "Capítulo I") ficam no
  mesmo ficheiro, o segundo como sub-secção com âncora no índice.
- **Preservação de formatação** — negrito e itálico, sobrescritos e imagens
  embebidas no interior do documento são mantidos.
- **Notas de rodapé** — texto menor no fim da página é preservado como nota
  pequena, numerada quando a numeração existir.
- **Detecção de "verso"** — blocos de linhas curtas centradas (poemas, versos)
  são mantidos centrados, sem serem confundidos com títulos.
- **Epígrafes e dedicatórias** — páginas isoladas com poucas linhas curtas e
  fonte mais pequena são reconhecidas como epígrafes; uma única linha centrada
  como dedicatória. Cada uma fica no seu próprio ficheiro/página, sem ser
  confundida com um título de capítulo.
- **Imagens em páginas sem texto** — se uma página do livro não tiver texto
  algum, é porque contém uma imagem (mapas, ilustrações, contracapa); essa
  imagem é extraída e incluída no EPUB.
- **Numeração automática de capítulos** — quando um capítulo começa numa nova
  página (quebra de página com espaço em branco no topo) mas não tem um título
  detectado, o conversor cria automaticamente `Capítulo I`, `Capítulo II`,
  `Capítulo III`, … A quebra de página marca o fim do capítulo anterior.
- **Documentos sem títulos** — se nenhum título for encontrado, o conteúdo é
  dividido em ficheiros por blocos de páginas (300 por omissão) para não
  criar um ficheiro demasiado grande.

---

## Instalação

Requisitos:

- Python 3.9 ou superior;
- Biblioteca **PyMuPDF** (única dependência, usada para ler o PDF).

Instalação:

```bat
pip install -r requisitos.txt
```

ou, manualmente:

```bat
pip install pymupdf
```

Para verificar se está tudo pronto:

```bat
python pdf2epub.py --help
```

> Em **Linux (Kali/Debian)** não instale globalmente com `pip` (é bloqueado por
> defeito). Use um ambiente virtual — ver
> [Linux (Kali / Debian)](#linux-kali--debian).

---

## Como usar

### Linha de comandos

```bat
python pdf2epub.py caminho\para\livro.pdf
```

O EPUB é criado na mesma pasta do PDF, com o mesmo nome e extensão `.epub`
(ex.: `livro.pdf` → `livro.epub`).

### Modo arrastar-e-soltar (Windows)

1. Instale os requisitos uma vez (ver [Instalação](#instalação)).
2. Arraste **um ou vários ficheiros PDF** para cima do ficheiro
   `converter.bat` e solte.
3. Cada PDF é convertido para EPUB na mesma pasta.

Também pode executar o `converter.bat` e depois arrastar PDFs para a janela.

### Linux (Kali / Debian)

O Kali já traz o Python 3. Nas versões recentes, o sistema **bloqueia** o
`pip install` global (erro `externally-managed-environment`), por isso o
recomendado é usar um **ambiente virtual** dentro da pasta do projeto:

```bash
# 1. Dependências do sistema (uma vez)
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

# 2. Entrar na pasta do projeto
cd ~/PDF2EPUB_Conv/pdf2epub

# 3. Criar e ativar o ambiente virtual (uma vez)
python3 -m venv .venv
source .venv/bin/activate

# 4. Instalar a dependência (uma vez, com o venv ativo)
pip install -r requisitos.txt

# 5. Converter (com o venv ativo)
python pdf2epub.py "A Guerra dos Tronos - A Muralha de Gelo.pdf"

# 6. Sair do ambiente virtual quando terminar
deactivate
```

O EPUB é criado ao lado do PDF, com o mesmo nome e extensão `.epub`. Para
voltar a converter noutro dia, basta repetir os passos 3 (ativar o venv),
5 (converter) e 6 (sair).

> **Alternativa sem venv:** instalar o PyMuPDF só para o utilizador com
> `pip install --user --break-system-packages pymupdf` (ou usar `pipx`).
> Prefira sempre o ambiente virtual.

> **Se `python3 -m venv .venv` der `Operation not permitted: 'lib'`:** a pasta
> do projeto está num sistema de ficheiros que **não suporta symlinks** (pen
> USB, cartão SD, partição Windows montada, pasta partilhada de máquina
> virtual, FAT/exFAT). Nesse caso crie o venv no disco Linux e use-o a partir
> daí — não precisa de mover o projeto:
>
> ```bash
> mkdir -p ~/.venvs
> python3 -m venv ~/.venvs/pdf2epub
> source ~/.venvs/pdf2epub/bin/activate
> pip install pymupdf
> cd /caminho/para/a/pasta/do/projeto
> python pdf2epub.py "livro.pdf"
> deactivate
> ```
>
> Para confirmar em que sistema de ficheiros está a pasta:
> `df -T .` (se aparecer `vfat`, `exfat`, `ntfs` ou `fuseblk`, é esta a causa).

> **Erro `ModuleNotFoundError: No module named 'pymupdf'`** significa que o
> ambiente virtual não está ativo (passo 3) ou a dependência não foi instalada
> (passo 4).

### Opções

| Opção | Descrição |
| --- | --- |
| `pdf` | (obrigatório) ficheiro PDF de entrada |
| `-o, --saida SAIDA` | nome do ficheiro EPUB de saída. Por omissão: mesmo nome do PDF com extensão `.epub` |
| `--titulo TITULO` | título do livro. Por omissão usa o metadado `title` do PDF ou o nome do ficheiro |
| `--autor AUTOR` | autor do livro. Por omissão usa o metadado `author` do PDF |
| `--lingua CODIGO` | código de língua do conteúdo (ex.: `pt`, `pt-BR`, `en`, `es`, `fr`). Predefinição: `pt` |
| `--nao-dividir` | não divide em vários ficheiros os documentos sem títulos |
| `--paginas-por-ficheiro N` | documentos sem títulos: páginas por ficheiro. Predefinição: `300` |

### Exemplos

```bat
:: Converter usando o título/metadados do PDF
python pdf2epub.py "C:\Livros\Crime e Castigo.pdf"

:: Escolher o nome de saída e forçar metadados
python pdf2epub.py livro.pdf -o saida.epub --titulo "Crime e Castigo" --autor "F. Dostoievski"

:: Definir a língua do conteúdo
python pdf2epub.py relatorio.pdf --lingua pt-BR

:: Documento longo sem capítulos: ficheiros de 200 páginas cada
python pdf2epub.py tese.pdf --paginas-por-ficheiro 200

:: Mesmo documento, mas tudo num único ficheiro
python pdf2epub.py tese.pdf --nao-dividir
```

Durante a conversão é impresso um resumo no ecrã:

```text
Páginas: 589
Corpo: 12.0 pt | margens 84–530 | linha 20.8 pt
Criado: C:\Livros\Crime e Castigo.epub
```

---

## Como funciona (internamente)

O conversor executa, em sequência, os seguintes passos:

### 1. Abertura e leitura do PDF

Cada página é aberta com PyMuPDF e o texto é extraído ao nível dos "spans"
(fragmentos de texto com a mesma fonte). Os spans que pertencem à mesma linha
visual são agrupados, preservando:

- posição horizontal e vertical;
- tamanho de letra;
- fonte (para saber se é negrito ou itálico).

As imagens de cada página também são recolhidas (com a sua posição).

### 2. Remoção de cabeçalhos, rodapés e números de página

- Uma linha repetida em **muitas páginas** na zona superior (topo, até ~7,5 % da
  altura) ou inferior (a partir de ~93 %) da página é considerada cabeçalho ou
  rodapé corrente e é removida. Uma linha só é removida se aparecer em pelo
  menos **3 páginas** e em **≥ 20 %** das páginas do documento.
- Linhas compostas apenas por números (1–4 dígitos) ou numeração romana,
  situadas no topo ou no rodapé da página, são removidas como números de
  página.

### 3. Estimativa da geometria do documento

Com as linhas de conteúdo (já sem o "mobiliário") o programa calcula:

- **tamanho do corpo de texto** — o tamanho de letra mais frequente;
- **margens** — a coluna esquerda mais comum e o limite direito do texto;
- **espaçamento normal entre linhas** — mediana das distâncias verticais entre
  linhas consecutivas dentro da mesma página.

Estas medidas são a base de todas as decisões seguintes (títulos, parágrafos,
notas).

### 4. Deteção de títulos (capítulos / secções)

Uma linha é candidata a título se for **curta** (até ~110 caracteres) e tiver
realce tipográfico, como:

- **negrito**;
- **tamanho maior** do que o corpo de texto;
- **centrada** e curta (relativamente à largura da coluna);
- normalmente com espaço vertical à volta maior do que o espaçamento normal.

A classificação distingue:

- **`h1`** — títulos "fortes" (muito maiores, negrito e maior, etc.);
- **`h2`** — títulos mais discretos (ex.: "Capítulo II" centrado do mesmo
  tamanho do corpo);
- **verso** — linhas curtas centradas consecutivas (poemas), que ficam no
  corpo do texto centradas em vez de serem tratadas como títulos.

Regras anti-falsos-positivos evitam tratar frases soltas (diálogos, finais de
parágrafo) como títulos. Marcas de fim como **FIM / FIN / END / THE END /
FINIS** são tratadas como um parágrafo de fecho estilizado e não abrem um novo
ficheiro.

### 4.1 Epígrafes e dedicatórias

Uma **página isolada** com poucas linhas curtas (até 8), sem texto de corpo e
com **fonte mais pequena** que o corpo é tratada como **epígrafe**; uma **única
linha curta e centrada** (não encostada à margem) é tratada como
**dedicatória**. Cada uma é colocada num ficheiro próprio (portanto numa página
sua) com formatação centrada, em vez de ser fundida no texto corrente ou
confundida com um título de capítulo.

### 4.2 Aberturas de capítulo e numeração automática

Quando uma página começa com **muito espaço em branco no topo** (comparado com
a margem superior habitual das páginas de texto), considera-se que essa quebra
de página marca o **fim do capítulo anterior** e o **início de um novo
capítulo**. Se o início da página não tiver um título detectado, o conversor
cria automaticamente o título `Capítulo I`, `Capítulo II`, `Capítulo III`, …
(numeração romana). Se já existir um título real na página, esse título é
usado e a numeração automática não é aplicada.

### 5. Reconstrução de parágrafos

As linhas de corpo são reagrupadas em parágrafos. Considera-se que **começa um
novo parágrafo** quando:

- a linha começa com **recuo** (indentação) em relação à margem esquerda
  (estilo de livros clássicos); **ou**
- existe um **espaço vertical** entre esta linha e a anterior maior que ~1,5× o
  espaçamento normal (estilo com linha em branco entre parágrafos); **ou**
- a linha anterior é **curta e termina uma frase** (final de parágrafo típico).

O agrupamento funciona ao longo de todo o documento: um parágrafo que termina
no fim de uma página e continua na seguinte é unido sem quebra.

### 6. Notas de rodapé

Numa página, as linhas de texto **mais pequenas** (pelo menos ~1 pt abaixo do
tamanho do corpo) que aparecem **depois da última linha normal** da página são
tratadas como notas de rodapé. São agrupadas, numeradas (se tiverem número) e
inseridas no EPUB como parágrafos pequenos, perto do local onde apareciam. Os
números de chamada dentro do texto são mantidos como sobrescritos.

### 6.1 Imagens do interior

As imagens grandes de cada página são detetadas, extraídas (JPEG/PNG) e
inseridas como `<figure>` no local aproximado onde aparecem na página.
Quando uma página **não tem texto algum** mas tem uma imagem (ex.: mapa,
ilustração, contracapa), essa imagem é incluída mesmo assim — no início do
livro se for frontispício, no final se for contracapa.

### 7. Divisão em ficheiros e índice

- A primeira página do PDF é usada como **capa** (imagem), exceto o seu texto
  que, se tiver menos de 60 palavras, é considerado página de título e não é
  repetido no corpo.
- Sempre que é encontrado um título, abre-se um novo ficheiro de conteúdo.
  Títulos **consecutivos sem texto entre eles** (ex.: "Segunda parte" +
  "Capítulo I") ficam no mesmo ficheiro, com o segundo como sub-secção.
- O conteúdo que aparece **antes do primeiro título** vai para um ficheiro
  inicial chamado **Início**.
- É gerado um **índice navegável** (`nav.xhtml`) com uma entrada por ficheiro
  e sub-entradas para as secções internas.
- Se **não houver títulos**, o documento é dividido em ficheiros de ~300
  páginas (configurável), com entradas "Páginas X–Y".

### 8. Geração do EPUB

O programa constrói:

- `mimetype` (obrigatório, primeiro ficheiro, não comprimido);
- `META-INF/container.xml`;
- `OEBPS/content.opf` (metadados: título, autor, língua, identificador,
  lista de ficheiros e ordem de leitura);
- `OEBPS/nav.xhtml` (índice e landmarks);
- `OEBPS/style.css`;
- um ficheiro XHTML por capítulo/parte;
- `images/cover.png` (1.ª página) e imagens do interior.

O resultado é compactado num único ficheiro `.epub` válido.

---

## Estrutura do EPUB gerado

```
livro.epub
├── mimetype
├── META-INF/
│   └── container.xml
└── OEBPS/
    ├── content.opf
    ├── nav.xhtml
    ├── style.css
    ├── cover.xhtml
    ├── cap001.xhtml      ← Início (conteúdo antes do 1.º título)
    ├── cap002.xhtml      ← Dedicatória / Epígrafe (ficheiro próprio)
    ├── cap003.xhtml      ← Primeiro capítulo
    ├── ...
    └── images/
        ├── cover.png     ← 1.ª página do PDF
        └── imgN.jpg/png  ← imagens do interior
```

> Em documentos **sem títulos** os ficheiros chamam-se `parte001.xhtml`,
> `parte002.xhtml`, … (um por bloco de páginas).

---

## Qualidade e validação

O conversor foi testado em:

- **"Crime e Castigo" de F. Dostoievski** (589 páginas, PDF de texto real):
  ~216 000 palavras recuperadas integralmente, índice fiel à numeração da
  edição original, capa a partir da página 1.
- **"As Intermitências da Morte" de José Saramago** (217 páginas): 15 capítulos
  sem títulos numerados automaticamente, epígrafes e dedicatória em páginas
  próprias, texto integral preservado.
- **"A Guerra dos Tronos – A Muralha de Gelo" de George R. R. Martin**
  (1113 páginas): 72 capítulos com títulos reais preservados (Prólogo, Bran,
  Catelyn, …), mapa e contracapa incluídos, texto integral preservado.
- Um **PDF sintético** com outro estilo de paginação (cabeçalho corrente,
  parágrafos separados por linha em branco, capítulos a negrito, nota de
  rodapé).

Ambos os EPUB resultantes passam o **epubcheck 5.3.0** sem erros nem avisos.
Para validar um EPUB gerado, pode usar o validador oficial:

```bat
java -jar epubcheck.jar livro.epub
```

---

## Limitações e dicas

- **PDFs digitalizados (imagens) não funcionam** — não contêm camada de texto.
  O programa emite um erro a avisar que o PDF não parece ter texto extraível.
  Solução: fazer OCR primeiro (ex.: Tesseract, Adobe, ferramentas online) e só
  depois converter o PDF com texto.
- **Colunas múltiplas** (revistas científicas com 2 colunas) não são
  suportadas de forma fiável — o texto das duas colunas pode misturar-se. O
  conversor está otimizado para documentos de coluna única.
- **Língua**: por omissão o EPUB é marcado como `pt`. Se o documento estiver
  noutra língua, use `--lingua` (o código está escrito nos metadados e é usado
  pelos leitores de ebooks).
- **Deteção de títulos** é heurística. Documentos com paginação muito invulgar
  podem gerar divisões a mais ou a menos. Não há perda de texto nesses casos,
  apenas divisão diferente do índice.
- **Fórmulas matemáticas, tabelas complexas e diagramas** não são convertidos
  estruturalmente — o texto é extraído na ordem em que aparece.
- O título/autoria podem ser forçados com `--titulo`/`--autor` se os metadados
  do PDF estiverem vazios ou forem feios (ex.: nomes internos de ficheiro).

---

## Resolução de problemas

| Problema | Solução |
| --- | --- |
| `Erro: é necessário instalar a biblioteca PyMuPDF` | Executar `pip install pymupdf` |
| `Operation not permitted: 'lib'` ao correr `python3 -m venv .venv` | A pasta está num sistema de ficheiros **sem suporte a symlinks** (FAT/exFAT, pen USB, pasta partilhada de VM, partição Windows montada). Crie o venv no disco Linux: `python3 -m venv ~/.venvs/pdf2epub` e ative-o a partir daí |
| `error: externally-managed-environment` ao usar `pip install` | Não instale globalmente; use um ambiente virtual (ver [Linux (Kali / Debian)](#linux-kali--debian)) |
| `Erro: o PDF não parece conter texto extraível (é um PDF digitalizado?)` | O PDF é imagem/scan; fazer OCR primeiro |
| O título/índice aparece com o nome do ficheiro | Usar `--titulo "Título certo"` |
| O leitor de ebooks mostra a língua errada | Usar `--lingua en` (ou `pt-BR`, `es`, `fr`, …) |
| EPUB com um ficheiro demasiado grande (sem capítulos) | Reduzir `--paginas-por-ficheiro` (ex.: 150) |
| Capítulos divididos de forma inesperada | A divisão é automática (heurística tipográfica) e não perde texto. Documentos com paginação invulgar podem precisar de ajustes manuais no EPUB final |
| O PDF tem muitas imagens grandes e o EPUB fica pesado | As imagens são incluídas tal como estão; pode reduzir/otimizar no PDF de origem |

---

## Notas finais

O conversor é **autónomo** (só precisa de Python + PyMuPDF) e não envia
conteúdo para a internet. Todos os ficheiros temporários de conversão são
criados e apagados automaticamente.
