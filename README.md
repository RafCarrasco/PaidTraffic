# OfferLab — mineração automatizada 0.2

Pipeline Python 3.12+ / SQLite para pesquisar ofertas e referências de conteúdo digital. Sem pacotes externos, servidor, infraestrutura paga ou chamada de IA. Não publica anúncios, compra produtos nem cadastra serviços. Primeira execução real: 74 referências de livros digitais em português de um catálogo CC BY 4.0; não são anúncios ou 20 ofertas comerciais já validadas.

## Executar agora

Na raiz do checkout:

```bash
python -m unittest discover -s tests -v
python -m offerlab --config config/catalog.json
python -m offerlab --config config/auto.json
```

`catalog.json` coleta metadados públicos da Ebook Foundation sem credenciais. `auto.json` tenta Meta primeiro e continua pelo catálogo mesmo após falha. A Meta está negando a operação com code 10/subcode 2332002; [diagnóstico e ação necessária](docs/META_DIAGNOSIS.md). Não há Computer Use disponível neste ambiente. O token existente não deve ser impresso ou reenviado no chat.

Relatórios locais: `reports/auto/ranking.json`, `ranking.csv`, `report.md` e `latest-run.json`. O ranking agregado exclui fontes que falharam no ciclo atual; cada fonte também tem sua pasta e relatório de estado. Banco compartilhado: `data/offerlab.sqlite3`. Fontes ficam isoladas por nome/ID; dados fictícios não são permitidos no modo auto. Registros antigos permanecem no acervo: ver last_seen, record_kind e source_limitations antes de comparar. O modo demo separado continua disponível em `config/demo.json`.

## Agendamento

```bash
python -m offerlab --config config/auto.json --schedule
```

Executa imediatamente e repete após interval_seconds contados do fim de cada ciclo. Ctrl+C encerra. Falhas e estado parcial ficam registrados, e o próximo ciclo continua agendado. Para horários fixos, configure cron no computador/runner que permanecerá ligado. Exemplo às 09h **America/Sao_Paulo**, somente se esse for o fuso configurado no cron/host:

```cron
0 9 * * * cd /workspace/PaidTraffic && /usr/bin/flock -n /tmp/offerlab.lock python -m offerlab --config config/auto.json >> /workspace/PaidTraffic/data/scheduler.log 2>&1
```

Antes: crie `data/`, ajuste caminhos/Python/fuso, injete a credencial segura no processo do agendador e mantenha um único agendador por banco/pasta. Não colocar segredos no crontab. Nenhum cron ou daemon foi instalado automaticamente. **Uma tarefa Codex não é serviço 24/7**: processo e relógio do runner podem parar entre tarefas. `--schedule` não sobrevive à restauração da máquina; reinicie-o. Sem garantia de monitoramento contínuo ou novas ofertas em intervalo fixo.

## Fontes e configuração

- `meta`: API oficial Ads Library, agora com erro numérico sanitizado e `--doctor-meta` (1 requisição). Integração real segue bloqueada por autorização da aplicação.
- `catalog`: catálogo licenciado CC BY 4.0, pin de revisão, idioma, categoria, título, URL e evidência por linha/hash. Funciona agora. Conteúdo majoritariamente programação; útil para pesquisar conteúdo/diferenciação, não cobre todos os nichos.
- `apple`: adaptador oficial de busca de ebooks com preço/moeda/storefront quando disponíveis; testado com respostas controladas, bloqueado pela rede no teste ao vivo. Desabilitado em auto até conferir condições atuais e conectividade.
- `import`: ingestão em lote de exportações JSON autorizadas, sem cadastro manual de cada anúncio.
- `demo`: três anúncios FICTÍCIOS, fonte/pastas separadas.

Formatos, condições, licença e ativação: [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md). Fonte não pode virar demo silenciosamente. Catálogo não significa anúncio: o relatório tem `record_kind`, proveniência e limitações.

Cada JSON controla países ISO, termos, periodicidade, max_requests, max_ads, page_size, banco/pasta, versão Graph e pesos. Limites são por fonte por ciclo, não diários; duplicatas também contam em max_ads. Fontes auto herdam parâmetros gerais e podem sobrescrevê-los; pastas de relatório devem ser distintas. Países/termos filtram APIs conforme seu contrato; no catálogo filtramos termo sobre título/categoria, e países não filtram a nacionalidade. Imports preservam todos os registros autorizados até o limite. A ordem dos termos pode consumir o orçamento antes dos seguintes. Por padrão, catalog_ref=latest resolve o HEAD oficial a cada ciclo e verifica o hash da licença antes de coletar; cada evidência fixa o SHA obtido. Um SHA explícito permite reprodução sem atualização upstream.

## Persistência e classificação

`ads`: último estado por fonte/ID, first_seen e last_seen locais. `observations`: evidência bruta, contexto da busca, SHA-256 e referência da execução. `runs`: progresso, status, requests, erro sanitizado, contagem de novos/atualizados, configuração não secreta, diagnóstico e custo não medido. Migração aditiva preserva bancos 0.1. IDs diferentes não são fundidos por semelhança semântica; catálogo deduplica URL dentro de cada lista de idioma.

O enriquecimento atual extrai metadados da fonte, sem baixar produtos ou visitar destinos. Fatos da fonte ficam em raw/evidence; classificação e score são hipóteses heurísticas. Score de triagem/completude de 0 a 100: sinal de produto digital (40), texto (20), URL HTTP(S) disponível (20), data de início de anúncio (20). Pesos configuráveis somam 100 e são preservados com as contribuições. URL pode não ser landing page válida; snapshot não conta como landing page. Catálogo gratuito pode pontuar alto em completude sem ter valor comercial. Não estimamos demanda comprovada, faturamento, margem, persistência contínua ou risco legal sem evidências.

CLI: 0 quando as fontes terminam sem falha (podem ter limites atingidos); 1 quando há falha total **ou parcial**; 2 em configuração inválida; 130 em interrupção. Em auto parcial, relatórios úteis das outras fontes são gerados mesmo retornando 1. `latest-run.json` diferencia success, limited, partial e failed. `limited` indica corte de orçamento; não cobertura completa. Em fonte isolada que falhou, ranking anterior pode permanecer: `ranking_current=false`. O relatório agregado ignora essa fonte no ciclo. Um HTTP negado não apaga evidências anteriores.

Logs vão a stderr, com progresso e erros sem token. Nenhuma IA paga executada; custo externo desconhecido não é registrado como zero. `.env`, data/, reports/ e caches estão ignorados. Não existe carregamento automático de .env. Backups: API SQLite backup ou processo parado. Não executar duas instâncias na mesma pasta de relatórios.

## Limitações e próximos passos

Falta habilitar o acesso específico à Ads Library e validar a resposta de sucesso da Meta. Documentação oficial e Apple estavam bloqueadas pelo proxy; domínios necessários foram salvos no rascunho do ambiente, que precisa ser aplicado/publicado pelo usuário. Sem scraping, retry automático, análise financeira, IA, UI sofisticada ou monitoramento de anúncios 24/7. O catálogo de livros gratuitos é uma alternativa legítima de pesquisa, mas não substitui a evidência de anúncios nem valida demanda por ofertas low-ticket em Portugal.

Leia [arquitetura](docs/ARCHITECTURE.md), [handoff](docs/HANDOFF.md) e [evidência da execução](docs/RESEARCH.md).
