# Operação do Controle de Validade Veneza

## Atualizar o banco existente

1. Faça um backup antes de atualizar.
2. Confira a versão com `SELECT version_num FROM alembic_version;` no SQL Editor do Supabase.
3. Se estiver em `20260909_v2` ou `20260909_setores`, execute primeiro todo o arquivo `database/atualizar_20260912.sql`.
4. Se estiver em `20260912_operacao`, execute todo o arquivo `database/atualizar_20260913.sql`. Se já estiver em `20260913_exposicao`, não reaplique.
5. Alternativa no servidor: `flask --app run db upgrade` executa as migrações pendentes. Para banco totalmente vazio, use apenas `database/novo_banco.sql`.
6. Publique a nova versão no Render depois de atualizar o banco.

As atualizações preservam usuários e produtos. Campos financeiros e de lote antigos ficam apenas por compatibilidade; não são solicitados no cadastro. As fotos são privadas: os papéis públicos da API do Supabase não têm acesso à tabela. O aplicativo acessa pelo servidor.

## Produtos, validade e exposição

O menu **Validades próximas** lista os produtos ativos em ordem crescente de dias restantes. O padrão é até 30 dias, com filtro de 0 a 365 dias e atalhos de 10, 15 e 30. Vermelho indica 0–10 dias; amarelo, 11–15; verde, 16–30; acima de 30, cinza. Vencidos têm uma aba própria. Busca por descrição, código ou PLU e permissões por loja/setor se aplicam à listagem. Esta tela não depende dos relatórios nem exige nova migração além da atualização de fotos descrita acima.

- Pesquise pela descrição ou código de barras, inclusive pela câmera. Se não encontrar, use o registro manual.
- Cadastre a descrição do produto, validade, código de barras quando houver e PLU opcional. Informe quantidade, loja e setor; para encarregados, loja e setor vêm do usuário. Não é necessário número de lote. Validades diferentes devem ser registradas separadamente.
- O gerente coloca o produto em **Em Rebaixa**. Em **Produtos e exposição → Detalhes e fotos**, o encarregado da mesma loja e setor envia a foto e descreve onde expôs o produto.
- O gerente confere as fotos pelo mesmo menu. O dashboard geral mostra produtos com e sem foto atual, respeitando os filtros de loja e setor.
- Alterar quantidade, validade, status, loja ou setor exige nova foto. Fotos anteriores ficam no histórico. Produtos vencidos não aceitam novas fotos de exposição.
- Para encerrar o acompanhamento, informe um motivo. O encarregado precisa ter uma foto atual; o gerente pode encerrar exceções com justificativa. Encerrados deixam os alertas e permanecem consultáveis.
- A data exibida é a de envio. Uma foto serve como evidência para conferência humana, sem garantir automaticamente a exposição ou sua duração.

As imagens aceitas são JPEG, PNG e WebP até 6 MB e 25 megapixels; são convertidas para JPEG de até 1280 pixels e 512 KiB, sem metadados EXIF. Ficam no banco e entram no backup criptografado quando este estiver ativado. Acompanhe o consumo de espaço do banco; o histórico de fotos cresce com o uso. Não há novas credenciais de armazenamento para configurar.

## Gmail por HTTPS — configuração inicial

