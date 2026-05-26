# MVP Checklist — Decky Dev Sandbox (Fase 1)

Lista executável para considerar o MVP **pronto para uso diário** no desenvolvimento de plugins (ex.: `map-storage`).

---

## A. Repositório e infraestrutura

- [ ] Monorepo `decky-dev-sandbox` criado com pnpm workspaces
- [ ] `apps/desktop` abre janela 1280×800 (macOS testado)
- [ ] CI: lint + build do host em push
- [ ] Licença e README com disclaimer “não afiliado à Valve”

---

## B. Plugin Loader

- [ ] Carrega `plugin.json` e exibe nome/versão
- [ ] Falha com mensagem clara se `dist/index.js` ausente
- [ ] Executa bundle e captura `definePlugin`
- [ ] Monta `content` React no painel Quick Access simulado
- [ ] Error Boundary exibe stack sem derrubar o host
- [ ] Hot reload ao salvar `dist/index.js` (< 3 s em máquina dev)

---

## C. API Shim (`sandbox-api`)

- [ ] `definePlugin` registra título, ícone e conteúdo
- [ ] `callable` encaminha para backend configurável
- [ ] `toaster` exibe mensagem visível
- [ ] `addEventListener` / `removeEventListener` funcionam
- [ ] Evento `timer_event` (ou equivalente) dispara após `start_timer` em modo mock

---

## D. Backend

- [ ] Modo **mock**: `sandbox.backend.json` na raiz do plugin
- [ ] Modo **python**: subprocess `main.py` com timeout
- [ ] Log de cada chamada `callable` no DevTools
- [ ] Alternar modo mock/python na UI de config do sandbox

---

## E. Plugin Manager

- [ ] Adicionar plugin por caminho absoluto (ex.: `/Users/evertonxavier/projects/map-storage`)
- [ ] Symlink ou referência sem copiar `node_modules`
- [ ] Habilitar / desabilitar plugin
- [ ] Remover plugin da lista (não deletar fonte)

---

## F. CLI

- [ ] `sandbox dev <path>` inicia host + aponta para plugin
- [ ] Opcional: disparar `pnpm watch` no diretório do plugin
- [ ] `sandbox validate <path>` verifica `plugin.json`, `dist/index.js`, `package.json`

---

## G. Validação com `map-storage`

- [ ] `pnpm run build` sem erros no plugin
- [ ] Sandbox exibe “Panel Section” e botões do template
- [ ] Clique em “Add two numbers…” retorna número (mock ou Python)
- [ ] Clique em timer dispara toast ou handler de evento
- [ ] Alterar texto em `src/index.tsx` → rebuild → UI reflete mudança

---

## H. Documentação

- [ ] Quickstart em README (< 10 min para primeiro run)
- [ ] Seção “O que não funciona no sandbox” linkando [compatibilidade-decky.md](./compatibilidade-decky.md)
- [ ] Instruções “validar no Deck” (path plugins + reload)

---

## I. Qualidade mínima

- [ ] Sem crash ao plugin lançar exceção no render
- [ ] Sem memory leak óbvio após 20 reloads consecutivos
- [ ] Versão semver `0.5.0` taggeada no repositório sandbox

---

## J. Fora do MVP (não bloquear release 0.5)

- [ ] Bridge SSH (`sandbox deploy`)
- [ ] Gamepad completo
- [ ] Windows build
- [ ] Suporte `bin/` nativo
- [ ] `routerHook`

---

## Critério final “Go”

Marcar MVP como **Go** quando **todos** os itens das seções A–G estiverem `[x]` e pelo menos **80%** da seção H.

---

## Comandos de referência (`map-storage`)

```bash
cd /Users/evertonxavier/projects/map-storage
pnpm i
pnpm run build
# Após sandbox existir:
# sandbox dev /Users/evertonxavier/projects/map-storage
```

---

*Roadmap completo: [roadmap.md](./roadmap.md)*
