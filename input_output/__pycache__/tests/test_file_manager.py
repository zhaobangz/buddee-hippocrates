import os
import tempfile
import shutil
import importlib.util

# Load FileManager directly from tools/file_manager.py to avoid importing
# the top-level `tools` package which may have side-effects.
spec = importlib.util.spec_from_file_location('tools.file_manager', os.path.join(os.path.dirname(__file__), '..', 'tools', 'file_manager.py'))
fm_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm_mod)
FileManager = fm_mod.FileManager


def create_sample_files(base):
    files = [
        'a.txt', 'b.pdf', 'c.jpg', 'd.png', 'e.mp3', 'f.py', 'g.zip'
    ]
    for name in files:
        path = os.path.join(base, name)
        with open(path, 'w') as f:
            f.write('sample')
    return files


def test_organize_by_extension_dry_run():
    tmp = tempfile.mkdtemp()
    try:
        create_sample_files(tmp)
        fm = FileManager()
        actions = fm.organize_by_extension(tmp, dry_run=True)
        assert isinstance(actions, dict)
        assert len(actions) == 7
        # Ensure files remain in original location
        for name in os.listdir(tmp):
            assert name in ('a.txt','b.pdf','c.jpg','d.png','e.mp3','f.py','g.zip')
    finally:
        shutil.rmtree(tmp)


def test_organize_by_category_moves_files():
    tmp = tempfile.mkdtemp()
    try:
        create_sample_files(tmp)
        fm = FileManager()
        actions = fm.organize_by_category(tmp, dry_run=False)
        # After moving, original dir should be mostly empty
        remaining = [p for p in os.listdir(tmp) if os.path.isfile(os.path.join(tmp,p))]
        assert len(remaining) == 0
        # Check that target folders were created
        target_root = os.path.join(tmp, 'organized_by_category')
        assert os.path.exists(target_root)
        subdirs = os.listdir(target_root)
        assert any(subdirs)
    finally:
        shutil.rmtree(tmp)
