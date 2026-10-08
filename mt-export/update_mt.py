#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export the supplied Yuu SFA configuration to upstream MT 1.14 JSON.

Never starts sing-box, changes network settings, or tests proxy connections.
Online mode downloads node subscriptions only; --snapshots is fully offline.
Requires Python >=3.9. Pure Python JSON Schema dependencies are bundled.
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zipfile


class ExportError(Exception):
    pass


class HTTPSOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require(urllib.parse.urlsplit(newurl).scheme == 'https', 'subscription redirected to non-HTTPS URL')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def require(condition, message):
    if not condition:
        raise ExportError(message)


def parse_jsonc(text, label):
    # Only remove comments outside quoted strings. URLs and escaped quotes survive.
    token = r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?\*/'
    text = re.sub(token, lambda m: m[0] if m[0].startswith('"') else ' ', text)
    text = re.sub(r'("(?:\\.|[^"\\])*")|,(\s*[}\]])',
                  lambda m: m[1] if m[1] else m[2], text)
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, label + ': duplicate JSON key')
            result[key] = value
        return result
    def invalid_constant(value):
        raise ExportError(label + ': non-finite JSON number')
    try:
        return json.loads(text.lstrip('\ufeff'), object_pairs_hook=pairs,
                          parse_constant=invalid_constant)
    except json.JSONDecodeError as exc:
        raise ExportError(f'{label}: invalid JSON at line {exc.lineno}, column {exc.colno}') from None


def read_json(path, label):
    path = Path(path)
    try:
        return parse_jsonc(path.read_text(encoding='utf-8-sig', errors='strict'), label)
    except OSError as exc:
        raise ExportError(f'{label}: cannot read {path.absolute()} '
                          f'({type(exc).__name__}, errno={exc.errno}: {exc.strerror})') from exc
    except UnicodeError as exc:
        raise ExportError(f'{label}: invalid UTF-8 in {path.absolute()}') from exc


def items(value):
    return value if isinstance(value, list) else [value]


def compile_filter(pattern):
    """Supported Go regexp subset, including this config's 美国|(?i)DMIT.

    Do not attempt to accept arbitrary Go expressions with Python semantics.
    Non-ASCII case folding, POSIX classes and unsupported flags need review.
    """
    if not pattern:
        return None
    require(isinstance(pattern, str), 'filter must be a string')
    require(not re.search(r'\\[pPzQ]|\[\[:|\(\?[=!<]|\\[1-9]', pattern),
            'filter uses an unsupported regexp feature')
    if '(?i)' in pattern:
        require(pattern.count('(?i)') == 1, 'multiple inline (?i) flags need review')
        before, after = pattern.split('(?i)', 1)
        # Only a leading flag or a top-level alternative is supported.
        depth = 0
        escaped = False
        in_class = False
        for char in before:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '[':
                in_class = True
            elif char == ']':
                in_class = False
            elif not in_class and char == '(':
                depth += 1
            elif not in_class and char == ')':
                depth -= 1
        require(depth == 0 and not in_class, 'nested inline (?i) needs review')
        pattern = before + '(?i:' + after + ')'
    require(not re.search(r'\(\?(?!:|i:)', pattern), 'unsupported regexp flags')
    try:
        return re.compile(pattern, re.ASCII)
    except re.error:
        raise ExportError('invalid or unsupported filter regexp') from None


def filtered(nodes, include=None, exclude=None):
    yes, no = compile_filter(include), compile_filter(exclude)
    return [node for node in nodes
            if (not yes or yes.search(node['tag'])) and
               (not no or not no.search(node['tag']))]


def provider_nodes(document, label):
    if isinstance(document, dict):
        require(not document.get('endpoints'), label + ': endpoint subscriptions need manual migration')
        nodes = document.get('outbounds')
    else:
        nodes = document
    require(isinstance(nodes, list), label + ': expected sing-box JSON outbounds array; no YAML/base64 conversion')
    result, names = [], set()
    for node in nodes:
        require(isinstance(node, dict), label + ': invalid outbound object')
        # Match Yuu's sing-box subscription parser: ignore config-only outbounds.
        if node.get('type') in ('direct', 'block', 'dns', 'selector', 'urltest'):
            continue
        tag = node.get('tag')
        require(isinstance(tag, str) and tag, label + ': node missing tag')
        require(tag not in names, label + ': duplicate node tag')
        names.add(tag)
        result.append(copy.deepcopy(node))
    require(result, label + ': empty subscription')
    return result


