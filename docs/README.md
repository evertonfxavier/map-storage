# Decky Dev Sandbox — Documentação do Plano

Conjunto de documentos que descreve o plano completo para um **ambiente de desenvolvimento local** que simula a experiência do Steam Deck + Decky Loader, permitindo iterar em plugins sem hardware alvo em todo ciclo.

## Objetivo

Reduzir o tempo entre “mudei o código” e “vi o plugin na UI”, mantendo um caminho claro para validação final no Steam Deck real.

## Documentos

| Arquivo | Conteúdo |
|---------|----------|
| [plano-completo.md](./plano-completo.md) | Visão geral, escopo, arquitetura, fases, stack, riscos e critérios de sucesso (documento mestre) |
| [arquitetura.md](./arquitetura.md) | Diagramas, módulos, fluxos de dados e contratos entre camadas |
| [roadmap.md](./roadmap.md) | Fases detalhadas, entregas, estimativas e dependências |
| [compatibilidade-decky.md](./compatibilidade-decky.md) | Matriz de APIs Decky, o que mockar vs. o que exige dispositivo real |
| [mvp-checklist.md](./mvp-checklist.md) | Checklist executável para o primeiro release utilizável |

## Contexto do repositório atual

Este repositório (`map-storage`) é um plugin Decky baseado no [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template). O sandbox descrito aqui é um **projeto separado** (recomendado: repositório `decky-dev-sandbox` ou monorepo com `packages/sandbox`), mas pode consumir plugins locais como este para testes.

## Leitura recomendada

1. [plano-completo.md](./plano-completo.md) — visão de ponta a ponta  
2. [arquitetura.md](./arquitetura.md) — como montar o sistema  
3. [roadmap.md](./roadmap.md) — ordem de implementação  
4. [mvp-checklist.md](./mvp-checklist.md) — antes de codar o MVP  

## Referências externas

- [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template)
- [Decky Loader wiki](https://github.com/SteamDeckHomebrew/decky-loader/wiki) (desenvolvimento e deploy)
- [@decky/ui](https://www.npmjs.com/package/@decky/ui) / [@decky/api](https://www.npmjs.com/package/@decky/api)
