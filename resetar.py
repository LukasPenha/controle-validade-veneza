from app import create_app, db
from app.models import Usuario

app = create_app()

with app.app_context():
    # -----------------------------------------------------------------
    # ONDE ALTERAR:
    usuario_alvo = "duylio@superveneza.com.br"  # <--- Coloque seu usuário/e-mail aqui
    nova_senha   = "123456"                # <--- Coloque a nova senha desejada aqui
    # -----------------------------------------------------------------

    user = Usuario.query.filter_by(username=usuario_alvo).first()
    
    if user:
        user.set_password(nova_senha)
        db.session.commit()
        print(f"\n✅ SUCESSO: A senha do usuário '{usuario_alvo}' foi alterada para '{nova_senha}'!\n")
    else:
        print(f"\n❌ ERRO: O usuário '{usuario_alvo}' não foi encontrado no banco de dados.\n")
