# Controle de validade Veneza

Aplicação Flask para produtos por loja e setor, dashboard executivo, central de alertas e e-mails personalizados.

A V2 usa consulta gratuita à Open Food Facts por nome ou código de barras, com câmera. O catálogo interno foi removido. Descrição, validade, código de barras e PLU opcional identificam o produto; quantidade e setor permitem acompanhar a rebaixa. Não é necessário registrar lote.

**Já usa a V2?** Siga a sequência de atualização no [guia de operação](docs/OPERACAO.md): a atualização de 13/09 acrescenta fotos privadas da exposição. Alternativamente, `flask --app run db upgrade` executa as migrações pendentes. Para instalações vazias, use o [SQL completo](database/novo_banco.sql).

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

Use HTTPS, `COOKIE_SECURE=true` e PostgreSQL. A versão inclui Gmail por HTTPS/OAuth, fotos da exposição, acompanhamento de rebaixa, auditoria e proteção de login. Os workflows de e-mail e backup vêm desativados até configurar as credenciais e variáveis conforme o [guia](docs/OPERACAO.md). SMTP continua disponível em hospedagens compatíveis.

Dados: [Open Food Facts](https://world.openfoodfacts.org), sob [ODbL e termos de uso](https://world.openfoodfacts.org/terms-of-use). Cobertura não garantida; confira a embalagem.
