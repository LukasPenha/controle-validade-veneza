# Publicação, Gmail e alertas

## Antes de publicar esta versão

Esta alteração adiciona três tabelas: `email_preference`, `email_token` e
`email_delivery`. Não modifica as colunas de produtos, usuários, lojas ou setores.
As sessões antigas precisarão de novo login; trocas de senha invalidam sessões anteriores.

1. Mantenha um backup do banco antes da atualização.
2. Configure `SCHEDULER_ENABLED=false` durante a migração.
3. Instale as dependências de `requirements.txt`.
4. No ambiente que acessa o banco existente, execute:

   ```sh
   flask --app run db current
   flask --app run db upgrade
   ```

   O repositório não tinha revisões de banco versionadas. A nova revisão parte da
   instalação existente. Se `db current` indicar uma revisão desconhecida, recupere
   os arquivos antigos de migração antes de continuar; não substitua o histórico
   com `stamp`. Em um banco novo, crie o esquema inicial antes dessa migração.
5. Reinicie o serviço com a nova versão.

A migração foi testada em uma cópia local SQLite com as tabelas originais e um
usuário existente. Não foi executada no banco hospedado.

## Render gratuito para demonstração

Configure `PUBLIC_BASE_URL=https://controle-validade-veneza-1.onrender.com` e
`COOKIE_SECURE=true`. Deixe `SCHEDULER_ENABLED=false` e `MAIL_SERVER` vazio para
testar dashboard, busca, câmera e preferências sem enviar mensagens.

O [Render Free](https://render.com/docs/free) bloqueia saída nas portas SMTP
25, 465 e 587 e pode suspender o serviço após 15 minutos sem tráfego. Por isso,
Gmail SMTP e entregas pontuais não funcionam nesse plano. A fila pode ser consultada
nos testes locais; nenhuma mensagem real é enviada pelos testes.

## Gmail em hospedagem compatível

Na conta Google do remetente, ative a verificação em duas etapas e gere uma
[senha de app](https://support.google.com/accounts/answer/185833?hl=pt-BR).
Use essa senha em `MAIL_PASSWORD`, nunca a senha normal da conta.

No Render, abra **Environment** do serviço e cadastre os valores de `.env.example`:

| Variável | Valor |
|---|---|
| PUBLIC_BASE_URL | https://controle-validade-veneza-1.onrender.com |
| MAIL_SERVER | smtp.gmail.com |
| MAIL_PORT | 587 |
| MAIL_USE_TLS | true |
| MAIL_USE_SSL | false |
| MAIL_USERNAME | E-mail Gmail do remetente |
| MAIL_PASSWORD | Senha de app do Google |
| MAIL_DEFAULT_SENDER | Mesmo e-mail do remetente |

Não coloque credenciais no código nem envie senhas em mensagens.

## Execução automática

Para uma primeira instalação sempre ativa, execute um único processo (`python run.py`)
com `SCHEDULER_ENABLED=true`. O processamento de e-mail ocorre a cada minuto,
e a verificação interna de notificações continua às 8h. Não use vários workers
com o agendador habilitado em todos.

Alternativamente, mantenha o agendador desabilitado no servidor web e execute
`flask --app run send-emails` a cada minuto em um único executor externo sempre ativo.
Esse comando processa apenas os e-mails; a tarefa interna das 8h precisará de
agendamento separado nessa arquitetura.

O fuso é America/Sao_Paulo. O envio fica elegível no minuto escolhido, diário ou
no dia semanal selecionado. Se o serviço retornar mais tarde no mesmo dia,
processará o envio atrasado. Dias anteriores não são repostos. Mudanças de horário
após um envio passam a valer no próximo dia elegível.

Cada usuário recebe no máximo um resumo agendado por data. Sem produtos, o envio
é marcado como ignorado. Falhas comuns são tentadas até três vezes. Se o processo
parar durante um envio, o registro fica `sending` para conferência do operador;
não é reenviado automaticamente porque o SMTP pode já ter aceitado a mensagem.
Não há garantia de entrega exatamente uma vez em falhas de rede após aceitação SMTP.

## Preferências e recuperação

Em **Meu perfil e alertas**, cada usuário escolhe o destino, confirma o endereço,
habilita os alertas, informa faixa de 0 a 365 dias e frequência/horário. Para trocar
o endereço, precisa da senha atual e de uma nova confirmação. Encarregados recebem
apenas sua loja e setor; gerente e auxiliar apenas sua loja; gerente geral e gerente
de trocas têm visão global. O escopo é conferido novamente ao enviar.

Os links de confirmação e senha expiram em 30 minutos e são de uso único. Abrir um
link não o consome: é necessário enviar o formulário. Recuperação usa o e-mail
armazenado em `username`; contas cujo usuário não é e-mail precisam ter o cadastro
corrigido pelo gerente geral. O destino dos alertas não altera a identidade da conta.

## Dashboard e catálogo

O gráfico mensal soma unidades e informa registros. Ano e mês filtram o calendário
e sua tabela. Os indicadores de vencidos e próximos vencimentos consideram todas
as datas, respeitando loja e setor. Rankings agrupam pelo PLU e mostram as cinco
maiores somas. Produtos excluídos deixam de aparecer; o sistema não mede perdas
confirmadas ou vendas. Datas vencidas são anteriores a hoje, e a faixa futura inclui hoje.

Em **Datas Curtas**, digite nome, PLU ou código, ou toque em **Ler código com a câmera**.
O navegador solicita permissão e tenta usar a câmera traseira. Ao ler, selecione o
produto e informe quantidade e validade. Produtos ausentes precisam ser cadastrados
no catálogo. O leitor não descobre automaticamente a validade do lote.

API autenticada pela sessão existente:

- `GET /api/catalogo?term=arroz`: busca nome, PLU e três códigos cadastrados (até 20 resultados).
- `GET /api/buscar-produto/0789000000012`: correspondência exata, preservando zeros iniciais.
- `GET /api/buscar-catalogo` e `/api/buscar-produtos-catalogo`: aliases da busca.

Nenhuma base comercial externa está integrada. Os dados vêm do catálogo Veneza.
A câmera exige HTTPS (ou localhost), permissão do navegador e um dispositivo compatível.

## Testar sem produção

`python -m unittest discover -s tests -v` testa segurança, preferências, calendário,
escopo dos alertas, recuperação, API e migração com dados isolados.

Com Playwright e Chrome disponíveis, `node tests/ui_check.cjs` verifica a interface
contra a prévia local já iniciada. Usa câmera simulada; a leitura óptica em Android
e iPhone deve ser validada com o telefone real.

`python tests/preview_app.py` abre a prévia em `http://127.0.0.1:8011`, com banco em
memória e envio desabilitado. Usuários fictícios: `demo`, `setor`, `gerente`, `auxiliar`,
`trocas`. Senha de demonstração: `Demo-veneza-2026`. Nunca publique esse servidor de prévia.
