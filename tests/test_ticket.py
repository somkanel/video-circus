import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
SCRIPT=Path(__file__).resolve().parents[1]/'skills/circus-ticket/scripts/ticket.py'
spec=importlib.util.spec_from_file_location('ticket',SCRIPT);t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
class TicketTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.package=self.root/'input';self.final=self.package/'final';self.final.mkdir(parents=True)
  source={'media':None,'sha256':None,'scope':[0,10],'duration':10}
  transcript={'segments':[{'id':'s000001','start':0,'end':10,'text':'Speaker <script>alert(1)</script>'}]}
  content={'summary':'A fixture','chapters':[{'start':0,'end':10,'title':'Chapter'}],'content':[{'start':0,'end':10,'kind':'source_claim','text':'A sourced claim.','evidence_ids':['s000001']}],'unresolved':[{'start':0,'end':10,'reason':'Not listened.'}]}
  review={'reviewed_segment_ids':['s000001'],'reviewed_frame_ids':[]}
  for name,value in [('content.json',content),('transcript-corrected.json',transcript),('visual-evidence.json',{'frames':[],'observations':[]}),('review.json',review),('coverage.json',{})]:
   (self.final/name).write_text(json.dumps(value))
  (self.package/'raw.txt').write_text('original raw input')
  prepared={'source':source,'artifacts':{'raw.txt':t.sha(self.package/'raw.txt')}}
  (self.package/'manifest.json').write_text(json.dumps(prepared))
  self.manifest=self.final/'manifest.json'
  self.m={'schema':'circus-juggler/1','status':'partial','source':source,'artifacts':prepared['artifacts'],'remaining':['quiet_intervals_not_checked'],'final_artifacts':{p.name:t.sha(p) for p in self.final.iterdir()}}
  self.save_manifest()
  self.editorial=self.root/'editorial.json';self.edit={'title':'Fixture @@DATA@@ <script>evil()</script>','brief':[{'text':'A summary <b>untrusted</b>','kind':'source_claim','evidence_ids':['s000001']}]};self.save_editorial()
  self.args=argparse.Namespace(manifest=str(self.manifest),editorial=str(self.editorial),output=str(self.root/'report'))
 def save_manifest(self):self.manifest.write_text(json.dumps(self.m))
 def save_editorial(self):self.editorial.write_text(json.dumps(self.edit))
 def test_partial_is_preserved_and_self_contained(self):
  result=t.render(self.args);self.assertEqual(result['source_status'],'partial');self.assertEqual(result['visual_qa'],'not_performed')
  p=self.root/'report';doc=json.loads((p/'report.json').read_text());self.assertEqual(doc['remaining'],['quiet_intervals_not_checked'])
  self.assertNotIn(str(self.package),(p/'report.html').read_text());self.assertEqual(t.sha(p/'report.html'),result['files']['report.html'])
 def test_unreviewed_and_stale_inputs_rejected(self):
  for status in ['materials_ready','stale','failed']:
   self.m['status']=status;self.save_manifest()
   with self.assertRaises(t.TicketError):t.render(self.args)
 def test_modified_prepared_material_rejected(self):
  (self.package/'raw.txt').write_text('changed')
  with self.assertRaises(t.TicketError):t.render(self.args)
 def test_modified_final_content_rejected(self):
  (self.final/'content.json').write_text('{}')
  with self.assertRaises(t.TicketError):t.render(self.args)
 def test_forged_and_unobserved_evidence_rejected(self):
  for eid in ['s999999','f0000000000']:
   self.edit['brief'][0]['evidence_ids']=[eid];self.save_editorial()
   with self.assertRaises(t.TicketError):t.render(self.args)
 def test_untrusted_text_cannot_break_html_or_json_script(self):
  self.edit['brief'][0]['text']='</script><script>malicious()</script>';self.save_editorial();t.render(self.args)
  page=(self.root/'report/report.html').read_text()
  self.assertNotIn('<script>malicious()</script>',page);self.assertNotIn('<script>evil()</script>',page)
  self.assertIn('&lt;script&gt;',page);self.assertIn('@@DATA@@',page)
  self.assertIn('\\u003cscript\\u003e',page)
 def test_report_cannot_overwrite_input_or_prior_report(self):
  self.args.output=str(self.package)
  with self.assertRaises(t.TicketError):t.render(self.args)
  self.args.output=str(self.root/'report');t.render(self.args)
  with self.assertRaises(t.TicketError):t.render(self.args)
 def test_seal_path_cannot_escape_package(self):
  self.m['final_artifacts']['../raw.txt']=t.sha(self.package/'raw.txt');self.save_manifest()
  with self.assertRaises(t.TicketError):t.render(self.args)
 def test_required_final_file_cannot_be_unsealed(self):
  del self.m['final_artifacts']['content.json'];self.save_manifest()
  with self.assertRaises(t.TicketError):t.render(self.args)
 def test_unreviewed_transcript_is_marked_and_cannot_support_editorial(self):
  path=self.final/'transcript-corrected.json';data=json.loads(path.read_text())
  data['segments'].append({'id':'s000002','start':5,'end':10,'text':'Unreviewed draft'})
  path.write_text(json.dumps(data));self.m['final_artifacts'][path.name]=t.sha(path);self.save_manifest()
  t.render(self.args);page=(self.root/'report/report.html').read_text()
  self.assertIn('未审阅</small>',page)
  self.edit['brief'][0]['evidence_ids']=['s000002'];self.save_editorial();self.args.output=str(self.root/'new-report')
  with self.assertRaises(t.TicketError):t.render(self.args)
 def test_optional_navigation_only_points_to_existing_sections(self):
  t.render(self.args);page=(self.root/'report/report.html').read_text()
  self.assertNotIn('href="#faq"',page);self.assertNotIn('href="#highlights"',page)
  self.assertIn('href="#uncertainty"',page)
 def test_verified_reviewed_alternate_caption_can_be_cited(self):
  tracks={'tracks':[{'id':'track2','segments':[{'id':'t2s000001','start':0,'end':10,'text':'Verified alternate text'}]}]}
  trackpath=self.package/'subtitle-tracks.json';trackpath.write_text(json.dumps(tracks))
  prepared=json.loads((self.package/'manifest.json').read_text());prepared['artifacts']['subtitle-tracks.json']=t.sha(trackpath)
  (self.package/'manifest.json').write_text(json.dumps(prepared));self.m['artifacts']=prepared['artifacts']
  reviewpath=self.final/'review.json';review=json.loads(reviewpath.read_text())
  review.update(reviewed_subtitle_ids=['t2s000001'],verified_subtitle_tracks=['track2']);reviewpath.write_text(json.dumps(review))
  self.m['final_artifacts']['review.json']=t.sha(reviewpath);self.save_manifest()
  self.edit['brief'][0]['evidence_ids']=['t2s000001'];self.save_editorial()
  t.render(self.args);report=json.loads((self.root/'report/report.json').read_text())
  self.assertEqual(report['evidence']['t2s000001']['type'],'subtitle')
  review['verified_subtitle_tracks']=[];reviewpath.write_text(json.dumps(review))
  self.m['final_artifacts']['review.json']=t.sha(reviewpath);self.save_manifest()
  self.args.output=str(self.root/'rejected-report')
  with self.assertRaises(t.TicketError):t.render(self.args)
if __name__=='__main__':unittest.main()
