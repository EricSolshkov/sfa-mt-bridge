"""Offline tests: synthetic subscriptions only; no core or endpoint access."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import update_mt as tool


def node(tag, **extra):
    return dict(type='shadowsocks', tag=tag, server='192.0.2.1', server_port=443,
                method='chacha20-ietf-poly1305', password='synthetic-test-password', **extra)


def source():
    return {
        'dns': {'servers':[{'tag':'Local-Dns','type':'quic','server':'192.0.2.53'},
                            {'tag':'FakeDns','type':'fakeip','inet4_range':'198.18.0.0/15','inet6_range':'fc00::/18'}],
                'rules':[{'query_type':['A','AAAA'],'server':'FakeDns'}]},
        'inbounds':[{'type':'tun','tag':'tun','address':['172.19.0.1/24','fdfe:dcba:9876::1/126'],
                     'stack':'system','dns_mode':'hijack','auto_route':True,'auto_redirect':True,'interface_name':'source'}],
        'outbounds':[{'type':'direct','tag':'Direct'},
                     {'type':'selector','tag':'Proxy','providers':['P']}],
        'outbound_providers':[{'type':'remote','tag':'P','url':'https://example.invalid/sub?token=never-log-this'}],
        'route':{'final':'Proxy','default_domain_resolver':{'server':'Local-Dns'},
                 'rules':[{'action':'resolve','match_only':True}], 'concurrent_dial':True},
        'experimental':{'urltest_unified_delay':True}
    }


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = tool.schema_validator()

    def test_jsonc_preserves_urls_regex_and_rejects_duplicate_keys(self):
        value = tool.parse_jsonc('{"url":"https://a/b//c",/* hi */"x":[1,],}', 'test')
        self.assertEqual(value,{'url':'https://a/b//c','x':[1]})
        with self.assertRaises(tool.ExportError): tool.parse_jsonc('{"a":1,"a":2}', 'test')

    def test_go_flags_and_exclusion(self):
        nodes = [node('美国 A'),node('US dmit'),node('🇺🇸 Hawaii'),node('美国 DMIT')]
        result = tool.filtered(nodes,'美国|(?i)DMIT','(?i)DMIT$')
        self.assertEqual([x['tag'] for x in result],['美国 A'])

    def test_fixed_members_are_not_filtered(self):
        config = {'outbounds':[{'type':'direct','tag':'Direct'},
                  {'type':'selector','tag':'Emby','outbounds':['Direct'],'providers':['P'],'include':'AWS'}]}
        tool.expand_nodes(config,{'P':[node('AWS'),node('Other')]})
        self.assertEqual(config['outbounds'][1]['outbounds'],['Direct','P :: AWS'])

    def test_same_provider_detour_is_renamed(self):
        config = {'outbounds':[{'type':'direct','tag':'Direct'}]}
        tool.expand_nodes(config,{'P':[node('first',detour='second'),node('second')]})
        self.assertEqual(config['outbounds'][1]['detour'],'P :: second')

    def test_duplicate_and_ambiguous_names(self):
        with self.assertRaises(tool.ExportError):
            tool.provider_nodes({'outbounds':[node('A'),node('A')]},'P')
        config = {'outbounds':[{'type':'selector','tag':'Group','outbounds':['A']}]}
        with self.assertRaises(tool.ExportError):
            tool.expand_nodes(config,{'P':[node('A')],'Q':[node('A')]})

    def test_empty_group_stops_export(self):
        config = {'outbounds':[{'type':'selector','tag':'Group','providers':['P'],'include':'no-match'}]}
        with self.assertRaises(tool.ExportError): tool.expand_nodes(config,{'P':[node('A')]})

    def test_cycle_and_missing_reference(self):
        config = {'dns':{},'route':{},'outbounds':[
            {'type':'selector','tag':'Group','outbounds':['N']},node('N',detour='Group')]}
        with self.assertRaises(tool.ExportError): tool.check_references(config)
        config['outbounds'][1]['detour']='missing'
        with self.assertRaises(tool.ExportError): tool.check_references(config)

    def test_platform_cleanup_keeps_doq_and_dual_stack(self):
        config=source()
        guard={'type':'logical','mode':'and','rules':[{'ip_version':6},
               {'default_interface_address':'2000::/3','invert':True}],'action':'reject'}
        config['route']['rules'].insert(0,guard)
        tool.platform_cleanup(config,'ordinary',False)
        self.assertEqual(config['dns']['servers'][0]['type'],'quic')
        self.assertEqual(config['dns']['rules'][0]['query_type'],['A','AAAA'])
        self.assertEqual(config['inbounds'][0]['address'][1],'fdfe:dcba:9876::1/126')
        self.assertEqual(config['inbounds'][0]['stack'],'system')
        self.assertNotIn('auto_redirect',config['inbounds'][0])
        self.assertEqual(config['route']['rules'],[{'action':'resolve','server':'Local-Dns'}])

    def test_unknown_fields_fail_without_password_disclosure(self):
        config=source()
        tool.expand_nodes(config,{'P':[node('A',unsupported='TOP-SECRET')]})
        tool.platform_cleanup(config,'ordinary',False)
        with self.assertRaises(tool.ExportError) as error: tool.validate(config,self.validator)
        self.assertNotIn('TOP-SECRET',str(error.exception))
        self.assertNotIn('synthetic-test-password',str(error.exception))

    def test_failed_download_keeps_last_good_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); config=directory/'source.json'; out=directory/'output.json'
            config.write_text(json.dumps(source()),encoding='utf8'); out.write_text('LAST-GOOD',encoding='utf8')
            opener=mock.Mock(); opener.open.side_effect=OSError('contains-secret-url')
            with mock.patch.object(tool.urllib.request,'build_opener',return_value=opener):
                with self.assertRaises(tool.ExportError) as error:
                    tool.main(['--config',str(config),'--output',str(out)])
            self.assertEqual(out.read_text(encoding='utf-8'),'LAST-GOOD')
            self.assertNotIn('secret-url',str(error.exception))
            self.assertNotIn('never-log-this',str(error.exception))

    def test_output_cannot_overwrite_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); config=directory/'source.json'
            snapshots=directory/'snapshots'; snapshots.mkdir()
            config.write_text(json.dumps(source()),encoding='utf8')
            snapshot=snapshots/'P.json'; snapshot.write_text('PROTECTED',encoding='utf8')
            with self.assertRaises(tool.ExportError):
                tool.main(['--config',str(config),'--output',str(snapshot),'--snapshots',str(snapshots)])
            self.assertEqual(snapshot.read_text(encoding='utf-8'),'PROTECTED')

    def test_https_downgrade_blocked_before_redirect(self):
        handler=tool.HTTPSOnlyRedirect()
        with self.assertRaises(tool.ExportError):
            handler.redirect_request(None,None,302,'',{},'http://example.invalid/token')

    def test_inline_rule_import_and_remove_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); config=source()
            (directory/'RuleProviders').mkdir()
            (directory/'RuleProviders'/'local.json').write_text(
                '{"version":3,"rules":[{"domain_suffix":["example.com",],},],}',encoding='utf8')
            config['route']['rule_set']=[{'type':'local','tag':['local'],'format':'source','path':'RuleProviders/{tag}.json'}]
            tool.inline_rules(config,directory/'config.json',None)
            self.assertEqual(config['route']['rule_set'],[{'type':'inline','tag':'local','rules':[{'domain_suffix':['example.com']}]}])
            tool.platform_cleanup(config,'remove',False)
            self.assertEqual(config['route']['rules'],[])

    def test_offline_export_keeps_naive_and_never_fetches(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); config=directory/'source.json'; out=directory/'output.json'
            snapshots=directory/'snapshots'; snapshots.mkdir()
            config.write_text(json.dumps(source()),encoding='utf8')
            snapshots.joinpath('P.json').write_text(json.dumps({'outbounds':[node('SS'),{
                'type':'naive','tag':'Naive','server':'192.0.2.2','server_port':443,
                'username':'test','password':'test','tls':{'enabled':True}}]}),encoding='utf8')
            opener=mock.Mock(); opener.open.side_effect=AssertionError('network forbidden in offline test')
            with mock.patch.object(tool.urllib.request,'build_opener',return_value=opener):
                tool.main(['--config',str(config),'--output',str(out),'--snapshots',str(snapshots)])
            self.assertFalse(opener.open.called)
            result=json.loads(out.read_text(encoding='utf8'))
            self.assertEqual(result['outbounds'][-1]['type'],'naive')
            self.assertEqual(result['route']['rules'][0]['server'],'Local-Dns')
            tool.validate(result,self.validator)


if __name__=='__main__': unittest.main()
