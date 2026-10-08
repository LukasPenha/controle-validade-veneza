import importlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from sqlalchemy import inspect
from sqlalchemy.pool import NullPool
from werkzeug.datastructures import FileStorage
from app import create_app, db
from app.inventory import normalize_photo
from tools.build_vercel import build


class VercelTests(unittest.TestCase):
    def test_entrypoint_https_login_and_no_startup_migration(self):
        with patch.dict(os.environ, {
            'DATABASE_URL': 'sqlite://', 'SECRET_KEY': 'vercel-ci-only-' * 4,
            'SCHEDULER_ENABLED': 'true',
        }):
            module = importlib.import_module('wsgi')
        app = module.app
        self.assertFalse(app.config['SCHEDULER_ENABLED'])
        with app.app_context():
            self.assertIs(app.config['SQLALCHEMY_ENGINE_OPTIONS']['poolclass'], NullPool)
            self.assertEqual(inspect(db.engine).get_table_names(), [])
        response = app.test_client().get('/login', headers={'X-Forwarded-Proto': 'https'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Strict-Transport-Security', response.headers)
        self.assertIn(b'/static/css/workspace.css', response.data)
        self.assertIn('Secure', response.headers.get('Set-Cookie', ''))

    def test_build_only_copies_public_assets(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            root = Path(directory)
            (root / 'app/static/css').mkdir(parents=True)
            (root / 'app/static/css/site.css').write_text('body {}')
            (root / '.env').write_text('SECRET_KEY=not-public')
            build(root)
            self.assertEqual((root / 'public/static/css/site.css').read_text(), 'body {}')
            self.assertFalse((root / 'public/.env').exists())

    def test_upload_limit_matches_deployment(self):
        app = create_app({'TESTING': True, 'SECRET_KEY': 'upload-ci-only-' * 4,
                          'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                          'SCHEDULER_ENABLED': False, 'MAX_PHOTO_BYTES': 4 * 1024 * 1024})
        with app.app_context():
            with self.assertRaisesRegex(ValueError, '4 MB'):
                normalize_photo(FileStorage(stream=io.BytesIO(b'x' * (4 * 1024 * 1024 + 1)), filename='photo.png'))
            stream = io.BytesIO()
            Image.new('RGB', (80, 60), 'red').save(stream, format='PNG')
            stream.seek(0)
            self.assertTrue(normalize_photo(FileStorage(stream=stream, filename='photo.png')).startswith(b'\xff\xd8'))

