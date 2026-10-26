#!/usr/bin/env python3
"""Explicit-pair APFS CoW: prepare/check/execute. No discovery, deletion policy or service control."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import _apfs_core as core

SCHEMA = 'apfs-explicit-pairs-v1'
LFS_QUIET = core.quiet


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def protected(path):
    parts = Path(path).parts
    return ('.codex' in parts or 'claude-dotfiles' in parts or 'com.tencent.xinWeChat' in parts
            or '.ssh' in parts or 'Credentials' in parts)


def physical(path):
    p = Path(path)
    if not p.is_absolute() or '..' in p.parts or protected(p):
        raise ValueError('nonabsolute, traversal or protected path')
    # /tmp itself is a macOS alias. Normalize before recording, then reject inner aliases.
    if str(p).startswith('/tmp/'):
        p = Path('/private'+str(p))
    elif str(p).startswith('/var/'):
        p = Path('/private'+str(p))
    core.no_symlink_components(p)
    p = p.resolve(strict=True)
    if protected(p):
        raise ValueError('protected physical path')
    core.no_symlink_components(p)
    return p


def write_new(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2); f.flush(); os.fsync(f.fileno())


def guard(cfg):
    if cfg['kind'] == 'lfs':
        LFS_QUIET(Path(cfg['cache']), Path(cfg['work']))
    else:
        if '.git' in Path(cfg['cache']).parts or '.git' in Path(cfg['work']).parts:
            raise ValueError('ordinary pair cannot enter .git')
        opened = core.open_files([Path(cfg['cache']), Path(cfg['work'])])
        if opened:
            raise RuntimeError('exact pair is open: '+json.dumps(opened))


def check_pair(cfg):
    target, source = physical(cfg['cache']), physical(cfg['work'])
    if str(target) != cfg['cache'] or str(source) != cfg['work']:
        raise ValueError('manifest paths must be physical')
    if core.ident(target) != cfg['cache_stat'] or core.ident(source) != cfg['work_stat']:
        raise RuntimeError('frozen pair identity changed')
    if target.stat().st_dev != source.stat().st_dev or target.stat().st_ino == source.stat().st_ino or target.stat().st_nlink != 1:
        raise RuntimeError('cross-device, hardlinked or same-inode target')
    cc, sc = core.native.clone_info(target), core.native.clone_info(source)
    if not cc['clone_id'] or not sc['clone_id'] or cc['clone_id'] == sc['clone_id'] or cc['full_clone_refs'] != 1 or cc['extended_flags'] & 0x41:
        raise RuntimeError('target already shared or native sharing observation unknown')
    if cfg['kind'] not in ('ordinary', 'lfs'):
        raise ValueError('unsupported kind')
    if cfg['kind'] == 'lfs':
        repo = physical(cfg['repo']); oid = cfg['oid']
        if target != repo/'.git/lfs/objects'/oid[:2]/oid[2:4]/oid or source != repo/cfg['work_relative']:
            raise ValueError('LFS pair escapes repository binding')
        if len(cfg['pointer_ref']) != 40 or any(c not in '0123456789abcdef' for c in cfg['pointer_ref']):
            raise ValueError('LFS pointer_ref must be immutable SHA')
        expected = 'version https://git-lfs.github.com/spec/v1\noid sha256:'+oid+'\nsize '+str(cfg['size'])
        if core.command(['git','-C',str(repo),'show',cfg['pointer_ref']+':'+cfg['work_relative']]) != expected:
            raise ValueError('immutable LFS pointer mismatch')
        if max(cfg['cache_stat'][3:5]) > time.time_ns()-24*3600*10**9:
            raise ValueError('LFS target is within strict 24-hour cooldown')
    guard(cfg)
    if core.stable_hash(target, cfg['cache_stat']) != cfg['oid'] or core.stable_hash(source, cfg['work_stat']) != cfg['oid']:
        raise RuntimeError('pair content mismatch')
    tm, sm = core.metadata(target), core.metadata(source)
    core.ensure_supported(target, tm); core.ensure_supported(source, sm)
    # Read-only target atime can advance; all other fields remain frozen.
    saved = cfg['target_metadata']; adjusted = dict(saved, atime_ns=tm['atime_ns'])
    if tm != adjusted or tm['atime_ns'] < saved['atime_ns'] or sm != cfg['source_metadata']:
        raise RuntimeError('frozen metadata changed')
    temp = Path(cfg['exact_temporary_path'])
    if temp.parent != target.parent or os.path.lexists(temp):
        raise RuntimeError('temporary name occupied or escaped')
    guard(cfg)
    return dict(cache_metadata=tm, work_metadata=sm)


def prepare(pairs, output, reserve, lock_file):
    if sys.platform != 'darwin':
        raise RuntimeError('macOS APFS required')
    if type(reserve) is not int or reserve <= 0 or not isinstance(pairs, list) or not pairs:
        raise ValueError('nonempty pairs and positive reserve required')
    objects=[]; directories={}; targets=set(); sources=set()
    for row in pairs:
        t, s = physical(row['target']), physical(row['source'])
        if str(t) in targets:
            raise ValueError('duplicate target')
        targets.add(str(t)); sources.add(str(s))
        ti, si = core.ident(t), core.ident(s)
        guard(dict(kind=row.get('kind','ordinary'),cache=str(t),work=str(s)))
        # Native pre-screen before reading full payloads.
        cc=core.native.clone_info(t); sc=core.native.clone_info(s)
        if ti[0] != si[0] or ti[1] == si[1] or ti[5] != 1 or not cc['clone_id'] or not sc['clone_id'] or cc['clone_id']==sc['clone_id'] or cc['full_clone_refs']!=1 or cc['extended_flags'] & 0x41:
            raise ValueError('not an independent unshared target')
        h=core.stable_hash(t,ti)
        if core.stable_hash(s,si)!=h:
            raise ValueError('bytes differ')
        cfg=dict(kind=row.get('kind','ordinary'),cache=str(t),work=str(s),oid=h,size=ti[2],cache_stat=ti,work_stat=si,
                 target_metadata=core.metadata(t),source_metadata=core.metadata(s),reserve_bytes=reserve,bound_inputs={},
                 exact_temporary_path=str(t.parent/('.cow-'+h+'-'+str(ti[1])+'.tmp')))
        if cfg['kind']=='lfs':
            cfg.update(repo=str(physical(row['repo'])),pointer_ref=row['pointer_ref'],work_relative=row['work_relative'])
        check_pair(cfg)
        for p in (t.parent,s.parent):
            st=p.stat();directories[str(p)]=[st.st_dev,st.st_ino]
        objects.append(cfg)
    if targets & sources:
        raise ValueError('targets may not be retained sources of any pair')
    lock=None
    if lock_file:
        p=physical(lock_file);st=p.lstat()
        if not stat.S_ISREG(st.st_mode):raise ValueError('lock must be an existing ordinary file')
        lock=dict(path=str(p),identity=[st.st_dev,st.st_ino])
    write_new(output,dict(schema=SCHEMA,objects=objects,directories=directories,lock=lock,
                          bound_tools={str(Path(__file__).resolve()):digest(__file__),str(Path(core.__file__).resolve()):digest(core.__file__),str(Path(core.native.__file__).resolve()):digest(core.native.__file__)},
                          limits='Caller authorization and inactive-resource classification required. Inode/ctime change. No kernel CAS against non-cooperating writers. No automatic service or NAS operation.'))


def load(path):
    raw=Path(path).read_bytes();m=json.loads(raw)
    if m['schema']!=SCHEMA or not m['objects']:
        raise ValueError('invalid manifest')
    for p,h in m['bound_tools'].items():
        if digest(p)!=h:raise ValueError('execution tool changed')
    for p,i in m['directories'].items():
        st=physical(p).stat()
        if [st.st_dev,st.st_ino]!=i:raise ValueError('parent directory changed')
    return m,hashlib.sha256(raw).hexdigest()


@contextmanager
def item_lock(lock):
    if lock is None:
        yield;return
    fd=os.open(lock['path'],os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if [st.st_dev,st.st_ino]!=lock['identity']:raise ValueError('lock identity changed')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def execute(manifest, approved, run_dir, pause_file=None):
    m,h=load(manifest)
    if approved!=h:raise ValueError('manifest SHA mismatch (digest is not user authorization)')
    root=Path(run_dir);root.mkdir(mode=0o700,exist_ok=False)
    write_new(root/'candidate.json',m)
    done=[];before=core.free_bytes(Path(m['objects'][0]['cache']).parent)
    status='failed';error=None
    try:
        for index,cfg in enumerate(m['objects']):
            if pause_file and os.path.lexists(pause_file):
                status='paused';break
            current,hh=load(manifest)
            if hh!=h:raise ValueError('manifest drift')
            with item_lock(m['lock']):
                checked=check_pair(cfg)
                previous=core.quiet
                # The primitive repeats fresh occupancy guards at every mutation boundary.
                def scoped(t,s):
                    if (str(t),str(s))!=(cfg['cache'],cfg['work']):raise ValueError('pair escaped manifest')
                    guard(cfg)
                core.quiet=scoped
                try:result=core.execute(cfg,checked,h,observe_space=False,artifact_dir=root)
                finally:core.quiet=previous
            done.append(dict(index=index,target=cfg['cache'],result=result,identity=core.ident(cfg['cache']),metadata=core.metadata(cfg['cache'])))
            write_new(root/('completed-'+str(index)+'.json'),done[-1])
        else:status='complete'
    except BaseException as e:
        error=repr(e)
    summary=dict(schema=SCHEMA,status=status,manifest_sha256=h,completed=done,unprocessed_count=len(m['objects'])-len(done),error=error,
                 before_available_bytes=before,after_available_bytes=core.free_bytes(Path(m['objects'][0]['cache']).parent),physical_release_bytes=None)
    write_new(root/'summary.json',summary)
    if error:raise RuntimeError(error)
    return summary


def remainder(manifest, summary_path, output):
    m,h=load(manifest);s=json.loads(Path(summary_path).read_text())
    if s['manifest_sha256']!=h or s['status'] not in ('complete','paused','failed'):
        raise ValueError('summary does not bind this manifest')
    n=len(s['completed'])
    if s['unprocessed_count'] != len(m['objects'])-n:raise ValueError('incomplete ledger')
    for i,r in enumerate(s['completed']):
        cfg=m['objects'][i]
        if r['index']!=i or r['target']!=cfg['cache'] or not r['result']['ok'] or core.ident(cfg['cache'])!=r['identity'] or core.metadata(cfg['cache'])!=r['metadata']:
            raise ValueError('completed prefix changed')
        if core.native.clone_info(cfg['cache'])['clone_id'] != core.native.clone_info(cfg['work'])['clone_id'] or core.ident(cfg['work'])!=cfg['work_stat'] or core.metadata(cfg['work'])!=cfg['source_metadata']:
            raise ValueError('completed pair source/sharing changed')
    pending=m['objects'][n:]
    if not pending:raise ValueError('no remainder')
    # Never refresh a failed/rolled-back identity or waive cooldown. Defer it explicitly.
    for cfg in pending:check_pair(cfg)
    m['objects']=pending
    m['resume_proof']=dict(parent_manifest_sha256=h,summary_sha256=digest(summary_path),completed_excluded=n)
    write_new(output,m)
    return dict(selected=len(pending),completed_excluded=n)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('prepare');a.add_argument('--pairs',required=True);a.add_argument('--output',required=True);a.add_argument('--reserve-bytes',required=True,type=int);a.add_argument('--lock-file')
    a=sub.add_parser('check');a.add_argument('manifest')
    a=sub.add_parser('execute');a.add_argument('manifest');a.add_argument('--approved-manifest-sha256',required=True);a.add_argument('--run-dir',required=True);a.add_argument('--pause-file')
    a=sub.add_parser('remainder');a.add_argument('manifest');a.add_argument('--summary',required=True);a.add_argument('--output',required=True)
    a=p.parse_args()
    try:
        if a.cmd=='prepare':
            prepare(json.loads(Path(a.pairs).read_text()),a.output,a.reserve_bytes,a.lock_file);print(json.dumps({'manifest_sha256':digest(a.output),'mutation':False}))
        elif a.cmd=='check':
            m,h=load(a.manifest)
            for cfg in m['objects']:check_pair(cfg)
            print(json.dumps({'objects':len(m['objects']),'manifest_sha256':h,'mutation':False}))
        elif a.cmd=='execute':
            s=execute(a.manifest,a.approved_manifest_sha256,a.run_dir,a.pause_file);print(json.dumps({k:v for k,v in s.items() if k!='completed'}))
        else:print(json.dumps(remainder(a.manifest,a.summary,a.output)))
    except (RuntimeError,ValueError,KeyError,TypeError,OSError) as e:p.exit(2,str(e)+'\n')


if __name__=='__main__':main()
