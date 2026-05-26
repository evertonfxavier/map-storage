# Plano completo: Decky Dev Sandbox

## 1. Resumo executivo

O **Decky Dev Sandbox** é uma aplicação desktop (e opcionalmente web) focada em desenvolvedores de plugins Decky. Ela imita **visual e fluxos principais** do Steam Deck em Game Mode + área de configurações onde plugins aparecem, oferece um **runtime de plugins** compatível com um subconjunto documentado das APIs `@decky/ui` e `@decky/api`, e permite **instalar, recarregar e depurar** plugins locais sem deploy SSH a cada alteração.

**Não é** um emulador de SteamOS nem um substituto do Decky Loader em produção. É um acelerador de desenvolvimento com validação final obrigatória no hardware ou VM Linux com Decky real.

### Metas de produto

| Meta | Descrição |
|------|-----------|
| Produtividade | Ciclo editar → ver UI em &lt; 5 s (hot reload) |
| Fidelidade visual | Layout, tipografia e componentes próximos ao Quick Access / Settings |
| Compatibilidade pragmática | 70–80% dos plugins “só frontend” funcionam sem alteração |
| Transparência | Deixar explícito o que funciona no sandbox vs. no Deck |
| Extensibilidade | Plugins de teste, mocks configuráveis, bridge para Deck real |

---

## 2. Problema e oportunidade

### Problema atual

- Desenvolvimento no macOS/Windows limita-se a `pnpm run build` e inspeção de `dist/`.
- Teste integrado exige Steam Deck (ou Linux + Decky), rede, SSH e reload manual.
- Plugins com backend Python/binários falham ou se comportam diferente fora do alvo.
- Novos desenvolvedores não têm feedback visual rápido.

### Oportunidade

- Centralizar mocks das APIs mais usadas (`definePlugin`, `callable`, `toaster`, eventos).
- Reutilizar `@decky/ui` no host quando possível (mesmos componentes visuais).
- Carregar `dist/index.js` do plugin como o Loader faz (IIFE/UMD + globals).
- Oferecer “modo bridge”: mesmo plugin no sandbox e sync opcional para o Deck.

---

## 3. Escopo

### Dentro do escopo (MVP → v1)

- Shell UI estilo Steam Deck (resolução configurável: 1280×800, 1920×1200).
- Painel Quick Access simulado com lista de plugins instalados.
- Instalação de plugin a partir de pasta local (estrutura `plugin.json`, `package.json`, `dist/index.js`).
- Hot reload ao detectar mudança em `dist/` ou via `pnpm watch` integrado.
- Mock de `@decky/api`: `definePlugin`, `callable`, `toaster`, `addEventListener` / `removeEventListener`.
- Mock de backend Python via processo local ou stubs JSON (respostas configuráveis).
- Console de logs (frontend + “backend” mock).
- Gerenciador de plugins: instalar, habilitar/desabilitar, remover.
- Documentação de gaps de compatibilidade.

### Fora do escopo (v1)

- Emulação completa de jogos Steam / biblioteca.
- Paridade 100% com todas as APIs internas do Steam client.
- Instalação da loja oficial de plugins (decky-plugin-database) sem adaptação.
- Execução garantida de binários `bin/` compilados para Linux aarch64/x86_64 SteamOS.
- Substituir Decky Loader no dispositivo do usuário final.

### Escopo futuro (v2+)

- Bridge SSH: deploy automático para Deck após validação no sandbox.
- Perfil “SteamOS VM” (QEMU/UTM) orquestrado pelo sandbox.
- Gravação/replay de sessões para regressão visual.
- Marketplace local de plugins em desenvolvimento.
- Suporte parcial a `routerHook` e rotas Steam reais (via hooks documentados).

---

## 4. Personas e casos de uso

| Persona | Caso de uso |
|---------|-------------|
| Autor de plugin | Desenvolve UI e lógica JS; testa botões, painéis, toasts no sandbox |
| Autor full-stack | Mocka `callable` no sandbox; valida Python no Deck em pipeline CI |
| Mantenedor | Usa sandbox em CI headless para smoke test de build de plugins |
| Iniciante | Aprende estrutura `definePlugin` sem possuir Steam Deck no dia 1 |

