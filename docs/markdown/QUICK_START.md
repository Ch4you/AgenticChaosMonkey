# 🚀 快速开始指南

## 📋 目录

1. [环境准备](#环境准备)
2. [三种使用方式](#三种使用方式)
3. [完整测试流程](#完整测试流程)
4. [查看结果](#查看结果)
5. [常用命令](#常用命令)

---

## 环境准备

### 1. 检查前置条件

```bash
./scripts/check_prerequisites.sh
```

确保以下组件已安装并运行：
- ✅ Python 3.10+
- ✅ Ollama（本地LLM，运行在11434端口）
- ✅ mitmproxy
- ✅ 所有Python依赖

### 2. 安装依赖

```bash
# 推荐：使用开发模式安装（使用pyproject.toml）
pip install -e .

# 或安装开发依赖
pip install -e ".[dev]"

# 传统方式：从requirements.txt安装
pip install -r requirements.txt
```

---

## 三种使用方式

### 方式1：一键测试脚本（最简单）⭐

**适用场景**：快速测试完整流程，适合日常使用

```bash
./scripts/run_chaos_test.sh
```

**功能**：
- ✅ 自动启动Mock Server
- ✅ 自动启动Chaos Proxy
- ✅ 运行Travel Agent测试
- ✅ 生成Resilience Scorecard报告
- ✅ 自动清理进程

**输出**：
- 日志文件：`logs/proxy.log`, `logs/agent_output.log`
- 报告文件：`reports/resilience_report.md`, `reports/resilience_report.json`

---

### 方式2：CLI工具 + Dashboard（推荐）⭐

**适用场景**：交互式测试，实时查看监控数据

#### 步骤1：启动Chaos平台

```bash
agent-chaos run examples/plans/travel_agent_chaos.yaml --mock-server
```

**你会看到**：
- ✅ 漂亮的ASCII Logo
- ✅ 实验计划加载信息
- ✅ 服务启动状态（Mock Server, Proxy, Dashboard）
- ✅ 实时Dashboard界面（在终端中）

**重要信息**：
```
✓ Dashboard available at http://127.0.0.1:8081
```

#### 步骤2：在另一个终端运行Agent

```bash
# 设置代理环境变量（重要！）
export HTTP_PROXY=http://localhost:8080
export HTTPS_PROXY=http://localhost:8080
export NO_PROXY=""

# 运行Agent
python examples/production_simulation/travel_agent.py \
  --query "Book a flight from New York to Los Angeles on December 25th, 2025"
```

#### 步骤3：查看Dashboard（可选）

打开浏览器访问：`http://127.0.0.1:8081`

**如果遇到连接问题**，配置浏览器绕过代理：
- Chrome: 设置 → 系统 → 代理 → 高级 → 例外: `127.0.0.1, localhost`
- Firefox: 设置 → 网络设置 → 不使用代理: `127.0.0.1, localhost`

#### 步骤4：停止实验

在运行`agent-chaos`的终端按 `Ctrl+C`

---

### 方式3：手动启动（最灵活）⭐

**适用场景**：需要精确控制每个组件，调试时使用

#### 步骤1：启动Mock Server

```bash
# 终端1
python src/tools/mock_server.py
```

**验证**：
```bash
curl http://localhost:8001/health
# 应该返回: {"status": "healthy"}
```

#### 步骤2：启动Chaos Proxy

```bash
# 终端2
mitmdump -s agent_chaos_sdk/proxy/addon.py --listen-port 8080
```

#### 步骤3：运行Agent

```bash
# 终端3
export HTTP_PROXY=http://localhost:8080
export HTTPS_PROXY=http://localhost:8080
export NO_PROXY=""

python examples/production_simulation/travel_agent.py \
  --query "Book a flight from New York to Los Angeles on December 25th, 2025"
```

#### 步骤4：生成报告

```bash
# 终端3（继续）
python src/reporter/generate.py
```

---

## 完整测试流程

### 1. 运行单元测试

```bash
# 运行所有单元测试
pytest tests/unit/ -v

# 带覆盖率报告
pytest tests/unit/ --cov=agent_chaos_sdk --cov-report=term-missing
```

### 2. 运行端到端测试

选择上述三种方式之一（推荐方式1或方式2）

### 3. 查看结果

#### 查看终端输出

- Agent会打印执行过程
- 如果使用CLI，会显示实时Dashboard
- 如果使用脚本，会显示报告摘要

#### 查看日志文件

```bash
# Proxy日志（JSON格式，用于报告生成）
cat logs/proxy.log

# Agent输出日志
cat logs/agent_output.log

# Proxy标准输出（详细调试信息）
cat logs/proxy_stdout.log
```

#### 查看报告

```bash
# Markdown报告（人类可读）
cat reports/resilience_report.md

# JSON报告（机器可读）
cat reports/resilience_report.json

# 或者在浏览器中打开
open reports/resilience_report.md
```

### 4. 理解报告

报告包含以下指标：

- **Grade**: 整体评分（A/B/C/D/F）
- **Resilience Score**: 弹性分数（0-100）
- **Tool Calls**: 工具调用统计（总数、成功、失败）
- **Fuzzing**: 模糊测试统计（尝试次数、成功次数）
- **Recovery**: 恢复率（失败后重试的成功率）
- **Outcome**: 最终结果（完成/崩溃）
- **Protocol Attacks**: 协议攻击检测
- **Race Conditions**: 竞态条件检测

---

## 常用命令

### CLI命令

```bash
# 初始化一个新的chaos plan模板
agent-chaos init

# 验证chaos plan YAML文件
agent-chaos validate examples/plans/travel_agent_chaos.yaml

# 运行实验（带Mock Server）
agent-chaos run examples/plans/travel_agent_chaos.yaml --mock-server

# 运行实验（不带Mock Server，使用外部服务）
agent-chaos run examples/plans/travel_agent_chaos.yaml

# 记录会话（用于回放）
agent-chaos record examples/plans/travel_agent_chaos.yaml --tape session.tape

# 回放会话
agent-chaos replay session.tape --plan examples/plans/travel_agent_chaos.yaml
```

### 报告生成

```bash
# 基本用法（自动查找日志）
python src/reporter/generate.py

# 指定日志文件
python src/reporter/generate.py --log-file logs/proxy.log

# 自定义输出目录
python src/reporter/generate.py --output-dir reports/
```

### 测试命令

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit/ -v

# 运行集成测试
pytest tests/integration/ -v

# 运行特定测试文件
pytest tests/unit/test_security.py -v

# 运行带覆盖率的测试
pytest --cov=agent_chaos_sdk --cov-report=html
```

---

## 🔧 配置Chaos策略

### 编辑Chaos Plan

编辑 `examples/plans/travel_agent_chaos.yaml`：

```yaml
scenarios:
  - name: "flight_search_delay"
    type: "latency"
    target_ref: "flight_search_api"
    enabled: true        # 改为true启用
    probability: 1.0     # 概率（0.0-1.0）
    params:
      delay: 5.0         # 延迟秒数
```

### 可用的策略类型

1. **latency**: 网络延迟
2. **error**: 错误注入
3. **mcp_fuzzing**: 协议模糊测试
4. **group_chaos**: 基于角色的组策略
5. **hallucination**: 认知层攻击（数据篡改）
6. **context_overflow**: 上下文溢出攻击
7. **phantom_document**: RAG投毒
8. **swarm_disruption**: Swarm破坏

### 重新加载配置

如果使用CLI，修改YAML后需要：
1. 停止当前运行的`agent-chaos`（Ctrl+C）
2. 重新运行`agent-chaos run`

如果使用手动模式，修改配置后需要重启Proxy。

---

## 📊 可观测性

### Dashboard（实时监控）

访问：`http://127.0.0.1:8081`

功能：
- 实时请求统计
- Chaos注入事件
- 拓扑图可视化
- 错误追踪

### Jaeger（分布式追踪）

```bash
# 启动Jaeger（需要Docker）
docker-compose up -d

# 访问Jaeger UI
open http://localhost:16686
```

### Prometheus/Grafana（指标监控）

```bash
# 启动Prometheus和Grafana
docker-compose up -d

# 访问Prometheus
open http://localhost:9090

# 访问Grafana
open http://localhost:3000
# 默认用户名/密码: admin/admin
```

---

## 🐛 故障排除

### 常见问题

1. **端口被占用**
   ```bash
   lsof -i :8080  # Proxy端口
   lsof -i :8001  # Mock Server端口
   lsof -i :8081  # Dashboard端口
   kill -9 <PID>  # 杀死进程
   ```

2. **Agent无法连接Mock Server**
   - 检查`HTTP_PROXY`环境变量是否正确设置
   - 确保`NO_PROXY`为空（强制localhost走代理）

3. **Dashboard连接被拒绝**
   - 配置浏览器绕过代理（见方式2步骤3）
   - 检查Dashboard是否已启动

4. **测试失败**
   - 检查Ollama是否运行：`ollama list`
   - 查看日志文件获取详细错误信息
   - 运行单元测试确保基础功能正常

5. **报告显示"Fuzzing: Attempted: 0"**
   - 检查chaos plan中的策略是否`enabled: true`
   - 检查`probability`是否大于0

---

## 📚 更多资源

- **完整测试指南**: 查看 `COMPREHENSIVE_TESTING_GUIDE.md`
- **项目README**: 查看 `README.md`
- **Chaos Plan示例**: 查看 `examples/plans/` 目录
- **API文档**: 查看各个模块的docstring

---

## 🎯 下一步

1. ✅ 运行一键测试脚本验证系统
2. ✅ 启用不同的chaos策略进行测试
3. ✅ 查看Dashboard了解实时监控
4. ✅ 分析报告了解Agent的弹性表现
5. ✅ 尝试不同的chaos plan配置

**祝你测试愉快！** 🐵

