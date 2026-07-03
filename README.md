# 六子棋 (Six-in-a-Row)

一款基于 Kivy 框架的六子棋 Android 游戏，支持人机对战和双人模式。

## 游戏规则

- 15×15 棋盘，黑白双方轮流落子
- **第一手**：黑棋落 1 子
- **之后每手**：双方各落 2 子
- 横、竖、斜任意方向率先**连成 6 子**的一方获胜
- 棋盘下满无胜负则为平局

## 功能

- 人机对战 / 双人模式切换
- AI 自动落子（基于局面评分）
- 悔棋、重开
- 背景音乐（程序合成）
- 音效开关

## 构建 APK

本项目通过 GitHub Actions 自动构建，提交到 `main` 分支即可触发：

1. Fork / Clone 本仓库
2. 修改 `main.py` 后提交
3. 在 GitHub 仓库 Actions 页面下载 APK Artifact

也可本地使用 python-for-android 构建：

```bash
pip install python-for-android kivy cython
p4a apk --private . --package org.liuziqi --name "六子棋" --version 1.0 --bootstrap sdl2 --requirements python3,kivy --arch arm64-v8a --debug
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | Kivy Android 版主程序 |
| `liuziqi.py` | Windows 桌面版（tkinter） |
| `.github/workflows/buildozer.yml` | CI 构建配置 |

## 许可证

MIT
