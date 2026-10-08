# SFA/Yuu → iOS MT 手动订阅更新工具

读取 SFA 配置中的订阅地址，生成上游 1.14 配置结构的完整 iOS MT JSON。适配此次提供的 config_sfa.json、四个 remote 节点订阅和五份本地规则。

**工具不会启动 sing-box，也不包含核心二进制。不执行节点测速、连通性测试、VPN/TUN 或系统代理设置。** 在线模式仅通过 Python HTTPS 获取四份节点订阅；离线模式不访问网络。当前本机不允许运行代理工具，只进行了离线生成和静态检查。

## 快速使用：MT 管理器或 Termux

工具包已内置纯 Python JSON Schema 校验依赖，不需要 pip、Rust、Go 或编译核心。只需 Python 3.9 以上；若源机器还没有 Python，在 Termux 普通模式安装：

```sh
pkg install python
```

文件编码明确固定为 UTF-8：配置、规则、schema 和订阅正文均按 UTF-8 解码（允许输入含 UTF-8 BOM）；配置及报告写为无 BOM 的 UTF-8、LF 换行，中文和 emoji 原样保留。非 UTF-8 输入会报错，不猜测编码。启动器启用 Python UTF-8 模式；直接运行 Python 脚本时也显式设定标准输入输出为 UTF-8，不依赖系统区域设置。MT 管理器查看输出时请选择 UTF-8。

1. 将完整工具 ZIP 解压到 SFA 根目录，使工具位于其下的 `MT exporter` 文件夹。保留 vendor 目录和 schema 文件，不能只复制 update-now.sh。
2. 脚本自动从上一级读取 `config.json`，并根据其本地规则路径读取 `RuleProviders/`，无需复制主配置或准备规则 ZIP。工具包本身不含订阅 token 或节点密码。
3. 在 MT 管理器中以 shell/root 方式执行 `update-now.sh`；或在 Termux 中执行：

```sh
sh "/storage/emulated/0/sfa-root-path/MT exporter/update-now.sh"
```

如读取源文件需要 root，可以从 Termux 发起：

```sh
su -c 'sh "/storage/emulated/0/sfa-root-path/MT exporter/update-now.sh"'
```

启动器会尝试 PATH 中的 python3/python，以及 `/data/data/com.termux/files/usr/bin/python`。若 Termux 是其他包名或其他安装路径，先设置实际解释器路径：

```sh
export MT_EXPORT_PYTHON=/你的实际路径/bin/python
sh "/storage/emulated/0/sfa-root-path/MT exporter/update-now.sh"
```

Python 本身须在所选运行环境可执行；root 不等于 Android 自带 Python。脚本不会自动调用 su，不会启动或重启 SFA。普通 Termux 若没有共享存储访问权限，可用系统授权或选择已有访问权限的路径；也可以直接在 root 环境执行。

目录结构如下；上面的 sfa-root-path 替换为实际 SFA 根目录。路径由脚本自身位置计算，与运行时的当前目录无关，支持目录名中的空格。

```text
sfa-root-path/
├── config.json                  # SFA 原配置，只读
├── RuleProviders/               # 本地规则，只读
└── MT exporter/
    ├── update-now.sh
    ├── run-android.sh
    ├── update_mt.py
    ├── sing-box-1.14.schema.json
    ├── vendor/
    └── out/                     # 首次成功生成时自动创建
        ├── config.json
        └── config.json.report.json
```

成功后生成：

- `MT exporter/out/config.json`：完整 MT 配置，包含节点认证信息，传到 iPhone 后导入。
- `MT exporter/out/config.json.report.json`：节点/分组数量、订阅摘要、成员列表、迁移行为及校验说明，不包含密码/token。

每次运行都读取上一级的最新配置和规则，并重新拉取节点订阅。成功后自动、原子覆盖 out/config.json，无需确认或手动删除旧文件；失败时保留旧配置。不会覆盖上一级的 SFA config.json。目录可整体移动，不需要修改脚本中的绝对路径。

## 自定义源文件位置

```sh
sh "/storage/emulated/0/sfa-root-path/MT exporter/run-android.sh" \
  --config /实际SFA配置目录/config.json \
  --rules-zip /实际规则目录/RuleProviders.zip \
  --output "/storage/emulated/0/sfa-root-path/MT exporter/out/config.json"
```

如果配置文件所在目录已经有 `RuleProviders/*.json`，可不传 `--rules-zip`，相对路径会以配置文件目录为基准读取。ZIP 模式要求包内路径与源配置对应，本次即 `RuleProviders/custom-direct.json` 等。

两个语义选项：

```sh
# 默认：match_only 改普通 resolve；保留 IP 分流兜底
sh update-now.sh --resolve-mode ordinary

# 删除原 match_only resolve 步骤；改变对未解析域名的 IP 分类兜底
sh update-now.sh --resolve-mode remove

# 保留原 Mixed 入站、Clash API 等本地服务；默认仅留 TUN
sh update-now.sh --keep-local-services
```

`--resolve-mode ordinary` 会给原 match_only resolve 显式指定原 default_domain_resolver 的服务器。解析出的 IP 可能用于后续连接，因此不是 match_only 的无损替代；`remove` 也有不同的分流代价。

## 本次转换的默认策略

保留：

