import base64
import copy
import gzip
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'mt-export'), str(ROOT/'android-mt/app/src/main/python')]
import update_mt as tool
import mobile_bridge as mobile
import qrs_profile as qrs
from test_update_mt import source, node


class FakeBridge:
    def __init__(self, config=None):
        self.config = config or source()
        self.files = {'/sfa/config.json': json.dumps(self.config, ensure_ascii=False).encode('utf-8')}
        self.events = []
        self.fetches = []
    def progress(self, message): self.events.append(message)
    def readBase64(self, path):
        path = path.replace('\\', '/')
        return base64.b64encode(self.files[path]).decode('ascii')
    def fetchBase64(self, url, ua):
        self.fetches.append((url, ua))
        return base64.b64encode(json.dumps({'outbounds': [node('日本 🇯🇵'), node('美国')]}).encode()).decode()


def invoke(bridge, **kwargs):
    return json.loads(mobile.run(bridge, '/sfa/config.json', '测试 🇯🇵', kwargs.get('mode','ordinary'),
                                 kwargs.get('keep',False), kwargs.get('check',False), kwargs.get('base','')))


class MobileTests(unittest.TestCase):
    def test_separate_rule_directory_and_absolute_rule_path(self):
        config = source()
        config['route']['rule_set'] = [
            {'type':'local','tag':'A','path':'RuleProviders/A.json','format':'source'},
            {'type':'local','tag':'B','path':'/absolute/B.json','format':'source'}]
        bridge = FakeBridge(config)
        raw = b'{"version":3,"rules":[{"domain":["example.invalid"]}]}'
        bridge.files['/shared/RuleProviders/A.json'] = raw
        bridge.files['/absolute/B.json'] = raw
        self.assertFalse(invoke(bridge, check=True)['ok'])
        result = invoke(bridge, base='/shared', check=True)
        self.assertTrue(result['ok'], result)
        self.assertEqual(bridge.fetches, [])
        result = invoke(bridge, base='/shared')
        self.assertTrue(result['ok'], result)
        self.assertEqual([r['type'] for r in json.loads(result['config'])['route']['rule_set']], ['inline','inline'])

    def test_relative_rule_base_is_rejected(self):
        bridge = FakeBridge()
        self.assertFalse(invoke(bridge, base='relative', check=True)['ok'])
        self.assertEqual(bridge.fetches, [])

    def test_conversion_uses_original_engine(self):
        bridge = FakeBridge()
        result = invoke(bridge)
        self.assertTrue(result['ok'], result)
        expected = copy.deepcopy(bridge.config)
        tool.inline_rules(expected, Path('/sfa/config.json'), None)
        tool.expand_nodes(expected, {'P':[node('日本 🇯🇵'), node('美国')]})
        tool.platform_cleanup(expected, 'ordinary', False)
        self.assertEqual(json.loads(result['config']), expected)
        self.assertEqual(result['nodes'], 2)
        self.assertTrue(result['frames'])

    def test_check_reads_rules_but_never_downloads(self):
        config = source()
        config['route']['rule_set'] = [{'type':'local', 'tag':['A','B'], 'path':'rules/{tag}.json', 'format':'source'}]
        bridge = FakeBridge(config)
        for name in ('A','B'):
            bridge.files['/sfa/rules/'+name+'.json'] = b'{"version":3,"rules":[{"domain":["example.invalid"]}]}'
        self.assertTrue(invoke(bridge, check=True)['ok'])
        self.assertEqual(bridge.fetches, [])
        del bridge.files['/sfa/rules/B.json']
        self.assertFalse(invoke(bridge, check=True)['ok'])
        self.assertEqual(bridge.fetches, [])

    def test_errors_do_not_disclose_url_or_arbitrary_exception(self):
        bridge = FakeBridge()
        bridge.fetchBase64 = mock.Mock(side_effect=RuntimeError('java.io.IOException MTB_HTTP:403 https://example.invalid/?secret=PASSWORD'))
        result = invoke(bridge)
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'], 'MTB_HTTP:403')
        self.assertNotIn('PASSWORD', json.dumps(result))
        self.assertIn('mobile_bridge.py', result['trace'])

    def test_utf8_errors_and_duplicate_keys_fail(self):
        for raw in (b'\xff', b'{"a":1,"a":2}'):
            bridge = FakeBridge(); bridge.files['/sfa/config.json'] = raw
            self.assertFalse(invoke(bridge)['ok'])
            self.assertFalse(bridge.fetches)

    def test_unknown_fields_keep_schema_validation(self):
        bridge = FakeBridge()
        bridge.fetchBase64 = lambda *args: base64.b64encode(json.dumps({'outbounds':[node('A', unknown='PRIVATE_VALUE')]}).encode()).decode()
        result = invoke(bridge)
        self.assertFalse(result['ok'])
        self.assertIn('schema validation', result['message'])
        self.assertNotIn('PRIVATE_VALUE', json.dumps(result))

    def test_modes_remain_available(self):
        result = invoke(FakeBridge(), mode='remove')
        self.assertTrue(result['ok'])
        self.assertEqual(json.loads(result['config'])['route']['rules'], [])

    def test_qrs_envelope_and_bpf(self):
        config = json.dumps({'tag':'中文 🇯🇵', 'large':'abcdef'*2000}, ensure_ascii=False)
        frames = qrs.frames(config, '配置 🇯🇵', 100)
        blocks = [base64.b64decode(frame.split('#')[1]) for frame in frames]
        header = struct.unpack('<IIIII', blocks[0][:20])
        k, length, checksum = header[2:]
        wrapped = zlib.decompress(b''.join(b[20:] for b in blocks)[:length])
        self.assertEqual(checksum, zlib.crc32(wrapped) ^ k)
        n = struct.unpack('>I', wrapped[:4])[0]
        meta = json.loads(wrapped[4:4+n])
        size = struct.unpack('>I', wrapped[4+n:8+n])[0]
        bpf = wrapped[8+n:]
        self.assertEqual(len(bpf),size)
        self.assertEqual(bpf[:2],b'\x03\x01')
        raw = gzip.decompress(bpf[2:])
        self.assertIn(config.encode('utf-8'),raw)
        self.assertEqual(meta['filename'],'MT.bpf')

    @unittest.skipUnless((ROOT/'analysis/private-providers').is_dir(), 'private snapshots not available')
    def test_workspace_snapshot_matches_exporter(self):
        original = tool.read_json(ROOT/'config_sfa.json','source')
        bridge = FakeBridge(original)
        with zipfile.ZipFile(ROOT/'RuleProviders.zip') as archive:
            for name in archive.namelist():
                if name.endswith('.json'): bridge.files['/sfa/'+name] = archive.read(name)
        raw_by_url = {}
        for provider in original['outbound_providers']:
            candidates = [(ROOT/'analysis/private-providers'/(provider['tag']+ext)) for ext in ('.json','.txt')]
            raw_by_url[provider['url']] = next(p for p in candidates if p.is_file()).read_bytes()
        bridge.fetchBase64 = lambda url, ua: base64.b64encode(raw_by_url[url]).decode()
        actual = invoke(bridge)
        self.assertTrue(actual['ok'], {k:v for k,v in actual.items() if k not in ('config','frames')})
        providers, _ = tool.load_providers(original, ROOT/'analysis/private-providers',40)
        expected = copy.deepcopy(original)
        tool.expand_nodes(expected,providers)
        tool.inline_rules(expected,ROOT/'config_sfa.json',ROOT/'RuleProviders.zip')
        tool.platform_cleanup(expected,'ordinary',False)
        tool.validate(expected,tool.schema_validator())
        self.assertEqual(json.loads(actual['config']),expected)
        self.assertEqual(actual['nodes'],87)
        self.assertEqual(actual['groups'],14)


if __name__ == '__main__': unittest.main()
