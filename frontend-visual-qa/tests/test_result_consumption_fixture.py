"""Check fixture facts and actual JavaScript transitions; this is not browser QA."""
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class Scripts(HTMLParser):
    def __init__(self,text):
        super().__init__();self.scripts={};self.active=None;self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='script':self.active=attrs.get('id');self.scripts[self.active]=''
    def handle_data(self,data):
        if self.active is not None:self.scripts[self.active]+=data
    def handle_endtag(self,tag):
        if tag=='script':self.active=None

NODE_HARNESS=r"""
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element{
 constructor(id='',tag='div'){this.id=id;this.tagName=tag.toUpperCase();this.attrs={};this.handlers={};this.children=[];this.hidden=false;this.disabled=false;this.html='';this.text='';}
 set innerHTML(value){this.html=value;this.text='';this.children=[];}
 get innerHTML(){return this.html;}
 set textContent(value){this.text=String(value);this.html='';this.children=[];}
 get textContent(){return this.text+this.children.map(child=>child.textContent).join('');}
 appendChild(child){this.children.push(child);return child;}
 setAttribute(key,value){this.attrs[key]=String(value);}
 getAttribute(key){return this.attrs[key]??null;}
 addEventListener(key,fn){this.handlers[key]=fn;}
 click(){if(!this.disabled)this.handlers.click?.({preventDefault(){}});}
}
const elements=Object.fromEntries([...input.html.matchAll(/\bid="([^"]+)"/g)].map(match=>[match[1],new Element(match[1])]));
const panels=[];
for(const match of input.html.matchAll(/<section[^>]*id="([^"]+)"[^>]*data-panel="([^"]+)"[^>]*>/g)){
 const el=elements[match[1]];el.attrs['data-panel']=match[2];el.hidden=/\bhidden\b/.test(match[0]);panels.push(el);
}
elements.authority.textContent=input.authority;
const location={search:'?case=case-a'},events=[],window={addEventListener(){},dispatchEvent(event){events.push(event.detail);}};
const context={document:{getElementById:id=>elements[id],createElement:tag=>new Element('',tag),querySelectorAll:()=>panels},location,history:{replaceState(_a,_b,url){location.search=url;}},window,URLSearchParams,CustomEvent:class{constructor(type,opts){this.type=type;this.detail=opts.detail;}}};
vm.runInNewContext(input.runtime,context,{timeout:1000});
const snapshot=()=>({route:location.search,identity:elements.identity.textContent,pre:elements['ordinary-content'].children.some(el=>el.tagName==='PRE'),html:elements['ordinary-content'].innerHTML,reader:elements['reader-content'].innerHTML,source:elements['source-time'].textContent,unread:elements['unread-count'].textContent,record:elements['record-coordinate'].textContent,diagnostic:JSON.parse(elements['diagnostic-content'].textContent),panels:Object.fromEntries(panels.map(el=>[el.getAttribute('data-panel'),el.hidden]))});
const result={initial:snapshot()};
elements['show-reader'].click();result.reader=snapshot();
elements['show-diagnostics'].click();result.diagnostics=snapshot();
elements['return-result'].click();result.returned=snapshot();
elements['next-update-trigger'].click();elements['next-update-trigger'].click();result.updatedA=snapshot();
elements['read-update'].click();result.readA=snapshot();
elements['route-b'].click();result.initialB=snapshot();
elements['next-update-trigger'].click();result.updatedB=snapshot();
elements['read-update'].click();result.readB=snapshot();
elements['route-a'].click();result.backA=snapshot();
result.events=events;console.log(JSON.stringify(result));
"""

class ResultConsumptionFixtureContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(ROOT/'evals/files/result-consumption-fixture.html').read_text()
        cls.authority=json.loads((ROOT/'evals/files/result-consumption-authority.json').read_text())
        cls.scripts=Scripts(cls.html).scripts
        run=subprocess.run(['node','-e',NODE_HARNESS],input=json.dumps({'html':cls.html,'authority':cls.scripts['authority'],'runtime':cls.scripts['fixture-runtime']}),text=True,capture_output=True,timeout=10)
        if run.returncode:raise AssertionError('JavaScript harness failed: '+run.stderr)
        cls.trace=json.loads(run.stdout)

    def test_embedded_facts_equal_independent_authority(self):
        self.assertEqual(json.loads(self.scripts['authority']),self.authority)
        self.assertEqual(set(self.authority['cases']),{'case-a','case-b'})

    def test_exit_zero_is_distinct_from_business_result(self):
        a=self.authority['cases']['case-a'];b=self.authority['cases']['case-b']
        self.assertEqual(a['process']['exit_code'],0)
        self.assertEqual(a['business_result'],'blocked')
        self.assertEqual(b['business_result'],'requested_draft_complete')
        self.assertIn('fix has not been applied',a['markdown'])

    def test_ordinary_and_reader_are_separate_consumption_surfaces(self):
        a=self.trace['initial'];b=self.trace['initialB']
        self.assertTrue(a['pre']);self.assertIn('<strong>',a['reader'])
        self.assertFalse(b['pre']);self.assertEqual(b['html'],b['reader'])
        self.assertIn('printf',b['html'])

    def test_three_surfaces_return_to_the_same_identity(self):
        for key,panel in [('reader','reader'),('diagnostics','diagnostics'),('returned','result')]:
            with self.subTest(key=key):
                row=self.trace[key]
                self.assertEqual(row['route'],'?case=case-a')
                self.assertIn('node-alpha / job-a / session-a',row['identity'])
                self.assertFalse(row['panels'][panel])
                self.assertEqual(sum(not hidden for hidden in row['panels'].values()),1)

    def test_new_record_is_observed_before_being_read_and_not_duplicated(self):
        self.assertEqual(self.trace['initial']['unread'],'0 unread')
        self.assertEqual(self.trace['updatedA']['unread'],'1 unread')
        self.assertIn('report-a-0',self.trace['updatedA']['record'])
        self.assertEqual(self.trace['readA']['unread'],'0 unread')
        self.assertIn('report-a-1',self.trace['readA']['record'])
        self.assertEqual(len(self.trace['events']),2)

    def test_route_change_updates_the_new_record_identity(self):
        event=self.trace['events'][1]
        self.assertEqual((event['machine'],event['job'],event['session'],event['record_id']),('node-beta','job-b','session-b','report-b-1'))
        self.assertIn('report-b-1',self.trace['readB']['record'])
        self.assertIn('report-a-1',self.trace['backA']['record'])
        self.assertEqual(self.trace['backA']['unread'],'0 unread')

    def test_unknown_source_time_never_becomes_observation_time(self):
        for case in self.authority['cases'].values():
            self.assertIsNone(case['source_time']);self.assertIsNone(case['next_update']['source_time_after'])
        for key in ['initial','updatedA','readA','initialB','updatedB','readB']:
            with self.subTest(key=key):
                self.assertIsNone(self.trace[key]['diagnostic']['source_time'])
                self.assertIn('Source time: Not recorded',self.trace[key]['source'])
        self.assertNotEqual(self.trace['initial']['diagnostic']['observed_at'],self.trace['updatedA']['diagnostic']['observed_at'])

    def test_healthy_unknowns_and_optional_json_remain_legitimate(self):
        data=self.trace['initialB']['diagnostic']
        self.assertIsNone(data['model']['value']);self.assertIsNone(data['dispatch']['record'])
        self.assertIsNone(data['identity']['parent_session_binding'])
        self.assertIn('Raw JSON remains available',self.trace['initialB']['reader'])

    def test_result_consumption_cases_and_no_runtime_dependencies(self):
        cases=json.loads((ROOT/'evals/evals.json').read_text())['evals']
        by_id={row['id']:row for row in cases}
        self.assertEqual(len(by_id),len(cases),'eval IDs must remain unique')
        for case_id in (29,30):
            self.assertIn(case_id,by_id)
            row=by_id[case_id]
            self.assertEqual(row['files'],['evals/files/result-consumption-fixture.html','evals/files/result-consumption-authority.json'])
        for forbidden in ['fetch(', 'XMLHttpRequest', 'https://', 'http://', 'expected grade', 'defect name']:
            self.assertNotIn(forbidden,self.html)

if __name__=='__main__':unittest.main()
