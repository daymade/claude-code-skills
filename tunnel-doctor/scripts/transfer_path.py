"""Read-only SSH transfer preflight and the transfer-path PreToolUse decision owner.

TERMINATION: no remote copy starts until a <=120s exact-command proof exists;
preflight either writes that proof after live probes or returns a concrete unknown.
No network changes, approval dialog, automatic retry or transfer is performed here.
Coverage: literal scp/rsync commands. Opaque scripts and arbitrary SSH streams are
not a sandboxed surface. Unknown remote sizes require preflight; <=8 MiB local
regular-file uploads, loopback and dry runs do not. No public-address blacklist.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time

TTL = 120
SMALL = 8 * 1024 * 1024
STATE = Path.home()/'.local/state/daymade-agent-hooks/transfer-path'


def run(argv, timeout=6):
    p = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    if p.returncode:
        raise ValueError(f'{Path(argv[0]).name} probe failed ({p.returncode}): '+p.stderr.decode(errors='replace')[-500:])
    return p.stdout.decode(errors='replace')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def segments(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|()\n')
    lexer.whitespace = ' \t\r'
    lexer.whitespace_split = True
    out = []
    for word in lexer:
        if word and all(c in ';&|()\n' for c in word):
            if out: yield out
            out = []
        else: out.append(word)
    if out: yield out


def transfers(command, cwd):
    """Parse argv; never interpret quoted documentation as executable commands."""
    found = []
    for words in segments(command):
        while words and (re.match(r'^\w+=', words[0]) or words[0] in ('command','env','sudo')):
            words = words[1:]
        if not words: continue
        name = Path(words[0]).name
        if name not in ('scp','rsync'): continue
        if any(x.startswith('rsync://') for x in words):raise ValueError('rsync daemon transport is outside SSH preflight coverage')
        if name == 'rsync' and any(x in ('--dry-run','--list-only') or re.match(r'^-[A-Za-z]*n[A-Za-z]*$', x) for x in words[1:]):
            continue
        ssh, operands, i = [], [], 1
        takes = {'-e','--rsh','--exclude','--include','--filter','--files-from','--exclude-from',
                 '--include-from','--log-file','--out-format','--bwlimit','--timeout','--contimeout',
                 '--rsync-path','--chmod','--chown','--block-size','--max-size','--min-size'} if name=='rsync' else {'-i','-o','-P','-S','-F','-J','-c','-l'}
        while i < len(words):
            word = words[i]
            if name=='scp' and len(word)>2 and word[:2] in takes:
                words[i:i+1]=[word[:2],word[2:]];word=words[i]
            if word in takes:
                if i+1 >= len(words): raise ValueError('incomplete copy option')
                value = words[i+1]
                if word in ('-e','--rsh'):
                    shell = shlex.split(value)
                    if not shell or Path(shell[0]).name != 'ssh': raise ValueError('only SSH rsync transport is supported')
                    ssh = shell[1:]
                elif name=='scp':
                    if word=='-S':
                        if Path(value).name!='ssh': raise ValueError('custom scp transport is unknown')
                    else: ssh.extend(['-p' if word=='-P' else word, value])
                i += 2
                continue
            if word.startswith('--rsh='):
                shell = shlex.split(word.split('=',1)[1])
                if not shell or Path(shell[0]).name!='ssh': raise ValueError('unknown rsync transport')
                ssh = shell[1:]
            elif word == '--': operands.extend(words[i+1:]); break
            elif not word.startswith('-'): operands.append(word)
            elif name=='scp' and word in ('-4','-6','-C'): ssh.append(word)
            i += 1
        remote = []
        for operand in operands:
            m = re.match(r'^((?:[^/@:]+@)?(?:\[[^]]+\]|[^/:]+)):(.+)$', operand)
            if m: remote.append(m.group(1))
        if not remote: continue
        if len(set(remote)) != 1 or len(remote)!=1: raise ValueError('third-party/multiple remote copy requires separate preflights')
        host = remote[0]
        if any(x in host for x in '$`\n'): raise ValueError('dynamic remote endpoint is unknown')
        if host.split('@')[-1].strip('[]') in ('localhost','127.0.0.1','::1'): continue
        # Small known local uploads do not need a bulk-path decision. Remote
        # reads and directories have unknown size until the live preflight.
        sources = operands[:-1]
        if operands and operands[-1].startswith(host+':'):
            paths = [Path(os.path.expanduser(p)) if Path(os.path.expanduser(p)).is_absolute() else Path(cwd)/os.path.expanduser(p) for p in sources]
            if paths and all(p.is_file() and not p.is_symlink() for p in paths) and sum(p.stat().st_size for p in paths)<=SMALL:
                continue
        found.append(dict(host=host, ssh=ssh, argv=words))
    return found


def ssh_options(item):
    # -G is configuration inspection, not a connection; do not allow a shell
    # transport to hide another destination from the path classifier.
    raw = run(['ssh','-G',*item['ssh'],item['host']])
    pairs = [line.split(' ',1) for line in raw.splitlines() if ' ' in line]
    config = {}
    for key,value in pairs: config.setdefault(key,[]).append(value)
    for key in ('proxycommand','proxyjump'):
        if config.get(key, ['none'])[0] not in ('none',''): raise ValueError(key+' route is not supported by this preflight')
    if config.get('controlpath',['none'])[0] not in ('none',''):raise ValueError('multiplexed SSH route unknown; select ControlPath=none for this transfer')
    return config


def network():
    # Addresses, interface state and routes, excluding volatile packet counters.
    raw = run(['/sbin/ifconfig'] if sys.platform=='darwin' else ['ip','-j','address'])
    if sys.platform=='darwin':
        rows = [x.strip() for x in raw.splitlines() if re.search(r'(^\S+: flags=|\binet6? |status:)', x)]
    else:
        rows=[]
        for interface in json.loads(raw):
            addresses=[{key:a[key] for key in ('family','local','prefixlen','scope','flags') if key in a} for a in interface.get('addr_info',[])]
            rows.append(dict(ifname=interface.get('ifname'),flags=sorted(interface.get('flags',[])),
                             operstate=interface.get('operstate'),addresses=sorted(addresses,key=lambda a:json.dumps(a,sort_keys=True))))
        rows.sort(key=lambda a:a['ifname'] or '')
    route = run(['/sbin/route','-n','get','default'] if sys.platform=='darwin' else ['ip','-j','route','show','default'])
    if sys.platform!='darwin':
        route=[{key:r[key] for key in ('dst','gateway','dev','prefsrc','metric','table','protocol','scope','type','multipath') if key in r} for r in json.loads(route)]
    return digest([rows,route])


def local_networks():
    raw = run(['/sbin/ifconfig'] if sys.platform=='darwin' else ['ip','-j','address'])
    nets = []
    if sys.platform=='darwin':
        iface = ''
        for line in raw.splitlines():
            if line and not line[0].isspace(): iface=line.split(':')[0]
            if iface.startswith(('utun','lo','tun','tailscale')): continue
            m = re.search(r'inet (\S+) netmask (0x[0-9a-f]+)',line)
            if m:
                mask = ipaddress.IPv4Address(int(m.group(2),16))
                nets.append(ipaddress.ip_network(f'{m.group(1)}/{mask}',strict=False))
    else:
        for row in json.loads(raw):
            if row['ifname'].startswith(('lo','tun','tailscale')): continue
            for a in row.get('addr_info',[]):
                if a.get('family')=='inet': nets.append(ipaddress.ip_network(f"{a['local']}/{a['prefixlen']}",strict=False))
    return nets


def route_kind(address):
    ip = ipaddress.ip_address(address.split('%')[0])
    raw = run(['/sbin/route','-n','get',address] if sys.platform=='darwin' else ['ip','-j','route','get',address])
    if sys.platform=='darwin':
        m = re.search(r'interface: (\S+)',raw)
        interface = m.group(1) if m else None
        routed = bool(re.search(r'gateway: (?:\d+\.){3}\d+',raw))
    else:
        row = json.loads(raw)[0]; interface=row.get('dev'); routed='gateway' in row
    if not interface or interface.startswith(('utun','tun','tailscale')): return 'unknown'
    if ip.version==6 and ip.is_link_local and not routed: return 'lan-direct'
    if ip.version==4 and not routed and any(ip in n for n in local_networks()): return 'lan-direct'
    return 'wan-direct'


def tailscale_path(host):
    ts = shutil.which('tailscale')
    if not ts: raise ValueError('Tailscale CLI unavailable')
    raw = run([ts,'ping','--c','3','--until-direct=false','--timeout','2s',host],timeout=9)
    lines = [line for line in raw.splitlines() if 'pong from ' in line]
    if len(lines)<2: raise ValueError('insufficient current Tailscale path samples')
    def parse(line):
        if 'peer-relay' in line.lower(): return 'peer-relay'
        if 'DERP' in line or re.search(r'via (?:relay|derp)\b',line,re.I): return 'derp'
        m = re.search(r'via (\[[^]]+\]|[\d.]+):\d+',line)
        if m:
            kind = route_kind(m.group(1).strip('[]'))
            return kind if kind=='lan-direct' else 'wan-direct' if kind=='wan-direct' else 'unknown'
        return 'unknown'
    kinds = [parse(line) for line in lines]
    if 'unknown' in kinds or len(set(kinds[-2:]))!=1: raise ValueError('Tailscale path is unknown or still converging')
    return dict(kind=kinds[-1], samples=lines)


def target_route(config):
    host = config['hostname'][0]
    try: ip = ipaddress.ip_address(host)
    except ValueError:
        addresses = sorted({r[4][0] for r in socket.getaddrinfo(host,None,socket.AF_INET)})
        if not addresses: raise ValueError('endpoint did not resolve')
        if len(addresses)!=1: raise ValueError('ambiguous endpoint addresses')
        host=addresses[0]; ip=ipaddress.ip_address(host)
    if ip.version==4 and ip in ipaddress.ip_network('100.64.0.0/10'):
        return tailscale_path(host)
    if ip.version==6 and ip in ipaddress.ip_network('fd7a:115c:a1e0::/48'):
        return tailscale_path(host)
    return dict(kind=route_kind(host), samples=[host])


def key(command,cwd): return digest([command,str(Path(cwd).resolve())])


def sample(ssh,host):
    """Observe the actual SSH TCP socket while its bounded payload is in flight."""
    proc=subprocess.Popen([*ssh,host,'dd if=/dev/zero bs=65536 count=16 2>/dev/null'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    started=time.monotonic();peer=None
    try:
        deadline=started+5
        while time.monotonic()<deadline and peer is None:
            try:raw=run(['lsof','-nP','-a','-p',str(proc.pid),'-iTCP','-Fn'],timeout=2)
            except ValueError:raw=''
            for line in raw.splitlines():
                if not line.startswith('n') or '->' not in line:continue
                endpoint=line.split('->',1)[1].split(' ')[0]
                peer=endpoint.rsplit(':',1)[0].strip('[]')
            if peer is None:time.sleep(.05)
        if peer is None:raise ValueError('live SSH socket was not observed')
        ip=ipaddress.ip_address(peer.split('%')[0])
        if ip.version==4 and ip in ipaddress.ip_network('100.64.0.0/10') or ip.version==6 and ip in ipaddress.ip_network('fd7a:115c:a1e0::/48'):
            path=tailscale_path(str(ip))
        else:path=dict(kind=route_kind(peer),samples=[peer])
        data,err=proc.communicate(timeout=20)
        if proc.returncode or len(data)!=1048576:raise ValueError('bounded 1 MiB sample failed')
        return dict(sample_bytes=len(data),seconds=round(time.monotonic()-started,3),socket_peer=peer,sample_path=path)
    finally:
        if proc.poll() is None:proc.kill();proc.communicate()


def validate_proof(proof, command, cwd, items, now, net, configs, routes):
    if not isinstance(proof,dict) or proof.get('schema')!=1 or proof.get('key')!=key(command,cwd): return 'missing or wrong-command preflight'
    stamp = proof.get('at')
    if type(stamp) not in (int,float) or not 0<=now-stamp<=TTL: return 'expired preflight'
    if proof.get('network')!=net: return 'local network changed'
    rows = proof.get('targets')
    if not isinstance(rows,list) or len(rows)!=len(items): return 'target proof missing'
    for row,item,config,route in zip(rows,items,configs,routes):
        if not isinstance(row,dict) or row.get('host')!=item['host'] or row.get('config')!=digest(config): return 'SSH target/options changed'
        if route.get('kind')=='unknown' or row.get('route')!=route: return 'actual route changed or unknown'
        if row.get('checked_lan') is not True or type(row.get('sample_bytes')) is not int or row['sample_bytes']!=1048576: return 'LAN comparison or live sample missing'
    return None


def current_routes(items):
    configs = [ssh_options(item) for item in items]
    routes = [target_route(config) for config in configs]
    # Latency values are observations, not a stable route identity.
    for route in routes: route['samples']=[re.sub(r' in .*$', '',line) for line in route['samples']]
    return configs,routes


def evaluate(event):
    rule='transfer-path'
    command=(event.get('tool_input') or {}).get('command','') if isinstance(event,dict) else ''
    row=dict(rule=rule,code=0,stdout='',stderr='',status='complete')
    if not command or not re.search(r'\b(?:scp|rsync)\b',command): return row
    try:
        cwd=event.get('cwd') or os.getcwd()
        if 'turn_id' in event:
            from codex_workdir import lookup
            actual=lookup(event,command)
            if not isinstance(actual,str):raise ValueError('copy working directory is unknown')
            cwd=actual
        items=transfers(command,cwd)
        if not items:return row
        path=STATE/(key(command,cwd)+'.json')
        try: proof=json.loads(path.read_text())
        except (OSError,ValueError): proof=None
        if proof is None: reason='missing preflight'
        else:
            configs,routes=current_routes(items)
            reason=validate_proof(proof,command,cwd,items,time.time(),network(),configs,routes)
        if not reason:return row
    except Exception as error: reason=str(error)
    row.update(code=2,stderr=f'BLOCKED (transfer-path): {reason}. Save the exact copy command to a private file; run the installed transfer_path.py preflight --command-file <file> --cwd <original-cwd>. It probes trusted SSH identity, current LAN/Tailscale underlay and 1 MiB throughput; then retry the unchanged command within {TTL}s. No route or service changes are authorized by this gate.\n')
    return row


def preflight(command,cwd):
    items=transfers(command,cwd)
    if not items: return dict(status='not-required')
    # A failed refresh cannot leave the previous attempt's proof usable.
    (STATE/(key(command,cwd)+'.json')).unlink(missing_ok=True)
    before=network(); targets=[]
    for item in items:
        config=ssh_options(item)
        ssh=['ssh',*item['ssh'],'-o','BatchMode=yes','-o','ConnectTimeout=4','-o','StrictHostKeyChecking=yes']
        # SSH authentication verifies the target before considering discovered
        # interface addresses. A subnet match alone never establishes identity.
        remote=run([*ssh,item['host'],'hostname; id -un; ifconfig 2>/dev/null || ip -o -4 addr show'],timeout=8)
        addresses=set(re.findall(r'\binet (\d+\.\d+\.\d+\.\d+)',remote))
        addresses.update(re.findall(r'\binet (\d+\.\d+\.\d+\.\d+)/',remote))
        if not addresses: raise ValueError('remote interface discovery returned no addresses')
        route=target_route(config)
        if route['kind']=='unknown': raise ValueError('current data path unknown')
        lan=[]
        for address in sorted(addresses):
            ip=ipaddress.ip_address(address)
            if not any(ip in n for n in local_networks()): continue
            # Retain the original host-key namespace; do not accept a new key.
            # Override only the address, leaving the alias to resolve its Port,
            # IdentityFile, user and trust options exactly as the real copy does.
            alias=config.get('hostkeyalias',config['hostname'])[0]
            try:
                candidate=['ssh','-o','HostName='+address,'-o','HostKeyAlias='+alias,*ssh[1:]]
                identity=run([*candidate,item['host'],'hostname; id -un'],timeout=6)
                if identity.splitlines()[:2]==remote.splitlines()[:2]: lan.append(address)
            except (ValueError,subprocess.TimeoutExpired): pass
        if lan and route['kind']!='lan-direct':
            raise ValueError('verified LAN endpoint available: '+', '.join(lan)+'; select it with the existing host-key alias, or use Tailscale only after LAN-direct convergence, then preflight that exact command')
        observed=sample(ssh,item['host'])
        if observed['sample_path']['kind']!=route['kind']:raise ValueError('actual SSH socket and selected route disagree')
        after=target_route(config)
        route['samples']=[re.sub(r' in .*$', '',line) for line in route['samples']]
        after['samples']=[re.sub(r' in .*$', '',line) for line in after['samples']]
        if route!=after: raise ValueError('route changed during sample; retry preflight after convergence')
        targets.append(dict(host=item['host'],config=digest(config),route=route,checked_lan=True,
                            lan_candidates=lan,**observed))
    if network()!=before: raise ValueError('local network changed during preflight')
    proof=dict(schema=1,key=key(command,cwd),at=time.time(),network=before,targets=targets)
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=STATE/(proof['key']+'.json'); temporary=path.with_suffix('.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(proof,stream)
    os.replace(temporary,path)
    return dict(status='ready',expires_in_seconds=TTL,targets=targets)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('preflight','guard'))
    parser.add_argument('--command-file',type=Path)
    parser.add_argument('--cwd',default=os.getcwd())
    args=parser.parse_args()
    try:
        if args.action=='guard':
            row=evaluate(json.load(sys.stdin));print(row['stderr'],end='',file=sys.stderr);return row['code']
        if args.command_file is None:parser.error('--command-file is required')
        print(json.dumps(preflight(args.command_file.read_text().strip(),args.cwd),ensure_ascii=False));return 0
    except Exception as error:
        print(json.dumps(dict(status='unknown',reason=str(error))),file=sys.stderr);return 2


if __name__=='__main__':sys.exit(main())
