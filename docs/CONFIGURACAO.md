# Instalação V2 — banco totalmente novo

**Atualização de 12/09:** quem já instalou a V2 deve preservar o banco e usar `database/atualizar_20260912.sql`. Veja `docs/OPERACAO.md` para as novas funções, Gmail por HTTPS e backups. As instruções de banco vazio abaixo são apenas para a primeira instalação.

Esta versão substitui o catálogo interno por consulta externa e usa um esquema novo. Não execute os antigos scripts com DROP TABLE. O banco anterior não precisa ser acessado.

## 1. Preparar o banco

Crie um PostgreSQL vazio no provedor escolhido. Escolha uma forma de instalar as tabelas:

- Execute `database/novo_banco.sql` no editor SQL do **novo banco**. O arquivo contém uma transação, tabelas, restrições, índices e a versão das migrações. Não inclui usuários ou senhas.
- Ou configure `DATABASE_URL` localmente apontando para esse banco vazio e execute `python -m flask --app run init-db`. O comando recusa bancos que já tenham tabelas.

Não execute ambos: eles instalam o mesmo esquema. Para futuras versões, use `python -m flask --app run db upgrade`, seguindo as instruções da versão.

## 2. Criar o primeiro acesso

Os setores iniciais são incluídos na instalação. Se instalou o SQL anterior e a lista de setores ficou vazia, execute `database/cadastrar_setores.sql` no banco atual ou `python -m flask --app run db upgrade`. Isso preserva os registros existentes. No cadastro do encarregado, selecione a mesma loja e setor dos lotes que ele deve acompanhar; os IDs não devem ser presumidos.

Com as dependências instaladas e o `.env` apontando para o **novo banco**:

```powershell
.\.venv\Scripts\python -m flask --app run create-admin
```

O terminal pede o e-mail, a senha e sua confirmação, sem mostrar a senha. Use pelo menos 10 caracteres. O comando cria o primeiro gerente geral e os setores iniciais. Depois entre no site, cadastre lojas e usuários. Não há login ou senha padrão.

No Render Free, execute esse comando no seu computador usando a URL externa de conexão do novo PostgreSQL. Não envie essa URL com senha em conversas nem a publique no Git. No Render, configure a conexão apropriada em `DATABASE_URL`.

## 3. Configurar o Render

Instalação: `pip install -r requirements.txt`. Início: `gunicorn run:app --workers 1`.

| Variável em Environment | Valor |
| --- | --- |
| `DATABASE_URL` | Conexão do novo PostgreSQL |
| `SECRET_KEY` | Sua chave aleatória já salva, com pelo menos 32 caracteres |
| `PUBLIC_BASE_URL` | `https://controle-validade-veneza-1.onrender.com` |
| `COOKIE_SECURE` | `true` |
| `SCHEDULER_ENABLED` | `false` inicialmente |
| `PRODUCT_API_USER_AGENT` | `VenezaValidade/2.0 (seu-email-de-contato)` |

Não coloque a SECRET_KEY no código. Atualize código e conexão do banco no mesmo processo de publicação: a versão anterior não é compatível com este esquema.

## 4. Produtos e câmera

Em **Pesquisar produto**, digite nome/marca ou leia o código e toque em Pesquisar. Selecione o resultado e registre quantidade, validade, setor e lote. PLU interno é opcional.

A Open Food Facts não exige chave de API para consulta. O banco guarda seus lotes e um cache temporário; não existe catálogo editável. A busca ocorre ao clicar, não a cada letra. Há intervalo compartilhado entre consultas e cache de uma hora (cinco minutos para resultados vazios). Um código não encontrado não cria produto automaticamente. Veja `docs/APIS_PRODUTOS.md`.

A câmera exige HTTPS e permissão do navegador. O código de barras comum identifica o produto; validade e quantidade continuam sendo informadas pela equipe.

## 5. Central de alertas

- Avisos de lote registrado, mudança de status, proximidade (até 7 dias), vencimento hoje e vencido.
- Prioridades, filtros, paginação, leitura individual ou de todos os avisos atuais. Abrir a central não marca tudo como lido.
- Gerente e auxiliar veem sua loja; encarregado vê somente sua loja e setor. Gerentes geral e de trocas têm acesso global.
- Cada pessoa tem sua própria leitura. Verificações não duplicam o mesmo evento. Mudança de data ou etapa do vencimento leva o aviso anterior ao histórico.
- O botão de verificação manual atualiza a área do usuário, inclusive nos testes no Render Free.

Os 7 dias da central são fixos. A faixa dos e-mails é independente e configurável por usuário.

## 6. E-mails e recuperação de senha

No perfil, cada pessoa escolhe seu e-mail ou outro endereço, confirma o destinatário por link e define faixa de 0 a 365 dias, frequência diária ou semanal, dia e horário de São Paulo. E-mails exigem confirmação do endereço.

A fila mostra situação e tentativas no perfil. Permissões e configurações são revalidadas antes do envio. Falhas conhecidas permitem até três tentativas com espera crescente. Se a conexão cair sem confirmação do SMTP, fica **Não confirmado**, sem repetição automática que poderia duplicá-lo. Novos links de senha/confirmação podem ser solicitados após a espera de segurança.

No máximo um resumo por pessoa por dia. Sem produtos na faixa, fica **Sem produtos**. Se o serviço acordar depois do horário, pode enviar ainda naquele dia; resumos anteriores expiram. “Enviado” significa aceito pelo SMTP, sem garantia de chegada à caixa de entrada ou leitura.

Configure Gmail conforme `.env.example`: `smtp.gmail.com`, porta 587 com TLS, usuário remetente e [senha de app do Google](https://support.google.com/accounts/answer/185833?hl=pt-BR), quando disponível. Não publique credenciais.

**Render Free:** [a documentação](https://render.com/docs/free) informa suspensão por ociosidade e bloqueio de SMTP nas portas 25, 465 e 587. Use a integração Gmail por HTTPS e OAuth incluída em 12/09. O passo a passo e a execução externa da fila estão em `docs/OPERACAO.md`.

Em infraestrutura sempre ativa, escolha somente uma opção:

1. Um único processo com `SCHEDULER_ENABLED=true`: verifica validades a cada 5 minutos e e-mails a cada minuto.
2. Aplicação com `SCHEDULER_ENABLED=false` e agendador externo executando `python -m flask --app run process-notifications` a cada minuto, com o mesmo banco e variáveis. Esse comando processa avisos e e-mails.

O processo responsável também precisa ter acesso ao Gmail. Não há garantia de envio às 9h se ele estiver desligado ou dormindo.

## Validação

Testes em SQLite em memória cobrem instalação, autenticação/CSRF, escopo, tokens, agenda, fila, duplicidades e API com falhas simuladas. Interface verificada em 320, 390, 768 e 1440 pixels. Consulta real por código e nome verificada no ambiente de testes da Open Food Facts. Câmera física e Gmail real precisam de validação na implantação. O SQL PostgreSQL é gerado dos modelos e não foi executado no banco remoto do usuário.
