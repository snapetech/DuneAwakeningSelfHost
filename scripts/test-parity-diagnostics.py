#!/usr/bin/env python3
import base64, importlib.util, json, os, pathlib, subprocess, sys, tempfile, unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path); value=importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
PEERS=module('peers',ROOT/'scripts/game-peer-diagnostics.py')
REMOTE=module('remote',ROOT/'scripts/remote-targets.py')

class Tests(unittest.TestCase):
 def test_peer_addresses_coarsen_and_filter(self):
  lines=['ipv4 2 udp 17 20 src=203.0.113.42 dst=192.0.2.1 sport=50000 dport=7777 [UNREPLIED] src=192.0.2.1 dst=203.0.113.42 sport=7777 dport=50000',
         'ipv4 2 tcp 6 100 ESTABLISHED src=198.51.100.8 dst=192.0.2.1 sport=5555 dport=22']
  self.assertEqual(PEERS.parse(lines,PEERS.ranges('7777-7810'),False)[0]['peer'],'203.0.113.0/24')
  self.assertEqual(PEERS.parse(lines,PEERS.ranges('7777-7810'),True)[0]['peer'],'203.0.113.42')
 def test_remote_config_rejects_relative_secrets(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'x.json'; p.write_text(json.dumps({'schemaVersion':1,'targets':[{'id':'a','host':'a.test','port':22,'user':'dash','expectedHostname':'a','identityFile':'relative','knownHostsFile':'/tmp/known','adminRemotePort':1,'adminLocalPort':2}]}))
   with self.assertRaises(ValueError): REMOTE.load_config(p)
 def test_remote_ssh_is_strict(self):
  args=REMOTE.ssh_base({'port':22,'identityFile':'/tmp/key','knownHostsFile':'/tmp/known'})
  self.assertIn('StrictHostKeyChecking=yes',args); self.assertIn('ClearAllForwardings=yes',args)
 def test_remote_rotation_mutator_adds_backs_up_and_removes(self):
  old_blob=base64.b64encode(b'o'*32).decode(); new_blob=base64.b64encode(b'n'*32).decode()
  old_line=f'ssh-ed25519 {old_blob} old'; new_line=f'ssh-ed25519 {new_blob} new'
  with tempfile.TemporaryDirectory() as td:
   home=pathlib.Path(td); ssh=home/'.ssh'; ssh.mkdir(mode=0o700)
   authorized=ssh/'authorized_keys'; authorized.write_text(old_line+'\n',encoding='utf-8')
   env={**os.environ,'HOME':str(home)}
   encoded_old=base64.b64encode(old_blob.encode()).decode()
   encoded_new=base64.b64encode(new_line.encode()).decode()
   for action in ('add','remove'):
    subprocess.run([sys.executable,'-c',REMOTE.REMOTE_ROTATE,action,encoded_old,encoded_new],
                   env=env,check=True,capture_output=True,text=True)
   lines=authorized.read_text(encoding='utf-8').splitlines()
   self.assertEqual([line.split()[1] for line in lines],[new_blob])
   self.assertEqual(len(list(ssh.glob('authorized_keys.before-add-*'))),1)
   self.assertEqual(len(list(ssh.glob('authorized_keys.before-remove-*'))),1)
   self.assertEqual(oct(authorized.stat().st_mode & 0o777),'0o600')
 def test_cvar_catalog_invariants(self):
  data=json.loads((ROOT/'config/cvar-catalog.json').read_text())
  self.assertEqual(data['entryCount'],len(data['entries']))
  self.assertGreater(data['entryCount'],3000)
  self.assertEqual(len(data['binarySha256']),64)
  self.assertEqual(len({row['name'] for row in data['entries']}),data['entryCount'])

if __name__=='__main__': unittest.main()
