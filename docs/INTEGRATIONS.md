# Fontes e credenciais

## Meta Ad Library

`mode=meta`: GET oficial em `https://graph.facebook.com/v26.0/ads_archive`, termos, países e status ACTIVE configuráveis, paginação por cursor, timeout de 30s, orçamento por execução. Requer acesso autorizado à Ads Library na conta/app e `META_ACCESS_TOKEN` injetado pelo gerenciador seguro de segredos. O cliente não carrega `.env`. Não imprimir nem passar tokens como argumento CLI/JSON.

O token já está vinculado no ambiente atual; não é preciso duplicá-lo. O proxy de segredos precisa encaminhar Authorization exclusivamente ao host `graph.facebook.com`. Esta execução recebeu code 10 / subcode 2332002: ver [diagnóstico e ação humana](META_DIAGNOSIS.md). `ads_read` por si só não prova acesso à Ads Library. Não há scraping, follow de `paging.next` ou coleta privada. Credenciais em parâmetros de URL ou campos access_token/authorization são removidas antes de persistir evidências (URLs de snapshot podem contê-las). Erros remotos brutos são descartados; apenas HTTP, código, subcódigo e diagnóstico controlado são persistidos.

Referência oficial: https://developers.facebook.com/docs/marketing-api/reference/ads_archive/ . Campos, versão e categorias disponíveis dependem da política atual e da autorização/região. A referência estava bloqueada pelo proxy durante o diagnóstico; não confundir teste de autorização com validação de todo o esquema de sucesso.

## Catálogo público licenciado — funcionando sem credencial

`mode=catalog`, `config/catalog.json`: lista `free-programming-books`, mantida pela Ebook Foundation e colaboradores, https://github.com/EbookFoundation/free-programming-books . A licença CC BY 4.0 do catálogo foi lida diretamente do repositório; cópia integral em `docs/licenses/free-programming-books-CC-BY-4.0.txt`. A atribuição e a URL da licença acompanham cada registro exportado. Não há alterações no catálogo original; conversão de Markdown para registros, filtragem por termo/categoria e classificação são transformações do OfferLab.

Por padrão, `catalog_ref=latest` resolve automaticamente o HEAD oficial via Git HTTPS a cada ciclo, verifica se o hash da licença continua idêntico à CC BY 4.0 revisada e só então coleta as listas pt_PT e pt_BR. Uma mudança de licença interrompe essa fonte para revisão, sem impedir outras fontes. O orçamento de 4 operações cobre resolução Git, licença e dois arquivos. Cada evidência preserva o SHA imutável resolvido, permitindo rastrear atualizações upstream. Para reprodução, substitua latest por um SHA específico; a primeira revisão verificada foi `52e40c13216706ff4a0b63c3224c34abaa266e1d`. Git deve estar instalado para latest (já disponível neste runner). Isso acompanha o catálogo, não anúncios em tempo real.

O leitor busca somente o arquivo Markdown público, com limite de 2 MB, e extrai título, categoria, referência de autoria, idioma da lista e URL. Cada evidência contém URL, revisão, linha, citação e hash do arquivo. Não visita PDFs nem páginas vinculadas. A licença do catálogo **não licencia os livros**; não baixar, copiar ou revender produtos a partir dessa licença. `pt_PT` significa lista localizada, não mercado de venda confirmado; pt_BR aparece explicitamente separado. `price` e `market_country` permanecem nulos. São referências de recursos gratuitos/concorrência de conteúdo, não ofertas comerciais validadas, anúncios, vendas ou prova de demanda.

## Apple Search API — adaptador preparado, ainda não validado ao vivo

`mode=apple`, `config/apple.json`: API pública oficial https://itunes.apple.com/search , buscando `media=ebook`, `entity=ebook`, `country=PT`. Não exige token pelo contrato conhecido. Referência oficial: https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html . Rever condições atuais antes de habilitar uso contínuo. Acesso ao endpoint e à documentação foi bloqueado pelo proxy neste runner; somente testes com respostas controladas foram executados. **Não está habilitada em auto.json.**

O adaptador preserva título, autor, URL, preço/moeda quando fornecidos e storefront; não infere vendas, não baixa arte/capas, não segue páginas nem usa afiliados. Faz no máximo 20 GET/minuto por processo, sem retry automático. O limite de resultados não é paginação completa do catálogo. Para ativar após validar condições e acesso de rede, execute `python -m offerlab --config config/apple.json`; depois adicione `{"mode":"apple","report_dir":"reports/apple"}` a sources em uma cópia local de auto.json. Não habilite múltiplos processos para multiplicar limites. Nenhuma cobrança, compra ou cadastro é executado.

## Exportação autorizada — sem cadastro anúncio a anúncio

`mode=import` aceita um JSON obtido legitimamente de um provedor/exportação própria. Ideal para o processo que já produz exports: o agendador relê o arquivo e atualiza IDs. `authorized=true` é declaração auditável do operador, não prova automática de licença. Não processar exports com dados privados ou credenciais.

Configuração local (fora do Git se contiver informações pessoais):

```json
{"mode":"import","import_path":"data/export.json","countries":["PT"],"keywords":["curso"],"max_ads":1000,"database":"data/offerlab.sqlite3","report_dir":"reports/import"}
```

Formato do arquivo (placeholders, não dados coletados):

```json
{
  "authorized": true,
  "source_url": "https://seu-provedor.example/exportacao",
  "authorization_basis": "Descrição da licença/permissão aplicável",
  "records": [{"id":"ID-estavel", "text":"Texto original", "url":"https://origem.example/oferta", "advertiser":"Nome", "country":"PT", "language":"pt-PT"}]
}
```

`records` e proveniência são obrigatórios; `price`/`currency` são opcionais. Import limita arquivo a 2 MB, respeita max_ads, preserva record original e hash do export, e deduplica por ID dentro da fonte import. Use IDs prefixados por provedor para misturar exports. Termos/países da configuração são contexto, não filtro automático do export. O conector não acessa URLs importadas.

## Extensões e IA

Fontes implementam o contrato `ads()` de `interfaces.py` por compatibilidade com o primeiro MVP; registros agora têm record_kind para distinguir anúncios, catálogos e exports. Nova fonte exige autorização e proveniência verificável. Enriquecimento atual usa apenas metadados disponibilizados (título, categoria, idioma, preço quando disponível), sem visitar landing pages. Não há permissão comprovada para coleta automática dos sites referenciados; isso deve ser avaliado por fonte antes de adicionar enriquecimento de páginas. Não basta ignorar robots ou trocar user-agent para alegar autorização.

`AIClassifier` é apenas interface: nenhum SDK ou chamada paga, nenhuma credencial de IA necessária.
