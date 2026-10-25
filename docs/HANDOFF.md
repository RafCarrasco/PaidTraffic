# Handoff — issue #1

Estado: pipeline real alternativo funcionando; Meta bloqueada por autorização da aplicação. Token seguro está disponível. HTTP 400/code 10/subcode 2332002 reproduzidos com v26.0/PT/receitas/ACTIVE. Nenhum Computer Use disponível. Não repetir testes Meta sem mudança de estado. Ação humana precisa: conferir o acesso específico à Ads Library na mesma conta/app, conforme META_DIAGNOSIS.md; não gerar outro token/empresa/app às cegas.

Execução inicial real do catálogo: 74 referências (3 na lista pt_PT, 71 na pt_BR), não anúncios ou vendas; termos python/programação/javascript/receitas. Revisão observada 52e40c13216706ff4a0b63c3224c34abaa266e1d. Repetição confirmou 74 anúncios/registros únicos no acervo catalog e novas observações, sem duplicação de IDs. Dados e relatórios estão ignorados pelo Git; evidência resumida em RESEARCH.md. Scripts e licença estão no commit. Os livros não foram baixados.

Comandos na raiz:

```bash
python -m unittest discover -s tests -v
python -m offerlab --config config/catalog.json
python -m offerlab --config config/auto.json
python -m offerlab --config config/auto.json --schedule
```

19 testes passaram (sem rede): erros Meta redigidos, paginação, budgets, dedup/upsert, histórico, migração, catálogo com licença/latest, import com proveniência, Apple com respostas controladas e continuidade após Meta negada. Auto gera rankings JSON/CSV e report.md, com latest-run.json parcial/exit1 se Meta falhar; coleta catalog isolada pode concluir success/exit0. Um retorno parcial não significa ausência de resultados.

Fontes implementadas: Meta, catálogo licenciado, import de exportação autorizada, Apple opcional e demo separada. Apple/documentação oficial estavam bloqueadas pelo proxy e não foram validadas ao vivo. Rascunho de rede contém domínios oficiais necessários, preservando graph.facebook.com. Revisar/salvar e publicar pelo ambiente não é o mesmo que já ter aplicado/validado as rotas. Segredo existente foi preservado; nenhum valor é necessário no chat.

O runner Codex não é serviço 24/7; nenhum agendador foi instalado. Reiniciar processo após restauração e usar só uma instância por banco/pasta. Usar checkout existente: tarefas cloud já são isoladas; não criar worktree salvo solicitação explícita. Preservar dados locais e segredos fora do Git.

Próximos passos: conferir acesso Meta; permitir rede para documentação/Apple; validar catálogo comercial permitido e então revisar 20 ofertas realmente comerciais em Portugal. O acervo atual é material para pesquisa/diferenciação, não validação de oportunidade low-ticket. Não introduzir IA paga, campanhas ou compras sem aprovação.