### Fluxos principais

1. **Abrir projeto de plugin** → Sandbox detecta `plugin.json` → Monta entrada em Quick Access.
2. **Watch + reload** → Alteração em `src/` → build → reload automático do `dist/index.js`.
3. **Chamar backend** → `callable("add")` → Mock Server ou subprocess `main.py` local.
4. **Validar no Deck** → Botão “Deploy to Deck” → rsync/SSH → instruções de reload no Loader.

---

## 5. Arquitetura de alto nível

```
┌─────────────────────────────────────────────────────────────────┐
│                    Decky Dev Sandbox (Host)                      │
├─────────────────────────────────────────────────────────────────┤
│  Presentation Layer                                              │
│  ├─ Deck Chrome (frame, gamepad cursor, safe areas)              │
│  ├─ Quick Access Panel                                           │
│  └─ Dev Tools (logs, network, plugin inspector)                  │
├─────────────────────────────────────────────────────────────────┤
│  Plugin Runtime                                                  │
│  ├─ Loader (import dist/index.js, register definePlugin)        │
│  ├─ Module shims (@decky/ui, @decky/api → host implementations) │
│  └─ Lifecycle (mount/unmount, HMR)                             │
├─────────────────────────────────────────────────────────────────┤
│  API Emulation Layer                                             │
│  ├─ callable router → MockBackend | Python subprocess | WS       │
│  ├─ Event bus (timer_event, custom)                             │
│  └─ Storage / settings persistence (JSON local)                  │
├─────────────────────────────────────────────────────────────────┤
│  Plugin Manager                                                  │
│  ├─ Scan ~/.local/share/decky-sandbox/plugins (configurável)    │
│  ├─ Validate plugin.json + dist                                  │
│  └─ Symlink / copy from dev workspace                            │
└─────────────────────────────────────────────────────────────────┘
         │ optional                    │ production truth
         ▼                             ▼
   Mock Backend                   Steam Deck + Decky Loader
   (JSON / Python local)          (main.py, bin/, Steam APIs)
```

Detalhamento em [arquitetura.md](./arquitetura.md).

---

## 6. Stack tecnológica recomendada

| Camada | Tecnologia | Motivo |
|--------|------------|--------|
| Desktop shell | **Electron** ou **Tauri 2** | Acesso filesystem, subprocess, multiplataforma |
| UI host | **React 19** + **TypeScript** | Alinhado ao ecossistema Decky |
| Componentes | **@decky/ui** (bundled no host) | Máxima fidelidade visual |
| Build host | **Vite** | HMR rápido no próprio sandbox |
| Plugin load | **dynamic import** / script tag + globals | Compatível com output Rollup do template |
| Mock API | Pacote **`@decky/sandbox-api`** (nome provisório) | Shim publicável para testes unitários |
| Backend mock | **Node** child_process → `python3 main.py` ou **FastAPI** sidecar | Paridade com `callable` |
| Persistência | JSON em `~/.decky-sandbox/` | Simples, inspecionável |
| CI | GitHub Actions + Playwright | Screenshot smoke de plugins exemplo |
| Empacotamento | electron-builder / Tauri bundle | macOS, Linux, Windows |

**Decisão sugerida:** Tauri se priorizar binário leve; Electron se priorizar ecossistema maduro e `child_process` Python sem fricção no macOS.

---

## 7. Compatibilidade com Decky

Princípio: **implementação em camadas** (L0 → L3).

| Nível | Significado | Exemplo |
|-------|-------------|---------|
| L0 | Comportamento idêntico no sandbox | `PanelSection`, `ButtonItem`, `toaster` |
| L1 | API presente, semântica simplificada | `callable` → mock fixo ou script local |
| L2 | API stub com warning em runtime | `routerHook`, Steam store APIs |
| L3 | Não suportado — exige Deck | Binários `bin/`, D-Bus, paths SteamOS |

