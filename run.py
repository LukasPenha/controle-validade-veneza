import os
from app import create_app
from waitress import serve

app = create_app()

if __name__ == '__main__':
    # Define a porta (8000 é padrão)
    port = int(os.environ.get("PORT", 8000))
    print(f"Rodando na porta {port}...")
    
    # Inicia o servidor (Waitress é melhor para produção/estabilidade)
    serve(app, host='0.0.0.0', port=port)