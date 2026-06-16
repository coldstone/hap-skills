# 工作流共享规则

> 本文件被 `10_create_workflows.md` 和 `11_create_action_workflows.md` 共同引用。阅读步骤文件时**必须完整阅读本文件**。

---

## 触发节点引用约定

本文档中使用 **`<triggerNodeRef>`** 作为触发节点引用的通用占位符。实际传值时，必须根据工作流类型替换为正确的值：

| 工作流类型 | 如何获取触发节点引用 | `node` 传值格式 | 公式/模板占位符格式 |
| :--- | :--- | :--- | :--- |
| **普通工作流**（`create_process` 新建） | 调用 `create_process` 或 `get_workflow_structure` 后，从返回结果中提取触发节点的 `nodeAlias` | `{ "nodeAlias": "<实际别名>" }` | `$<实际别名>-fieldId$` |
| **自定义动作工作流**（方案自带 `processId`） | 调用 `get_workflow_structure` 后，从返回结果中提取触发节点的物理 `nodeId` | `{ "nodeId": "<实际nodeId>" }` | `$<实际nodeId>-fieldId$` |

> ⚠️ **绝对禁止假设触发节点的别名是固定字符串（如 `"trigger"`）。** 触发节点的别名由系统分配，不同工作流各不相同。自定义动作工作流的触发节点甚至没有可用的别名，只能使用物理 `nodeId`。如果使用了错误的别名，发布校验将抛出 `StartNodeControlsIsNull` 致命错误。

## 名称 → ID 映射规则

方案中使用中文名称引用工作表和字段，你必须从 `worksheetContext` 中查找对应的真实 ID：

- **工作表名称** → `worksheetContext[].name` → 取 `id`
- **字段名称** → `worksheetContext[].fields[].name` → 取 `id`
- **选项值名称** → `worksheetContext[].fields[].options[].value` → 取 `key`
- **角色名称** → `roleContext[].name` → 取 `id`
- **视图名称** → `viewIdByName["工作表名/视图名"]` → 取 viewId

> 🚫 **fieldId 必须使用字段的真实 `id`，严禁使用字段的 `alias`。** 工作流 API 不识别 alias。

> ⚠️ **禁止自行编造 ID**。如果方案中提到的名称在 `worksheetContext` 中找不到，跳过该节点并说明。

### 降级策略

- **角色找不到**：从 `roleContext` 中选择语义最接近的角色替代；若为空，改用 `{ kind: "triggerUser" }`
- **视图找不到**：使用该工作表的第一个视图

## 易错规则

### fieldId 必须用真实 ID，绝对严禁使用 alias

HAP 工作流物理引擎在解析节点逻辑时**完全不识别字段的 alias**（如 `status`、`title` 等）。如果在工作流配置中传入 alias，会导致逻辑静默丢失或产生 `INVALID_FIELD` 报错。所有引用字段 ID 的位置，必须从 `worksheetContext` 中映射出真实的 24 位十六进制字段 ID！

此规则适用于所有包含 `fieldId` 的物理配置：
- `ValueRef.fieldId`、`FieldValueRef.fieldId`
- `FieldPatch.fieldId`
- `Condition.left.fieldId`、`Condition.right.fieldId`
- `config.formula` 中 `$nodeAlias-fieldId$` 的 fieldId 部分（含触发节点引用，详见「触发节点引用约定」）
- `config.content` / `config.body` 模板中的 fieldId 部分
- `trigger.config.trigger_fields[]`

---

### Condition：left.node 始终必填

Condition 结构为 `{ left, op, right }`。其中 `left` 属于 `FieldValueRef`，**`node` 属性绝对不能缺省**（即使是查询节点自身的内部过滤条件）。

- **查询节点自身的 filter（如 `get_single` / `get_multiple`）**：`left.node` **必须且只能引用当前查询节点自身**；`right` 引用上游节点（如触发节点或更早的查询节点）以提供动态过滤值。
  
  *示例*（查询节点 `find_book` 的 filter 中，`left.node` 指向 `find_book` 自身，`right.node` 指向上游节点）：
  ```json
  {
    "logic": "and",
    "items": [
      {
        "left": { "kind": "field", "node": { "nodeAlias": "find_book" }, "fieldId": "674046935a63abb6377d23a1" },
        "op": "eq",
        "right": { "kind": "field", "node": "<triggerNodeRef>", "fieldId": "674046935a63abb6377d23ff" }
      }
    ]
  }
  ```

- **分支节点 filter（`branch`）**：`left.node` 必须引用分支上游的某个数据源节点。
- **触发器 filter**：`left.node` 引用触发节点自身（按「触发节点引用约定」传值）。

