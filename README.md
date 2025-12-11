## Electron集成架构
### 1. 双进程架构
- 主进程 ( electron/main.js ): 负责启动Python后端服务器
- 渲染进程 : 显示Dash网页界面
### 2. 关键文件说明
package.json ( package.json:1-46 ):

- 设置了Electron入口点： "main": "electron/main.js"
- 提供了多个打包脚本： pack:mac , pack:win , pack:linux
- 配置了electron-builder的打包参数
Electron主进程 ( electron/main.js:1-50 ):

- 自动检测并启动Python后端（优先使用打包后的可执行文件）
- 在端口8052启动本地服务器
- 创建浏览器窗口加载Dash应用
打包脚本 ( scripts/pack.js:1-50 ):

- 使用PyInstaller将Python应用打包成可执行文件
- 使用electron-builder创建各平台安装包
## 打包到Electron的完整步骤
### 第一步：项目结构准备
```
log_filter/
├── electron/           # Electron相关文件
│   ├── main.js        # 主进程
│   └── preload.js     # 预加载脚本（安全通信）
├── scripts/           # 打包脚本
│   └── pack.js        # 自动化打包脚本
├── app.py            # 原始的Dash应用
└── package.json      # Node.js配置
```
### 第二步：依赖安装
```
# 安装Electron相关依赖
npm install electron electron-builder --save-dev
```
### 第三步：配置package.json
需要设置：

- main 字段指向Electron主进程文件
- 添加打包脚本和构建配置
- 配置electron-builder参数
### 第四步：创建Electron主进程
主要功能：

- 启动Python后端服务器
- 创建浏览器窗口
- 处理应用生命周期
### 第五步：打包流程
1. 打包Python后端 : 使用PyInstaller将app.py打包成可执行文件
2. 打包Electron前端 : 使用electron-builder创建各平台安装包
3. 资源整合 : 将Python可执行文件作为额外资源打包
## 当前项目的打包命令
# 打包mac版本
```
npm run pack:mac

# 打包windows版本  
npm run pack:win

# 打包linux版本
npm run pack:linux

# 打包所有平台
npm run pack:all

# 开发模式运行
npm run electron:dev
```