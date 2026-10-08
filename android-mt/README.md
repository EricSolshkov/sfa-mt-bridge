# MT 配置桥 · Android 首版

在 Android 读取 Yuu/SFA 配置与本地规则，下载节点订阅，转换成完整 MT 配置，然后显示 QRS 动态二维码供 iPhone 扫描。无需安装 Python、Termux、运行脚本、启动本地服务器或跨设备复制配置文件。

## 安装与使用

`dist/MT-Bridge-0.1.2-arm64-test.apk` 是已签名的个人测试 APK，支持 **Android 8.0+、64 位 ARM**。应用名：**MT 配置桥**；包名：`local.mtbridge`。不是应用商店发布版。

1. 安装 APK。源配置默认预填为 `/storage/emulated/0/Android/data/io.nekohasekai.sfa/files/config.json`，可以手动修改。
2. 如果目录受保护，打开「使用 Root 读取配置与规则」，在 Magisk / KernelSU / APatch 等 Root 管理器中允许本应用。手机必须已有可用的 `su`。
3. 点「检查文件访问」。应用读取主配置及引用的所有本地规则，不下载订阅；相对规则路径以主配置目录为基准，支持 `{tag}` 替换和绝对路径。
4. 点首页「更新并生成二维码」。转换成功后自动进入二维码界面。
5. iPhone 在 sing-box MT 中选择新建配置 → 扫描二维码，保持对准直到提示导入。漏帧会在后续循环补齐；可以切换慢速。扫描时 Android 屏幕自动保持常亮。

### 0.1.2：修复 Android 应用目录隔离导致的 Root 读取失败

Root 读取改用 `su -M -c`，在全局挂载命名空间执行只读文件访问。已在当前 Android 16 / KernelSU 设备的真实应用进程中复现：普通 `su` 的 UID 虽然为 0，却看不到 SFA 的私有配置；`su -M` 能看到主配置与共享规则。ADB `run-as ... su` 原先继承了不同的命名空间，所以不能替代应用进程验证。

新增仅显式执行的 `RootDeviceProbeTest`，对照两种命名空间并通过生产文件读取器和嵌入式 Python 检查当前设置引用的本地文件；不下载订阅、不写入转换结果。其他 Root 实现需要支持 `-M` / `--mount-master`。

### 0.1.1：SFA 私有配置与共享规则分开存放

新增「规则基准目录」：留空沿用主配置目录，填写后所有相对规则路径从该目录解析，绝对路径保持原样。无需移动源文件。

本次连接设备已只读核实：

```text
主配置路径：
/data/user/0/io.nekohasekai.sfa/files/configs/1.json

规则基准目录（填写 RuleProviders 的上一级）：
/storage/emulated/0/Android/data/io.nekohasekai.sfa/files
```

开启 Root，先检查文件访问。`configs/1.json` 是此次设备的配置文件，不保证其他设备或其他配置仍是编号 1。原默认共享目录里的 `config.json` 在此次设备上不存在。升级保留已有设置，因此需手动填入上述两个路径。诊断新增 Root/普通读取模式。

以后只需打开应用 → 更新并生成二维码 → iPhone 扫码。路径、Root 开关、配置名和迁移设置都会记住。已有成功结果可直接重新显示，转换失败不会替换它。

Root 模式只做有边界的文件读取，不执行配置内容或任意用户命令，不修改源文件，不启动/停止 SFA 或 VPN。路径按 shell 单引号规则转义并拒绝控制字符；单文件上限 20 MiB，Root 操作 45 秒超时。普通模式只能访问 Android 允许本应用读取的路径；首版没有文件选择器或完整文件管理器。

## 转换行为

直接打包同一 workspace 的 `../mt-export/update_mt.py`，避免维护第二份转换实现。仅给原引擎增加可选读取/下载/进度回调；原 CLI 调用兼容。详见 `../mt-export/README.md`。

- provider 展开、组筛选和顺序、节点重名与 detour 引用改写。
- 本地 source rules 内嵌；远程规则定义保留。
- 默认保留 DoQ、IPv6、FakeIP 等既有能力；遵循原脚本的明确平台转换策略。
- `match_only` 默认转普通 resolve，可选移除；普通 resolve 会影响后续拨号 IP，移除会影响 IP 分类兜底，均不等价于原功能。
- 默认移除非 TUN 入站与本地 API，界面可选择保留。
- 完整上游 1.14.0 JSON Schema、tag/引用、空组/default、selector/detour 循环校验。
- 仍只支持原转换器范围内的 sing-box JSON 订阅，不自动转换 Clash YAML、base64 节点列表或未知 provider 扩展。

