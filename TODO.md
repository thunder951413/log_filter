# TODO

## AI 分析
- [ ] free-code 加入设置 skill 接口，或者直接固定 skill 位置
- [ ] 给 free-code 的 skill 加入限制语句，描述主要做什么
- [ ] 给 free-code 的网页交互部分加入设置页面

## 架构优化
- [ ] 将 `app.py` (~10200 行) 按功能区拆分为多个模块文件

## 代码质量
- [ ] 前端全局变量规范化（`window.chatStates`、`window.activeJobTimers` 等应抽离为模块）
- [ ] 清理 macOS 资源 fork 文件 (`._*`)，更新 `.gitignore`

## 功能完善
- [ ] 将 `tabs` 相关变量从 Python 命名空间改为 `dcc.Store`，避免使用全局变量 `tabs`
- [ ] 统一 try-catch 中的错误处理模式，避免静默异常
