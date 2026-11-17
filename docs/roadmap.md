# 开发计划

OpenDMR 是业余时间做的项目，下面只是打算做的事和大致先后，**没有时间表**，顺序也可能变。欢迎在
[Issues](https://github.com/va3bpf/OpenDMR/issues) 里提建议，或者直接提交 PR。

English: [roadmap.en.md](roadmap.en.md)

## 近期

**APRS**

- 信标在 APRS 配置的发射频率上发（OpenGD77 的 "Transmit frequency"，CPS 里的「Frec TX」），DMR 信道选了 APRS
  配置也能发信标，发完回到原来的信道（[#35](https://github.com/va3bpf/OpenDMR/pull/35)）
- 卫星模式发 APRS 信标：用卫星的 APRS 频率（自动修正多普勒）和卫星的路径（如 ISS 的 `RS0ISS`、SONATE-2 的
  `DP0SNX`）（[#55](https://github.com/va3bpf/OpenDMR/issues/55)）
- 在空中实测：信标用 APRS 解码器 / aprs.fi 接收，QSY 信息，卫星转发

**写频软件（OpenDMR CPS）**

- 编辑 APRS 配置（最多 8 套：路径、注释、图标、信标频率、QSY 等）；现在只是把电台里的配置原样写回
- 编辑 DTMF 等其他现在原样写回的部分

**说明书**

- 按新的配色重拍截图

## 以后

- 语音提示
- 写校准（现在只读）
- 「安全开机」「星（手动 / 自动）」这两项设置真正起作用
- 西班牙语界面的重音字母（现在字体只有 ASCII）
- 在空中实测：热点的 CW ID、卫星过境、脱网、按距离排序、AM / SSB 静噪延时

**P25**（详见 [p25.md](p25.md) 第 6 节）

- 开机后第一次通话收不到 HDU
- 个呼
- 弱信号灵敏度测量，和商用 P25 电台、MMDVM 热点互通实测
- 中继的上下行处理

**NXDN**（NXDN48 收发已完成，见 [nxdn/README.md](../nxdn/README.md)）

- NXDN ID 到呼号的数据库（来电显示呼号）
- 解调改进（空中语音帧误码约 1.4 %：均衡）
- 和商用 NXDN 电台互通实测

## 考虑中（需要较多时间和测试设备）

- NXDN96、NXDN 集群和加密
- P25 加密（DES / AES）、集群、Phase 2（TDMA）
