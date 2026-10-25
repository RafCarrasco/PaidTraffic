# Diagnóstico Meta — issue #1

Em 25/10/2026, o ambiente tinha binding seguro `META_ACCESS_TOKEN` e acesso de rede a `graph.facebook.com`. Uma chamada autenticada de leitura ao `v26.0/ads_archive`, com `ad_type=ALL`, `ad_active_status=ACTIVE`, país PT e termo receitas, retornou HTTP 400, OAuthException **code 10 / error_subcode 2332002**. A execução do pipeline reproduziu a mesma combinação. Nenhum valor de token foi impresso ou salvo no repositório.

## O que está e não está diagnosticado

A operação foi negada por autorização da aplicação para Ads Library. Não é uma falha de instalação do OfferLab nem razão para gerar outro token às cegas. Presença de `ads_read`, Facebook Login, criação do app, associação a portfólio ou sucesso em outros endpoints não comprovam acesso a `ads_archive`. O estado exato do cadastro, verificação de identidade/localização e adesão ao acesso da Ads Library na conta/app continua desconhecido: não há Computer Use ou sessão de navegador disponível neste runner.

Não foi possível conferir o texto **atual** das páginas oficiais durante esta execução: o proxy devolveu `Tunnel connection failed: 403 Forbidden` para os hosts de documentação. O diagnóstico acima se baseia na resposta autenticada da API e no contexto da issue, não numa confirmação das telas da conta. Não se afirma que adicionar uma permissão genérica ou um portfólio resolverá o erro.

Referências oficiais para a etapa humana:
- https://www.facebook.com/ads/library/api/
- https://developers.facebook.com/docs/marketing-api/reference/ads_archive/
- https://developers.facebook.com/docs/graph-api/changelog/

## Intervenção estritamente necessária

No navegador já autenticado **na mesma conta autorizada a usar o app OfferLab Intelligence**, abra a página oficial Ads Library API. Confira o fluxo específico de acesso à biblioteca e o status dos requisitos que a própria Meta apresentar. Conclua apenas os requisitos oficiais aplicáveis; caso o acesso já conste habilitado, encaminhe ao suporte da Meta o endpoint, a versão v26.0 e os códigos 10/2332002 para confirmar autorização dessa conta/app. Não encaminhe o token. Não criar novos apps/empresas nem enviar documentos por este repositório.

Depois de uma mudança real de estado, testar com:

```bash
python -m offerlab --config config/meta.example.json --doctor-meta
```

É uma única requisição (limite 1), sem IA paga, com diagnóstico em `reports/meta/latest-run.json`. Não dispara tentativas de escrita na conta. Um futuro erro 190 será classificado separadamente como token inválido/expirado; rate limits também têm diagnóstico distinto. Nunca trocar silenciosamente uma resposta negada por fixtures.

Os hosts oficiais foram adicionados ao rascunho de rede do ambiente para consulta posterior. Salvar rascunho não aplica configuração nem publica o ambiente. Nenhum bloqueio de autorização da Meta foi contornado. Enquanto isso, `config/auto.json` continua pelas fontes alternativas e registra estado parcial.
