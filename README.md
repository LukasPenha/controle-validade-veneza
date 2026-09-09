# Controle de validade Veneza

Aplicação Flask para lotes por loja e setor, dashboard executivo, central de alertas e e-mails personalizados.

A V2 usa consulta gratuita à Open Food Facts por nome ou código de barras, com câmera. O catálogo interno foi removido. Quantidade, validade e lote são informados após selecionar o produto.

Esta versão requer **um banco novo**. Veja o [guia de configuração](docs/CONFIGURACAO.md), o [SQL de instalação](database/novo_banco.sql) e a [comparação das APIs](docs/APIS_PRODUTOS.md).

## Executar

1. Crie o ambiente: `python -m venv .venv`.
2. Instale: `.venv/Scripts/python -m pip install -r requirements.txt`.
3. Configure `.env` conforme `.env.example`. Localmente use `COOKIE_SECURE=false` para HTTP.
4. Instale: `.venv/Scripts/python -m flask --app run init-db` (ou execute o SQL, nunca ambos).
5. Crie o acesso: `.venv/Scripts/python -m flask --app run create-admin`.
6. Inicie: `.venv/Scripts/python run.py`.

Nunca publique `.env`. A SECRET_KEY deve ser aleatória, com pelo menos 32 caracteres. Gere com `python -c "import secrets; print(secrets.token_hex(32))"` e preserve entre reinícios.

## Testes

Execute `.venv/Scripts/python -m unittest discover -s tests -v`.

Usam banco em memória, sem acessar o `.env`. `tests/preview_app.py` usa dados fictícios e consulta simulada. `tests/ui_check.cjs` verifica a interface com Playwright.

## Produção

Use HTTPS, `COOKIE_SECURE=true` e PostgreSQL. Render Free bloqueia Gmail SMTP e pode dormir; os e-mails exigem outra infraestrutura ou futura integração por HTTPS. Leia o guia antes de habilitar agendamentos.

Dados: [Open Food Facts](https://world.openfoodfacts.org), sob [ODbL e termos de uso](https://world.openfoodfacts.org/terms-of-use). Cobertura não garantida; confira a embalagem.
