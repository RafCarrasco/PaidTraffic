# Arquitetura mínima 0.2

CLI → configuração validada → orquestrador sequencial → fontes plugáveis → SQLite com upsert/histórico → classificação determinística → JSON/CSV/Markdown e resumo da execução.

Python 3.12+ e biblioteca padrão; Git HTTPS para resolver a revisão latest do catálogo oficial. Sem instalação de pacotes. Fontes: Meta oficial, catálogo CC BY 4.0, Apple Search API opcional, import autorizado e demo isolada. O nome legado ads() do protocolo não transforma metadados de catálogo em anúncios: record_kind é preservado no banco e nos relatórios.

`mode=auto` continua após falha de uma fonte e sinaliza estado parcial/exit 1; nunca injeta demo. Ranking agregado exclui fontes que falharam neste ciclo. Não mistura paths de relatório. max_requests e max_ads são por fonte, incluindo duplicatas e operações de consulta de revisão/licença no catálogo. Requests Apple são espaçados; não há retry automático.

SQLite: `ads` guarda último estado e score por fonte/ID; `observations` guarda raw, hash, termo/países consultados e timestamp; `runs` guarda status, contadores, diagnóstico e configuração não secreta. Migração aditiva acrescenta details/config sem descartar bancos 0.1. Anunciantes permanecem em raw, sem tabela separada. Cada registro é confirmado antes do próximo. Histórico preserva evidências anteriores a alterações.

Catálogo: latest resolve SHA por git ls-remote, valida hash da licença e extrai Markdown do commit fixado. Sem execução de código do catálogo. IDs são hash de idioma + URL; uma alteração de título não duplica o mesmo destino na mesma lista. Não consolida idiomas/edições ou ofertas diferentes por heurística semântica. Evidência referencia linha, citação, commit e hash do arquivo. Conversão e enriquecimento são locais: categoria, idioma, campos da fonte e classificação. Links de produtos não são visitados.

JSON/CSV têm substituição atômica por arquivo, sem transação conjunta; Markdown e latest-run também não são transação com SQLite. Um processo por pasta de relatórios; usar flock com cron. Estado após interrupção abrupta pode permanecer running e requer inspeção, não prova de sucesso. Configuração de segurança da plataforma não deve ser confundida com permissão de acesso à API Meta.

Operação contínua depende de computador/runner ligado; Codex não é hospedagem 24/7. Próximas expansões: fonte comercial autorizada e validada ao vivo, calibração humana das primeiras 20 ofertas, métricas de cobertura e critérios comerciais sustentados por evidência; depois UI, checkpoints/retries e IA com aprovação de orçamento.
