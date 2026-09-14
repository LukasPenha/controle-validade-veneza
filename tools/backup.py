"""Encrypted public-schema backup with restore rehearsal in disposable localhost DB.

Requires Docker, GnuPG, DATABASE_URL, BACKUP_PASSPHRASE and RESTORE_TEST_URL.
Never restores into the source or a remote database. No credential-bearing command logs.
"""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
from urllib.parse import urlsplit, unquote, parse_qs

PG_ENV = ('PGHOST','PGPORT','PGDATABASE','PGUSER','PGPASSWORD','PGSSLMODE')


def connection_env(url):
    parsed=urlsplit(url)
    if parsed.scheme not in ('postgresql','postgres') or not parsed.hostname or not parsed.path.strip('/'):
        raise ValueError('Conexão PostgreSQL inválida.')
    env=os.environ.copy()
    env.update(PGHOST=parsed.hostname,PGPORT=str(parsed.port or 5432),
        PGDATABASE=unquote(parsed.path.lstrip('/')),PGUSER=unquote(parsed.username or ''),
        PGPASSWORD=unquote(parsed.password or ''),
        PGSSLMODE=parse_qs(parsed.query).get('sslmode',['require'])[0])
    return env


def check_target(source, target):
    source_env, target_env=connection_env(source),connection_env(target)
    if target_env['PGHOST'] not in ('localhost','127.0.0.1') or target_env['PGDATABASE'] != 'veneza_restore':
        raise ValueError('A verificação exige banco local descartável chamado veneza_restore.')
    if (source_env['PGHOST'],source_env['PGPORT'],source_env['PGDATABASE']) == (target_env['PGHOST'],target_env['PGPORT'],target_env['PGDATABASE']):
        raise ValueError('Origem e destino não podem ser iguais.')
    return source_env,target_env


def run(args, env=None, input=None, label=None):
    result=subprocess.run(args,env=env,input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode:
        # stderr may include URLs, account names or row contents; never echo it into CI logs.
        detail = result.stderr.lower()
        reason = 'Confira conexão, senha, ferramentas e versões.'
        for marker, message in (
            (b'permission denied', 'Permissão de arquivo ou banco recusada.'),
            (b'password authentication failed', 'Autenticação do banco recusada.'),
            (b'connection refused', 'Servidor de banco indisponível.'),
            (b'server version mismatch', 'Cliente PostgreSQL incompatível com o servidor.'),
            (b'schema "public" already exists', 'O schema public já existe no destino.'),
            (b'no such file or directory', 'Arquivo ou diretório necessário ausente.'),
        ):
            if marker in detail:
                reason = message
                break
        raise RuntimeError(f'Falha em {label or Path(args[0]).name} (código {result.returncode}). {reason}')
    return result.stdout


def pg(folder,env,*args):
    command=['docker','run','--rm','--network','host']
    # pg_dump creates private files. Match the host user so GnuPG can read them.
    if hasattr(os,'getuid'):
        command.extend(['--user',f'{os.getuid()}:{os.getgid()}'])
    for key in PG_ENV:
        command.extend(['-e',key])
    command.extend(['-v',str(folder)+':/work','postgres:18',*args])
    return run(command,env=env,label=args[0])


def backup(output):
    source,target=check_target(os.environ['DATABASE_URL'],os.environ['RESTORE_TEST_URL'])
    passphrase=os.environ.get('BACKUP_PASSPHRASE','')
    if len(passphrase)<32:
        raise ValueError('BACKUP_PASSPHRASE exige pelo menos 32 caracteres aleatórios.')
    output=Path(output).resolve()
    if output.exists():
        raise ValueError('O arquivo de saída já existe; escolha outro nome.')
    with tempfile.TemporaryDirectory(prefix='veneza-backup-') as temporary:
        folder=Path(temporary).resolve()
        print('Etapa: gerar cópia PostgreSQL.',flush=True)
        # Read-only dump of the application schema. Auth/Storage belong to Supabase and are outside this backup.
        pg(folder,source,'pg_dump','--format=custom','--schema=public','--no-owner','--no-acl','--file=/work/data.dump')
        print('Etapa: criptografar e verificar arquivo.',flush=True)
        run(['gpg','--batch','--yes','--pinentry-mode','loopback','--passphrase-fd','0',
             '--symmetric','--cipher-algo','AES256','--output',str(folder/'backup.gpg'),str(folder/'data.dump')],
            input=passphrase.encode())
        run(['gpg','--batch','--yes','--pinentry-mode','loopback','--passphrase-fd','0',
             '--decrypt','--output',str(folder/'restore.dump'),str(folder/'backup.gpg')],input=passphrase.encode())
        def digest(path):
            with path.open('rb') as stream:
                return hashlib.file_digest(stream,'sha256').digest()
        if digest(folder/'data.dump') != digest(folder/'restore.dump'):
            raise RuntimeError('A cópia descriptografada não corresponde ao backup.')
        print('Etapa: restaurar no banco local descartável.',flush=True)
        count=pg(folder,target,'psql','-X','-tAc',"SELECT count(*) FROM pg_tables WHERE schemaname='public'").strip()
        if count != b'0':
            raise ValueError('O banco local de verificação precisa estar vazio; nada foi removido.')
        # A schema-filtered dump includes CREATE SCHEMA public. Fresh PostgreSQL
        # databases already contain it. RESTRICT refuses any remaining objects;
        # this runs only on the validated disposable local target, never source.
        pg(folder,target,'psql','-X','-v','ON_ERROR_STOP=1','-tAc',
           'DROP SCHEMA IF EXISTS public RESTRICT')
        pg(folder,target,'pg_restore','--exit-on-error','--no-owner','--no-acl','--dbname',target['PGDATABASE'],'/work/restore.dump')
        pg(folder,target,'psql','-X','-v','ON_ERROR_STOP=1','-tAc',
           'SELECT count(*) FROM public.usuario; SELECT count(*) FROM public.produto; SELECT count(*) FROM public.movimento; SELECT count(*) FROM public.audit_event; SELECT count(*) FROM public.exposure_proof;')
        output.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(folder/'backup.gpg',output)
    print('Backup criptografado criado e restauração local verificada.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:
        backup(args.output)
    except (ValueError,RuntimeError,KeyError,OSError) as error:
        print(str(error) if isinstance(error,(ValueError,RuntimeError)) else 'Configuração ou ferramenta de backup ausente.')
        raise SystemExit(1)
