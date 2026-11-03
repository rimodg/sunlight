"""Offline launchctl simulation. These tests do not prove native Mac operation."""
import argparse
import copy
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(ROOT / "scripts"))
import watch_service as service
from watch_engine import WatchEngine
from watch_journal import Journal


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.environment = self.root / "environment"
        self.environment.mkdir()
        self.pol = self.root / "reviewed-policy.json"
        self.pol.write_text('{"schema":"sunlight.watch-source-policy.v1","sources":[]}\n')
        self.args = argparse.Namespace(data_dir=str(self.root / "data"), environment=str(self.environment),
                                      launch_agents_dir=str(self.root / "agents"), label="org.sunlight.synthetic-test",
                                      interval=60, policy=str(self.pol), after_reboot=False)
        self.active = False
        self.commands = []

    def tearDown(self):
        self.temp.cleanup()

    def command(self, args, **kwargs):
        self.commands.append([str(a) for a in args])
        if args[0] == "launchctl":
            self.active = args[1] == "bootstrap"
        return subprocess.CompletedProcess(args, 0, "", "")

    def simulation(self):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(service, "pinned", return_value={"python": service.PIN}))
        stack.enter_context(patch.object(service, "run", side_effect=self.command))
        stack.enter_context(patch.object(service, "boot_epoch", return_value=123))
        stack.enter_context(patch.object(service, "loaded", side_effect=lambda label: (self.active, "state = running\npid = 4321")))
        return stack

    def test_install_idempotent_and_uninstall_keeps_every_data_file(self):
        with self.simulation():
            first = service.install(self.args)
            data = Path(self.args.data_dir)
            journal = Journal(data / "journal.sqlite3"); journal.close()
            original = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in data.rglob('*') if p.is_file()}
            plist = Path(self.args.launch_agents_dir) / (self.args.label + '.plist')
            initial_plist = (plist.read_bytes(), plist.stat().st_mtime_ns)
            second = service.install(self.args)
            self.assertEqual(second["created_or_changed"], [])
            self.assertEqual(len([c for c in self.commands if c[1] == 'bootstrap']), 1)
            for p, expected in original.items():
                self.assertEqual((p.read_bytes(), p.stat().st_mtime_ns), expected)
            self.assertEqual((plist.read_bytes(), plist.stat().st_mtime_ns), initial_plist)
            definition = plistlib.loads(plist.read_bytes())
            self.assertTrue(definition["RunAtLoad"])
            self.assertEqual(definition["ProgramArguments"][0], str(self.environment / 'bin/python'))
            self.assertTrue(definition["StandardErrorPath"].startswith(str(data)))
            service.uninstall(self.args)
            self.assertFalse(plist.exists())
            for p, expected in original.items():
                self.assertEqual(p.read_bytes(), expected[0])
            self.assertTrue(self.environment.exists())
            self.assertEqual(service.uninstall(self.args)["removed"], [])

    def test_missing_or_unpinned_environment_does_not_load(self):
        with patch.object(service, 'pinned', side_effect=ValueError('Pinned environment refused')), patch.object(service, 'loaded') as loaded:
            with self.assertRaises(ValueError):
                service.install(self.args)
            loaded.assert_not_called()
        self.assertFalse((Path(self.args.launch_agents_dir) / (self.args.label+'.plist')).exists())

    def test_foreign_plist_is_preserved(self):
        agents = Path(self.args.launch_agents_dir); agents.mkdir()
        target = agents / (self.args.label+'.plist')
        target.write_bytes(plistlib.dumps({'Label':self.args.label,'ProgramArguments':['/foreign/worker']}))
        before = target.read_bytes()
        with self.simulation(), self.assertRaises(ValueError):
            service.install(self.args)
        self.assertEqual(target.read_bytes(), before)

    def test_data_inside_checkout_and_symlink_refused(self):
        with self.assertRaises(ValueError):
            service.external(ROOT / 'do-not-create-runtime')
        link = self.root/'data-link'; link.symlink_to(self.environment, target_is_directory=True)
        with self.assertRaises(ValueError):
            service.external(link)

    def test_pin_requires_every_exact_locked_distribution(self):
        info = {'python':service.PIN,'prefix':str(self.environment),'packages':{}}
        with patch.object(service,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(info),'')):
            with self.assertRaises(ValueError):
                service.pinned(self.environment/'bin/python',environment=self.environment)
        info['python']='3.12.13'
        with patch.object(service,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(info),'')):
            with self.assertRaises(ValueError):
                service.pinned('/synthetic/python')

    def test_verify_requires_running_recent_completion_and_new_boot(self):
        with self.simulation():
            service.install(self.args)
            j = Journal(Path(self.args.data_dir)/'journal.sqlite3')
            try:
                WatchEngine(j,json.loads(self.pol.read_text())).tick()
            finally:
                j.close()
            self.assertTrue(service.verify(self.args)['running'])
            self.args.after_reboot = True
            with self.assertRaises(ValueError):
                service.verify(self.args)
            with patch.object(service,'boot_epoch',return_value=124):
                self.assertTrue(service.verify(self.args)['after_reboot_verified'])
            self.active = False
            with self.assertRaises(ValueError):
                service.verify(self.args)

    def test_source_drift_requires_reinstall(self):
        with self.simulation():
            service.install(self.args)
            path = Path(self.args.data_dir)/'source-policy.json'
            path.write_text(self.pol.read_text()+' ')
            with self.assertRaises(ValueError):
                service.verify(self.args)

    def test_linux_refuses_before_creating_data(self):
        if sys.platform == 'darwin':
            self.skipTest('Host-specific refusal test is for non-Mac builders')
        data = self.root/'never-created'
        run = subprocess.run([str(ROOT/'scripts/install-watch'),'--python',sys.executable,'--data-dir',str(data),
                              '--policy',str(self.pol)],capture_output=True,text=True)
        self.assertEqual(run.returncode,2)
        self.assertIn('macOS launchd is required',run.stderr)
        self.assertFalse(data.exists())

    def test_failed_environment_creation_is_preserved_without_loading_agent(self):
        self.args.environment=str(self.root/'new-runtime')
        self.args._created=[]
        def command(args, **kwargs):
            if 'venv' in args:
                Path(args[-1]).mkdir()
                return subprocess.CompletedProcess(args,0,'','')
            if 'pip' in args:
                raise subprocess.CalledProcessError(1,args)
            self.fail('Service command must not run after dependency failure')
        with patch.object(service,'run',side_effect=command), patch.object(service,'pinned'), patch.object(service,'loaded') as loaded:
            with self.assertRaises(subprocess.CalledProcessError):
                service.install(self.args)
            loaded.assert_not_called()
        self.assertTrue(Path(self.args.environment).exists())
        self.assertIn(self.args.environment,self.args._created)
        self.assertFalse((Path(self.args.launch_agents_dir)/(self.args.label+'.plist')).exists())


if __name__ == '__main__':
    unittest.main()