def load_providers(config, snapshots, timeout, fetch=None, progress=None):
    definitions = config.get('outbound_providers', [])
    require(definitions, 'source configuration has no outbound_providers')
    result, audit = {}, []
    # Do not inherit HTTP_PROXY/HTTPS_PROXY. This source uses Direct-client.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), HTTPSOnlyRedirect())
    clients = {x['tag']: x for x in config.get('http_clients', [])}
    for p in definitions:
        name = p.get('tag')
        require(isinstance(name, str) and name and name not in result, 'missing or duplicate provider tag')
        require(not re.search(r'[/\\\x00]', name) and name not in ('.', '..'), 'unsafe provider filename')
        label = 'provider ' + name
        if progress:
            progress('下载订阅：' + name)
        require(p.get('type') == 'remote', label + ': only remote providers are supported')
        allowed = {'tag','type','url','path','initial_path','user_agent','http_client',
                   'download_detour','health_check','update_interval','include','exclude'}
        require(not (set(p) - allowed), label + ': unsupported provider options (including overrides)')
        if snapshots:
            directory = Path(snapshots)
            candidates = [directory/(name+'.json'), directory/(name+'.txt')]
            found = [x for x in candidates if x.is_file()]
            require(len(found) == 1, label + ': need exactly one snapshot .json or .txt')
            try:
                raw = found[0].read_bytes()
            except OSError:
                raise ExportError(label + ': cannot read snapshot') from None
        else:
            url = p.get('url', '')
            parsed = urllib.parse.urlsplit(url)
            require(parsed.scheme == 'https' and parsed.hostname, label + ': HTTPS URL required')
            http = p.get('http_client', {})
            if isinstance(http, str):
                require(http in clients, label + ': missing HTTP client')
                http = clients[http]
            require(isinstance(http, dict), label + ': invalid HTTP client')
            require(not (set(http)-{'tag','detour'}), label + ': custom HTTP client options need review')
            detour = http.get('detour', p.get('download_detour'))
            if detour:
                direct_tags = {x['tag'] for x in config.get('outbounds', []) if x.get('type') == 'direct'}
                require(detour in direct_tags, label + ': proxy detour cannot be reproduced by this downloader')
            req = urllib.request.Request(url, headers={'User-Agent':p.get('user_agent','sing-box/1.14.0')})
            try:
                if fetch is not None:
                    raw = fetch(url, p.get('user_agent','sing-box/1.14.0'))
                else:
                    with opener.open(req, timeout=timeout) as response:
                        require(urllib.parse.urlsplit(response.url).scheme == 'https', label + ': non-HTTPS redirect')
                        raw = response.read(20 * 1024 * 1024 + 1)
            except urllib.error.HTTPError as exc:
                raise ExportError(f'{label}: HTTP {exc.code}; old output kept') from None
            except (OSError, urllib.error.URLError, ValueError):
                raise ExportError(label + ': download failed; old output kept') from None
        require(len(raw) <= 20 * 1024 * 1024, label + ': subscription too large')
        try:
            document = parse_jsonc(raw.decode('utf-8-sig', errors='strict'), label)
        except UnicodeError:
            raise ExportError(label + ': subscription is not UTF-8 JSON') from None
        nodes = filtered(provider_nodes(document, label), p.get('include'), p.get('exclude'))
        require(nodes, label + ': provider filter produced no nodes')
        result[name] = nodes
        audit.append({'tag':name,'nodes':len(nodes),'sha256':hashlib.sha256(raw).hexdigest(),
                      'source':'snapshot' if snapshots else 'download'})
    return result, audit