Matriz completa em [compatibilidade-decky.md](./compatibilidade-decky.md).

---

## 8. Roadmap por fases

Resumo; cronograma detalhado em [roadmap.md](./roadmap.md).

### Fase 0 — Fundação (1 semana)

- Repositório `decky-dev-sandbox`, CI, licença, README.
- Shell mínima 1280×800, tema escuro Steam-like.
- Prova de conceito: carregar `dist/index.js` de um plugin e renderizar um `PanelSection`.

### Fase 1 — MVP (2–3 semanas)

- Plugin Manager (pasta local + symlink).
- Shims `@decky/api` completos para template oficial.
- Hot reload + integração `pnpm watch` (CLI `sandbox dev /path/to/plugin`).
- Mock backend para `callable` (JSON + opcional `main.py`).
- DevTools: console + lista de plugins.

### Fase 2 — Beta (3–4 semanas)

- Gamepad / teclado (navegação por foco estilo Deck).
- Mais componentes `@decky/ui` validados (Dialog, Dropdown, Tabs).
- Perfis de resolução e escala UI.
- Projeto exemplo + plugin `map-storage` como caso de teste.
- Documentação “Sandbox vs Deck”.

### Fase 3 — v1.0 (4–6 semanas)

- Bridge SSH para Deck (deploy + reload).
- CLI `decky-sandbox` (init, dev, validate, pack).
- Validação estrutural de plugin (layout zip / plugin store).
- Testes E2E com 3 plugins referência da comunidade.
- Releases macOS + Linux (+ Windows se viável).

### Fase 4 — v2 (contínuo)

- CI headless, gravação visual, VM profile, extensões comunitárias.

---

## 9. Estrutura de repositório proposta

```
decky-dev-sandbox/
├── apps/
│   └── desktop/              # Electron/Tauri + React shell
├── packages/
│   ├── sandbox-api/          # Shims @decky/api para host e testes
│   ├── sandbox-ui/           # Deck chrome + Quick Access layout
│   ├── plugin-loader/        # Carrega dist/index.js, lifecycle
│   └── plugin-validator/     # plugin.json, dist, LICENSE
├── fixtures/
│   └── sample-plugin/        # Cópia mínima do template
├── docs/                     # Esta documentação (ou submodule)
├── scripts/
│   └── dev-plugin.sh
└── package.json              # pnpm workspace
```

---

## 10. Modelo de instalação de plugins no sandbox

1. Usuário aponta diretório raiz do plugin (ex.: `map-storage/`).
2. Validador exige: `plugin.json`, `package.json`, `dist/index.js`.
3. Sandbox registra metadata (nome, versão, ícone se houver).
4. Loader injeta globals e executa bundle do plugin.
5. `definePlugin` registra título, ícone, `content` (React tree).
6. Alteração em `dist/index.js` dispara unmount + remount (HMR).

**Opcional:** watcher no diretório do plugin que executa `pnpm run build` antes do reload.

---

## 11. Emulação do Decky Loader

O Loader real:

- Injeta frontend compilado na UI do Steam.
- Expõe bridge Python ↔ JS via `callable`.
- Gerencia ciclo de vida e permissões.

O sandbox replica **contratos**, não implementação interna:

| Contrato Loader | Sandbox |
|-----------------|---------|
| `definePlugin({ name, title, content, icon })` | Registry em memória + UI tab |
| `callable(name)` | RPC para MockBackend ou `main.py` |
| Eventos Python → JS | EventEmitter + WebSocket local opcional |
| `toaster` | Toast host nativo ou componente @decky/ui |
| Settings persistidos | `localStorage` / arquivo JSON por plugin |

**Não replicar:** instalação `.zip` via URL no dispositivo, atualizações OTA do Loader, integração com menu Steam original (a menos que v2 com hooks).

---

## 12. Visual “Steam Deck”

### Elementos de UI a reproduzir (prioridade)

