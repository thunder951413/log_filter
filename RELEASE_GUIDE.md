# LogFilter 发布指南

## 概述

本指南介绍如何使用 GitHub Actions 自动构建和发布 LogFilter 应用的多平台版本。

## 自动构建流程

### 触发方式

1. **自动触发**：推送版本标签时自动构建
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. **手动触发**：在 GitHub Actions 页面手动运行工作流

### 构建平台

- ✅ macOS (Intel + Apple Silicon)
- ✅ Windows (x64)
- ✅ Linux (x64)

### 输出文件

| 平台 | 文件名 | 格式 |
|------|--------|------|
| macOS | LogFilter-macOS.zip | .zip (包含 .app) |
| Windows | LogFilter-Windows.zip | .zip (包含 .exe) |
| Linux | LogFilter-Linux.tar.gz | .tar.gz |

## 用户安装指南

### macOS 用户

#### 方法 1：从 GitHub Releases 下载

1. 访问项目的 GitHub Releases 页面
2. 下载 `LogFilter-macOS.zip`
3. 解压文件
4. 将 `LogFilter.app` 拖到 `应用程序` 文件夹
5. 双击运行 `LogFilter.app`

#### 方法 2：使用启动脚本（推荐）

1. 确保已安装 Python 3.10+
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 运行启动脚本：
   ```bash
   python start_app.py
   ```

### Windows 用户

#### 前置条件

1. 安装 Python 3.10 或更高版本
   - 下载地址：https://www.python.org/downloads/
   - 安装时勾选 "Add Python to PATH"

2. 安装依赖
   ```cmd
   install_deps.bat
   ```

#### 方法 1：从 GitHub Releases 下载

1. 访问项目的 GitHub Releases 页面
2. 下载 `LogFilter-Windows.zip`
3. 解压文件
4. 双击运行 `LogFilter.exe`

#### 方法 2：使用启动脚本（推荐）

1. 运行启动脚本：
   ```cmd
   start_app.bat
   ```

### Linux 用户

#### 前置条件

1. 安装 Python 3.10+
   ```bash
   sudo apt install python3 python3-pip
   ```

2. 安装依赖
   ```bash
   pip3 install -r requirements.txt
   ```

#### 方法 1：从 GitHub Releases 下载

1. 访问项目的 GitHub Releases 页面
2. 下载 `LogFilter-Linux.tar.gz`
3. 解压文件：
   ```bash
   tar -xzf LogFilter-Linux.tar.gz
   ```
4. 运行应用：
   ```bash
   chmod +x LogFilter
   ./LogFilter
   ```

#### 方法 2：使用启动脚本（推荐）

1. 运行启动脚本：
   ```bash
   python3 start_app.py
   ```

## 开发者指南

### 本地构建

#### macOS

```bash
# 1. 安装 pake
brew install pake

# 2. 启动后端
python app.py

# 3. 打包应用
pake http://localhost:8052 --name LogFilter
```

#### Windows

```cmd
REM 1. 安装 pake
winget install tw93.pake

REM 2. 启动后端
python app.py

REM 3. 打包应用
pake http://localhost:8052 --name LogFilter
```

#### Linux

```bash
# 1. 安装 pake
cargo install pake-cli

# 2. 启动后端
python3 app.py

# 3. 打包应用
pake http://localhost:8052 --name LogFilter
```

### 使用 GitHub Actions 构建

#### 推送标签触发构建

```bash
# 创建并推送标签
git tag v1.0.0
git push origin v1.0.0
```

#### 手动触发构建

1. 访问项目的 GitHub Actions 页面
2. 选择 "Build and Release" 工作流
3. 点击 "Run workflow" 按钮
4. 选择分支并点击运行

### 下载构建产物

构建完成后，可以从以下位置下载：

1. **GitHub Releases**：自动发布的版本
2. **GitHub Actions Artifacts**：每次构建的产物（保留 90 天）

## 文件说明

### 启动脚本

| 文件 | 平台 | 说明 |
|------|------|------|
| start_app.py | 跨平台 | Python 启动脚本（推荐） |
| start_app.bat | Windows | Windows 批处理启动脚本 |
| install_deps.bat | Windows | Windows 依赖安装脚本 |

### 配置文件

| 文件 | 说明 |
|------|------|
| requirements.txt | Python 依赖列表 |
| app.py | 后端服务器主程序 |
| .github/workflows/build.yml | GitHub Actions 构建配置 |

## 故障排除

### macOS

#### 问题：应用无法打开

**解决方案：**
1. 右键点击应用，选择"打开"
2. 在系统偏好设置 > 安全性与隐私中允许运行

#### 问题：端口被占用

**解决方案：**
```bash
# 查找占用端口的进程
lsof -i :8052

# 终止进程
kill -9 <PID>
```

### Windows

#### 问题：Python 未找到

**解决方案：**
1. 重新安装 Python，确保勾选 "Add Python to PATH"
2. 或手动添加 Python 到系统 PATH

#### 问题：依赖安装失败

**解决方案：**
```cmd
REM 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Linux

#### 问题：权限不足

**解决方案：**
```bash
chmod +x LogFilter
```

#### 问题：依赖安装失败

**解决方案：**
```bash
# 使用国内镜像源
pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 版本管理

### 版本号规范

遵循语义化版本规范：`MAJOR.MINOR.PATCH`

- **MAJOR**：不兼容的 API 变更
- **MINOR**：向后兼容的功能新增
- **PATCH**：向后兼容的问题修复

### 发布流程

1. 更新版本号
2. 更新 CHANGELOG.md
3. 提交代码
4. 创建并推送标签
5. GitHub Actions 自动构建
6. 检查构建结果
7. 发布 Release

## 更新日志

### v1.0.0 (2026-03-19)

- 初始版本发布
- 支持 macOS、Windows、Linux 平台
- 自动化构建流程
- 完整的启动脚本和依赖管理

## 技术支持

如有问题，请：
1. 查看本文档的故障排除部分
2. 检查 GitHub Issues
3. 提交新的 Issue 描述问题

## 许可证

请查看项目根目录的 LICENSE 文件。
