import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('audit_generator',Path(__file__).parents[1]/'scripts/generate_audit_html.py')
audit=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(audit)

class SharedViewerDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.project=self.root/'project';self.project.mkdir()
        self.registry=self.root/'registry.json'
        self.bridge=self.root/'asr_entry.py';self.bridge.write_text('pass')
        self.config={'service_script':str(self.root/'viewer_service.py'),'datasets':[{'type':'asr','assets_root':str(self.project),'adopted':True}]}
        self.write()
        self.args=argparse.Namespace(project_dir=self.project,original_dir=None,output=None,csv_dir=None,txt_dir=None,diarization_dir=None,audio_dir=None,manifest=None,title='Example')
        self.env=patch.dict('os.environ',{'MESSAGE_VIEWER_CONFIG':str(self.registry)});self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def write(self):self.registry.write_text(json.dumps(self.config))
    def test_registered_project_invokes_real_bridge_and_keeps_existing_ui(self):
        marker=self.root/'called.json';old=self.project/'reader.html';old.write_text('existing shared redirect')
        self.bridge.write_text('import json,sys\nfrom pathlib import Path\nPath('+repr(str(marker))+').write_text(json.dumps(sys.argv[1:]))\n')
        self.args.output=old
        self.assertTrue(audit.dispatch_registered_viewer(self.args))
        self.assertEqual(old.read_text(),'existing shared redirect')
        called=json.loads(marker.read_text());self.assertEqual(called[0],str(self.project));self.assertIn('--config',called);self.assertIn(str(old),called)
    def test_unregistered_or_absent_registry_preserves_standalone_route(self):
        self.args.project_dir=self.root/'other'
        with patch.object(audit.subprocess,'run') as run:
            self.assertFalse(audit.dispatch_registered_viewer(self.args));run.assert_not_called()
        self.registry.unlink();self.assertFalse(audit.dispatch_registered_viewer(self.args))
    def test_unavailable_bridge_and_failed_handoff_never_fall_back_to_old_ui(self):
        self.bridge.unlink()
        with self.assertRaises(RuntimeError):audit.dispatch_registered_viewer(self.args)
        self.bridge.write_text('raise SystemExit(7)')
        with self.assertRaises(subprocess.CalledProcessError):audit.dispatch_registered_viewer(self.args)
        self.config['datasets'][0]['adopted']=False;self.write()
        with self.assertRaises(RuntimeError):audit.dispatch_registered_viewer(self.args)
        self.config['datasets'][0]['adopted']='false';self.write()
        with self.assertRaises(RuntimeError):audit.dispatch_registered_viewer(self.args)
    def test_mismatched_original_directory_stops_before_dispatch(self):
        self.args.original_dir=self.root/'different'
        with patch.object(audit.subprocess,'run') as run:
            with self.assertRaises(RuntimeError):audit.dispatch_registered_viewer(self.args)
            run.assert_not_called()

if __name__=='__main__':unittest.main()
