# SFA → MT 配置桥

在 Android 手机上读取 Yuu/SFA 配置、更新订阅并转换为完整 sing-box MT 配置，通过屏幕上的 QRS 动态二维码传给 iPhone。无需在手机上安装 Python、运行脚本或复制配置文件。

## 下载

[下载 v0.1.2 ARM64 测试 APK](https://github.com/EricSolshkov/sfa-mt-bridge/raw/refs/heads/main/android-mt/dist/MT-Bridge-0.1.2-arm64-test.apk)

- Android 8.0 以上，64 位 ARM；包名 `local.mtbridge`。
- 读取其他应用的私有配置需要已 Root 的手机，并在 Root 管理器中授权。
- APK 使用开发者本机的调试签名，是个人测试版本；自行构建的签名通常不同，不能直接覆盖安装。
- v0.1.2 已在 Android 16 / KernelSU 上验证私有目录读取，用户已反馈可用。

## 使用

1. 安装 APK，填写 SFA 主配置的完整路径，开启 Root 读取。
2. 如果规则与主配置不在同一目录，填写「规则基准目录」。
3. 点「检查文件访问」，确认主配置与本地规则均可读取。
4. 点「更新并生成二维码」。
5. 在 iPhone 的 sing-box MT 中选择新建配置 → 扫描二维码，保持对准直到提示导入。

一种经过验证的目录组合：

```text
主配置：/data/user/0/io.nekohasekai.sfa/files/configs/1.json
规则基准目录：/storage/emulated/0/Android/data/io.nekohasekai.sfa/files
```

配置编号和包名可能不同，请按实际情况填写。主配置中的 `RuleProviders/{tag}.json` 会相对于规则基准目录读取；该字段留空时，相对于主配置目录读取。绝对规则路径保持原样。

设置会保存，日常只需更新并扫码。转换失败保留上次成功结果。扫码传输的是本地配置快照，后续更新需重新扫码；同名配置的处理以 MT 提示为准。

## 能力与边界

- 复用 `mt-export/update_mt.py` 完整转换逻辑，展开 provider、筛选分组、改写 detour、内嵌本地规则。
- 上游 sing-box 1.14.0 JSON Schema、引用和分组循环校验。
- Root 文件读取使用 `su -M`，解决 Android 应用挂载命名空间隔离；Root 实现必须支持该参数。
- Android 原生 HTTPS 下载；QRS/BPF 编码和转换在本机完成。
- 不启动代理核心，不修改 SFA 配置，不上传配置到转换服务。
- 只支持转换器范围内的 sing-box JSON 订阅，不自动转换 Clash YAML 或 base64 节点列表。
- `match_only` 的两种迁移方式都有行为差异，Schema 校验不能替代实际网络验证。

二维码包含节点凭据，请只向自己的设备展示。仓库和 APK 不包含用户配置、真实订阅快照、签名私钥或访问令牌。

## 构建与测试

准备 JDK 17、Android SDK 35 / Build Tools 35.0.0。设置 `JAVA_HOME`、`ANDROID_HOME`，或在 `android-mt/local.properties` 中配置 `sdk.dir`。

```powershell
cd android-mt
./gradlew.bat assemblePhoneDebug testPhoneDebugUnitTest lintPhoneDebug
```

Linux/macOS 使用 `./gradlew`。Python 运行环境会打包进 APK，手机无需额外安装。

在仓库根目录运行离线验证：

```sh
python -m unittest discover -s mt-export -p 'test_*.py' -v
python -m unittest discover -s android-mt/tests -p 'test_*.py' -v
cd android-mt
python tests/export_qrs_fixture.py
npm ci --ignore-scripts
npm run test:qrs
```

私有快照一致性测试在没有本地快照时自动跳过。Android instrumentation 位于 `app/src/androidTest`；其中 `RootDeviceProbeTest` 仅用于明确选择的、已授权 Root 的测试设备。不要在用户设备上运行会写入合成结果的 `EmbeddedConverterTest`。

## 代码与许可

- [Android 工程及详细说明](android-mt/README.md)
- [转换器](mt-export/README.md)
- [第三方组件](android-mt/THIRD_PARTY_NOTICES.md)

项目采用 GPL-3.0，第三方组件保留各自许可证。未包含 sing-box 核心二进制。