---

### Condition.op 合法枚举

> ⚠️ HAP 工作流仅支持以下操作符字面值，**禁止使用任何其他操作符**（如 `ge`/`le`/`is_empty`/`neq` 等变体）：

`eq`（等于）· `ne`（不等于）· `gt`（大于）· `gte`（大于等于）· `lt`（小于）· `lte`（小于等于）· `in`（属于数组）· `not_in`（不属于数组）· `empty`（为空）· `not_empty`（不为空）· `contains`（包含）· `not_contains`（不包含）· `starts_with`（开头是）· `ends_with`（结尾是）· `all_contains`（同时包含）· `belongs`（属于部门/组织）· `not_belongs`（不属于部门/组织）· `checked`（已勾选）· `unchecked`（未勾选）

---

### 查询结果分支处理规范

- **`get_single` 结果分支判空**：直接在下游 `branch` 中判断该查询节点的 `rowid` 是否为 `not_empty`：
  
  ```json
  {
    "left": { "kind": "field", "node": { "nodeAlias": "find_single_book" }, "fieldId": "rowid" },
    "op": "not_empty"
  }
  ```

- **`get_multiple` 结果分支判空**：**绝对严禁**直接判断 `get_multiple` 节点的 `rowid`。必须采用以下二阶段链式逻辑：
  1. **步骤一**：先紧随其后创建一个 `rollup`（汇总统计）节点，对 `get_multiple` 节点的记录进行 `COUNT` 聚合。
  2. **步骤二**：在 downstream 的 `branch` 条件分支中，判断该 `rollup` 节点输出的 `total_count` 字段是否大于 0。
  
  *完整串联示例*：
  ```json
  // 1. 创建 rollup 节点 count_overdue
  {
    "nodeAlias": "count_overdue",
    "nodeType": "rollup",
    "config": {
      "target": { "kind": "record", "node": { "nodeAlias": "find_overdue_records" } },
      "aggregations": [{ "alias": "total_count", "fieldId": "rowid", "func": "COUNT" }]
    }
  }
  // 2. 分支判断 rollup 字段
  {
    "left": { "kind": "field", "node": { "nodeAlias": "count_overdue" }, "fieldId": "total_count" },
    "op": "gt",
    "right": { "kind": "literal", "value": 0 }
  }
  ```

---

### config.target 而非 sourceNode

HAP `NodeSpec` 基础模式上**完全没有 `sourceNode` 属性**。凡是需要指定数据源记录的节点，必须将配置写在 `config.target` 内，使用 `RecordValueRef`（`kind` 固定为 `"record"`）：

- **✅ 正确示例**：
  ```json
  {
    "nodeAlias": "update_status",
    "nodeType": "update_record",
    "config": {
      "target": { "kind": "record", "node": "<triggerNodeRef>" },
      "fields": [...]
    }
  }
  ```
- **❌ 错误示例**：`{ "sourceNode": { ... }, "config": { ... } }` （API 会静默报错丢弃）

---

### 分支路径（branch path）的使用与引用约束

分支路径的 alias 仅作为组织节点层级结构的路由标记：
- ❌ **绝对不能作为下游任何节点的 `prevNode`**：分支路径内的第一个子节点，其 `prevNode` 物理指向该路径的 alias，其 `parentNode` 也必须指向该路径的 alias。路径内部后续节点的 `prevNode` 指向路径内部的前一个节点。
- ❌ **绝对不能作为 `target.node` 的值**：如 `cc`、`update_record` 节点的 `config.target.node` 必须指向具体的触发器节点或 `get_single` 节点，**绝不能指向分支路径 alias**。

---

### send_email / send_internal_notice 正文模板高标准

- **严禁使用 literal 盲盒正文**：正文绝对不要只写一行"您有新的审批，请处理"这种宽泛笼统、对收件人无实质价值的文本。
- **高标准格式**：正文必须物理传 `{ "kind": "template" }`，并且强烈推荐将 `bodyType` 设定为 `"html"`，在正文中将关键的业务字段（如申请人、单号、日期、费用等）通过 `$nodeAlias-fieldId$` 形式做精美拼接。其中 `nodeAlias` 部分引用触发节点时，需按「触发节点引用约定」使用实际别名或 nodeId。
  
  *HTML 邮件高仿真示例*（假设触发节点别名为 `start`）：
  ```json
  {
    "subject": { "kind": "template", "value": "借阅超时告警：$start-674046935a63abb6377d23a1$ 已经超期" },
    "body": {
      "kind": "template",
      "value": "<h3>图书超期未归还温馨提醒</h3><p><b>借阅人：</b>$start-674046935a63abb6377d23b2$</p><p><b>图书名称：</b>$start-674046935a63abb6377d23a1$</p><p><b>应还日期：</b>$start-674046935a63abb6377d23c5$</p><p>请尽快将图书归还至服务台，谢谢您的配合！</p>"
    },
    "bodyType": "html"
  }
  ```

