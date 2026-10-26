#!/usr/bin/env python3
"""Classify bounded native observations; unique stream allocation is only an upper bound."""
import argparse
from collections import defaultdict
import json


def integer(v):
    return type(v) is int and v >= 0


def account(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError('nonempty observation list required')
    groups=defaultdict(list);unknown=[];paths=set();nominal=0
    required=('device','inode','logical_bytes','allocated_bytes','nlink','clone_id','full_clone_refs','extended_flags')
    for r in rows:
        if not isinstance(r,dict) or not isinstance(r.get('path'),str) or not r['path'] or r['path'] in paths:
            raise ValueError('invalid or duplicate path')
        paths.add(r['path'])
        if r.get('stable') is not True or not all(integer(r.get(k)) for k in required):
            unknown.append(dict(path=r['path'],reason='incomplete_or_unstable_observation'));continue
        nominal+=r['allocated_bytes']
        if not r['clone_id'] or not r['inode'] or not r['nlink'] or r['extended_flags'] & ~0x52:
            unknown.append(dict(path=r['path'],reason='unknown_native_state'));continue
        groups[(r['device'],r['clone_id'])].append(r)
    internal=[];external=[]
    for key,group in groups.items():
        inodes=defaultdict(list)
        for r in group:inodes[r['inode']].append(r)
        values={(r['logical_bytes'],r['allocated_bytes'],r['full_clone_refs']) for r in group}
        if len(values)!=1:
            unknown.append(dict(paths=[r['path'] for r in group],reason='inconsistent_stream_metadata'));continue
        logical,allocated,refs=next(iter(values))
        if not refs:
            unknown.append(dict(paths=[r['path'] for r in group],reason='zero_ref_count'));continue
        row=dict(device=key[0],clone_id=key[1],unique_inodes=len(inodes),logical_bytes=logical,allocated_upper_bytes=allocated)
        if refs!=len(inodes) or any(any(r['nlink']!=len(paths) for r in paths) for paths in inodes.values()):
            external.append(row);continue
        internal.append(row)
    return dict(path_accounted_allocated_bytes=nominal,observed_paths=len(rows),
                wholly_internal_streams=internal,external_or_missing_reference_streams=external,unknown=unknown,
                internal_allocated_upper_bytes=sum(r['allocated_upper_bytes'] for r in internal),
                physical_release_bytes=None,limits='Complete-in-set full-clone/hardlink refs only. Partial sharing, snapshots and concurrent activity can reduce release; no cleanup authority.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('observations');a=p.parse_args()
    try:
        with open(a.observations) as f:print(json.dumps(account(json.load(f)),indent=2))
    except (ValueError,TypeError,OSError) as e:p.exit(2,str(e)+'\n')


if __name__=='__main__':main()