下载使用 Android HTTPS 实现、系统证书校验和源 provider 的 User-Agent，禁用自动跳转并逐次检查 HTTPS。只有用户点转换才下载；没有定时任务、遥测、在线转换服务或代理核心。失败信息包含阶段、受控错误码和转换栈位置，不显示订阅正文或带 token 的 URL。

## QRS 与隐私

转换结果封装为 sing-box BPF v1 本地配置：消息类型 3、版本 1、gzip 内容、UTF-8 字符串长度 varint、Local 类型 0。然后加入 QRS 文件元数据、zlib 压缩、CRC32 XOR 分片数，生成 350 字节分片的 LT degree-one 帧循环播放。

这是 QRS 可解码的系统分片序列，不使用随机喷泉混合帧；每个分片都要至少被拍到一次。前缀 `https://qrss.netlify.app/#` 是兼容协议字符串，本应用不打开该网址或向其发送配置。请使用 MT 内置扫描器。

结果只保存在本应用私有存储，备份与设备迁移已禁用。二维码包含完整节点凭据，和配置文件一样应只展示给自己的设备。诊断仍可能包含文件路径、规则和分组名称。

## 本机构建

固定：JDK 17、Gradle 8.13、Android Gradle Plugin 8.9.2、SDK 35 / build-tools 35.0.0、Chaquopy 17.0.0、Python 3.13。运行时内置 Python，手机无需额外环境。设置 JDK 17 与 Android SDK 后可直接使用随附 Gradle wrapper 构建。

```powershell
./build-local.ps1 -Tests
```

或设置 JDK 17 / Android SDK，使用随项目提供的 Gradle wrapper：

```powershell
./gradlew.bat assemblePhoneDebug testPhoneDebugUnitTest lintPhoneDebug
```

`phone` 为 arm64-v8a；`emulator` 为 x86_64。两者包名相同，分别用于真实 ARM 手机和本机模拟器。调试签名使用本机 Android debug keystore；未来升级需要保留同一签名，卸载会清除设置和成功结果。

## 验证

```powershell
python -m unittest discover -s ../mt-export -p 'test_*.py' -v
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/export_qrs_fixture.py
npm ci --ignore-scripts
npm run test:qrs
```

- 原转换器 14 项测试。
- 移动适配 10 项测试，包括独立规则基准目录、绝对规则路径、非法基准路径，以及 workspace 现有私有快照的 87 节点 / 14 分组与原引擎逐字段一致；没有快照的其他电脑会跳过此项。
- 上游 `luby-transform@0.2.0` 独立解码合成测试帧，覆盖漏帧、乱序和重复帧，核对 BPF 名称、类型、完整配置字节。
- Java 单元测试覆盖路径转义、控制字符拒绝、读取上限。
- Android 15 x86_64 模拟器 instrumentation 验证实际嵌入的 Python、vendor/Schema、Java 文件桥、配置转换、每帧二维码图像读回、原生错误码和 HTTPS 限制。仅合成数据，不访问真实订阅。

安装包不包含 `config_sfa.json`、私有订阅快照、真实节点凭据或测试生成结果。`src/androidTest` 仅进入独立测试 APK。

0.1.2 已通过 Android 16 / KernelSU 实机文件读取测试，用户已反馈可用；其他设备、Root 管理器与 MT 版本仍需验证。手机应用版本不直接等于核心版本。扫码导入的是本地快照，后续需重新扫码；同名配置是否覆盖由 MT 实际行为决定。Schema 不能替代运行时路由、DNS 和网络验证。

## 工程位置

- `app/src/main/java/local/mtbridge/`：原生界面、只读 Root 文件桥和 HTTPS 下载。
- `app/src/main/python/mobile_bridge.py`：移动 I/O 适配与安全诊断。
- `app/src/main/python/qrs_profile.py`：BPF/QRS 编码。
- `../mt-export/update_mt.py`：唯一转换逻辑来源，构建时按白名单打包。
- `tests/`、`app/src/test/`、`app/src/androidTest/`：离线与模拟器验证。
- `THIRD_PARTY_NOTICES.md`、`app/src/main/assets/licenses/`：依赖来源和许可证。