def expand_nodes(config, providers):
    base = config.get('outbounds', [])
    require(isinstance(base,list), 'outbounds must be an array')
    global_tags = [x.get('tag') for x in base]
    require(all(isinstance(x,str) and x for x in global_tags), 'all base outbounds need tags')
    require(len(set(global_tags)) == len(global_tags), 'duplicate base outbound tag')
    global_tags = set(global_tags)
    mapping, by_original, exported = {}, {}, []
    for owner, nodes in providers.items():
        for raw in nodes:
            tag = owner + ' :: ' + raw['tag']
            require(tag not in global_tags and tag not in mapping.values(), 'generated tag collision')
            mapping[(owner, raw['tag'])] = tag
            by_original.setdefault(raw['tag'], []).append(tag)
    def resolve(tag, owner=None):
        require(isinstance(tag,str), 'outbound reference must be a string')
        local = mapping.get((owner,tag))
        if tag in global_tags:
            require(not local, 'ambiguous local/global outbound reference: ' + tag)
            return tag
        if local:
            return local
        if tag in mapping.values():
            return tag
        matches = by_original.get(tag, [])
        require(len(matches) == 1, 'missing or ambiguous outbound reference: ' + tag)
        return matches[0]
    for owner, nodes in providers.items():
        for raw in nodes:
            node = copy.deepcopy(raw)
            node['tag'] = mapping[(owner,raw['tag'])]
            if node.get('detour'):
                node['detour'] = resolve(node['detour'], owner)
            exported.append(node)
    groups = []
    for node in base:
        if node.get('detour'):
            node['detour'] = resolve(node['detour'])
        if node.get('type') not in ('selector','urltest'):
            continue
        members = [resolve(tag) for tag in node.get('outbounds', [])]
        sources = list(providers) if node.get('use_all_providers') else node.get('providers', [])
        require(isinstance(sources,list), 'group providers must be an array')
        require(sources or not (node.get('include') or node.get('exclude')), 'filter without providers needs review')
        for owner in sources:
            require(owner in providers, 'group references missing provider: '+owner)
            members.extend(mapping[(owner,raw['tag'])] for raw in filtered(
                providers[owner],node.get('include'),node.get('exclude')))
        node['outbounds'] = list(dict.fromkeys(members))
        require(node['outbounds'], 'empty group: '+node['tag'])
        if node.get('default'):
            node['default'] = resolve(node['default'])
            require(node['default'] in node['outbounds'], 'group default is not a member')
        for key in ('providers','include','exclude','use_all_providers'):
            node.pop(key,None)
        groups.append({'tag':node['tag'],'count':len(node['outbounds']),'members':node['outbounds']})
    config['outbounds'] = base + exported
    config.pop('outbound_providers',None)
    # References outside nodes may also address a provider node by original tag.
    def rewrite(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('outbound','detour','external_ui_download_detour','download_detour') and isinstance(item,str) and item:
                    value[key] = resolve(item)
                else:
                    rewrite(item)
        elif isinstance(value,list):
            for item in value: rewrite(item)
    for key,value in config.items():
        if key != 'outbounds': rewrite(value)
    return groups, len(exported)


def inline_rules(config, config_path, rules_zip, reader=None):
    converted = []
    z = None
    if rules_zip:
        try:
            z = zipfile.ZipFile(rules_zip)
        except (OSError,zipfile.BadZipFile):
            raise ExportError('cannot read rule providers ZIP') from None
    try:
        for definition in config.get('route',{}).get('rule_set',[]):
            if definition.get('type') != 'local':
                converted.append(definition)
                continue
            require(definition.get('format','source') == 'source', 'local binary rule-set cannot be embedded as JSON')
            require(set(definition) <= {'type','tag','format','path'}, 'local rule-set options need review')
            for tag in items(definition['tag']):
                path = definition['path'].replace('{tag}',tag)
                if z:
                    name = path.replace('\\','/')
                    if name.startswith('./'): name = name[2:]
                    require(name in z.namelist(), 'rule file missing in ZIP: '+name)
                    try:
                        document = parse_jsonc(z.read(name).decode('utf-8-sig', errors='strict'), 'rule '+tag)
                    except UnicodeError:
                        raise ExportError('rule is not UTF-8: '+tag) from None
                else:
                    document = (reader or read_json)(config_path.parent/path, 'rule '+tag)
                require(isinstance(document,dict) and isinstance(document.get('rules'),list) and document['rules'], 'invalid or empty rule-set: '+tag)
                require(document.get('version') in (1,2,3,4), 'unsupported source rule-set version: '+tag)
                converted.append({'type':'inline','tag':tag,'rules':document['rules']})
    finally:
        if z: z.close()
    config.setdefault('route',{})['rule_set'] = converted


def is_ipv6_guard(rule):
    if rule.get('type') != 'logical' or rule.get('mode') != 'and':
        return False
    clauses = rule.get('rules',[])
    if len(clauses) != 2:
        return False
    has_v6 = any(x == {'ip_version':6} for x in clauses)
    has_interface = any(set(x) == {'default_interface_address','invert'} and x['invert'] is True
                        and items(x['default_interface_address']) == ['2000::/3'] for x in clauses)
    return has_v6 and has_interface and (
        (rule.get('action') == 'reject' and set(rule) <= {'type','mode','rules','action'}) or
        (rule.get('action') == 'predefined' and rule.get('rcode') == 'NOERROR'
         and set(rule) <= {'type','mode','rules','action','rcode'}))


def platform_cleanup(config, resolve_mode, keep_services):
    changes = []
    for section in ('dns','route'):
        rules = config.get(section,{}).get('rules',[])
        retained = []
        for rule in rules:
            if is_ipv6_guard(rule):
                changes.append(section+': removed desktop interface IPv6 guard; dual stack retained')
                continue
            if section == 'route' and 'match_only' in rule:
                require(rule.get('action') == 'resolve', 'match_only outside resolve')
                match_only = rule.pop('match_only')
                require(isinstance(match_only,bool), 'match_only must be boolean')
                if match_only and resolve_mode == 'remove':
                    changes.append('route: removed match_only resolve; domain IP-classification fallback changes')
                    continue
                if match_only:
                    resolver = config['route'].get('default_domain_resolver')
                    server = resolver.get('server') if isinstance(resolver,dict) else resolver
                    require(rule.get('server') or server, 'resolve requires an explicit real DNS server')
                    rule.setdefault('server',server)
                    changes.append('route: ordinary resolve; resolved IPs can affect subsequent dialing')
            retained.append(rule)
        config.setdefault(section,{})['rules'] = retained
    config['route'].pop('concurrent_dial',None)
    config.setdefault('experimental',{}).pop('urltest_unified_delay',None)
    changes.append('removed concurrent_dial and urltest_unified_delay')
    inbounds = []
    for inbound in config.get('inbounds',[]):
        if inbound.get('type') == 'tun':
            for key in ('interface_name','auto_redirect'):
                inbound.pop(key,None)
        elif not keep_services:
            changes.append('removed optional inbound: '+inbound.get('tag',inbound.get('type','unknown')))
            continue
        inbounds.append(inbound)
    config['inbounds'] = inbounds
    require(any(x.get('type') == 'tun' for x in inbounds), 'no TUN inbound')
    config.setdefault('log',{}).pop('output',None)
    cache = config['experimental'].get('cache_file',{})
    cache.pop('path',None)
    if not keep_services:
        config['experimental'].pop('clash_api',None)
        config['experimental'].pop('v2ray_api',None)
    changes.append('using application log/cache paths; source DoQ, IPv6, FakeIP pools retained')
    return changes


def check_references(config):
    def tagged(objects, label):
        result = set()
        for obj in objects:
            for tag in items(obj.get('tag',[])):
                require(isinstance(tag,str) and tag and tag not in result, 'invalid/duplicate '+label+' tag')
                result.add(tag)
        return result
    out = tagged(config.get('outbounds',[]), 'outbound')
    dns = tagged(config.get('dns',{}).get('servers',[]), 'DNS')
    rs = tagged(config.get('route',{}).get('rule_set',[]), 'rule-set')
    http = tagged(config.get('http_clients',[]), 'HTTP client')
    inbound = tagged(config.get('inbounds',[]), 'inbound')
    def refs(value, registry, label):
        for ref in items(value):
            require(ref in registry, 'missing '+label+' reference: '+str(ref))
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                require(key not in {'providers','include','exclude','use_all_providers','match_only','outbound_providers','concurrent_dial','urltest_unified_delay','default_interface_address','network_interface_address','domain_match_strategy','default_domain_match_strategy'}, 'unhandled fork/platform field: '+key)
                if key in ('detour','outbound','download_detour','external_ui_download_detour') and item:
                    refs(item,out,'outbound')
                if key in ('http_client','default_http_client') and isinstance(item,str) and item:
                    refs(item,http,'HTTP client')
                if key in ('domain_resolver','default_domain_resolver') and item:
                    refs(item.get('server') if isinstance(item,dict) else item,dns,'DNS')
                walk(item)
        elif isinstance(value,list):
            for item in value: walk(item)
    walk(config)
    def rules(values, dns_rules=False):
        for rule in values:
            if 'rule_set' in rule: refs(rule['rule_set'],rs,'rule-set')
            if 'inbound' in rule: refs(rule['inbound'],inbound,'inbound')
            if rule.get('server'): refs(rule['server'],dns,'DNS')
            if rule.get('rules'): rules(rule['rules'],dns_rules)
    rules(config.get('route',{}).get('rules',[]))
    rules(config.get('dns',{}).get('rules',[]),True)
    if config['route'].get('final'): refs(config['route']['final'],out,'outbound')
    if config['dns'].get('final'): refs(config['dns']['final'],dns,'DNS')
    edges = {}
    for node in config['outbounds']:
        targets = list(node.get('outbounds',[]))
        if node.get('detour'): targets.append(node['detour'])
        refs(targets,out,'outbound')
        if node.get('type') in ('selector','urltest'):
            require(node.get('outbounds'), 'empty outbound group')
            if node.get('default'): require(node['default'] in targets,'default is outside group')
        edges[node['tag']] = targets
    done, visiting = set(), set()
    def visit(tag):
        require(tag not in visiting,'selector/detour cycle at '+tag)
        if tag in done: return
        visiting.add(tag)
        for target in edges[tag]: visit(target)
        visiting.remove(tag)
        done.add(tag)
    for tag in edges: visit(tag)


def schema_validator():
    vendor = Path(__file__).with_name('vendor')
    if vendor.is_dir():
        sys.path.insert(0,str(vendor))
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        raise ExportError('missing vendor dependencies; extract the complete tool ZIP') from None
    schema = read_json(Path(__file__).with_name('sing-box-1.14.schema.json'),'bundled schema')
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(config, validator):
    errors = list(validator.iter_errors(config))
    if errors:
        # Schema messages can contain passwords or whole node objects. Never print them.
        paths = ['/'.join(map(str,e.absolute_path)) or '<root>' for e in errors[:8]]
        raise ExportError('upstream 1.14 schema validation failed at: '+', '.join(paths))
    check_references(config)


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    text = json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',errors='strict',newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True,help='source SFA JSON/JSONC')
    parser.add_argument('--output',type=Path,required=True,help='MT JSON output (atomic replacement)')
    parser.add_argument('--rules-zip',type=Path,help='ZIP containing RuleProviders/*.json; otherwise read relative to source config')
    parser.add_argument('--snapshots',type=Path,help='offline mode: provider-tag.json or .txt; NEVER downloads')
    parser.add_argument('--resolve-mode',choices=['ordinary','remove'],default='ordinary')
    parser.add_argument('--keep-local-services',action='store_true',help='keep non-TUN inbounds and Clash/V2Ray APIs')
    parser.add_argument('--timeout',type=float,default=40)
    args = parser.parse_args(argv)
    require(args.timeout > 0,'timeout must be positive')
    report_path = args.output.with_suffix(args.output.suffix+'.report.json')
    protected = {args.config.resolve(),Path(__file__).resolve(),Path(__file__).with_name('sing-box-1.14.schema.json').resolve()}
    if args.rules_zip: protected.add(args.rules_zip.resolve())
    require(args.output.resolve() not in protected and report_path.resolve() not in protected,'output would overwrite input/tool')
    require(not args.output.is_symlink() and not report_path.is_symlink(),'output paths must not be symlinks')
    validator = schema_validator()  # Fail before network activity if prerequisites are missing.
    source = read_json(args.config,'source config')
    require(isinstance(source,dict),'source must be a JSON object')
    if args.snapshots:
        for provider in source.get('outbound_providers',[]):
            for suffix in ('.json','.txt'):
                protected.add((args.snapshots/(provider.get('tag','')+suffix)).resolve())
    if not args.rules_zip:
        for definition in source.get('route',{}).get('rule_set',[]):
            if definition.get('type') == 'local':
                for tag in items(definition.get('tag',[])):
                    protected.add((args.config.resolve().parent/definition['path'].replace('{tag}',tag)).resolve())
    require(args.output.resolve() not in protected and report_path.resolve() not in protected,'output would overwrite a provider/rule input')
    config = copy.deepcopy(source)
    providers, provider_audit = load_providers(source,args.snapshots,args.timeout)
    groups, count = expand_nodes(config,providers)
    inline_rules(config,args.config.resolve(),args.rules_zip)
    changes = platform_cleanup(config,args.resolve_mode,args.keep_local_services)
    validate(config,validator)
    report = {'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'target_schema':'upstream v1.14.0 / MT with corresponding core capabilities',
              'mode':'offline' if args.snapshots else 'subscription-download',
              'validation':'JSON Schema 2020-12 + references + selector/detour acyclicity; no core execution',
              'proxy_nodes':count,'providers':provider_audit,'groups':groups,'changes':changes,
              'limitations':['no device, connectivity, certificate or remote SRS validation',
                             'provider health checks and automatic node updates are not exported',
                             'remote rule-sets keep their existing refresh behavior']}
    # Publish config last: download/parse/filter/schema/reference failures leave it untouched.
    atomic_json(report_path,report)
    atomic_json(args.output,config)
    print(f'OK: {count} nodes, {len(groups)} groups; schema and references valid. No core executed.')
    print('Config: '+str(args.output))
    print('Report: '+str(report_path))
    return 0


if __name__ == '__main__':
    # Also applies when invoked directly without the Android shell launcher.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='strict')
    try:
        sys.exit(main())
    except Exception:
        # Include chained causes and unexpected exceptions for on-device debugging.
        # SystemExit (including argparse --help) and KeyboardInterrupt are unaffected.
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
