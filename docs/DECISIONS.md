# Decisões

- 2026-10-25: priorizar pipeline automatizado por atualização explícita do escopo; adiar Streamlit e cadastro manual.
- Usar Python/SQLite sem dependências para facilitar execução e agendamento local.
- API oficial somente; credencial ausente deve falhar, nunca acionar demo automaticamente.
- Demo isolada por fonte e caminhos padrão, com marcações FICTÍCIO.
- Score inicial mede sinais de produto digital/completude, não lucratividade. Critérios comerciais completos foram adiados por falta de evidência e definições calibradas.
- Não adicionar infraestrutura paga nem executar IA. Não publicar campanhas ou criar serviços externos.
- Nenhum agendador instalado automaticamente; CLI contínua e exemplo cron documentados.

## 2026-10-25 — issue #1

- Reproduzir a negativa Meta em v26.0; registrar code 10/subcode 2332002 sem mensagens remotas/token. Não atribuir a solução a ads_read, Facebook Login ou portfólio sem evidência.
- Não pedir novamente o token: binding seguro está presente. A intervenção necessária é conferir o acesso específico à Ads Library na conta/app; documentação oficial estava bloqueada pela rede.
- Usar catálogo público da Ebook Foundation sob CC BY 4.0 como fonte real alternativa de pesquisa de conteúdo, sem apresentá-lo como anúncios/demanda/ofertas pagas validadas. Licença integral e atribuição preservadas; licença dos livros não é concedida pelo catálogo.
- Automatizar atualização do catálogo via latest + verificação de licença; fixar SHA/linha/hash por evidência para auditabilidade. SHA explícito continua suportado para reprodução.
- Preparar Apple Search API, mas mantê-la fora de auto até verificar acesso/condições atuais: teste ao vivo bloqueado por rede, apenas respostas controladas validadas.
- Orquestração tolera falha de fonte e gera resultado parcial. CLI retorna 1 em parcial para monitoramento; o agendador continua ciclos futuros. Nunca preencher falhas com dados fictícios.
- Import em lote exige origem e declaração de autorização. Sem scraping de landing pages e sem downloads de produtos; enriquecimento usa metadados já autorizados.
- Nenhum daemon, cron, cobrança, campanha ou chamada de IA foi instalado/executado. Disponibilizar alterações em branch/commit do Git, sem alterar main automaticamente.