Esta integração envia pelo seu Gmail usando a API oficial em HTTPS; não usa as portas SMTP bloqueadas no Render Free. É preciso autorizar **a conta remetente**, não cada destinatário. Fonte: [envio pela Gmail API](https://developers.google.com/workspace/gmail/api/guides/sending).

1. Abra o [Google Cloud Console](https://console.cloud.google.com/), crie/selecione um projeto e habilite **Gmail API**.
2. Configure o consentimento OAuth no Google Auth Platform, informando nome do aplicativo e contato. Para testes, adicione seu Gmail remetente como usuário de teste.
3. Crie um cliente OAuth do tipo **Aplicativo da Web**. Para obter o token inicial pelo Playground, cadastre exatamente `https://developers.google.com/oauthplayground` como URI de redirecionamento autorizada.
4. Abra o [OAuth Playground oficial](https://developers.google.com/oauthplayground/). Na engrenagem, marque **Use your own OAuth credentials** e informe o Client ID e Client Secret desse cliente.
5. Solicite somente o escopo `https://www.googleapis.com/auth/gmail.send`, com acesso offline. Autorize com a conta que enviará os e-mails. Troque o código por tokens em **Exchange authorization code for tokens** e guarde o Refresh Token em um gerenciador de senhas.
6. No Render, em Environment, configure:

| Nome | Conteúdo |
| --- | --- |
| `MAIL_TRANSPORT` | `gmail_api` |
| `MAIL_DEFAULT_SENDER` | O Gmail que você autorizou |
| `GMAIL_CLIENT_ID` | Client ID do seu projeto |
| `GMAIL_CLIENT_SECRET` | Client Secret |
| `GMAIL_REFRESH_TOKEN` | Refresh Token |
| `PUBLIC_BASE_URL` | `https://controle-validade-veneza-1.onrender.com` |
| `SCHEDULER_ENABLED` | `false` se usar a execução externa abaixo |

Não coloque esses valores no Git ou em conversas. `MAIL_PASSWORD` e senha de app não são usados no modo `gmail_api`. Se optar por SMTP em outro plano, selecione explicitamente `MAIL_TRANSPORT=smtp`.

**Para sair do teste:** o Google informa que tokens de aplicativos externos em modo Testing podem expirar em 7 dias para esse escopo. Planeje a configuração de produção e eventuais requisitos de verificação com sua conta antes de depender do envio. Tokens também podem ser revogados. [Documentação OAuth](https://developers.google.com/identity/protocols/oauth2). O Playground usando credenciais próprias é para obter/testar a autorização inicial; não foi realizada autorização em seu nome.

## Agendamentos no GitHub

Os workflows de produção vêm **desativados por condição**, mesmo após o push. Eles só executam quando as variáveis abaixo forem habilitadas. Os testes usam apenas dados fictícios.

No seu repositório, abra **Settings → Secrets and variables → Actions**.

Crie os **Secrets** `DATABASE_URL` (conexão externa do banco), `SECRET_KEY` (a mesma do Render), `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` e `GMAIL_REFRESH_TOKEN`. Prefira a conexão direta ou o pooler em modo sessão para compatibilidade com os jobs; mantenha TLS.

Crie as **Variables** `PUBLIC_BASE_URL`, `MAIL_DEFAULT_SENDER` e, depois de concluir a configuração, `RUN_MAIL_JOBS=true`.

Na aba Actions, execute **Processar notificações → Run workflow** uma vez. Ele processa validades e e-mails pendentes. Depois use seu perfil para solicitar a confirmação do e-mail, confirme o link e programe o resumo.

O workflow tenta executar a cada 5 minutos, nos minutos 2, 7, 12 etc. Não depende de o site Render estar acordado. Horário configurado no perfil é o início da janela de envio; às 9h o processamento tende a ocorrer a partir de 9h02. O GitHub pode atrasar ou não executar agendamentos sob carga e desativa agendamentos em repositórios públicos após inatividade prolongada. Não promete horário exato nem disponibilidade contínua. Consulte [eventos agendados](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) e acompanhe limites de minutos da sua conta. Para operação com SLA, use um worker sempre ativo com execução a cada minuto.

Mantenha apenas um responsável pelos agendamentos: workflow ou scheduler interno. Envios interrompidos ficam como **Não confirmado**, sem repetição cega. Verifique no perfil o histórico de aceitação, falhas e fila. Não foi enviado e-mail real durante os testes desta alteração.

## Backups com teste de recuperação

O workflow **Backup criptografado e restauração** usa `pg_dump` para copiar o schema `public`, criptografa com GnuPG/AES-256 e verifica a descriptografia. Em seguida restaura a cópia em um PostgreSQL temporário, local ao job, e verifica tabelas essenciais. Apenas o arquivo criptografado é publicado como artefato, por 7 dias. O banco de origem é somente lido. Auth, Storage, arquivos, variáveis do Render e objetos fora de `public` não fazem parte dessa cópia.

Para habilitar:

1. Gere uma frase aleatória forte de pelo menos 32 caracteres, guarde uma cópia fora do GitHub e configure o Secret `BACKUP_PASSPHRASE`.
2. Confirme o Secret `DATABASE_URL` e configure a Variable `BACKUPS_ENABLED=true`.
3. Execute o workflow manualmente e verifique o resultado. Depois baixe o artefato de backup e guarde uma cópia externa protegida. A agenda diária é 06h23 UTC (03h23 em São Paulo), sujeita aos atrasos do GitHub.
4. Se a primeira execução falhar, o backup de produção ainda não está validado. Confira Actions; não considere apenas a existência do workflow como prova de proteção.

O cliente PostgreSQL utilizado é versão 18 e deve ser da mesma versão principal ou mais recente que o servidor. O teste local usa PostgreSQL 18. Consulte [pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html) e [pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html).

Para recuperação real, baixe o artefato, descriptografe com GnuPG (senha solicitada interativamente) e restaure **em um novo banco vazio**, nunca sobre o banco ativo sem validação:

```text
gpg --output veneza.dump --decrypt veneza.dump.gpg
psql --dbname=BANCO_NOVO -X -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public RESTRICT"
pg_restore --exit-on-error --no-owner --no-acl --dbname=BANCO_NOVO veneza.dump
```

O dump inclui a criação do schema `public`. O comando anterior remove somente esse schema vazio no **banco novo de recuperação**; `RESTRICT` recusa a operação se houver objetos dependentes. Se houver erro, pare e confira o destino. Não use `CASCADE` nem execute esse preparo no banco de produção.

Configure a conexão de restauração por variáveis de ambiente PostgreSQL; não escreva senha no comando. Após conferir usuários, produtos, fotos e acesso, planeje a troca de `DATABASE_URL`. Sem a frase de criptografia, não é possível recuperar o arquivo. O teste automático é executado com dados fictícios no CI; a recuperação do seu banco real só estará validada após a primeira execução habilitada.

## Proteção de login

O banco compartilha um limite de 10 tentativas por conta por janela de 15 minutos, inclusive entre processos. A limitação responde de forma igual para contas existentes e inexistentes; e-mails são normalizados. A chave armazenada para a limitação é derivada com HMAC. O limite adicional por IP é opcional (`LOGIN_IP_LIMIT_ENABLED=true`) e só deve ser ligado quando `REMOTE_ADDR` representar corretamente o cliente: não confiamos em cabeçalhos encaminhados enviados pelo visitante.

## Testes

Execute `python -m unittest discover -s tests -p 'test_*.py'`. O CI também executa instalação/atualização no PostgreSQL, dois envios simultâneos da mesma foto e backup/recuperação em bancos descartáveis. A câmera foi verificada por leitura simulada; teste também no aparelho real.
