import ctypes
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPTS=Path(__file__).parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import batch_budget
import stream_accounting


class BudgetTests(unittest.TestCase):
    def test_ceiling_cannot_close_gap(self):
        r=batch_budget.assess(dict(available_bytes=159_000_000_000,target_available_bytes=200_000_000_000,remaining_items=2500,pilot_items=10,pilot_seconds=100,reclaim_upper_bytes=4_000_000_000))
        self.assertEqual(r['upper_bound_remaining_gap_bytes'],37_000_000_000)
        self.assertEqual(r['estimated_remaining_seconds'],25000)
        self.assertIn('insufficient',r['decision']);self.assertFalse(r['capacity_goal_complete'])

    def test_unknown_ceiling_and_met_watermark(self):
        v=dict(available_bytes=159,target_available_bytes=200,remaining_items=0,pilot_items=1,pilot_seconds=2,reclaim_upper_bytes=None)
        self.assertIn('unknown',batch_budget.assess(v)['decision'])
        v['available_bytes']=201;self.assertIn('sustainability_unverified',batch_budget.assess(v)['decision'])

    def test_missing_null_boolean_negative(self):
        v=dict(available_bytes=0,target_available_bytes=200,remaining_items=4,pilot_items=2,pilot_seconds=3,reclaim_upper_bytes=1)
        for k in v:
            for value in [None,True,-1,float('nan')]:
                if k=='reclaim_upper_bytes' and value is None:continue
                with self.assertRaises((ValueError,KeyError,TypeError)):batch_budget.assess(dict(v,**{k:value}))
        del v['reclaim_upper_bytes']
        with self.assertRaises(KeyError):batch_budget.assess(v)


class AccountingTests(unittest.TestCase):
    def row(self,path,ino,refs=2,links=1):
        return dict(path=path,device=1,inode=ino,logical_bytes=10,allocated_bytes=4096,nlink=links,clone_id=8,full_clone_refs=refs,extended_flags=0x40,stable=True)

    def test_internal_shared_once_and_external_excluded(self):
        r=stream_accounting.account([self.row('a',1),self.row('b',2)])
        self.assertEqual(r['internal_allocated_upper_bytes'],4096);self.assertEqual(r['path_accounted_allocated_bytes'],8192)
        r=stream_accounting.account([self.row('a',1,3),self.row('b',2,3)])
        self.assertEqual(r['internal_allocated_upper_bytes'],0);self.assertEqual(len(r['external_or_missing_reference_streams']),1)

    def test_hardlink_paths_not_clone_refs(self):
        r=stream_accounting.account([self.row('a',1,1,2),self.row('b',1,1,2)])
        self.assertEqual(r['internal_allocated_upper_bytes'],4096)
        r=stream_accounting.account([self.row('a',1,1,2)])
        self.assertEqual(r['internal_allocated_upper_bytes'],0)

    def test_missing_null_or_unstable_unknown(self):
        for k in ['inode','clone_id','full_clone_refs','extended_flags','stable']:
            for value in [None,False]:
                a=self.row('a',1);a[k]=value
                r=stream_accounting.account([a]);self.assertEqual(r['internal_allocated_upper_bytes'],0)
            a=self.row('a',1);del a[k];self.assertEqual(stream_accounting.account([a])['internal_allocated_upper_bytes'],0)
        with self.assertRaises(ValueError):stream_accounting.account([])


