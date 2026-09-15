import json,os,sys,tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from nv_runtime import hyperframes_command
from nv_core import read,write
from synthesize_full import _read_explicit_credentials,TTSUserError

class Portability(unittest.TestCase):
    def test_windows_shim_resolves_to_node_entry(self):
        with tempfile.TemporaryDirectory(prefix='中文 spaces ') as t:
            root=Path(t);pkg=root/'node_modules/hyperframes';pkg.mkdir(parents=True)
            (pkg/'bin').mkdir();(pkg/'bin/cli.mjs').write_text('',encoding='utf-8')
            (pkg/'package.json').write_text(json.dumps({'name':'hyperframes','version':'0.8.35','bin':{'hyperframes':'bin/cli.mjs'}}),encoding='utf-8')
            with patch('nv_runtime.executable',return_value='C:/Program Files/nodejs/node.exe'):
                cmd=hyperframes_command(root,root/'node_modules/.bin/hyperframes.cmd')
                self.assertEqual(len(cmd),2);self.assertEqual(cmd[1],str((pkg/'bin/cli.mjs').resolve()));self.assertTrue(cmd[0].endswith('node.exe'))
    def test_utf8_crlf_and_space_path(self):
        with tempfile.TemporaryDirectory(prefix='中文 spaces ') as t:
            p=Path(t)/'中文.json';p.write_bytes('{\r\n"text":"中文"\r\n}'.encode('utf-8'))
            self.assertEqual(read(p)['text'],'中文');write(p,{'text':'汉字'});self.assertIn('汉字',p.read_bytes().decode('utf-8'))
    def test_windows_file_credentials_fail_with_action(self):
        unused=Path('unused')
        with patch('synthesize_full.os.name','nt'):
            with self.assertRaisesRegex(TTSUserError,'access_token_env'):_read_explicit_credentials(unused,'key')
    def test_missing_dependencies_degrade(self):
        from doctor import inspect
        with tempfile.TemporaryDirectory() as t, patch('doctor.executable',side_effect=ValueError('missing dependency')), patch('doctor.hyperframes_command',side_effect=ValueError('missing HyperFrames')):
            report=inspect(Path(t))
            self.assertTrue(report['capabilities']['build'])
            self.assertFalse(report['capabilities']['render_environment'])
            self.assertIsNone(report['checks']['browser']['ok'])
    def test_font_change_invalidates_build(self):
        import shutil
        from build_storyboard import build
        from check_project import check
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'video'
            shutil.copytree(Path(__file__).resolve().parents[1]/'assets/project-template',root)
            build(root)
            font=root/'vendor/fonts/NotoSansCJKsc-Regular.otf'
            font.write_bytes(font.read_bytes()+b'changed')
            self.assertFalse(check(root)['passed'])
    def test_node_launcher_preserves_arguments(self):
        import shutil
        if not shutil.which('node'):self.skipTest('node unavailable')
        with tempfile.TemporaryDirectory(prefix='中文 spaces ') as t:
            p=Path(t)/'echo args.py';p.write_text('import sys,json;print(json.dumps(sys.argv[1:],ensure_ascii=False))',encoding='utf-8')
            launcher=Path(__file__).resolve().parents[1]/'scripts/run_python.mjs'
            result=subprocess.run(['node',str(launcher),str(p),'中文 space','literal & | $'],capture_output=True,text=True,encoding='utf-8',check=True,env={**os.environ,'NARRATIVE_VIDEO_PYTHON':sys.executable})
            self.assertEqual(json.loads(result.stdout),['中文 space','literal & | $'])
if __name__=='__main__':unittest.main()
