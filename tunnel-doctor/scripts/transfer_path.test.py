"""Offline transfer-path decisions; live/corpus evidence is recorded privately."""
import json
import ipaddress
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import transfer_path as t


class TransferPath(unittest.TestCase):
    def event(self,cmd):return dict(cwd='/tmp',tool_name='Bash',tool_input={'command':cmd})

    def test_literal_coverage_and_healthy_commands(self):
        for cmd in ('echo "rsync a host:/x"','ssh host hostname','rsync --version',
                    'rsync -an host:/data /tmp/data','rsync --list-only host:/x',
                    'cp /tmp/a /tmp/b','scp localhost:/tmp/a /tmp/a'):
            with self.subTest(cmd=cmd):self.assertEqual(t.transfers(cmd,'/tmp'),[])
        for cmd in ('rsync -a host:/data /tmp/data','/usr/bin/scp -P 2222 a host:/x',
                    'rsync -a -e "ssh -o BatchMode=yes" host:/x /tmp/x',
                    'cd /tmp && scp host:/a /tmp/a'):
            with self.subTest(cmd=cmd):self.assertEqual(len(t.transfers(cmd,'/tmp')),1)

    def test_small_local_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'small';p.write_bytes(b'x')
            self.assertEqual(t.transfers('scp small host:/tmp/a',folder),[])
            self.assertEqual(len(t.transfers('scp missing host:/tmp/a',folder)),1)
            self.assertEqual(len(t.transfers('scp . host:/tmp/a',folder)),1)

    def test_missing_proof_blocked(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(t,'STATE',Path(folder)):
            self.assertEqual(t.evaluate(self.event('rsync -a host:/x /tmp/x'))['code'],2)

    def test_proof_validation_axes(self):
        cmd='rsync -a host:/x /tmp/x';items=[dict(host='host')];config={'hostname':['host']}
        route=dict(kind='lan-direct',samples=['x']);row=dict(host='host',config=t.digest(config),route=route,checked_lan=True,sample_bytes=1048576)
        proof=dict(schema=1,key=t.key(cmd,'/tmp'),at=1000,network='net',targets=[row])
        def check(p=proof,now=1001,net='net',configs=None,routes=None):
            return t.validate_proof(p,cmd,'/tmp',items,now,net,configs or [config],routes or [route])
        self.assertIsNone(check())
        for bad in (None,{},dict(proof,key='wrong'),dict(proof,at=None),dict(proof,at=0),dict(proof,at=2000),dict(proof,targets=None),dict(proof,targets=[]),dict(proof,network=None)):
            with self.subTest(bad=bad):self.assertIsNotNone(check(bad))
        self.assertIsNotNone(check(now=1121));self.assertIsNotNone(check(net='changed'))
        self.assertIsNotNone(check(configs=[{'hostname':['other']}]))
        self.assertIsNotNone(check(routes=[dict(kind='derp',samples=['relay'])]))
        for key in ('checked_lan','sample_bytes','host','config','route'):
            for value in (None,'',False):
                self.assertIsNotNone(check(dict(proof,targets=[dict(row,**{key:value})])))

    def test_remediation_allows_exact_command_only(self):
        cmd='rsync -a host:/x /tmp/x';event=self.event(cmd);items=t.transfers(cmd,'/tmp')
        config={'hostname':['host']};route=dict(kind='lan-direct',samples=['x'])
        proof=dict(schema=1,key=t.key(cmd,'/tmp'),at=1000,network='net',targets=[dict(host='host',config=t.digest(config),route=route,checked_lan=True,sample_bytes=1048576)])
        with tempfile.TemporaryDirectory() as folder, patch.object(t,'STATE',Path(folder)), patch.object(t.time,'time',return_value=1001), patch.object(t,'network',return_value='net'),patch.object(t,'current_routes',return_value=([config],[route])):
            self.assertEqual(t.evaluate(event)['code'],2)
            (Path(folder)/(t.key(cmd,'/tmp')+'.json')).write_text(json.dumps(proof))
            self.assertEqual(t.evaluate(event)['code'],0)
            self.assertEqual(t.evaluate(self.event(cmd+'2'))['code'],2)
            with patch.object(t.time,'time',return_value=1121):self.assertEqual(t.evaluate(event)['code'],2)

    def test_tailscale_labels_and_convergence(self):
        for text,expected in [('via 192.0.2.1:41641','wan-direct'),('via DERP(fra)','derp'),('via peer-relay(node)','peer-relay')]:
            raw='\n'.join('pong from test (100.64.0.1) '+text+' in 1ms' for _ in range(3))
            with patch.object(t,'run',return_value=raw),patch.object(t.shutil,'which',return_value='/bin/tailscale'),patch.object(t,'route_kind',return_value='wan-direct'):
                self.assertEqual(t.tailscale_path('100.64.0.1')['kind'],expected)
        with patch.object(t,'run',return_value='pong from test via mystery in 1ms'),patch.object(t.shutil,'which',return_value='/bin/tailscale'):
            with self.assertRaises(ValueError):t.tailscale_path('100.64.0.1')


    def test_live_preflight_wan_fallback_and_lan_preference(self):
        cmd='rsync -a host:/data /tmp/data';config={'hostname':['host'],'user':['tester']}
        observed=dict(sample_bytes=1048576,seconds=.1,socket_peer='198.51.100.1',sample_path=dict(kind='wan-direct',samples=['198.51.100.1']))
        with tempfile.TemporaryDirectory() as folder,patch.object(t,'STATE',Path(folder)),patch.object(t,'network',return_value='net'),patch.object(t,'ssh_options',return_value=config),patch.object(t,'target_route',return_value=dict(kind='wan-direct',samples=['198.51.100.1'])),patch.object(t,'sample',return_value=observed),patch.object(t,'run',return_value='node\ntester\n inet 192.0.2.9 netmask 0xffffff00') as probe,patch.object(t,'local_networks',return_value=[]):
            self.assertEqual(t.preflight(cmd,'/tmp')['status'],'ready')
            with patch.object(t,'local_networks',return_value=[ipaddress.ip_network('192.0.2.0/24')]):
                with self.assertRaisesRegex(ValueError,'verified LAN endpoint available'):t.preflight(cmd,'/tmp')
            self.assertFalse((Path(folder)/(t.key(cmd,'/tmp')+'.json')).exists())
            self.assertTrue(any(call.args[0][-2]=='host' and 'HostName=192.0.2.9' in call.args[0] for call in probe.call_args_list))
            with patch.object(t,'run',return_value='node\ntester\n'):
                with self.assertRaisesRegex(ValueError,'no addresses'):t.preflight(cmd,'/tmp')

    def test_linux_network_identity_ignores_lifetime_countdown(self):
        def addresses(lifetime,address='192.0.2.2'):
            return json.dumps([dict(ifname='eth0',flags=['UP'],operstate='UP',addr_info=[dict(family='inet',local=address,prefixlen=24,valid_life_time=lifetime,preferred_life_time=lifetime)])])
        with patch.object(t.sys,'platform','linux'),patch.object(t,'run',side_effect=[addresses(100),'[]',addresses(99),'[]',addresses(99,'192.0.2.3'),'[]']):
            first=t.network();self.assertEqual(first,t.network());self.assertNotEqual(first,t.network())

    def test_probe_safety_options_win_openssh_first_value_precedence(self):
        cmd='rsync -a -e "ssh -F /dev/null -o BatchMode=no -o StrictHostKeyChecking=no -o ConnectTimeout=99" host:/data /tmp/data'
        config={'hostname':['host'],'user':['tester']}
        observed=dict(sample_bytes=1048576,seconds=.1,socket_peer='198.51.100.1',sample_path=dict(kind='wan-direct',samples=['198.51.100.1']))
        with tempfile.TemporaryDirectory() as folder,patch.object(t,'STATE',Path(folder)),patch.object(t,'network',return_value='net'),patch.object(t,'ssh_options',return_value=config),patch.object(t,'target_route',return_value=dict(kind='wan-direct',samples=['198.51.100.1'])),patch.object(t,'sample',return_value=observed),patch.object(t,'run',return_value='node\ntester\n inet 192.0.2.9 netmask 0xffffff00') as probe,patch.object(t,'local_networks',return_value=[]):
            t.preflight(cmd,'/tmp')
            argv=probe.call_args_list[0].args[0]
        inspected=subprocess.run(['ssh','-G',*argv[1:-1]],capture_output=True,text=True,check=True)
        fields=dict(line.split(' ',1) for line in inspected.stdout.splitlines() if ' ' in line)
        self.assertEqual(fields['batchmode'],'yes')
        self.assertEqual(fields['stricthostkeychecking'],'true')
        self.assertEqual(fields['connecttimeout'],'4')


if __name__=='__main__':unittest.main()
