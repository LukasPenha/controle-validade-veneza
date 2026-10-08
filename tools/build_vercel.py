"""Publica somente os assets públicos; fotos privadas permanecem no banco."""
from pathlib import Path
from shutil import copytree


def build(root=None):
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    copytree(root / 'app' / 'static', root / 'public' / 'static', dirs_exist_ok=True)


if __name__ == '__main__':
    build()
