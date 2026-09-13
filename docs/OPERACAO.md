# Atualização de 12/09/2026

## Publicar sem perder dados

1. Preserve o banco atual. Faça uma cópia antes da atualização.
2. No SQL Editor do Supabase, execute **todo** o arquivo `database/atualizar_20260912.sql`. Aceita as versões `20260909_v2` e `20260909_setores`, inclui os setores que faltarem e não remove usuários/lotes. A transação será cancelada se houver erro. Não reaplique depois de concluída.
3. Alternativa ao SQL: com a conexão correta, execute `python -m flask --app run db upgrade`. Escolha apenas uma forma.
4. Publique o código atualizado no Render. Código novo exige banco atualizado; o arquivo `novo_banco.sql` é exclusivamente para instalações vazias.
5. Abra Lotes e baixas, confira os registros existentes e teste com um lote de teste identificado como tal.

O custo dos lotes antigos fica **não informado**. Não calculamos perdas históricas sem evidência. As permissões das tabelas do aplicativo para os papéis públicos `anon`/`authenticated` do Supabase são removidas; o Flask continua usando sua conexão privada de servidor. Nunca use a senha do banco no navegador.

## Rotina da equipe

- Registre o lote pela API ou pelo link **Produto não encontrado ou de fabricação própria**. Esse lançamento excepcional não cria catálogo e não publica dados na Open Food Facts.
- Informe o custo unitário quando conhecido. Não use zero para representar um valor desconhecido.
- Em **Lotes e baixas → Detalhes e baixas**, registre venda, descarte ou devolução. Quantidade não pode superar o saldo. Venda exige o preço recebido por unidade; devolução permite crédito confirmado opcional. Informe motivo/referência.
- Vendas e descartes parciais reduzem o saldo. Duplo envio da mesma baixa não repete a operação. Operações simultâneas são serializadas pelo bloqueio do lote no PostgreSQL.
- Quando o saldo chega a zero, o lote sai das listas ativas e dos próximos e-mails. Consulte-o em Encerrados. Arquivamento preserva os registros; lotes com saldo exigem baixa antes.
- Valores de movimentações são preservados. Atualizar o custo não muda baixas passadas. Alterações de saldo diretamente no formulário antigo ficam bloqueadas depois da primeira baixa.
- O histórico mostra usuário, data, campo e valores anteriores/novos dos lotes desde esta atualização. Não é uma reconstrução retroativa e não substitui auditoria do próprio administrador do banco.
- O dashboard soma perdas pelo custo das unidades descartadas, receita bruta das vendas e créditos confirmados das devoluções. Usa a data da baixa no ano escolhido e os filtros de loja/setor. Valores sem custo/crédito são sinalizados; receita não é lucro.

Não há estorno automático de baixa nesta versão. Confira destino e quantidade antes de confirmar; um ajuste incorreto precisa ser analisado preservando o histórico.

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
pg_restore --exit-on-error --no-owner --no-acl --dbname=BANCO_NOVO veneza.dump
```

Configure a conexão de restauração por variáveis de ambiente PostgreSQL; não escreva senha no comando. Após conferir usuários, lotes, movimentos e acesso, planeje a troca de `DATABASE_URL`. Sem a frase de criptografia, não é possível recuperar o arquivo. O teste automático é executado com dados fictícios no CI; a recuperação do seu banco real só estará validada após a primeira execução habilitada.

## Proteção de login

O banco compartilha um limite de 10 tentativas por conta por janela de 15 minutos, inclusive entre processos. A limitação responde de forma igual para contas existentes e inexistentes; e-mails são normalizados. A chave armazenada para a limitação é derivada com HMAC. O limite adicional por IP é opcional (`LOGIN_IP_LIMIT_ENABLED=true`) e só deve ser ligado quando `REMOTE_ADDR` representar corretamente o cliente: não confiamos em cabeçalhos encaminhados enviados pelo visitante.

## Testes

Execute `python -m unittest discover -s tests -p 'test_*.py'`. O CI também executa instalação/atualização no PostgreSQL, duas baixas concorrentes e backup/recuperação em bancos descartáveis. A câmera foi verificada por leitura simulada; teste também no aparelho real.
