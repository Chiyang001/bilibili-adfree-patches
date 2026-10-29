# Bilibili 广告过滤补丁

针对用户自行提供的 Bilibili Android 9.17.0 安装包的版本限定研究与补丁脚本。

开发者：炽阳001

- Bilibili：https://space.bilibili.com/404891612
- GitHub：https://github.com/Chiyang001?tab=repositories

仓库仅包含补丁、构建和验证脚本及说明，不包含官方安装包、修改后的 APK、反编译代码、签名密钥、设备截图或日志。没有发布 Release。

## 使用

自行准备与脚本固定 SHA256 匹配的原始安装包，命名为 `iBiliPlayer-bili.apk`，放到项目根目录。

```powershell
apktool d -r -o work/decoded iBiliPlayer-bili.apk
python scripts/build.py
```

需要 Windows、Python、Java、Apktool 3.0.3 和 Android SDK Build Tools 37.0.0。默认工具路径及环境变量见 `scripts/build.py`。

输出、反编译产物和本地签名材料分别保存在被忽略的 `dist/`、`work/`、`keys/` 中，不应提交。设备验证脚本仅用于自己授权的设备，设备序列号应按实际情况设置。

补丁覆盖开屏、商业弹窗、首页与搜索广告、视频详情商业字段、暂停广告、相关推荐商业卡片和流量套餐推广。完整说明见 `说明.txt`。

这是实验性、严格绑定版本的补丁。已在一台 Android 16 ARM64 设备进行有限验证，不能保证覆盖全部服务端广告变体或所有功能。重新签名后不能直接覆盖官方签名版本；卸载会影响本地数据。下载、付费/DRM、发布和外部分享等未完成验证。