1. Frame 16:10 com bezels opcionais.
2. Overlay Quick Access (deslize da direita ou atalho).
3. Lista vertical de plugins com ícone + título.
4. Área de conteúdo do plugin (scroll, `PanelSection`).
5. Indicadores de botões (A/B/X/Y) quando gamepad ativo.
6. Fonte e espaçamento aproximados ao Steam (CSS variables, não cópia de assets proprietários).

### Diretriz legal/design

- Não redistribuir assets oficiais Valve/Steam.
- Usar **inspiração visual** + `@decky/ui` (open source do ecossistema Decky).
- Marca clara: “Dev Sandbox — não afiliado à Valve”.

---

## 13. Segurança e isolamento

- Plugins são código arbitrário: executar em **context isolado** (iframe com sandbox ou VM2 / worker limitado).
- `callable` para subprocess Python: timeout, sem shell arbitrário, cwd restrito ao plugin.
- Não executar binários `bin/` do plugin no host macOS sem aviso explícito (arquitetura errada).
- Assinatura opcional de plugins em modo “trusted dev only”.

---

## 14. Riscos e mitigações

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Drift de API Decky | Plugins quebram no sandbox | Versionar shims com `@decky/api` peer dep; matriz L0–L3 |
| `@decky/ui` assume globals Steam | Render incorreto | Camada de providers mock no host |
| Backend Python diferente do Deck | Bugs só no hardware | Documentar + bridge deploy; testes integração no Deck |
| Escopo infinito (“igual Steam Deck”) | Projeto não lança | MVP estrito; fases com critérios de saída |
| Manutenção dupla | Custo alto | Compartilhar pacote `sandbox-api` com comunidade |

---

## 15. Critérios de sucesso

### MVP (Fase 1)

- [ ] Plugin baseado no template oficial abre no sandbox sem alteração de código.
- [ ] Botão que chama `callable("add")` retorna valor (mock ou Python local).
- [ ] Hot reload em &lt; 3 s após `pnpm run build`.
- [ ] Logs visíveis quando plugin lança erro no mount.

### v1.0

- [ ] 3 plugins comunitários “UI-only” funcionam com ≤ 5 linhas de adaptação documentadas.
- [ ] CLI `sandbox dev` documentado; README com fluxo macOS → Deck.
- [ ] Bridge SSH opcional testado em ≥ 1 Steam Deck real.

### Métricas

- Tempo médio de feedback (edit → visible): alvo &lt; 5 s.
- % APIs `@decky/api` cobertas: alvo 60% no v1, 80% no v2.
- NPS interno devs (opcional): ≥ 8 após 1 mês de uso.

---

## 16. Integração com `map-storage`

Este plugin pode servir como **fixture de referência**:

1. No sandbox: `sandbox dev /Users/evertonxavier/projects/map-storage`.
2. Validar `PanelSection`, botões, `add`, `start_timer` / `timer_event`.
3. Quando backend real for necessário: habilitar subprocess `main.py` do repositório.
4. Antes de release: checklist [mvp-checklist.md](./mvp-checklist.md) + teste no Deck.

---

## 17. Próximos passos imediatos

1. Criar repositório `decky-dev-sandbox` (monorepo pnpm).
2. Spike Fase 0: carregar `map-storage/dist/index.js` em host Vite mínimo.
3. Implementar shim `definePlugin` + registry.
4. Iterar Fase 1 conforme [roadmap.md](./roadmap.md).
5. Publicar matriz de compatibilidade viva em [compatibilidade-decky.md](./compatibilidade-decky.md).

---

## 18. Glossário

| Termo | Definição |
|-------|-----------|
| **Decky Loader** | Carregador de plugins no Steam Deck |
| **Plugin** | Pacote com `plugin.json`, frontend `dist/`, opcional `main.py` / `bin/` |
| **callable** | Ponte JS → função Python exposta em `main.py` |
| **Quick Access** | Menu lateral onde plugins aparecem no Game Mode |
| **Sandbox** | Este ambiente de desenvolvimento simulado |
| **Bridge** | Fluxo de deploy do sandbox/macOS para o Deck físico |

---

*Documento versão 1.0 — maio/2026*