@unittest.skipUnless(sys.platform=='darwin','native APFS acceptance requires macOS')
class NativeTests(unittest.TestCase):
    def setUp(self):
        import apfs_cow
        self.c=apfs_cow
        self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name).resolve()
        self.source=self.r/'source';self.target=self.r/'target'
        payload=b'cow-fixture-0123'*65536
        self.source.write_bytes(payload);self.target.write_bytes(payload)
        for p,value in [(self.source,b''),(self.target,b'value')]:
            buf=ctypes.create_string_buffer(value)
            self.c.core.native.ok(self.c.core.native.setx(os.fsencode(p),b'com.apple.quarantine',buf,len(value),0,0),'fixture xattr')
        self.source.chmod(0o444)
        self.pairs=[dict(source=str(self.source),target=str(self.target))]
        self.manifest=self.r/'manifest.json'

    def tearDown(self):self.tmp.cleanup()

    def test_native_preserves_path_bytes_metadata_and_shared_source(self):
        self.c.prepare(self.pairs,self.manifest,1024*1024,None)
        m,h=self.c.load(self.manifest);cfg=m['objects'][0];old=self.target.stat().st_ino
        # Ordinary data is not blocked by an unrelated LFS process.
        with mock.patch.object(self.c,'LFS_QUIET',side_effect=AssertionError('ordinary must not use global veto')):
            s=self.c.execute(self.manifest,h,self.r/'run')
        self.assertEqual(s['status'],'complete');self.assertNotEqual(self.target.stat().st_ino,old)
        self.assertEqual(self.c.core.sha(self.target),cfg['oid'])
        self.assertEqual(self.c.core.metadata(self.target),cfg['target_metadata'])
        self.assertEqual(self.c.core.metadata(self.source),cfg['source_metadata'])
        self.assertEqual(self.c.core.native.clone_info(self.target)['clone_id'],self.c.core.native.clone_info(self.source)['clone_id'])
        self.assertFalse(Path(cfg['exact_temporary_path']).exists())

    def test_pause_and_exact_remainder_without_mutation(self):
        self.c.prepare(self.pairs,self.manifest,1024*1024,None);m,h=self.c.load(self.manifest)
        pause=self.r/'pause';pause.touch();old=self.target.stat().st_ino
        self.assertEqual(self.c.execute(self.manifest,h,self.r/'run',pause)['status'],'paused')
        self.assertEqual(self.target.stat().st_ino,old)
        out=self.r/'remainder.json';v=self.c.remainder(self.manifest,self.r/'run/summary.json',out)
        self.assertEqual(v,dict(selected=1,completed_excluded=0))
        self.assertEqual(json.loads(out.read_text())['objects'],m['objects'])
        with self.assertRaises(ValueError):self.c.execute(out,'0'*64,self.r/'bad')
        self.assertFalse((self.r/'bad').exists())

    def test_postswap_failure_rolls_back_same_inode(self):
        self.c.prepare(self.pairs,self.manifest,1024*1024,None);m,h=self.c.load(self.manifest);cfg=m['objects'][0]
        native=self.c.core.native;original=native.swap;calls=[]
        def swapping(a,b,flags):
            rc=original(a,b,flags);calls.append(rc);return rc
        original_guard=self.c.guard
        def guard(c):
            if calls:raise RuntimeError('synthetic post-swap occupied condition')
            return original_guard(c)
        with mock.patch.object(native,'swap',side_effect=swapping),mock.patch.object(self.c,'guard',side_effect=guard):
            with self.assertRaises(RuntimeError):self.c.execute(self.manifest,h,self.r/'failed')
        self.assertEqual(self.target.stat().st_ino,cfg['cache_stat'][1]);self.assertEqual(len(calls),2)
        self.assertFalse(Path(cfg['exact_temporary_path']).exists())
        self.assertEqual(self.c.core.sha(self.target),cfg['oid'])
        # Rollback ctime is not silently accepted by a refreshed remainder.
        with self.assertRaises(RuntimeError):self.c.remainder(self.manifest,self.r/'failed/summary.json',self.r/'invalid-remainder')

    def test_in_use_failure_and_alias_hardlink_protected_no_mutation(self):
        with mock.patch.object(self.c.core,'open_files',return_value=[dict(pid=123,path=str(self.target))]):
            with self.assertRaises(RuntimeError):self.c.prepare(self.pairs,self.manifest,1,None)
        self.assertFalse(self.manifest.exists())
        alias=self.r/'alias';alias.symlink_to(self.target)
        with self.assertRaises(RuntimeError):self.c.physical(alias)
        with self.assertRaises(ValueError):self.c.physical(self.r/'.codex/sessions/x')
        os.link(self.target,self.r/'hardlink')
        with self.assertRaises(ValueError):self.c.prepare(self.pairs,self.manifest,1,None)

    def test_lsof_stderr_is_unknown_not_idle(self):
        for rc in (0,1):
            with mock.patch.object(self.c.core.subprocess,'run',return_value=subprocess.CompletedProcess([],rc,'','permission visibility unknown')):
                with self.assertRaises(RuntimeError):self.c.core.open_files([self.target])

    def test_busy_lock_refuses_and_releases_at_boundary(self):
        lock=self.r/'official.lock';lock.touch()
        self.c.prepare(self.pairs,self.manifest,1024*1024,lock);m,h=self.c.load(self.manifest)
        fd=os.open(lock,os.O_RDONLY)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(RuntimeError):self.c.execute(self.manifest,h,self.r/'busy')
            self.assertEqual(self.target.stat().st_ino,m['objects'][0]['cache_stat'][1])
        finally:os.close(fd)
        # After a completed item, another independently opened descriptor can lock.
        self.c.execute(self.manifest,h,self.r/'unblocked')
        fd=os.open(lock,os.O_RDONLY)
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:os.close(fd)

    def test_completed_prefix_excluded_and_pending_exact(self):
        second=self.r/'target2';second.write_bytes(self.source.read_bytes())
        pairs=self.pairs+[dict(source=str(self.source),target=str(second))]
        self.c.prepare(pairs,self.manifest,1024*1024,None);m,h=self.c.load(self.manifest)
        pause=self.r/'pause';original=self.c.core.execute
        def one(*args,**kwargs):
            result=original(*args,**kwargs);pause.touch();return result
        with mock.patch.object(self.c.core,'execute',side_effect=one):
            result=self.c.execute(self.manifest,h,self.r/'partial',pause)
        self.assertEqual((result['status'],len(result['completed'])),('paused',1))
        out=self.r/'remaining';self.c.remainder(self.manifest,self.r/'partial/summary.json',out)
        pending,ph=self.c.load(out);self.assertEqual(pending['objects'],m['objects'][1:])
        # Resume processes the second only, retaining the completed target inode.
        first_inode=self.target.stat().st_ino
        self.c.execute(out,ph,self.r/'resumed')
        self.assertEqual(self.target.stat().st_ino,first_inode)

    def test_actual_cli_prepare_rejects_invalid_input_without_manifest(self):
        pairs=self.r/'pairs.json';pairs.write_text('{}')
        result=subprocess.run([sys.executable,str(SCRIPTS/'apfs_cow.py'),'prepare','--pairs',str(pairs),'--output',str(self.manifest),'--reserve-bytes','1'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertFalse(self.manifest.exists())

    def test_metadata_preflight_reports_names_without_values(self):
        target=dict(self.c.core.metadata(self.target),xattrs={'com.apple.quarantine':'76616c7565'})
        for target_attrs, source_attrs, expected in [
            (target['xattrs'], dict(target['xattrs']), dict(source_only=[],target_only=[],different_values=[])),
            (target['xattrs'], {}, dict(source_only=[],target_only=['com.apple.quarantine'],different_values=[])),
            ({}, {'com.apple.quarantine':''}, dict(source_only=['com.apple.quarantine'],target_only=[],different_values=[])),
            (target['xattrs'], {'com.apple.quarantine':''}, dict(source_only=[],target_only=[],different_values=['com.apple.quarantine'])),
            (target['xattrs'], {**target['xattrs'],'com.apple.provenance':'1234'}, dict(source_only=['com.apple.provenance'],target_only=[],different_values=[])),
        ]:
            source=dict(target,xattrs=source_attrs)
            target_meta=dict(target,xattrs=target_attrs)
            output=io.StringIO()
            with mock.patch.object(self.c.core,'metadata',side_effect=[target_meta,source]),mock.patch('sys.stderr',output):
                self.c.metadata_preflight(self.target,self.source)
            event=json.loads(output.getvalue())
            self.assertEqual(event['metadata_differences']['xattrs'],expected)
            self.assertEqual(event['clone_metadata_compatibility'],'unverified')
            self.assertNotIn('1234',output.getvalue())
            self.assertNotIn(str(self.source),output.getvalue())

    def test_prepare_metadata_notice_precedes_payload_hash(self):
        original=self.c.core.stable_hash
        output=io.StringIO()
        def hashing(*args):
            event=json.loads(output.getvalue().splitlines()[0])
            self.assertEqual(event['event'],'metadata_preflight')
            self.assertEqual(event['metadata_differences']['xattrs']['different_values'],['com.apple.quarantine'])
            return original(*args)
        with mock.patch('sys.stderr',output),mock.patch.object(self.c.core,'stable_hash',side_effect=hashing):
            self.c.prepare(self.pairs,self.manifest,1024*1024,None)
        m,h=self.c.load(self.manifest)
        self.assertEqual(m['schema'],'apfs-explicit-pairs-v1')
        self.assertNotIn('verification',m)
        self.c.check_pair(m['objects'][0])

    def test_existing_metadata_exclusions_precede_payload_hash(self):
        healthy=self.c.core.metadata(self.target)
        for changed in [dict(flags=1),dict(mode=0o4644),dict(uid=os.getuid()+1),
                        dict(xattrs={'com.apple.ResourceFork':'00'}),
                        dict(xattrs={'synthetic.large':'00'*(1024*1024+1)})]:
            for side in (0,1):
                metadata=[healthy,healthy];metadata[side]=dict(healthy,**changed)
                with mock.patch.object(self.c.core,'metadata',side_effect=metadata),mock.patch.object(self.c.core,'stable_hash') as hashed,mock.patch('sys.stderr',io.StringIO()):
                    with self.assertRaises(RuntimeError):
                        self.c.prepare(self.pairs,self.manifest,1,None)
                    hashed.assert_not_called()
                self.assertFalse(self.manifest.exists())

    def test_cli_snapshot_scope_and_legacy_fields(self):
        pairs=self.r/'pairs.json';pairs.write_text(json.dumps(self.pairs))
        before=[self.c.core.ident(p) for p in (self.target,self.source)]
        commands=[['prepare','--pairs',str(pairs),'--output',str(self.manifest),'--reserve-bytes','1048576'],['check',str(self.manifest)]]
        for command in commands:
            result=subprocess.run([sys.executable,str(SCRIPTS/'apfs_cow.py'),*command],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            value=json.loads(result.stdout)
            self.assertFalse(value['mutation']);self.assertEqual(len(value['manifest_sha256']),64)
            self.assertEqual(value['verification'],dict(bytes_identity_metadata_snapshot='verified',clone_metadata_compatibility='unverified',physical_release='unverified'))
            self.assertEqual(json.loads(result.stderr.splitlines()[0])['event'],'metadata_preflight')
        self.assertEqual(value['objects'],1)
        self.assertEqual(before,[self.c.core.ident(p) for p in (self.target,self.source)])


if __name__=='__main__':unittest.main()
