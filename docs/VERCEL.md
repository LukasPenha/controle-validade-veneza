# Migração para Vercel

## Preparação

O Render permanece ativo durante a validação. Use a branch `codex/migracao-vercel`
para preparar a publicação; não desligue o Render antes de validar o novo endereço.
O projeto usa Flask, Python 3.13 e `wsgi.py`. A função roda em São Paulo (`gru1`),
próxima do banco Supabase existente. O build copia apenas `app/static` para
`public/static`, mantendo os endereços usados pelos templates.

## Configuração da conta

Use um plano Vercel permitido para uso comercial. Contratação e termos dependem
da decisão do titular da conta. Importe o repositório do GitHub e selecione Flask.

Configure apenas no ambiente Production:

- `DATABASE_URL`: conexão SSL com o transaction pooler do Supabase, porta 6543.
- `SECRET_KEY`: chave protegida do aplicativo.
- `PUBLIC_BASE_URL`: URL HTTPS definitiva do projeto na Vercel.
- `COOKIE_SECURE=true` e `SCHEDULER_ENABLED=false`.

O entrypoint força cookies seguros, confiança no proxy Vercel e limite por IP.
Não copie o banco de produção para ambientes Preview/Development. Para testar
alterações que gravam dados, configure um banco separado.

## Banco, tarefas e arquivos

O banco permanece no Supabase; não há migração de dados nem mudança de esquema
nesta mudança de hospedagem. A função não executa migrações ao iniciar. Futuras
migrações precisam ser aplicadas uma única vez antes de publicar código dependente.
O NullPool evita manter pools locais em cada instância; use o pooler do Supabase.
Backups continuam no GitHub Actions. O envio de e-mail continua pendente até
configurar o Gmail; não habilite `RUN_MAIL_JOBS` antes disso.

Fotos privadas continuam no banco, protegidas pelas permissões do aplicativo.
Na Vercel, cada foto enviada pode ter até 4 MiB (o limite total de requisição da
plataforma é 4,5 MB). A tela e a validação local avisam antes do envio. No Render,
o limite atual de 6 MiB permanece. Respostas de relatórios também devem respeitar
o limite da plataforma; teste um relatório representativo antes da troca.

## Conferência antes da troca

1. Confirmar o backup e a restauração de teste no GitHub.
2. Publicar na conta Vercel autorizada e conferir os logs.
3. Conferir HTTPS, login, estilos, scripts e câmera de código de barras.
4. Com um usuário autorizado, validar acessos por perfil, foto e relatório.
5. Atualizar o endereço divulgado e `PUBLIC_BASE_URL`; manter o Render disponível
   para retorno durante a transição. Não executar dois agendadores.

Referências: https://vercel.com/docs/frameworks/backend/flask e
https://vercel.com/docs/functions/limitations.
