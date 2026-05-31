# Healthsh — Roadmap de Desenvolvimento

> Monitor de saúde de sistema Linux, open-source, desktop-first.
> **Objetivos:** portfólio + uso diário pessoal.
> **Diferencial central:** IA que *interpreta e prevê* a saúde do sistema, não só plota métricas.

---

## Como usar este documento

Este arquivo é a fonte única de verdade para o desenvolvimento do Healthsh. Ele foi escrito para ser consumido por um **agente de codificação** que vai criar as issues no GitHub de forma **sequencial**, sprint por sprint.

Regras para o agente:

- Cada item em `### Issue:` vira **uma issue no GitHub**, na ordem em que aparece.
- Use o bloco `Labels:` para aplicar as labels (crie as labels antes, ver seção [Labels do GitHub](#labels-do-github)).
- Use o bloco `Depende de:` para montar a ordem/dependência. Não abra uma issue antes das suas dependências estarem fechadas.
- Copie a checklist de `Tarefas` como task list (`- [ ]`) no corpo da issue.
- Copie `Critérios de aceite` no corpo da issue, em seção própria.
- Cada Sprint vira um **Milestone** no GitHub (ex: `Sprint 1 — Dashboard v0.1`).
- Não invente escopo. Se faltar informação, abra a issue com o escopo descrito aqui e marque `needs-clarification`.

---

## 1. Visão geral do produto

Healthsh é um app de desktop que, ao ser aberto, mostra a saúde atual da máquina Linux em tempo real: CPU, RAM, disco/espaço, GPU, temperatura, logs do journald, containers Docker em execução e os processos que mais consomem recursos.

O que separa o Healthsh de `btop`, `htop`, `glances`, `netdata` e afins **não é** mostrar métricas — todos fazem isso. É a camada de **IA que interpreta**: prevê quando o disco vai encher, identifica containers com vazamento de memória, agrupa erros repetidos do journald e responde perguntas em linguagem natural ("por que meu PC travou às 14h?") cruzando métricas históricas com logs.

### Não-objetivos (v1)

- Não é um substituto de observabilidade de produção (não compete com Prometheus/Grafana).
- Não monitora máquinas remotas na v1 (foco na máquina local).
- Não tem backend/servidor — tudo roda local.
- Sem telemetria, sem analytics, sem coleta de dados do usuário.

---

## 2. Stack técnica

| Camada | Tecnologia | Motivo |
|---|---|---|
| Linguagem | Python 3.11+ | Leitura de sistema fácil, ecossistema maduro |
| UI | PySide6 (Qt 6) | Desktop nativo, leve, abre rápido (um monitor não pode pesar) |
| Gráficos tempo-real | PyQtGraph | Feito para séries temporais com alta taxa de atualização |
| Medidores custom | QPainter | Gauges circulares e indicadores autorais |
| Métricas | psutil + leitura direta de `/proc` e `/sys` | Cobertura ampla e baixo nível quando preciso |
| GPU | leitura via `nvidia-smi` / `/sys/class/drm` (fallback) | Suporte NVIDIA primeiro, AMD/Intel como evolução |
| Docker | SDK oficial `docker` (docker-py) | API estável para listar/inspecionar/agir em containers |
| Logs | `journalctl` via subprocess (JSON output) ou `systemd` python bindings | Acesso ao journald |
| Persistência leve | SQLite (stdlib `sqlite3`) | Histórico de métricas para previsões e diagnóstico |
| IA | Base de agentes do Blocksh (tool-calling, backends Anthropic/Ollama/OpenAI) | Reuso **apenas** quando chegar o Sprint de IA |
| Empacotamento | PyInstaller + AppImage (e `.deb` depois) | Distribuição em Linux |

> **Regra de leveza:** a thread de UI nunca bloqueia. Toda coleta roda em `QThread` worker, emitindo sinais. Métricas a cada **1s**; Docker e journald a cada **3s** (mais caros).

---

## 3. Arquitetura de pastas (do zero)

Arquitetura em camadas, limpa, sem dependência de fora pra dentro (UI depende de core; core não conhece UI). **Não** copiar código do Blocksh nesta fase — só a base de agentes, e apenas no Sprint 5.

```
healthsh/
├── healthsh/
│   ├── __init__.py
│   ├── app.py                      # bootstrap: QApplication, janela principal, tray
│   ├── domain/                     # entidades puras, sem dependências externas
│   │   ├── metrics.py              # CpuMetric, MemMetric, DiskMetric, GpuMetric, NetMetric
│   │   ├── process.py              # ProcessInfo
│   │   ├── container.py            # ContainerInfo, ContainerStats
│   │   ├── log_entry.py            # LogEntry (priority, unit, message, ts)
│   │   └── insight.py              # Insight (severity, title, message, source)
│   ├── core/                       # regras de negócio / casos de uso
│   │   ├── thresholds.py           # limites (warning/critical) por métrica
│   │   ├── analysis.py             # tendências, previsão de disco, detecção de vazamento
│   │   └── formatting.py           # bytes→GB, %, uptime, etc.
│   ├── services/                   # orquestração
│   │   ├── collector_service.py    # agenda e coordena collectors
│   │   ├── history_service.py      # grava/lê séries no SQLite
│   │   └── ai_service.py           # (Sprint 5) ponte com a base de agentes
│   ├── infra/                      # detalhes externos
│   │   ├── collectors/
│   │   │   ├── cpu_collector.py
│   │   │   ├── mem_collector.py
│   │   │   ├── disk_collector.py
│   │   │   ├── gpu_collector.py
│   │   │   ├── net_collector.py
│   │   │   ├── process_collector.py
│   │   │   ├── docker_collector.py
│   │   │   └── journald_collector.py
│   │   ├── threads/
│   │   │   ├── metrics_worker.py   # QThread 1s
│   │   │   └── slow_worker.py      # QThread 3s (docker + journald)
│   │   └── db/
│   │       └── sqlite_store.py
│   └── ui/
│       ├── theme/
│       │   ├── palette.py          # tokens de cor (ver Design System)
│       │   └── styles.py           # QSS global
│       ├── widgets/
│       │   ├── gauge.py            # gauge circular (QPainter)
│       │   ├── sparkline.py        # série temporal (PyQtGraph)
│       │   ├── core_bars.py        # barras por núcleo
│       │   ├── metric_card.py
│       │   ├── container_card.py
│       │   ├── log_line.py
│       │   └── ai_banner.py
│       ├── screens/
│       │   ├── dashboard_screen.py
│       │   ├── system_screen.py
│       │   ├── docker_screen.py
│       │   ├── logs_screen.py
│       │   ├── ai_screen.py
│       │   └── settings_screen.py
│       ├── sidebar.py
│       └── main_window.py
├── tests/
├── assets/
│   └── icons/
├── pyproject.toml
├── README.md
├── CLAUDE.md                       # instruções para o agente de código
└── HEALTHSH_ROADMAP.md             # este arquivo
```

---

## 4. Design System

Tema escuro, base **Tokyo Night**, limpo e moderno (mesma vibe dos mockups validados). Todos os valores abaixo são **normativos** — o agente deve usar exatamente estes hex, raios e espaçamentos.

### 4.1 Paleta de cores

| Token | Hex | Uso |
|---|---|---|
| `bg.window` | `#1a1b26` | Fundo da janela principal |
| `bg.chrome` | `#16161e` | Header (title bar) e sidebar |
| `bg.card` | `#1f2335` | Cards e painéis |
| `bg.card-inactive` | `#1b1c26` | Cards de itens parados/desabilitados |
| `bg.ai-banner` | `#1f2433` | Fundo da faixa/painel de IA |
| `border.default` | `#2a2c3d` | Bordas de cards, divisórias |
| `border.row` | `#20222e` | Divisória sutil entre linhas de tabela |
| `border.ai` | `#e0af68` | Borda do painel de IA (âmbar) |
| `track` | `#2a2c3d` | Trilho de barras/gauges (parte vazia) |
| `text.primary` | `#c0caf5` | Texto principal |
| `text.muted` | `#565f89` | Texto secundário, labels, hints |
| `accent.blue` | `#7dcfff` | CPU, item ativo, acento primário, links |
| `accent.purple` | `#bb9af7` | RAM / memória |
| `accent.amber` | `#e0af68` | Aviso, disco alto, temperatura, IA |
| `accent.green` | `#9ece6a` | OK, container rodando, GPU baixa, "live" |
| `accent.red` | `#f7768e` | Crítico, erro, botão de fechar |

> Mapeamento semântico das cores de severidade: **verde** = saudável, **âmbar** = atenção/aviso, **vermelho** = crítico/erro. As cores por métrica são fixas: CPU=blue, RAM/memória=purple, disco/temp=amber quando alto, GPU=green quando baixo.

### 4.2 Tipografia

- Família: sans-serif do sistema (Inter / Segoe UI / Cantarell — o que houver). Mono só para PIDs, portas e valores técnicos se desejado.
- Tamanhos: título de seção 13–14px/500; corpo 12px/400; labels e hints 10–11px/400; números de destaque (gauges/cards) 14–18px/500.
- **Dois pesos apenas:** 400 (regular) e 500 (semibold). Nunca 700.
- **Sentence case** em tudo. Nunca Title Case nem CAIXA ALTA.

### 4.3 Bordas, raios e espaçamento

| Elemento | Raio | Borda |
|---|---|---|
| Janela | `12px` | `1px solid #2a2c3d` |
| Card / painel | `10px` | `1px solid #2a2c3d` |
| Card pequeno (métrica) | `8px` | `1px solid #2a2c3d` |
| Barra de progresso | `3px` | sem borda |
| Pílula / badge | `999px` | conforme contexto |

- Padding interno de card: `12px 14px`.
- Gap entre cards em grid: `10–12px`.
- Padding do header e da sidebar: `12px 16px` / `16px 12px`.
- Bolinhas de status: `7–8px` de diâmetro, `border-radius: 50%`.
- "Traffic lights" do header: `11px`, nas cores `#f7768e` / `#e0af68` / `#9ece6a`.

### 4.4 Layout base (todas as telas)

Toda tela compartilha a mesma moldura:

1. **Header (title bar)** — altura ~44px, `bg.chrome`, borda inferior `border.default`. Da esquerda pra direita: 3 traffic lights → ícone + nome da seção (500) → subtítulo contextual em `text.muted` → à direita, indicador "live · 1s" (bolinha verde + texto) no Dashboard.
2. **Sidebar** — largura ~48px, `bg.chrome`, borda direita `border.default`. Ícones empilhados verticalmente (gap 18px), em `text.muted`; o item ativo fica `accent.blue`. Ordem: Dashboard, Sistema, Docker, Logs, IA, e **Settings fixado embaixo** (`margin-top:auto`).
3. **Área de conteúdo** — `padding: 16px`, fundo `bg.window`.

Ícones (Tabler outline): Dashboard=`layout-dashboard`, Sistema=`cpu`, Docker=`brand-docker`, Logs=`file-text`, IA=`sparkles`, Settings=`settings`. Header heart=`activity-heartbeat`. Container alerta=`flame`. Vazamento/IA=`sparkles`.

---

## 5. Especificação detalhada das telas

As 6 telas correspondem aos itens da sidebar. Cada uma é desenvolvida em um sprint. **A v0.1 é só o Dashboard + tray**; as demais entram incrementalmente.

### 5.1 Tela: Dashboard (visão geral) — *validada em mockup*

Subtítulo do header: `system health · <distro>` + indicador `live · 1s` à direita (bolinha `accent.green`).

Conteúdo, de cima pra baixo:

1. **Linha de 4 gauges** (grid 4 colunas, gap 10px). Cada gauge é um card pequeno (`bg.card`, raio 8px) com um anel circular (QPainter) de raio ~24px e traço 6px sobre trilho `track`, número central (14px/500, `text.primary`) e label embaixo (11px, `text.muted`):
   - **CPU** — anel `accent.blue`. Label `CPU · N cores`. Ex: 34%.
   - **RAM** — anel `accent.purple`. Label `RAM · usado/total`. Ex: 61%, `9.8/16G`.
   - **Disco** — anel `accent.amber` quando ≥75%. Label `Disco · N%`. Ex: 78%.
   - **GPU** — anel `accent.green` quando baixa. Label `GPU · temp°C`. Ex: 22%, 48°C.
2. **Card "Uso ao longo de 60s"** (`bg.card`, raio 10px). Header do card: título à esquerda (12px/500) + legenda à direita (`● CPU` blue, `● RAM` purple). Dentro, gráfico PyQtGraph com duas linhas (traço 2px) sem preenchimento: CPU em `accent.blue`, RAM em `accent.purple`. Janela deslizante de 60s.
3. **Faixa de IA** (`bg.ai-banner`, borda `border.ai` âmbar, raio 10px). Ícone `sparkles` âmbar + texto 12.5px/1.5: prefixo "Análise:" em `accent.amber`/500, depois o insight interpretado. Ex.: previsão de enchimento de disco + alerta de container vazando RAM. Nomes técnicos (caminhos, containers) em `accent.blue` mono.
4. **Grid de 2 colunas** (gap 12px):
   - **Containers** — card com título (ícone `brand-docker` blue). Lista: bolinha de status (verde rodando / `text.muted` parado) + nome + valor de RAM à direita (âmbar se alto, `text.muted` se baixo).
   - **Top memória** — card com título (ícone `flame` vermelho). Lista dos processos por RAM: nome à esquerda, valor em `accent.purple` à direita.

> **Coerência de dados:** o container citado na faixa de IA (ex. `postgres-dev`) é o mesmo que aparece na lista de Containers e em Top memória. A IA referencia entidades reais visíveis na tela.

### 5.2 Tela: Sistema / Processos

Subtítulo do header: `N cores · load X.XX · up Nd Nh`.

1. **"Por núcleo"** — label `text.muted` 12px, depois grid de 4 colunas com uma mini-barra por núcleo: label `core N` (10px) + trilho `track` 6px com preenchimento `accent.blue` (vira `accent.amber` quando o núcleo passa de ~85%).
2. **Linha de 3 cards pequenos**: `Temp CPU` (valor `accent.amber` se quente), `Swap` (usado/total), `Processos` (contagem total).
3. **Tabela de processos** — header do bloco com título "Processos" + controle de ordenação à direita (`ordenar: memória ▾` com a opção ativa em `accent.blue`). Tabela (`bg.card`, raio 8px) com colunas: `PID` (muted) | `Nome` (primary) | `CPU` (blue, ou amber se alto) | `MEM` (purple) | `User` (muted). Linhas separadas por `border.row`. Ordenável por CPU e por MEM.

### 5.3 Tela: Docker

Subtítulo do header: `N rodando · N parado`.

- **Um card por container** (`bg.card`, raio 10px), empilhados (gap 10px). Cabeçalho do card: bolinha de status (`accent.green` rodando) + nome (13px/500) + `imagem:tag · up Nd` (muted) + à direita ícones de ação em `text.muted`: `player-pause`, `refresh`, `file-text` (logs). Segunda linha: `CPU N%` (blue), `MEM N` (âmbar se alto, verde se ok), portas expostas.
- **Container parado**: card `bg.card-inactive`, opacidade ~0.7, bolinha `text.muted`, e única ação `player-play` em `accent.green`.
- **Nota de IA** ao final (mesma estética da faixa de IA do Dashboard): destaca container destoante e oferece investigar logs. Ex.: "`postgres-dev` está com RAM 9x acima dos outros e subindo. Quer que eu investigue os logs dele?"

### 5.4 Tela: Logs (journald)

Subtítulo do header: `journald · últimas Nh`.

1. **Barra de filtro** — dropdown de unidade/serviço (`todos os serviços ▾`) + pílulas de prioridade selecionáveis: `err` (`accent.red`), `warn` (`accent.amber`), `info` (`accent.blue`), `debug` (`text.muted`). Pílula ativa preenchida na cor; inativa só contorno.
2. **Painel de IA — agrupamento de erros** (estética de IA, borda âmbar): resume erros repetidos. Ex.: "12 erros idênticos de `NetworkManager` nas últimas 2h — possível flapping de conexão. Ver detalhes." Botão/affordance pra expandir.
3. **Lista de logs** — linhas mono (`bg.card`, raio 8px), cada uma: timestamp (`text.muted`) + barrinha/etiqueta de prioridade na cor da severidade + unidade (`accent.blue`) + mensagem (`text.primary`). Linhas separadas por `border.row`. Auto-scroll com opção de pausar.

### 5.5 Tela: IA / Diagnóstico (chat)

Subtítulo do header: `assistente · <backend>` (ex. `ollama:llama3`).

- **Área de conversa**: bolhas do usuário (alinhadas à direita, `bg.card`) e do assistente (à esquerda). Mensagens do assistente podem conter **chips de tool-call** mostrando o que o agente consultou — ex.: `📊 leu métricas 13:50–14:10`, `📄 leu journald (err)` — em pílulas `bg.card` com texto `accent.blue`. Isso evidencia o tool-calling (igual ao agente do Blocksh).
- **Diagnóstico**: resposta em linguagem natural cruzando histórico + logs. Ex. pergunta: "por que meu PC travou às 14h?" → agente lê métricas daquele intervalo no SQLite e logs do journald e responde com a causa provável.
- **Input** na base: campo de texto + seletor de backend (Ollama/Anthropic/OpenAI) + botão enviar (`accent.blue`).
- Sugestões rápidas (chips) acima do input: "Por que está lento?", "O disco vai encher?", "Algum container com problema?".

### 5.6 Tela: Settings

Subtítulo do header: `configurações`.

Seções em cards (`bg.card`, raio 10px):

1. **Coleta** — intervalo de métricas (default 1s), intervalo de Docker/journald (default 3s), retenção de histórico no SQLite (ex. 7 dias).
2. **IA** — backend (Ollama / Anthropic / OpenAI), campo de chave/endpoint conforme backend, toggle "insights automáticos no Dashboard".
3. **Alertas / thresholds** — limites warning/critical por métrica (CPU, RAM, disco, temp).
4. **Aparência** — tema (Tokyo Night default), opção de acento.
5. **Sistema** — toggle "iniciar com o sistema", toggle "minimizar para a bandeja", toggle "ícone na system tray".

---

## 6. Roadmap de Sprints

Cada sprint = um Milestone. As issues devem ser criadas na ordem listada. Versões: v0.1 ao fim do Sprint 1; v0.2 ao fim do Sprint 3; v1.0 ao fim do Sprint 7.

---

### Sprint 0 — Fundação do projeto

**Milestone:** `Sprint 0 — Fundação`
**Meta:** repositório, esqueleto da arquitetura, tema e janela vazia abrindo.

#### Issue: Inicializar repositório e configuração do projeto
Labels: `setup`, `infra`
Depende de: —
Tarefas:
- [ ] Criar `pyproject.toml` (build com hatchling ou poetry), Python 3.11+
- [ ] Adicionar dependências base: PySide6, pyqtgraph, psutil
- [ ] Configurar `ruff` (lint) e `black`/formatter, `pytest`
- [ ] Criar `.gitignore`, `LICENSE` (MIT), `README.md` inicial
- [ ] Criar `CLAUDE.md` com convenções do projeto
Critérios de aceite:
- `pip install -e .` funciona em ambiente limpo
- `ruff check` e `pytest` rodam sem erro (mesmo sem testes ainda)

#### Issue: Criar estrutura de pastas em camadas
Labels: `setup`, `architecture`
Depende de: Inicializar repositório
Tarefas:
- [ ] Criar a árvore de pastas da seção 3 com `__init__.py`
- [ ] Documentar a regra de dependência (UI→core, core não conhece UI) no `CLAUDE.md`
Critérios de aceite:
- Estrutura idêntica à seção 3 deste documento

#### Issue: Implementar sistema de tema (palette + QSS)
Labels: `ui`, `design-system`
Depende de: Criar estrutura de pastas
Tarefas:
- [ ] `ui/theme/palette.py` com **todos** os tokens da seção 4.1 (hex exatos)
- [ ] `ui/theme/styles.py` com QSS global aplicando bg, bordas, raios, tipografia da seção 4.3
- [ ] Função `apply_theme(app)` aplicável no bootstrap
Critérios de aceite:
- Todos os hex batem com a tabela 4.1
- Raios e paddings batem com a seção 4.3

#### Issue: Janela principal + sidebar + roteamento de telas
Labels: `ui`
Depende de: Implementar sistema de tema
Tarefas:
- [ ] `ui/main_window.py`: header (traffic lights + ícone + título + subtítulo), área de conteúdo
- [ ] `ui/sidebar.py`: 6 ícones Tabler na ordem da seção 4.4, item ativo em `accent.blue`, Settings fixado embaixo
- [ ] `QStackedWidget` trocando telas vazias (placeholders) ao clicar na sidebar
- [ ] `app.py`: bootstrap do `QApplication` + tema + janela
Critérios de aceite:
- App abre mostrando a moldura (header + sidebar + área vazia)
- Clicar em cada ícone troca a tela ativa e atualiza o destaque

---

### Sprint 1 — Dashboard v0.1 (+ system tray)

**Milestone:** `Sprint 1 — Dashboard v0.1`
**Meta:** primeira versão usável. Coleta real, gauges, gráfico 60s, listas e tray. **Sem IA ainda** (a faixa de IA entra como placeholder estático).

#### Issue: Camada de coleta de métricas (CPU, RAM, disco, GPU)
Labels: `infra`, `metrics`
Depende de: Sprint 0 concluído
Tarefas:
- [ ] `domain/metrics.py`: entidades CpuMetric, MemMetric, DiskMetric, GpuMetric
- [ ] `infra/collectors/`: cpu, mem, disk via psutil; gpu via `nvidia-smi` com fallback gracioso (sem GPU NVIDIA → mostrar "n/d")
- [ ] `core/formatting.py`: bytes→GB, percentuais, temperaturas
Critérios de aceite:
- Cada collector retorna a entidade de domínio correspondente
- Ausência de GPU não quebra o app

#### Issue: QThread worker de métricas (1s) com sinais
Labels: `infra`, `threading`
Depende de: Camada de coleta de métricas
Tarefas:
- [ ] `infra/threads/metrics_worker.py`: QThread coletando a cada 1s e emitindo sinal `metrics_ready`
- [ ] UI nunca bloqueia; start/stop limpos no ciclo de vida do app
Critérios de aceite:
- Dashboard atualiza a cada 1s sem travar a UI
- Encerrar o app finaliza a thread sem warning

#### Issue: Widget Gauge circular (QPainter)
Labels: `ui`, `widget`
Depende de: Implementar sistema de tema
Tarefas:
- [ ] `ui/widgets/gauge.py`: anel sobre trilho `track`, traço 6px, número central, label embaixo
- [ ] Cor do anel parametrizável; vira `accent.amber` ao cruzar threshold
- [ ] Antialiasing ligado
Critérios de aceite:
- Renderiza idêntico ao mockup (raio ~24px, traço 6px, número 14px/500)

#### Issue: Widget Sparkline 60s (PyQtGraph)
Labels: `ui`, `widget`
Depende de: QThread worker de métricas
Tarefas:
- [ ] `ui/widgets/sparkline.py`: janela deslizante de 60s, múltiplas séries
- [ ] Linhas CPU (`accent.blue`) e RAM (`accent.purple`), traço 2px, sem fill, sem eixos pesados
- [ ] Legenda no header do card
Critérios de aceite:
- Linha desliza suavemente a 1s, sem leak de memória

#### Issue: Listas de Containers (resumo) e Top memória
Labels: `ui`, `metrics`
Depende de: Camada de coleta de métricas
Tarefas:
- [ ] `infra/collectors/process_collector.py`: top N processos por RAM
- [ ] `ui/widgets/` listas com bolinha de status / valor à direita conforme spec 5.1
- [ ] Container parado em `text.muted`
Critérios de aceite:
- Top memória ordenado desc por RAM, atualizando ao vivo

#### Issue: Montar a tela Dashboard
Labels: `ui`, `screen`
Depende de: Gauge, Sparkline, Listas
Tarefas:
- [ ] `ui/screens/dashboard_screen.py` compondo: 4 gauges + card 60s + faixa de IA (placeholder estático) + grid Containers/Top memória
- [ ] Layout, gaps e raios exatamente conforme seção 5.1
Critérios de aceite:
- Tela bate visualmente com o mockup validado do Dashboard

#### Issue: System tray + iniciar minimizado
Labels: `ui`, `feature`
Depende de: Janela principal
Tarefas:
- [ ] `QSystemTrayIcon` com menu (abrir, sair) e ícone de status
- [ ] Fechar a janela minimiza para a tray (configurável)
Critérios de aceite:
- App roda na bandeja; clicar no ícone restaura a janela

#### Issue: Empacotar v0.1 (AppImage)
Labels: `release`, `infra`
Depende de: Montar a tela Dashboard, System tray
Tarefas:
- [ ] Script PyInstaller + geração de AppImage
- [ ] Tag `v0.1.0`, release notes
Critérios de aceite:
- AppImage abre em Ubuntu limpo e mostra o Dashboard ao vivo

---

### Sprint 2 — Tela Sistema / Processos

**Milestone:** `Sprint 2 — Sistema`
**Meta:** detalhamento por núcleo, temperaturas e tabela de processos.

#### Issue: Coleta por núcleo, temperatura, swap, load, uptime
Labels: `infra`, `metrics`
Depende de: Sprint 1 concluído
Tarefas:
- [ ] Uso por core (psutil percpu), temperaturas (`psutil.sensors_temperatures`), swap, load average, uptime
Critérios de aceite:
- Valores conferem com `htop`/`uptime` na mesma máquina

#### Issue: Widget barras por núcleo
Labels: `ui`, `widget`
Depende de: Coleta por núcleo
Tarefas:
- [ ] `ui/widgets/core_bars.py`: grid de mini-barras, `accent.blue` (→`accent.amber` >85%)
Critérios de aceite:
- Bate com a spec 5.2

#### Issue: Tabela de processos ordenável
Labels: `ui`, `widget`
Depende de: Coleta por núcleo
Tarefas:
- [ ] Colunas PID/Nome/CPU/MEM/User com cores da spec 5.2
- [ ] Ordenação por CPU e por MEM (controle no header)
Critérios de aceite:
- Ordenação funciona ao vivo, sem flicker

#### Issue: Montar tela Sistema
Labels: `ui`, `screen`
Depende de: barras por núcleo, tabela de processos
Tarefas:
- [ ] `ui/screens/system_screen.py`: por-núcleo + 3 cards (temp/swap/processos) + tabela
Critérios de aceite:
- Bate visualmente com a spec 5.2

---

### Sprint 3 — Tela Docker (v0.2)

**Milestone:** `Sprint 3 — Docker`
**Meta:** gestão e monitoramento de containers.

#### Issue: Coletor Docker (docker-py) em slow worker (3s)
Labels: `infra`, `docker`
Depende de: Sprint 2 concluído
Tarefas:
- [ ] `infra/collectors/docker_collector.py`: listar containers, stats (CPU/MEM), portas, uptime, estado
- [ ] `infra/threads/slow_worker.py`: QThread 3s emitindo `docker_ready`
- [ ] Ausência de Docker/daemon não derrubado → estado "Docker não detectado"
Critérios de aceite:
- Lista e stats conferem com `docker ps` / `docker stats`
- Sem Docker instalado, a tela mostra estado vazio amigável

#### Issue: Widget ContainerCard + ações
Labels: `ui`, `widget`, `docker`
Depende de: Coletor Docker
Tarefas:
- [ ] `ui/widgets/container_card.py` conforme spec 5.3 (rodando/parado)
- [ ] Ações start/stop/restart/logs ligadas ao docker-py (com confirmação onde fizer sentido)
Critérios de aceite:
- Ações refletem no `docker ps` real

#### Issue: Montar tela Docker
Labels: `ui`, `screen`, `docker`
Depende de: Widget ContainerCard
Tarefas:
- [ ] `ui/screens/docker_screen.py`: lista de cards + nota de IA placeholder
- [ ] Tag `v0.2.0`
Critérios de aceite:
- Bate visualmente com a spec 5.3

---

### Sprint 4 — Tela Logs (journald)

**Milestone:** `Sprint 4 — Logs`
**Meta:** visualização e filtro de logs do journald.

#### Issue: Coletor journald
Labels: `infra`, `logs`
Depende de: Sprint 3 concluído
Tarefas:
- [ ] `infra/collectors/journald_collector.py`: ler via `journalctl -o json` (ou bindings), parsear em `LogEntry`
- [ ] Filtro por unidade e por prioridade; janela das últimas N horas
- [ ] Rodar no slow worker (3s) com tail incremental
Critérios de aceite:
- Entradas conferem com `journalctl` na mesma janela

#### Issue: Barra de filtro + widget LogLine
Labels: `ui`, `widget`, `logs`
Depende de: Coletor journald
Tarefas:
- [ ] Dropdown de serviço + pílulas de prioridade (cores da spec 5.4)
- [ ] `ui/widgets/log_line.py`: timestamp + etiqueta de severidade + unidade + mensagem
- [ ] Auto-scroll com pausa
Critérios de aceite:
- Filtros aplicam ao vivo; cores por severidade corretas

#### Issue: Montar tela Logs
Labels: `ui`, `screen`, `logs`
Depende de: Barra de filtro + LogLine
Tarefas:
- [ ] `ui/screens/logs_screen.py`: filtro + painel de IA placeholder + lista
Critérios de aceite:
- Bate visualmente com a spec 5.4

---

### Sprint 5 — Inteligência (IA que interpreta) — *o diferencial*

**Milestone:** `Sprint 5 — IA`
**Meta:** ligar a base de agentes do Blocksh e transformar métricas/logs em insights e diagnóstico. **É aqui (e só aqui) que reusamos a base de agentes do Blocksh.**

#### Issue: Persistência de histórico (SQLite)
Labels: `infra`, `db`
Depende de: Sprint 4 concluído
Tarefas:
- [ ] `infra/db/sqlite_store.py` + `services/history_service.py`: gravar séries de métricas com timestamp; retenção configurável
- [ ] Consultas por intervalo de tempo (para diagnóstico retroativo)
Critérios de aceite:
- Métricas persistem entre execuções; consulta por intervalo retorna a série

#### Issue: Motor de análise (tendências e previsões)
Labels: `core`, `ai`
Depende de: Persistência de histórico
Tarefas:
- [ ] `core/analysis.py`: previsão de enchimento de disco (regressão simples sobre histórico), detecção de container/processo com memória crescente, agrupamento de erros repetidos do journald
- [ ] Saída padronizada como entidades `Insight` (severity/title/message/source)
Critérios de aceite:
- "Disco enche em ~N dias" calculado a partir da tendência real
- Vazamento detectado quando RAM cresce monotonicamente por janela X

#### Issue: Integrar base de agentes do Blocksh (tool-calling)
Labels: `ai`, `integration`
Depende de: Motor de análise
Tarefas:
- [ ] Portar **somente** a base de agentes do Blocksh para `services/ai_service.py` (backends Ollama/Anthropic/OpenAI)
- [ ] Expor tools para o agente: `get_metrics(range)`, `get_logs(filter,range)`, `get_containers()`, `get_processes()`
- [ ] Seleção de backend via Settings
Critérios de aceite:
- Agente consegue chamar as tools e responder cruzando métricas + logs

#### Issue: Faixa/painel de IA real no Dashboard, Docker e Logs
Labels: `ui`, `ai`
Depende de: Integrar base de agentes, Montar telas Dashboard/Docker/Logs
Tarefas:
- [ ] `ui/widgets/ai_banner.py`: substituir os placeholders pelos `Insight` reais
- [ ] Dashboard: previsão de disco + vazamento; Docker: container destoante; Logs: erros agrupados
Critérios de aceite:
- Banners mostram insights reais derivados dos dados ao vivo

#### Issue: Tela IA / Diagnóstico (chat com tool-calls visíveis)
Labels: `ui`, `screen`, `ai`
Depende de: Integrar base de agentes
Tarefas:
- [ ] `ui/screens/ai_screen.py`: conversa, chips de tool-call (`accent.blue`), input + seletor de backend + chips de sugestão (spec 5.5)
- [ ] Pergunta-exemplo "por que travou às 14h?" funciona ponta a ponta
- [ ] Tag `v0.5.0`
Critérios de aceite:
- Bate visualmente com a spec 5.5 e responde cruzando histórico + logs

---

### Sprint 6 — Settings + polimento

**Milestone:** `Sprint 6 — Settings`
**Meta:** configuração completa e ajustes finos.

#### Issue: Persistência de configurações
Labels: `infra`, `settings`
Depende de: Sprint 5 concluído
Tarefas:
- [ ] `QSettings` (ou arquivo TOML) para intervalos, IA, thresholds, aparência, sistema
Critérios de aceite:
- Configurações sobrevivem a reinício

#### Issue: Montar tela Settings
Labels: `ui`, `screen`, `settings`
Depende de: Persistência de configurações
Tarefas:
- [ ] `ui/screens/settings_screen.py` com as 5 seções da spec 5.6
- [ ] Mudanças de intervalo/threshold/backend aplicam em runtime
Critérios de aceite:
- Alterar intervalo de coleta muda a cadência sem reiniciar
- Thresholds alteram quando gauges viram âmbar/vermelho

#### Issue: Iniciar com o sistema
Labels: `feature`, `settings`
Depende de: Persistência de configurações
Tarefas:
- [ ] Gerar `.desktop` autostart quando o toggle estiver ligado
Critérios de aceite:
- Toggle cria/remove o autostart corretamente

---

### Sprint 7 — Release v1.0

**Milestone:** `Sprint 7 — v1.0`
**Meta:** documentação, empacotamento e lançamento.

#### Issue: Documentação e README final
Labels: `docs`, `release`
Depende de: Sprint 6 concluído
Tarefas:
- [ ] README com screenshots reais das telas, badges, instruções de instalação
- [ ] Seção de arquitetura e contribuição
Critérios de aceite:
- README cobre instalação via AppImage e a partir do código

#### Issue: Empacotamento .deb + AppImage e release v1.0
Labels: `release`, `infra`
Depende de: Documentação
Tarefas:
- [ ] Gerar `.deb` e AppImage; pipeline de release no GitHub Actions
- [ ] Tag `v1.0.0` + release notes consolidadas
Critérios de aceite:
- Instaladores funcionam em Ubuntu limpo

---

## 7. Convenções

### Labels do GitHub

Criar antes de abrir issues:

`setup`, `infra`, `architecture`, `ui`, `design-system`, `widget`, `screen`, `metrics`, `threading`, `docker`, `logs`, `ai`, `core`, `db`, `integration`, `settings`, `feature`, `release`, `docs`, `needs-clarification`.

### Branches

- `main` protegida; trabalho em `feature/<sprint>-<slug>` (ex.: `feature/s1-gauge-widget`).
- PR por issue, referenciando `Closes #<n>`.

### Commits (Conventional Commits)

`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`, `build:`. Ex.: `feat(ui): gauge circular com QPainter`.

### Milestones

Um por sprint, no formato `Sprint N — Nome`, com data alvo opcional.

---

## 8. Apêndice — resumo de tokens (cola rápida)

```
bg.window       #1a1b26
bg.chrome       #16161e
bg.card         #1f2335
bg.card-inactive#1b1c26
bg.ai-banner    #1f2433
border.default  #2a2c3d
border.row      #20222e
border.ai       #e0af68
track           #2a2c3d
text.primary    #c0caf5
text.muted      #565f89
accent.blue     #7dcfff   (CPU, ativo, links)
accent.purple   #bb9af7   (RAM, memória)
accent.amber    #e0af68   (aviso, disco alto, temp, IA)
accent.green    #9ece6a   (ok, rodando, live)
accent.red      #f7768e   (crítico, erro, fechar)

raio janela 12px · card 10px · card-pequeno 8px · barra 3px
padding card 12px 14px · gap grid 10–12px
fonte: sans do sistema · pesos 400/500 · sentence case
métricas 1s · docker/journald 3s · UI nunca bloqueia
```
