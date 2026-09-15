import unittest,tempfile,shutil,sys,re,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from nv_core import read,write,validate,local
from build_storyboard import build
from check_project import check
class Contracts(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'video';shutil.copytree(Path(__file__).resolve().parents[1]/'assets/project-template',self.root)
 def tearDown(self):self.tmp.cleanup()
 def test_non_ip_and_relocation(self):
  build(self.root);self.assertTrue(check(self.root)['passed']);other=Path(self.tmp.name)/'moved';shutil.copytree(self.root,other);self.assertTrue(check(other)['passed'])
 def test_portrait_initialization_and_build(self):
  task=Path(self.tmp.name)/'portrait'
  subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/create_project.py'),str(task),'--title','竖屏测试','--aspect-ratio','9:16'],check=True,stdout=subprocess.DEVNULL)
  video=task/'video';p=read(video/'project.json');self.assertEqual((p['width'],p['height']),(720,1280));build(video);self.assertTrue(check(video)['passed'])
  html=(video/'index.html').read_text(encoding='utf-8');self.assertIn('data-width="720" data-height="1280"',html);self.assertIn('href="portrait.css"',html)
  (video/'portrait.css').write_text('changed', encoding='utf-8');self.assertFalse(check(video)['passed'])
 def test_default_landscape(self):
  task=Path(self.tmp.name)/'landscape';subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/create_project.py'),str(task),'--title','默认测试'],check=True,stdout=subprocess.DEVNULL)
  p=read(task/'video/project.json');self.assertEqual((p['width'],p['height']),(1280,720));build(task/'video');self.assertNotIn('href="portrait.css"',(task/'video/index.html').read_text(encoding='utf-8'))
 def test_invalid_dimensions_rejected(self):
  p=self.root/'project.json';x=read(p);x.update(width=720,height=720);write(p,x);self.assertTrue(validate(self.root)['errors'])
 def test_ratio_mismatch_rejected(self):
  p=self.root/'project.json';x=read(p);x['aspect_ratio']='9:16';write(p,x);self.assertTrue(validate(self.root)['errors'])
 def test_gap_rejected(self):
  p=self.root/'script/shots.json';x=read(p);x['shots'][1]['start_ms']+=1;write(p,x);self.assertTrue(validate(self.root)['errors'])
 def test_unmapped_event_rejected(self):
  p=self.root/'script/shots.json';x=read(p);x['shots'][0]['event_ids']=[];write(p,x);self.assertTrue(validate(self.root)['errors'])
 def test_changed_design_invalidates_build(self):
  build(self.root);(self.root/'styles.css').write_text('changed', encoding='utf-8');self.assertFalse(check(self.root)['passed'])
 def test_local_edit_keeps_other_shots(self):
  build(self.root);before=(self.root/'index.html').read_text(encoding='utf-8');p=self.root/'script/shots.json';x=read(p);x['shots'][5]['items'][0]='修改后的重点';write(p,x);build(self.root);after=(self.root/'index.html').read_text(encoding='utf-8')
  for sid in ['S001','S002','S003','S004','S005']:
   pattern='<section id="'+sid+'".*?</section>';self.assertEqual(re.search(pattern,before).group(),re.search(pattern,after).group())
  self.assertNotEqual(before,after)
 def test_bad_beat_rejected(self):
  p=self.root/'script/shots.json';x=read(p);x['shots'][0]['beats'][0]['item_index']=99;write(p,x);self.assertTrue(validate(self.root)['errors'])
 def test_engine_config_invalidates_build(self):
  build(self.root);p=self.root/'hyperframes.json';x=read(p);x['media']['autoProxy']=False;write(p,x);self.assertFalse(check(self.root)['passed'])
 def test_path_escape(self):
  for x in ['../outside','/tmp/out']:
   with self.assertRaises(ValueError):local(self.root,x)
 def test_ip_needs_assets(self):
  p=self.root/'script/shots.json';x=read(p);x['shots'][0]['presentations']=['ip-character'];write(p,x);self.assertTrue(validate(self.root)['errors'])
 def test_text_is_not_html(self):
  p=self.root/'script/shots.json';x=read(p);x['shots'][0]['items'][0]='<script>alert(1)</script>';write(p,x);build(self.root);self.assertIn('&lt;script&gt;', (self.root/'index.html').read_text(encoding='utf-8'))
 def test_silent_rejects_narration_mode(self):
  p=self.root/'project.json';x=read(p);x['audio_mode']='source';write(p,x);self.assertTrue(validate(self.root)['errors'])
if __name__=='__main__':unittest.main()
