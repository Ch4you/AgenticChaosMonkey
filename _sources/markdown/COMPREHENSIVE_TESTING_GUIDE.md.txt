# 完整测试指南 - Agent Chaos Platform

本指南涵盖项目的所有测试阶段，从单元测试到端到端集成测试。

## 📋 目录

1. [快速开始](#快速开始)
2. [阶段1: 单元测试](#阶段1-单元测试)
3. [阶段2: 集成测试](#阶段2-集成测试)
4. [阶段3: 端到端测试](#阶段3-端到端测试)
5. [阶段4: CLI测试](#阶段4-cli测试)
6. [阶段5: Dashboard测试](#阶段5-dashboard测试)
7. [阶段6: 可观测性测试](#阶段6-可观测性测试)
8. [阶段7: 高级功能测试](#阶段7-高级功能测试)
9. [测试检查清单](#测试检查清单)

---

## 快速开始

### 前置条件检查

```bash
# 运行前置条件检查脚本
./scripts/check_prerequisites.sh
```

确保以下组件已安装：
- ✅ Python 3.10+
- ✅ Ollama (本地LLM)
- ✅ mitmproxy
- ✅ 所有Python依赖 (`pip install -e .` 或 `pip install -r requirements.txt`)

### 一键完整测试

```bash
# 运行完整的端到端测试（推荐）
./scripts/run_chaos_test.sh
```

这个脚本会自动：
1. 启动Mock Server
2. 启动Chaos Proxy
3. 运行Travel Agent测试
4. 生成Resilience Scorecard报告

---

## 阶段1: 单元测试

测试各个组件的独立功能。

### 运行所有单元测试

```bash
# 运行所有单元测试
pytest tests/unit/ -v

# 带覆盖率报告
pytest tests/unit/ --cov=agent_chaos_sdk --cov-report=term-missing
```

### 测试各个模块

#### 1.1 安全模块测试

```bash
# PII脱敏和认证测试
pytest tests/unit/test_security.py -v
```

**验证点**：
- ✅ PII脱敏（邮箱、信用卡、API密钥）
- ✅ URL脱敏
- ✅ Header脱敏
- ✅ 认证验证（X-Chaos-Token）

#### 1.2 策略测试

```bash
# 延迟策略
pytest tests/unit/test_latency_strategy.py -v

# 错误注入策略
pytest tests/unit/test_error_strategy.py -v

# MCP协议模糊测试
pytest tests/unit/test_mcp_fuzzing.py -v

# 数据损坏策略
pytest tests/unit/test_data_corruption.py -v

# 组策略（基于角色的chaos）
pytest tests/unit/test_group_strategy.py -v

# 认知层攻击
pytest tests/unit/test_cognitive_strategies.py -v

# RAG投毒策略
pytest tests/unit/test_rag_strategy.py -v
```

**验证点**：
- ✅ 策略正确应用延迟/错误
- ✅ 概率控制工作正常
- ✅ 模式匹配正确
- ✅ 异步执行不阻塞

#### 1.3 配置加载测试

```bash
# 配置加载和验证
pytest tests/unit/test_config_loader.py -v
```

**验证点**：
- ✅ YAML解析正确
- ✅ Pydantic验证工作
- ✅ 目标引用检查
- ✅ 场景配置验证

#### 1.4 装饰器测试

```bash
# 函数级chaos装饰器
pytest tests/unit/test_decorators.py -v
```

**验证点**：
- ✅ 装饰器正确注入chaos
- ✅ 概率控制
- ✅ OpenTelemetry追踪

#### 1.5 Swarm Runner测试

```bash
# 多Agent Swarm构建器
pytest tests/unit/test_swarm_runner.py -v
```

**验证点**：
- ✅ YAML解析
- ✅ Agent实例化
- ✅ 代理配置注入

---

## 阶段2: 集成测试

测试组件之间的交互。

### 运行集成测试

```bash
# 运行所有集成测试
pytest tests/integration/ -v

# 测试Proxy Addon
pytest tests/integration/test_proxy_addon.py -v
```

**验证点**：
- ✅ Proxy正确拦截请求
- ✅ 策略正确应用
- ✅ 认证中间件工作
- ✅ 日志记录正确
- ✅ 并发请求处理

---

## 阶段3: 端到端测试

测试完整的系统流程。

### 3.1 基础端到端测试

```bash
# 使用shell脚本（推荐）
./scripts/run_chaos_test.sh
```

**验证点**：
- ✅ Mock Server启动成功
- ✅ Chaos Proxy启动成功
- ✅ Agent成功调用工具
- ✅ Chaos正确注入
- ✅ 报告成功生成

### 3.2 手动端到端测试

#### 步骤1: 启动Mock Server

```bash
# 终端1
python src/tools/mock_server.py
# 应该看到: "Mock server running on http://127.0.0.1:8001"
```

**验证**：
```bash
curl http://localhost:8001/health
# 应该返回: {"status": "healthy"}
```

#### 步骤2: 启动Chaos Proxy

```bash
# 终端2
mitmdump -s agent_chaos_sdk/proxy/addon.py --listen-port 8080
```

**验证**：
```bash
# 检查端口是否监听
lsof -i :8080
# 应该显示mitmdump进程
```

#### 步骤3: 配置代理环境变量

```bash
# 终端3
export HTTP_PROXY=http://localhost:8080
export HTTPS_PROXY=http://localhost:8080
export NO_PROXY=""
```

#### 步骤4: 运行Travel Agent

```bash
# 终端3（继续）
python examples/production_simulation/travel_agent.py \
  --query "Book a flight from New York to Los Angeles on December 25th, 2025"
```

**验证点**：
- ✅ Agent成功生成工具调用
- ✅ 请求通过Proxy（检查proxy日志）
- ✅ Chaos策略被应用（如果启用）
- ✅ Agent处理响应或错误

#### 步骤5: 生成报告

```bash
# 终端3（继续）
python src/reporter/generate.py
```

**验证**：
```bash
# 查看报告
cat reports/resilience_report.md
cat reports/resilience_report.json
```

**验证点**：
- ✅ 报告成功生成
- ✅ 包含工具调用统计
- ✅ 包含chaos注入统计
- ✅ 包含恢复率分析
- ✅ 包含竞态条件检测

---

## 阶段4: CLI测试

测试Python CLI工具。

### 4.1 CLI基础命令

#### 初始化模板

```bash
# 生成chaos plan模板
agent-chaos init

# 验证生成的文件
cat chaos_plan.yaml
```

**验证点**：
- ✅ 文件成功创建
- ✅ 包含所有必需字段
- ✅ YAML格式正确

#### 验证Plan

```bash
# 验证示例plan
agent-chaos validate examples/plans/travel_agent_chaos.yaml

# 验证无效plan（应该报错）
agent-chaos validate examples/plans/invalid.yaml  # 如果存在
```

**验证点**：
- ✅ 有效plan通过验证
- ✅ 无效plan被拒绝
- ✅ 错误信息清晰

#### 运行实验

```bash
# 运行实验（带Mock Server）
agent-chaos run examples/plans/travel_agent_chaos.yaml --mock-server

# 在另一个终端运行Agent
export HTTP_PROXY=http://localhost:8080
python examples/production_simulation/travel_agent.py
```

**验证点**：
- ✅ CLI成功启动所有服务
- ✅ Dashboard URL显示
- ✅ 实时指标更新
- ✅ Ctrl+C优雅关闭

### 4.2 测试不同Chaos Plan

```bash
# 测试支付失败场景
agent-chaos run examples/plans/payment_failure.yaml --mock-server

# 测试认知层攻击
agent-chaos run examples/plans/cognitive_attacks.yaml --mock-server

# 测试RAG投毒
agent-chaos run examples/plans/rag_poisoning.yaml --mock-server

# 测试Swarm破坏
agent-chaos run examples/plans/swarm_disruption.yaml --mock-server
```

---

## 阶段5: Dashboard测试

测试实时可视化Dashboard。

### 5.1 启动Dashboard

```bash
# 使用CLI（自动启动）
agent-chaos run examples/plans/travel_agent_chaos.yaml --mock-server

# 应该看到: "✓ Dashboard available at http://127.0.0.1:8081"
```

### 5.2 访问Dashboard

1. **打开浏览器**: `http://127.0.0.1:8081`
2. **配置浏览器代理绕过**（如果遇到503错误）:
   - Chrome: 设置 → 系统 → 代理 → 高级 → 例外: `127.0.0.1, localhost`
   - Firefox: 设置 → 网络设置 → 不使用代理: `127.0.0.1, localhost`

### 5.3 验证Dashboard功能

**验证点**：
- ✅ Dashboard页面加载
- ✅ WebSocket连接成功（状态指示器变绿）
- ✅ 实时统计更新（Total Requests, Chaos Injected等）
- ✅ 拓扑图显示（User → Agent → Proxy → Tool）
- ✅ 事件列表显示实时事件
- ✅ 点击节点/事件显示详情
- ✅ 颜色编码正确（红色=错误，橙色=Chaos，绿色=成功）

### 5.4 触发事件测试

在Dashboard运行时，运行Agent：

```bash
# 另一个终端
export HTTP_PROXY=http://localhost:8080
python examples/production_simulation/travel_agent.py \
  --query "Book a flight from NY to LA"
```

**观察Dashboard**：
- ✅ 请求事件出现
- ✅ Chaos注入事件出现（如果启用）
- ✅ 响应事件出现
- ✅ 拓扑图更新
- ✅ 统计数字增加

---

## 阶段6: 可观测性测试

测试OpenTelemetry集成。

### 6.1 启动可观测性栈

```bash
# 启动Docker Compose（Jaeger + Prometheus + Grafana）
docker-compose up -d

# 验证服务启动
docker-compose ps
```

### 6.2 查看Jaeger追踪

1. **打开Jaeger UI**: `http://localhost:16686`
2. **运行测试**:
   ```bash
   ./scripts/run_chaos_test.sh
   ```
3. **在Jaeger中查看**:
   - 选择服务: `victim-agent` 或 `chaos-proxy`
   - 点击 "Find Traces"
   - 查看完整的追踪链路

**验证点**：
- ✅ 追踪显示完整的请求流程
- ✅ 包含chaos注入span
- ✅ 包含工具调用span
- ✅ 错误正确标记

### 6.3 查看Prometheus指标

1. **打开Prometheus**: `http://localhost:9090`
2. **查询指标**:
   ```promql
   # 总请求数
   chaos_engineering_ai_requests_total
   
   # Token使用
   chaos_engineering_ai_token_usage_total
   
   # Chaos注入次数
   chaos_engineering_ai_chaos_injections_total
   
   # 按角色分组的请求
   chaos_engineering_ai_requests_total{agent_role="TravelAgent"}
   ```

**验证点**：
- ✅ 指标正确记录
- ✅ 标签正确应用
- ✅ 时间序列数据可用

### 6.4 查看Grafana Dashboard

1. **打开Grafana**: `http://localhost:3000` (默认: admin/admin)
2. **导入预配置Dashboard**（如果有）
3. **查看图表**:
   - 请求率
   - 错误率
   - 延迟分布
   - Token使用

---

## 阶段7: 高级功能测试

### 7.1 协议模糊测试（MCP Fuzzing）

#### 启用Schema-Aware Fuzzing

编辑 `config/chaos_config.yaml`:

```yaml
strategies:
  - name: mcp_fuzzing
    type: mcp_fuzzing
    enabled: true
    probability: 1.0
    params:
      fuzz_type: schema_violation
      target_endpoint: "/search_flights"
```

#### 运行测试

```bash
./scripts/run_chaos_test.sh
```

**验证点**：
- ✅ 日期字段被注入无效格式
- ✅ 数字字段被注入类型错误
- ✅ 字符串字段被注入边界值
- ✅ Agent正确处理或失败

### 7.2 竞态条件检测

#### 测试场景

Agent可能并行调用 `search_flights` 和 `book_ticket`，导致竞态条件。

**验证点**：
- ✅ 报告检测到竞态条件
- ✅ 显示依赖关系违规
- ✅ 提供修复建议

查看报告：
```bash
cat reports/resilience_report.md | grep -A 5 "Race Condition"
```

### 7.3 组策略测试（基于角色）

#### 配置组策略

编辑 `config/chaos_config.yaml`:

```yaml
strategies:
  - name: disable_qa
    type: group_failure
    enabled: true
    params:
      target_role: "QAEngineer"
      probability: 1.0
```

#### 运行Swarm测试

```bash
# 如果有swarm示例
python examples/scalable_swarm/run_enterprise.py
```

**验证点**：
- ✅ 所有QA工程师的请求被拦截
- ✅ 其他角色不受影响
- ✅ 指标按角色分组

### 7.4 记录和回放（Tape Replay）

#### 记录会话

```bash
# 使用CLI记录模式
agent-chaos record examples/plans/travel_agent_chaos.yaml --tape test_session.tape

# 在另一个终端运行Agent
export HTTP_PROXY=http://localhost:8080
python examples/production_simulation/travel_agent.py
```

#### 回放会话

```bash
# 使用CLI回放模式
agent-chaos replay test_session.tape --plan examples/plans/travel_agent_chaos.yaml

# 在另一个终端运行Agent（应该使用录制的响应）
export HTTP_PROXY=http://localhost:8080
python examples/production_simulation/travel_agent.py
```

**验证点**：
- ✅ 请求匹配正确
- ✅ 返回录制的响应
- ✅ 无网络访问（Mock Server可以关闭）
- ✅ Chaos上下文被保留

### 7.5 RAG投毒测试

#### 配置RAG投毒策略

编辑 `examples/plans/rag_poisoning.yaml`:

```yaml
scenarios:
  - name: inject_fake_docs
    type: phantom_document
    enabled: true
    params:
      target_json_path: "$.results[*].snippet"
      mode: injection
      probability: 1.0
```

#### 运行测试

```bash
agent-chaos run examples/plans/rag_poisoning.yaml --mock-server
```

**验证点**：
- ✅ 响应被正确修改
- ✅ 虚假信息被注入
- ✅ Agent是否检测到异常

### 7.6 Swarm破坏测试

#### 配置Swarm破坏策略

编辑 `examples/plans/swarm_disruption.yaml`:

```yaml
scenarios:
  - name: mutate_messages
    type: swarm_disruption
    enabled: true
    params:
      attack_type: message_mutation
      target_traffic: AGENT_TO_AGENT
```

#### 运行测试

```bash
agent-chaos run examples/plans/swarm_disruption.yaml --mock-server
```

**验证点**：
- ✅ Agent间通信被正确分类
- ✅ 消息被正确修改
- ✅ Swarm行为受影响

---

## 测试检查清单

### ✅ 基础功能

- [ ] 单元测试全部通过 (`pytest tests/unit/`)
- [ ] 集成测试全部通过 (`pytest tests/integration/`)
- [ ] Mock Server启动成功
- [ ] Chaos Proxy启动成功
- [ ] Agent成功调用工具
- [ ] 报告成功生成

### ✅ 策略功能

- [ ] 延迟策略工作
- [ ] 错误注入策略工作
- [ ] MCP模糊测试工作
- [ ] 数据损坏策略工作
- [ ] 组策略工作
- [ ] 认知层攻击工作
- [ ] RAG投毒工作
- [ ] Swarm破坏工作

### ✅ CLI功能

- [ ] `agent-chaos init` 工作
- [ ] `agent-chaos validate` 工作
- [ ] `agent-chaos run` 工作
- [ ] `agent-chaos record` 工作
- [ ] `agent-chaos replay` 工作

### ✅ Dashboard功能

- [ ] Dashboard页面加载
- [ ] WebSocket连接成功
- [ ] 实时事件更新
- [ ] 拓扑图显示
- [ ] 统计数字更新
- [ ] 详情查看工作

### ✅ 可观测性

- [ ] Jaeger追踪显示
- [ ] Prometheus指标记录
- [ ] Grafana Dashboard显示（如果配置）

### ✅ 高级功能

- [ ] 竞态条件检测工作
- [ ] 记录和回放工作
- [ ] 协议模糊测试工作
- [ ] 组策略工作
- [ ] RAG投毒工作

---

## 故障排除

### 常见问题

1. **端口被占用**
   ```bash
   # 检查端口
   lsof -i :8080  # Proxy
   lsof -i :8081  # Dashboard
   lsof -i :8001  # Mock Server
   
   # 杀死进程
   kill -9 <PID>
   ```

2. **Dashboard连接被拒绝**
   - 查看 `DASHBOARD_FIX.md`
   - 配置浏览器绕过代理

3. **Agent无法连接Mock Server**
   - 检查 `HTTP_PROXY` 环境变量
   - 确保 `NO_PROXY` 为空（强制localhost走代理）

4. **测试失败**
   - 检查日志: `logs/proxy.log`, `logs/agent_output.log`
   - 运行 `pytest -v` 查看详细错误
   - 检查Ollama是否运行: `ollama list`

5. **报告生成错误**
   - 确保 `logs/proxy.log` 存在
   - 检查日志格式是否正确（JSON格式）
   - 查看错误信息: `python src/reporter/generate.py -v`

---

## 性能测试

### 并发请求测试

```bash
# 使用Apache Bench或类似工具
ab -n 100 -c 10 http://localhost:8001/search_flights
```

**验证点**：
- ✅ Proxy处理并发请求
- ✅ 无阻塞
- ✅ 日志正确记录

### 压力测试

```bash
# 运行多个Agent实例
for i in {1..10}; do
  python examples/production_simulation/travel_agent.py &
done
```

**验证点**：
- ✅ 系统稳定
- ✅ 无内存泄漏
- ✅ 响应时间合理

---

## 持续集成

### GitHub Actions

查看 `.github/workflows/test.yml` 了解CI配置。

**自动运行**：
- 单元测试
- 集成测试
- 类型检查 (mypy)
- 覆盖率报告

---

## 总结

完成以上所有测试阶段后，你应该能够：

1. ✅ **验证核心功能**: 所有策略和组件工作正常
2. ✅ **验证集成**: 系统各组件正确协作
3. ✅ **验证用户体验**: CLI和Dashboard易用
4. ✅ **验证可观测性**: 追踪和指标正确记录
5. ✅ **验证高级功能**: 所有前沿功能工作正常

**下一步**: 根据测试结果修复问题，然后可以开始使用平台进行实际的Agent混沌测试！

---

## 快速测试命令总结

```bash
# 1. 完整测试（推荐）
./scripts/run_chaos_test.sh

# 2. 单元测试
pytest tests/unit/ -v

# 3. CLI测试
agent-chaos run examples/plans/travel_agent_chaos.yaml --mock-server

# 4. Dashboard测试
# 访问 http://127.0.0.1:8081

# 5. 可观测性测试
docker-compose up -d
# 访问 http://localhost:16686 (Jaeger)
# 访问 http://localhost:9090 (Prometheus)
```

