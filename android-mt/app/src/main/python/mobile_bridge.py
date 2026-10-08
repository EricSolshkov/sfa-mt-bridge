"""Thin mobile I/O adapter; conversion stays in workspace mt-export/update_mt.py."""
import base64
import copy
import datetime
import json
import os
from pathlib import Path
import re
import traceback

import update_mt as tool
from qrs_profile import frames


def scrub(message):
    message = re.sub(r'https?://[^\s\"\'<>]+', '[URL 已隐藏]', str(message))
    return message[:3000]


def run(bridge, source_path, profile_name, resolve_mode, keep_services, check_only=False, rules_base=''):
    stage = '初始化'
    try:
        def progress(value):
            nonlocal stage
            stage = value
            bridge.progress(value)

        def reader(path, label):
            absolute = os.path.normpath(str(path))
            progress('读取：' + label + '\n' + absolute)
            raw = base64.b64decode(str(bridge.readBase64(absolute)), validate=True)
            try:
                return tool.parse_jsonc(raw.decode('utf-8-sig', errors='strict'), label)
            except UnicodeError:
                raise tool.ExportError(label + ': 文件不是 UTF-8') from None

        def fetch(url, user_agent):
            return base64.b64decode(str(bridge.fetchBase64(url, user_agent)), validate=True)

        tool.require(resolve_mode in ('ordinary', 'remove'), '无效 resolve 策略')
        tool.require(source_path.startswith('/') and '\x00' not in source_path,
                     '请填写 Android 配置文件的完整绝对路径')
        source_path = Path(os.path.normpath(source_path))
        tool.require(not rules_base or (rules_base.startswith('/') and '\x00' not in rules_base),
                     '规则基准目录必须是 Android 绝对路径，或留空使用主配置目录')
        rule_context = Path(os.path.normpath(rules_base)) / '_config.json' if rules_base else source_path
        source = reader(source_path, '主配置')
        tool.require(isinstance(source, dict), '源配置必须是 JSON 对象')
        config = copy.deepcopy(source)
        # Read rules first to surface path/root errors before subscription requests.
        tool.inline_rules(config, rule_context, None, reader=reader)
        if check_only:
            return json.dumps({'ok': True, 'checked': True,
                               'message': '配置和全部本地规则可读取；未下载订阅。'}, ensure_ascii=False)
        progress('加载完整配置校验器')
        validator = tool.schema_validator()
        providers, audit = tool.load_providers(source, None, 40, fetch=fetch, progress=progress)
        progress('展开节点与分组')
        groups, count = tool.expand_nodes(config, providers)
        changes = tool.platform_cleanup(config, resolve_mode, bool(keep_services))
        progress('校验配置、引用和链路循环')
        tool.validate(config, validator)
        config_text = json.dumps(config, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        progress('生成 MT 动态二维码')
        qr_frames = frames(config_text, profile_name)
        generated = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return json.dumps({'ok': True, 'generated_at': generated, 'name': profile_name,
                           'nodes': count, 'groups': len(groups), 'frames': qr_frames,
                           'config': config_text, 'changes': changes,
                           'report': {'generated_at': generated, 'providers': audit, 'groups': groups,
                                      'changes': changes, 'schema': 'upstream v1.14.0',
                                      'validation': 'Schema + references + acyclicity; no core execution'}},
                          ensure_ascii=False)
    except Exception as error:
        # Trace locations are useful; omit locals/source lines and arbitrary exception
        # messages from unexpected failures (which may include credentials).
        trace = '\n'.join(f'{os.path.basename(f.filename)}:{f.lineno} {f.name}'
                          for f in traceback.extract_tb(error.__traceback__))
        message = scrub(error) if isinstance(error, (tool.ExportError, ValueError)) else '操作失败，见下方阶段与类型；旧结果保留。'
        # Native I/O exposes controlled codes only; never include Java URL exceptions.
        codes = re.findall(r'MTB_[A-Z_]+(?::\d+)?', str(error))
        return json.dumps({'ok': False, 'stage': scrub(stage), 'message': message,
                           'code': codes[0] if codes else type(error).__name__, 'trace': trace},
                          ensure_ascii=False)
