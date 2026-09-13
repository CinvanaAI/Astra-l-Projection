import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('install_plugin', HERE / 'install_plugin.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_install_spaced_project_without_modifying_project(self):
        with tempfile.TemporaryDirectory(prefix='embodiment install ') as temporary:
            root = Path(temporary)
            project = root / 'My Project.uproject'
            original = b'{"FileVersion": 3}'
            project.write_bytes(original)
            preview = installer.install(project, True)
            self.assertTrue(preview['dry_run'])
            self.assertFalse((root / 'Plugins').exists())
            installer.install(project)
            self.assertEqual(original, project.read_bytes())
            self.assertTrue((root / 'Plugins/AgentEmbodiment/AgentEmbodiment.uplugin').is_file())
            with self.assertRaisesRegex(ValueError, 'already exists'):
                installer.install(project)
            self.assertEqual(original, project.read_bytes())

    def test_invalid_project_is_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / 'Invalid.uproject'
            project.write_text('not json', encoding='utf-8')
            with self.assertRaises(ValueError):
                installer.install(project)
            self.assertFalse((root / 'Plugins').exists())


if __name__ == '__main__':
    unittest.main()