---

### approve / fill_in 审批填写块设计规范

- **`allowReject` 物理使能**：对于审批（`approve`）节点，默认的 `allowReject` 是 `false`。在绝大多数真实业务中，必须显式将其配置为 `true`，以允许审批人拒绝申请。
- **`fill_in` 节点的 `assignee` 限制**：填写节点的 `assignee` 是**单个 `PersonRef` 结构**（非数组），且 `formProperties`（要填写的表单属性）必须至少声明一项。

---

### rollup / compute 物理输出字段常数

当下游节点（如通知正文或更新节点）想要引用 `rollup`、`compute` 或 `code` 节点的输出结果时，必须使用以下系统固定的常数字段 ID 或自定义参数名：

| 节点类型 | 参数配置类型 | 物理输出字段 ID (常数 / 自定义) | 下游引用占位符示例 |
| :--- | :--- | :--- | :--- |
| **`rollup`** | 聚合统计 (SUM/COUNT/AVG...) | **`number_fx_id`** | `$nodeAlias-number_fx_id$` |
| **`compute`** | `computeType = "number"` (数学公式) | **`number_fx_id`** | `$nodeAlias-number_fx_id$` |
| **`compute`** | `computeType = "dateDiff"` (日期差) | **`number_fx_id`** | `$nodeAlias-number_fx_id$` |
| **`compute`** | `computeType = "dateOffset"` (日期偏移) | **`date_fx_id`** | `$nodeAlias-date_fx_id$` |
| **`code`** | 代码块 (自定义输出参数) | **自定义输出名 `name`** | `$nodeAlias-outputName$` |

#### ⚠️ dateOffset 类型的日期偏移计算语法极其严格：
- 偏移量表达式 `offsetExpression` 必须包含正负号和单位（例如 `"+30d"`、`"+3d"`、`"-1d"`），大小写敏感。如果只写数字或不带单位，在发布校验阶段会直接报 `INVALID_NODE offsetExpression 格式不正确` 致命错误。
- 它的物理输出字段 ID 固定为 `date_fx_id`，下游节点引用其结果时必须使用 `$nodeAlias-date_fx_id$` 的形式。

---

### 避免 `StartNodeControlsIsNull` 发布校验错误

- **`update_record`（更新记录）节点执行后并没有暴露输出控制字段（输出 controls 为空）。**
- **绝对不能**在后续节点（如站内通知、审批、更新等）中通过形如 `$update_record_node-fieldId$` 强行引用更新记录节点的字段值。如果强行引用，明道云流程发布校验将直接拦截抛出 `StartNodeControlsIsNull`（起始节点配置控制为空或不存在）的致命阻断错误。
- **标准避错做法**：后续节点需要使用该记录的字段值时，应该直接追溯并引用触发源记录（如 `$<triggerNodeAlias>-fieldId$`）或之前通过查询节点获取到的物理记录（如 `$get_single_node-fieldId$`）。

---

## 节点创建原则

### 原则 1：同层节点尽量一次创建

同一层级的非分支节点，应合并到一次 `batch_create_process_nodes` 调用中。

### 原则 2：分支处理

分支节点的 `config.paths` 定义路径别名和条件。路径下的子节点通过 `parentNode` 挂入对应路径。

> ⚠️ 分支后不允许用 `prevNode` 直接接分支节点。分支后的所有节点必须通过 `parentNode` 挂到某个路径下。

> ⚠️ 分支路径下的第一个节点，`prevNode` 必须显式指向该路径的 alias（与 `parentNode` 相同）。

### 原则 3：审批块——一次性内联创建

审批块使用 `nodeType: "approval_block"`，内部节点写在 `config.process.nodes` 中：

```json
{
  "nodeAlias": "approval",
  "nodeType": "approval_block",
  "prevNode": "<triggerNodeRef>",
  "config": {
    "target": { "kind": "record", "node": "<triggerNodeRef>" },
    "initiators": [{ "kind": "field", "node": "<triggerNodeRef>", "fieldId": "ownerid" }],
    "process": {
      "mode": "create",
      "name": "审批流程",
      "nodes": [
        {
          "nodeAlias": "approve_step",
          "nodeType": "approve",
          "config": {
            "target": { "kind": "record", "node": { "nodeAlias": "approval_start" } },
            "approvers": [{ "kind": "role", "roleId": "role_xxx" }],
            "mode": "any",
            "allowReject": true
          }
        }
      ]
    }
  }
}
```

