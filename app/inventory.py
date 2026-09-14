"""Acompanhamento de validade, rebaixa e registro privado da exposição."""
import hashlib
import io
import warnings
from datetime import timedelta
from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from . import db
from .models import Produto, ExposureProof, AuditEvent, agora_brasil
from .notifications import scope, sync_expiry_notifications, add_event

inventory_bp = Blueprint('inventory', __name__)
MAX_UPLOAD = 6 * 1024 * 1024


def current_proof_exists():
    return db.session.query(ExposureProof.id).filter(
        ExposureProof.produto_id == Produto.id, ExposureProof.revision == Produto.exposure_revision).exists()


def visible_lots():
    return scope(Produto.query, Produto, current_user)


@inventory_bp.get('/validades-proximas')
@login_required
def upcoming():
    today = agora_brasil().date()
    days = request.args.get('dias', 30, type=int)
    mode = request.args.get('situacao', 'proximos')
    if not 0 <= days <= 365 or mode not in ('proximos', 'vencidos'):
        abort(400)
    term = request.args.get('busca', '').strip()[:100]
    query = visible_lots().filter(Produto.quantidade > 0, Produto.arquivado.is_(False))
    if term:
        query = query.filter(db.or_(Produto.nome_produto.ilike('%'+term+'%'),
                                   Produto.barcode == term, Produto.plu == term))
    expired_count = query.filter(Produto.validade < today).count()
    if mode == 'vencidos':
        query = query.filter(Produto.validade < today)
    else:
        query = query.filter(Produto.validade >= today, Produto.validade <= today + timedelta(days=days))
    products = query.order_by(Produto.validade, Produto.nome_produto, Produto.id).paginate(
        page=request.args.get('page', 1, type=int), per_page=30, error_out=False)
    return render_template('inventory/upcoming.html', products=products, today=today,
                           days=days, mode=mode, term=term, expired_count=expired_count)