- DoQ、新 DNS/FakeIP 结构和原地址池；不改成 DoH，也不擅自换 DNS 服务。
- 双栈地址与 A/AAAA 规则，TUN system 栈、原 IPv6 /126、dns_mode:hijack。
- DNS predefined 零地址响应、optimistic 缓存、default_domain_resolver。
- http_clients、远程 rule-set 多 tag/{tag} 定义及更新方式。
- 87 个现有节点，包括两个 NaiveProxy；TLS、插件、认证和链式 detour 参数。
- 所有 14 个分组的筛选语义和固定成员顺序；不将 selector 改成自动选最快。

转换/移除：

- 四个节点 provider → 标准 outbounds；按原名筛选后添加 `来源 :: 节点原名` 前缀，处理重名并改写引用。
- 五份本地 source rule-set → 内嵌 inline rules，不依赖 iOS 沙盒文件路径。JSONC 注释和尾逗号会归一化。
- 移除 concurrent_dial、urltest_unified_delay。
- 删除两个已识别的默认接口 IPv6 guard，保留双栈；iOS 不支持它们的原接口判断。这不保证所有接入网络下都有相同 IPv6 回退行为。
- match_only 按上面的显式策略替代。
- 删除 interface_name、auto_redirect，以及日志/缓存的桌面路径。
- 默认移除非 TUN 入站、Clash API 和 V2Ray API；这些是手机使用方式的简化，不意味着上游不支持。

## 校验与失败保护

输出前完成：严格 JSONC 解析（重复键也拒绝）、完整上游 1.14 JSON Schema 检查、重复 tag/未知引用检查、空分组/default 检查，以及 selector/detour 图的循环检查。

每个 provider 必须成功获取、解析且至少有一个节点。任何下载、格式、筛选或校验失败都会返回非零状态，并保留上一份 out/config.json。成功输出使用同目录临时文件加原子替换；不会先清空旧配置。报告先写、配置最后替换；极少数文件系统故障可能留下新报告和旧配置，出错时以 config 文件及终端状态为准。

入口捕获异常后会向标准错误输出完整 traceback（含保留的异常链），并以状态码 1 退出，无需手动修改 main。文件读取失败会报告绝对路径、异常类型和系统错误码；编码错误与文件不存在、权限不足分别报告。Schema 校验错误仍只提供字段路径，不展开可能含密码的节点内容。排查日志包含文件路径，转发前可按需脱敏。配置写入采用私有临时文件权限；共享存储上的实际访问控制仍由 Android 文件系统决定。

检查不覆盖：iOS 应用实际内核版本、端点连通性、DoQ/TLS 证书、链路质量、远程 SRS 此刻内容或将来的格式变化、移动端内存/功耗。你可在允许的设备/网络自行冒烟。schema 的目标是上游 v1.14.0，不把 MT 的应用版本号直接当作核心版本号。

## 支持范围

当前四个源返回 sing-box JSON：`{"outbounds":[...]}`，也接受直接节点数组。配置类 direct/block/dns/selector/urltest 项按 yuu 订阅解析器的方式忽略。实际节点协议由上游 schema 校验，因此不会再因旧 VT 限制剔除 Naive。

不自动转换 Clash YAML、base64 链接列表或 endpoints，也不实现 provider 字段覆写、代理下载 detour 或复杂自定义 HTTP 客户端。源格式/能力变化时明确报错，不能静默丢弃或降为 Direct。当前 Direct-client 无额外参数，Python 直接下载可满足此处需求；工具不继承 HTTP_PROXY/HTTPS_PROXY 环境代理。

正则实现覆盖这份配置使用的语法，包括 `美国|(?i)DMIT`，使用 ASCII 类与大小写策略处理此处英文关键词。它不是任意 Go/RE2 表达式的通用实现；Unicode 大小写、复杂内嵌 flags、POSIX 类等变化需审查。固定 outbounds 成员不受 provider 正则过滤。

服务端如果按 User-Agent 区分格式，工具默认发送 `sing-box/1.14.0`，有 provider.user_agent 时使用该值。若服务不返回 sing-box JSON，工具会中止而不是猜测内容。

## 离线生成与测试

已有订阅快照可按 `来源名.json` 或 `来源名.txt` 放在目录中；每个来源只能存在一个文件。例：FlowerCloud.txt、EVA.txt、Seednet.txt、Friends-Nodes.txt。

```sh
python update_mt.py \
  --config ../config.json \
  --snapshots /实际快照目录 --output out/config.json

python -m unittest discover -s . -p 'test_*.py' -v
```

测试使用合成节点和模拟下载错误，不访问真实订阅或端点、不启动核心。工具的 vendor 路径只在此进程中生效，不修改系统 Python 安装。

## 依赖来源

内置：jsonschema 4.17.3（MIT）、attrs 25.3.0（MIT）、pyrsistent 0.20.0（MIT，使用其原生纯 Python 回退）。相应许可证保留在 vendor 中。选取这组依赖是为了支持离线 Python 校验，避免 Android 上编译 Rust/C 扩展。

schema 来自 SagerNet/sing-box 的 v1.14.0 `docs/schema.json`（GPL-3.0，见 UPSTREAM-LICENSE）。没有修改 schema。下载源码包的哈希及 schema 哈希记录于 DEPENDENCIES.json。
