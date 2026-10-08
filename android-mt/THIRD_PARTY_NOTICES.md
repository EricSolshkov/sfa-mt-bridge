# Components and protocol references

| Component | Version/source | License |
|---|---|---|
| sing-box JSON Schema | upstream v1.14.0; existing mt-export/DEPENDENCIES.json | GPL-3.0 |
| jsonschema | 4.17.3; existing mt-export/vendor | MIT |
| attrs | 25.3.0; existing mt-export/vendor | MIT |
| pyrsistent | 0.20.0; existing mt-export/vendor | MIT |
| Chaquopy | 17.0.0, https://github.com/chaquo/chaquopy | MIT |
| CPython | 3.13 runtime distributed by Chaquopy | PSF and bundled third-party licenses |
| ZXing core | 3.5.3, https://github.com/zxing/zxing | Apache-2.0 |
| luby-transform | 0.2.0, https://github.com/qifi-dev/qrs | MIT; development tests only |
| AndroidX Test | runner 1.6.2 / ext junit 1.2.1 | Apache-2.0; test APK only |

Full main-component license texts are retained under app/src/main/assets/licenses. Chaquopy also distributes its runtime notices in the APK's embedded runtime.

The BPF/QRS Python implementation follows these source-level wire formats:

- SagerNet/sing-box, commit `abc21e4b5a568efdf411f102193f14e39db162f2`, `experimental/libbox/profile_import.go`.
- SagerNet/sing-box-for-apple, commit `3cc0835f2a44d9fc5ecc6140c149d374f915d43c`, `ApplicationLibrary/LubyTransform/{BinaryMeta,EncodedBlock,LubyTransformDecoder}.swift`.
- qifi-dev/qrs, commit `f3584e59d981e2686aed4289ad5e3e41aa6ac47c`, `packages/luby-transform/src/`.

No sing-box executable or native proxy core is included. The original converter and its schema are included with the source distribution. Private user configuration and subscription snapshots are excluded.
