# 容器验收测试

这里保存只针对比赛交付目录的验收脚本和记录模板。验收必须在没有当前仓库、没有 Compose 的干净目录中进行：

1. `docker build -t lexcyber-competition .`
2. `docker run --env-file .env -p 18080:8080 -v lexcyber-competition-data:/data lexcyber-competition`
3. 打开网页注册账号、建案、上传演示输入。
4. 确认任务轨迹包含解析、抽取、检索、模型、校核和人工复核。
5. 复核一次成功版本，再执行一次缺失法源或模型超时边界任务。

最近一次本地构建、启动和安全边界验证记录见 `VERIFICATION.md`。使用正式模型凭据进行评审时，应追加成功/失败任务编号、运行环境和结果哈希；不得记录 API Key。