def normalize_photo(upload):
    if not upload:
        raise ValueError('Tire ou selecione uma foto para registrar a exposição.')
    raw=upload.stream.read(MAX_UPLOAD+1)
    if not raw or len(raw)>MAX_UPLOAD:
        raise ValueError('Use uma foto de até 6 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('JPEG','PNG','WEBP') or source.width*source.height>25000000:
                    raise ValueError('Use foto JPEG, PNG ou WebP com até 25 megapixels.')
                source.load()
                photo=ImageOps.exif_transpose(source).convert('RGB')
            photo.thumbnail((1280,1280))
            for quality in (80,65,45):
                output=io.BytesIO()
                photo.save(output,format='JPEG',quality=quality,optimize=True)
                data=output.getvalue()
                if len(data)<=524288:
                    return data
        raise ValueError('A foto ficou muito grande. Fotografe de mais perto ou reduza a resolução.')
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise ValueError('Arquivo de imagem inválido. Use JPEG, PNG ou WebP.') from None


@inventory_bp.get('/lotes')
@inventory_bp.get('/produtos')
@login_required
def index():
    state=request.args.get('situacao','abertos')
    exposure=request.args.get('exposicao','todos')
    query=visible_lots()
    for param, column in [('store',Produto.loja_id),('sector',Produto.setor_id)]:
        value=request.args.get(param,0,type=int)
        if value:
            query=query.filter(column==value)
    if state=='abertos':
        query=query.filter(Produto.quantidade>0,Produto.arquivado.is_(False))
    elif state=='encerrados':
        query=query.filter(db.or_(Produto.quantidade==0,Produto.arquivado.is_(True)))
    elif state!='todos':
        abort(400)
    if exposure in ('pendente','registrada'):
        query=query.filter(Produto.status=='Em Rebaixa',Produto.validade>=agora_brasil().date())
        query=query.filter(current_proof_exists() if exposure=='registrada' else ~current_proof_exists())
    elif exposure!='todos':
        abort(400)
    term=request.args.get('busca','').strip()[:100]
    if term:
        query=query.filter(db.or_(Produto.nome_produto.ilike('%'+term+'%'),Produto.barcode==term))
    items=query.order_by(Produto.validade,Produto.id).paginate(page=request.args.get('page',1,type=int),per_page=20,error_out=False)
    proved={item.id for item in visible_lots().filter(Produto.id.in_([row.id for row in items.items]),current_proof_exists()).all()}
    return render_template('inventory/index.html',items=items,state=state,exposure=exposure,term=term,proved=proved,today=agora_brasil().date())


@inventory_bp.get('/lotes/<int:item_id>')
@inventory_bp.get('/produtos/<int:item_id>')
@login_required
def detail(item_id):
    item=visible_lots().filter_by(id=item_id).first_or_404()
    proofs=ExposureProof.query.filter_by(produto_id=item.id).order_by(ExposureProof.id.desc()).paginate(
        page=request.args.get('page',1,type=int),per_page=12,error_out=False)
    proved=ExposureProof.query.filter_by(produto_id=item.id,revision=item.exposure_revision).first() is not None
    events=AuditEvent.query.filter_by(produto_id=item.id).order_by(AuditEvent.id.desc()).limit(100).all()
    eligible=not item.arquivado and item.quantidade>0 and item.status=='Em Rebaixa' and item.validade>=agora_brasil().date()
    return render_template('inventory/detail.html',item=item,proofs=proofs,proved=proved,events=events,
        can_upload=current_user.role=='encarregado_setor' and eligible,
        can_close=current_user.role in ('gerente_geral','gerente','encarregado_setor') and not item.arquivado)


@inventory_bp.post('/lotes/<int:item_id>/exposicao')
@inventory_bp.post('/produtos/<int:item_id>/exposicao')
@login_required
def add_proof(item_id):
    if current_user.role!='encarregado_setor':
        abort(403)
    # Check scope before accepting/decoding the file; lock again before committing.
    item=visible_lots().filter_by(id=item_id).first_or_404()
    try:
        note=request.form.get('observacao','').strip()
        revision=request.form.get('revision',type=int)
        if not 3<=len(note)<=255:
            raise ValueError('Descreva onde o produto foi exposto (3 a 255 caracteres).')
        data=normalize_photo(request.files.get('foto'))
        item=visible_lots().filter_by(id=item_id).with_for_update().populate_existing().first_or_404()
        if item.arquivado or item.quantidade<=0 or item.status!='Em Rebaixa' or item.validade<agora_brasil().date():
            raise ValueError('A exposição exige produto ativo, dentro da validade e com status Em Rebaixa.')
        if revision!=item.exposure_revision:
            raise ValueError('O produto mudou. Atualize a página e confira os dados antes de enviar a foto.')
        digest=hashlib.sha256(data).hexdigest()
        if ExposureProof.query.filter_by(produto_id=item.id,revision=revision,image_sha=digest).first():
            flash('Esta foto já foi registrada para os dados atuais do produto.','info')
            return redirect(url_for('inventory.detail',item_id=item.id))
        proof=ExposureProof(produto_id=item.id,revision=revision,actor=current_user.username,note=note,
            quantidade=item.quantidade,validade=item.validade,image_sha=digest,image_data=data)
        db.session.add(proof)
        db.session.flush()
        db.session.add(AuditEvent(produto_id=item.id,loja_id=item.loja_id,setor_id=item.setor_id,
            actor=current_user.username,action='exposicao',changes={'exposicao':{'antes':'Pendente de registro','depois':note}}))
        add_event(item,f'exposure:{proof.id}','exposure','info',f'{item.nome_produto}: foto da exposição enviada por {current_user.nome_display}.')
        db.session.commit()
        flash('Exposição registrada com foto. O gerente já pode conferir.','success')
    except (ValueError,IntegrityError) as error:
        db.session.rollback()
        flash(str(error) if isinstance(error,ValueError) else 'Registro simultâneo detectado. Confira as fotos antes de repetir.','warning')
    return redirect(url_for('inventory.detail',item_id=item_id))


@inventory_bp.get('/exposicoes/<int:proof_id>/foto')
@login_required
def photo(proof_id):
    proof=ExposureProof.query.filter_by(id=proof_id).first_or_404()
    visible_lots().filter_by(id=proof.produto_id).first_or_404()
    response=send_file(io.BytesIO(proof.image_data),mimetype='image/jpeg',download_name=f'exposicao-{proof.id}.jpg',max_age=0)
    response.headers['Cache-Control']='private, no-store'
    return response


@inventory_bp.post('/lotes/<int:item_id>/encerrar')
@inventory_bp.post('/produtos/<int:item_id>/encerrar')
@login_required
def close(item_id):
    if current_user.role not in ('gerente_geral','gerente','encarregado_setor'):
        abort(403)
    item=visible_lots().filter_by(id=item_id).with_for_update().first_or_404()
    reason=request.form.get('motivo','').strip()
    if not 3<=len(reason)<=255:
        flash('Informe o motivo do encerramento (3 a 255 caracteres).','warning')
    elif current_user.role=='encarregado_setor' and not ExposureProof.query.filter_by(produto_id=item.id,revision=item.exposure_revision).first():
        flash('Registre a exposição com foto antes de encerrar. Para exceções, procure o gerente.','warning')
    elif not item.arquivado:
        item.arquivado=True
        db.session.add(AuditEvent(produto_id=item.id,loja_id=item.loja_id,setor_id=item.setor_id,actor=current_user.username,
            action='encerramento',changes={'motivo':{'antes':None,'depois':reason}}))
        db.session.commit()
        sync_expiry_notifications(user=current_user)
        flash('Acompanhamento encerrado. Fotos e histórico foram preservados.','success')
    return redirect(url_for('inventory.detail',item_id=item.id))


@inventory_bp.get('/historico')
@login_required
def history():
    events=scope(AuditEvent.query,AuditEvent,current_user).order_by(AuditEvent.id.desc()).paginate(
        page=request.args.get('page',1,type=int),per_page=30,error_out=False)
    return render_template('inventory/history.html',events=events)
