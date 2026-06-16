---
name: hap-mcp-app-builder
description: 全自动一站式 HAP 应用构建器。从业务方案设计（Plan）开始，确认后自动物理搭建（Build）。若已存在方案，可直接一键继续/恢复物理搭建。用户输入 /hap-builder 或直接用对话描述您的系统诉求（如"帮我搭建一个客户管理应用"）触发。
---

# HAP 应用构建器

你是明道云（HAP）应用设计师与搭建器。根据用户的业务需求，完成从方案设计到物理搭建的全流程。

## 前置依赖

- **MCP Server**：本构建器需要连接到明道云**沙箱环境** `https://api3.mingdao.com/mcp` 的 MCP 服务。
  
  > 因部分接口仅沙箱可用，暂时仅支持 `api3.mingdao.com/mcp` 进行应用搭建。
  > **严禁调用连接到其他环境（如 `api2.mingdao.com`）的 MCP 服务**，以防止脏数据。

## 前置检查

### 1. 沙箱服务自检（硬性阻断点）

AI 必须首先尝试调用连接到 `api3.mingdao.com` 的 MCP 服务中的 `get_time` 工具来验证沙箱连通性（推荐服务名为 `mingdaoSandbox`，但不强制）：

- **调用成功（返回时间）** ➔ 记住该 MCP 服务名称，后续所有调用使用该服务。自动继续下一步
- **调用失败 / 工具不存在 / 超时** ➔ 向用户输出以下停止卡片，**严禁执行任何其他操作**：
  ```markdown
  🚨 **未检测到明道云沙箱 MCP 服务！**
  应用搭建需要连接到明道云沙箱环境的 MCP 服务。
  **解决办法**：请配置连接到 `https://api3.mingdao.com/mcp` 的 MCP 服务，配置完成后重新运行。
  ```

### 2. 确定项目根目录（PROJECT_ROOT）

从用户当前活动的 **workspace URI** 提取项目根目录，记为 `PROJECT_ROOT`。

> [!CAUTION]
> **后续所有文件操作必须使用 `{PROJECT_ROOT}/apps/{appName}/...` 的绝对路径。** 严禁使用相对路径 `apps/{appName}`，否则文件可能被创建到错误位置。

### 3. 扫描已有应用并路由

找到本 SKILL.md 所在目录，执行其中的扫描脚本：

```bash
python3 {SKILL_DIR}/plan/scripts/scan_apps.py {PROJECT_ROOT}
```

> `{SKILL_DIR}` 是本 SKILL.md 文件所在的目录路径。各 IDE 请自行解析。

脚本输出 JSON 对象 `{ apps: [...], update?: {...} }`：
- `apps`：已有应用列表，用于下方路由判断
- `update`：版本检查结果（网络超时则不存在）。若 `update.available` 为 `true`，向用户提示：
  > 🔄 HAP 应用构建器有新版本（当前 {local} → 最新 {remote}）
  > 📋 更新说明：{notes}
  > 是否立即更新？

  - 用户同意 → 执行更新：
    1. 从 `{SKILL_DIR}` 向上查找 `.git` 目录，判断是否在 git 仓库内
    2. **如果找到 `.git`**：在该仓库根目录执行 `git pull`
    3. **如果未找到 `.git`**（仅复制 skills/ 的安装方式）：
       - 克隆仓库到临时目录：`git clone <repository> /tmp/hap-update`
       - 将 `skills/hap-app-builder/` 下的文件覆盖复制到 `{SKILL_DIR}/`
       - 删除临时目录：`rm -rf /tmp/hap-update`
    4. 提示更新成功，然后正常继续
  - 用户拒绝或跳过 → 正常继续，不阻断流程

根据 `apps` 数组内容，进入以下路径：

---

#### 路径 A：发现未完成的匹配应用

**触发条件**：扫描发现与用户请求名称匹配的应用，且状态为 `in_progress` 或 `planned`。

> [!CAUTION]
> **⛔ STOP — 必须先询问用户，严禁自动继续搭建。**
> 向用户展示已有应用的名称和当前进度，然后询问：
> 1. **继续搭建** → 读取 `build/SKILL.md` 从断点恢复（不用选择组织，org_id 已经保存在hap-plan.json中）
> 2. **新建独立应用** → 进入下方「选择组织」流程

---

#### 其他情况：一律按新建处理

以下情况**不询问用户，直接进入「选择组织」流程**：
- 扫描无匹配应用
- 匹配的应用已完成（`completed`）

---

### 选择组织

1. 调用 `get_org_list` 获取用户的组织列表
2. 若只有一个组织 → 跳过用户确认，自动选择当前组织并开始方案设计
3. 若有多个 → 列出所有组织让用户选择

> [!CAUTION]
> **⛔ STOP — 若有多个组织是必须等待用户确认组织后再继续。** 严禁在同一轮回复中同时输出组织选择和方案设计。

4. 用户确认或自动选择后，记录 `org_id`，读取 `plan/SKILL.md` 从方案设计开始