> ⚠️ **`initiators` 是必填项**：审批块必须显式指定发起人。常见做法是绑定触发记录的拥有者：`{ "kind": "field", "node": <triggerNodeRef>, "fieldId": "ownerid" }`。不传此字段会导致 `config.initiators: 不能为空` 致命校验错误。

> ⚠️ 审批内部节点引用记录时，使用 `{ nodeAlias: "approval_start" }`（固定别名）。**绝对不能**使用外部主流程的触发节点别名（如 `trigger`、`start` 等），因为审批子流程无法跨作用域识别外部别名，会导致 `找不到节点别名` 致命报错。

> 🚫 **审批块物理命名空间隔离（极易踩坑）**：
> `approval_block` 内部（`config.process.nodes`）与外部主流程是**完全隔离的执行上下文**：
> - 内部节点的 `prevNode` **不能**指向外部主流程中的任何节点
> - 外部主流程的节点 `prevNode` **不能**指向内部节点
> - 内部节点引用被审批的记录时，**只能**使用固定别名 `{ nodeAlias: "approval_start" }`，不能使用外部触发节点的别名
>
> 违反上述任一规则，均会触发 `prevNode 找不到` 或 `找不到节点别名` 的致命校验错误。

> ⚠️ **审批结果分两层**（必须明确区分放置位置）：
> - **审批内部**（放在 `config.process.nodes` 中）：在 `approve` 节点之后添加 `branchType: "approval_result"` 分支，用于写入审批人（`executorid`）、审批意见（`opinionSummary`）等审批详细信息到记录中
> - **主流程**（放在 `approval_block` 节点之后的外部主流程中）：用 `branch` 判断审批块的最终 `result`（`PASS` / `OVERRULE`），用于根据通过/驳回结果更新主记录的业务状态、发送通知等

### 原则 4：子流程——一次性内联创建

子流程使用 `nodeType: "sub_process"`，内部节点写在 `config.process.nodes` 中。

> ⚠️ **子流程内部数据作用域**：
> - 子流程开始节点固定别名 `sub_trigger`，代表当前正在处理的那条记录
> - 子流程内部节点引用当前记录时，使用 `{ nodeAlias: "sub_trigger" }`
> - **子流程无法跨作用域引用主流程节点**
> - 子流程内部可以有自己的查询节点，后续节点可引用内部查询节点的 alias

> 分支、审批块和子流程可以任意嵌套。

## 发布工作流

> [!CAUTION]
> **含子流程/审批块时的发布顺序（违反必报 `NodeAppIsNull` 致命错误）**：
>
> 明道云在创建 `sub_process` 或 `approval_block` 节点时，系统会为其内部自动创建一个**独立的子工作流**。该子工作流初始状态为**未发布**。如果直接发布主流程，主流程编译器会发现子流程未发布，抛出 `NodeAppIsNull` 致命错误并拒绝发布。
>
> **强制操作步骤**：
> 1. 调用 `batch_create_process_nodes` 创建含子流程/审批块的节点后，从返回值 `createdNodes` 中找到对应项，提取其内部流程的 `processId`
> 2. **先对每个内部 `processId` 调用 `publish_process`**，确保所有子流程/审批流程发布成功
> 3. **最后再对主流程的 `processId` 调用 `publish_process`**
>
> 如果主流程中有**多个**子流程/审批块，必须**逐个**发布所有内部流程后，才能发布主流程。

---

## 全局约束

- 节点中引用的 `worksheetId`、`fieldId` 必须来自 `worksheetContext`，**必须使用 ID，不能使用别名，不能自行编造**
- 系统级参数：使用 `{ kind: "systemField", fieldId: "nowTime" }` 表示当前时间

## nodeAlias 命名

- 使用英文蛇形命名法，简短且语义明确
- 示例：`find_related_book`、`update_stock`、`notify_applicant`
- 禁止使用中文、无意义序号

## 节点定位

- `prevNode`：前驱节点（执行顺序）。分支路径下的第一个节点填该路径 alias
- `parentNode`：容器归属。分支路径下的子节点填对应的路径 alias

## 数据引用规范

### ValueRef 的 6 种 kind

节点配置中所有值引用（`ValueRef`）通过 `kind` 字段决定取值方式。**选错 kind 是最常见的构造错误。**

