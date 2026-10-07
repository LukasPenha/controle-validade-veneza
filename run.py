import os
from app import create_app
from waitress import serve

app = create_app()

def server_options(config):
    options = {}
    hops = config.get('TRUSTED_PROXIES', 0)
    if hops > 0:
        # No Render, a porta da aplicação é acessada pelo proxy da plataforma.
        # O Waitress precisa preservar estes dois cabeçalhos para o ProxyFix.
        options.update(trusted_proxy='*', trusted_proxy_count=hops,
                       trusted_proxy_headers={'x-forwarded-for', 'x-forwarded-proto'})
    return options

if __name__ == '__main__':
    # Define a porta (8000 é padrão)
    port = int(os.environ.get("PORT", 8000))
    print(f"Rodando na porta {port}...")
    
    # Inicia o servidor (Waitress é melhor para produção/estabilidade)
    serve(app, host='0.0.0.0', port=port, **server_options(app.config))