| kind | 用途 | 必填属性 | 示例 |
|---|---|---|---|
| `field` | 引用上游节点的字段值 | `node` + `fieldId` | `{ kind: "field", node: { nodeAlias: "find_book" }, fieldId: "674...a1" }` |
| `systemField` | 引用系统级参数 | `fieldId` | `{ kind: "systemField", fieldId: "nowTime" }` |
| `literal` | 固定值 | `value` | `{ kind: "literal", value: "已完成" }` |
| `record` | 引用整条记录（用于 target 和关联记录字段赋值） | `node` | `{ kind: "record", node: { nodeAlias: "sub_trigger" } }` |
| `template` | 模板字符串（含占位符） | `value` | `{ kind: "template", value: "$start-674...a1$" }` |
| `empty` | 显式空值 | 无 | `{ kind: "empty" }` |

> ⚠️ **`systemField` 不需要也不能携带 `node` 属性。** 它是全局系统值，与任何节点无关。在模板中引用系统字段时，必须使用固定前缀 `system`，格式为 `$system-fieldId$`（如 `$system-nowTime$`）。**严禁**使用任意节点别名（如 `$sub_trigger-nowTime$`）——这会被引擎解析为该节点上名为 `nowTime` 的业务字段（不存在），导致静默丢失。

### systemField 合法枚举

| fieldId | 含义 | 常见用途 |
|---|---|---|
| `nowTime` | 节点执行时的当前时间 | compute 日期差/偏移的 startTime/endTime、delay until_time |
| `triggertime` | 工作流触发时间 | 记录触发时刻（与 nowTime 不同，延迟节点后两者会有差异） |
| `triggeraid` | 触发人账号 ID | FieldPatch 中写入发起人（注意：PersonRef 中用 `kind: "triggerUser"`，FieldPatch.value 中用 `kind: "systemField", fieldId: "triggeraid"`） |

### 占位符语法（`$...$`）

以下场景统一使用 `$nodeAlias-fieldId$` 占位符嵌入动态值：
- `kind: "template"` 的 `value`（通知正文、邮件主题等）
- `config.expression`（compute 数值公式）
- `config.offsetExpression`（compute 日期偏移表达式）

规则：
- `nodeAlias` 部分：引用触发节点时按「触发节点引用约定」使用实际别名或 nodeId
- `fieldId` 部分：必须是真实字段 ID，严禁 alias
- **系统字段**使用固定前缀 `system`：`$system-nowTime$`、`$system-triggertime$`、`$system-triggeraid$`

### 各作用域下的记录引用

| 作用域 | 引用当前记录的 node | 说明 |
|---|---|---|
| 主流程 | 按「触发节点引用约定」取得的实际别名或 nodeId | 详见文档顶部 |
| 子流程内部 | `{ nodeAlias: "sub_trigger" }` | 固定别名，代表当前遍历的那条记录 |
| 审批块内部 | `{ nodeAlias: "approval_start" }` | 固定别名，代表被审批的记录 |

- **触发记录**：`{ kind: "record", node: <triggerNodeRef> }`
- **其他表记录**：先用查询节点（`get_single` / `get_multiple`）获取，再用查询节点的 nodeAlias 引用
- **cc / approve / fill_in**：`config.target` 只支持单条记录。多条时用 `sub_process`
- **跨作用域禁令**：子流程/审批块内部**不能**引用外部主流程节点，反之亦然

### 常见错误对照

| ❌ 错误写法 | ✅ 正确写法 | 原因 |
|---|---|---|
| `{ kind: "field", node: { nodeAlias: "start" }, fieldId: "triggertime" }` | `{ kind: "systemField", fieldId: "triggertime" }` | `triggertime` 是系统字段，不属于任何节点，不需要 `node` |
| 模板中写 `$sub_trigger-nowTime$` | `$system-nowTime$` | 系统字段在模板中必须用固定前缀 `system`，不能用节点别名 |
| `{ kind: "field", node: { nodeAlias: "update_status" }, fieldId: "674...a1" }` | 引用触发节点或上游查询节点的 fieldId | `update_record` 节点无输出字段，引用会触发 `StartNodeControlsIsNull` |
| 子流程内 `{ node: { nodeAlias: "start" } }`（主流程别名） | `{ node: { nodeAlias: "sub_trigger" } }` | 子流程不能跨作用域引用主流程节点，只能内部引用 |
| 审批内 `{ node: { nodeAlias: "start" } }`（主流程别名） | `{ node: { nodeAlias: "approval_start" } }` | 审批块内部只能用固定别名 `approval_start` |
| `{ kind: "field", fieldId: "status" }` | `{ kind: "field", node: { nodeAlias: "..." }, fieldId: "674...a1" }` | `field` 必须携带 `node`；`fieldId` 必须用真实 ID，严禁 alias |
