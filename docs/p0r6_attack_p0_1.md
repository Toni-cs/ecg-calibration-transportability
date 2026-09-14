# R6-Phase2 P0-1反方攻击报告

> **反方代理**：R6-Phase2 P0-1反方挑刺代理（GLM-5.2）
> **攻击日期**：2026-09-10
> **攻击对象**：R6修复后的 `scripts/eval_l2_shift.py`（L193-196 新增 `__seed_strategy__` 标记）和 `scripts/run_e1a_l2_shift_full.py`（L278-281 safety 检查放宽）
> **依据**：`docs/p0r5_final_verdict.md` §3.1 R6必修清单 + `docs/p0r6_fix_p0_1.md` 正方修复报告
> **审查方法**：逐行代码阅读 + 7维度全覆盖攻击 + 具体反例构造

---

## 攻击点汇总

| 编号 | 维度 | 严重度 | 摘要 |
|------|------|--------|------|
| Attack-1 | 反例构造 | **致命** | eval_l2_shift.py 标记写入在 `if out_path.exists()` 条件块内，首次运行（文件不存在）时标记永远不写入，R6修复对首次运行结果完全失效 |
| Attack-2 | 逻辑断链 | **严重** | 修复报告§3.3声称"Attack-1 关闭✅"，但验证仅覆盖续传路径，未验证首次运行路径，逻辑链条存在未验证跳跃 |
| Attack-3 | 隐含假设 | **中等** | 标记值"md5_v1"硬编码 vs run_e1a的SEED_STRATEGY_VERSION常量，DRY违反，未来版本变更不同步 |
| Attack-4 | 边界失效 | **中等** | `cell["safety"]=0` 修改的是局部dict（L260 json.loads加载），函数返回后修改丢失，该行是死代码 |
| Attack-5 | 自相矛盾 | **轻微** | is_checkpoint_complete docstring仍声明safety为"安全率依赖项"（必需），但代码已改为可选，docstring与代码矛盾 |
| Attack-6 | 量级错误 | **中等** | eval_l2_shift不计算Brier reliability，其结果safety默认0会向下偏置aggregate_to_390的safety_rate聚合 |
| Attack-7 | 语义偏移 | **中等** | "safety字段缺失"（从未计算）被静默等同于"safety=0"（TS未改善），两种语义被混淆 |
| Attack-8 | 边界失效 | **轻微** | `cell["safety"]=0`在谓词函数中产生副作用（修改输入dict），违反纯函数约定，当前无害但重构脆弱 |

**汇总**：8个攻击点（1致命 + 1严重 + 4中等 + 2轻微）

---

## 逐条攻击

### Attack-1
- **维度**：反例构造
- **严重度**：**致命**
- **攻击**：R6修复将 `existing[sk]["__seed_strategy__"] = "md5_v1"` 写入位置放在 `if out_path.exists():` 条件块**内部**（L187条件，L196写入）。当 `eval_l2_shift.py` **首次运行**（`l2_shift_results.json` 不存在）时，L187条件为 False，整个 L188-197 块被跳过，L196 标记写入**永远不执行**。程序直接跳到 L198 `out_path.write_text(json.dumps(all_results, ...))` 保存 `all_results`——而 `all_results` 在 L185 赋值时只含 `seed_results`，**不含** `__seed_strategy__` 标记。

  **具体反例**：
  1. 用户首次运行 `python scripts/eval_l2_shift.py --source ptbxl --target chapman --seeds 42`
  2. L187: `out_path.exists()` → **False**（首次运行，文件不存在）
  3. L188-197 整块跳过，L196 标记写入**不执行**
  4. L198: 保存 `all_results = {"seed42": {shift结果...}}`——**无 `__seed_strategy__` 标记**
  5. 用户运行 `python scripts/run_e1a_l2_shift_full.py`
  6. `is_checkpoint_complete` L268: `seed_data.get("__seed_strategy__")` → `None` → `None != "md5_v1"` → **return False** → 重跑
  7. **R6修复完全失效**——这正是R5 Attack-1要修复的bug，R6修复对首次运行结果未修复

  **多seed首次运行更严重**：运行 `--seeds 42 43`：
  - Seed 42（文件不存在）：L187 False，跳过标记写入，保存 `{"seed42": {...无标记}}`
  - Seed 43（文件已存在）：L187 True，L196 写入 `existing["seed43"]["__seed_strategy__"] = "md5_v1"`，保存 `{"seed42": {...无标记}, "seed43": {...有标记}}`
  - **同一文件内 seed42 无标记、seed43 有标记，标记不一致**。run_e1a 检查 seed42 → 重跑，检查 seed43 → 通过，部分失败。

- **代码证据**：
  ```python
  # scripts/eval_l2_shift.py L185-198
  all_results[f"seed{seed}"] = seed_results       # L185: all_results 无标记
  out_path = run_dir / "l2_shift_results.json"     # L186
  if out_path.exists():                             # L187: 首次运行为 False
      existing = json.loads(...)                    # L188
      ...
      existing[sk]["__seed_strategy__"] = "md5_v1"  # L196: 在 if 内部！
      all_results = existing                        # L197
  out_path.write_text(json.dumps(all_results, ...)) # L198: 首次运行保存无标记的 all_results
  ```

  对比 `run_e1a_l2_shift_full.py` L427-435 的正确模式：
  ```python
  existing = load_existing_results(run_dir)          # L427: 无条件加载
  ...
  existing[sk].update(seed_results)                  # L431
  existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION  # L433: 无条件写入标记
  out_path.write_text(json.dumps(existing, ...))     # L435: 保存
  ```
  `run_e1a` 的标记写入在条件块**外部**（无条件执行），`eval_l2_shift` 的标记写入在条件块**内部**。两脚本模式不一致。

- **修复建议**：将标记写入移到 `if out_path.exists():` 块**外部**，或在首次运行分支也写入标记。最小修复：
  ```python
  all_results[f"seed{seed}"] = seed_results
  all_results[f"seed{seed}"]["__seed_strategy__"] = "md5_v1"  # 无条件写入
  out_path = run_dir / "l2_shift_results.json"
  if out_path.exists():
      existing = json.loads(out_path.read_text(encoding="utf-8"))
      sk = f"seed{seed}"
      if sk not in existing:
          existing[sk] = {}
      existing[sk].update(seed_results)
      existing[sk]["__seed_strategy__"] = "md5_v1"
      all_results = existing
  out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
  ```

---

### Attack-2
- **维度**：逻辑断链
- **严重度**：**严重**
- **攻击**：修复报告 `docs/p0r6_fix_p0_1.md` §3.3 声称：
  > "修复后：eval_l2_shift.py 续传写入结果时在 `existing[sk]` 中写入 `"__seed_strategy__": "md5_v1"` → run_e1a 检查通过 → 不重跑"
  > "**Attack-1 关闭**。✅"

  该验证存在逻辑断链：推理链条为 "添加标记写入 → 标记被写入 → run_e1a检查通过 → Attack-1关闭"，但中间步骤"标记被写入"**仅在续传路径成立**。验证未覆盖首次运行路径（`out_path.exists() == False`），该路径下标记不被写入，Attack-1 未关闭。

  修复报告§2.1的代码对比也只展示了"修改后（L192-197）"的续传分支代码，未展示首次运行分支（L185-186 + L198）的代码流，验证不完整。

  修复报告§3.2"改动最小性确认"声称"未改变已有功能逻辑（仅补充标记/放宽检查）"，但实际上标记写入被放在条件分支内，**改变了首次运行的保存内容**（虽然是无意的——本意是写入标记，实际首次运行未写入）。

- **代码证据**：`docs/p0r6_fix_p0_1.md` L116-119 声称 Attack-1 关闭，但未验证 L187 `if out_path.exists()` 为 False 的路径。
- **修复建议**：修复代码（见 Attack-1）后，重新验证首次运行 + 续传 + 多seed三种路径均写入标记。

---

### Attack-3
- **维度**：隐含假设
- **严重度**：**中等**
- **攻击**：`eval_l2_shift.py` L196 硬编码字符串 `"md5_v1"`，而 `run_e1a_l2_shift_full.py` L140 定义常量 `SEED_STRATEGY_VERSION = "md5_v1"` 并在 L433 使用常量引用。R6修复引入了**第二处硬编码**（此前只有 run_e1a 用常量，eval_l2_shift 不写标记），使DRY违反从"单点定义"退化为"常量+硬编码双源"。

  **隐含假设**：修复假设 `"md5_v1"` 永远等于 `SEED_STRATEGY_VERSION`。该假设在当前成立，但未来若修改种子派生算法（如改用 sha256 或增加派生参数），`SEED_STRATEGY_VERSION` 升级为 `"md5_v2"`，`eval_l2_shift.py` 的硬编码 `"md5_v1"` 不会同步，导致：
  1. eval_l2_shift 写入旧标记 `"md5_v1"`
  2. run_e1a 的 `is_checkpoint_complete` L268 检查 `seed_data.get("__seed_strategy__") != "md5_v2"` → True → return False → 重跑所有 eval_l2_shift 产出的结果
  3. 用户困惑：明明刚跑完 eval_l2_shift，为何 run_e1a 仍重跑？

  R5终审 `docs/p0r5_final_verdict.md` §2.1 已将此列为 backlog 改进项（Attack-2，降级中等），但R6修复不仅未解决，反而**新增了硬编码点**，使问题恶化。

- **代码证据**：
  ```python
  # run_e1a_l2_shift_full.py L140
  SEED_STRATEGY_VERSION = "md5_v1"  # 常量定义

  # run_e1a_l2_shift_full.py L433
  existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION  # 常量引用

  # eval_l2_shift.py L196（R6新增）
  existing[sk]["__seed_strategy__"] = "md5_v1"  # 硬编码字符串
  ```
- **修复建议**：在 `eval_l2_shift.py` 顶部导入或定义 `SEED_STRATEGY_VERSION = "md5_v1"`，L196 改为 `existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION`。更好方案：提取到 `src/data/l2_shifts.py` 共享模块，两脚本统一导入。

---

### Attack-4
- **维度**：边界失效
- **严重度**：**中等**
- **攻击**：`is_checkpoint_complete` L280-281 的 `cell["safety"] = 0` 修改的是局部变量 `cell`，它指向 `seed_data[sn]`，即 `data[sk][sn]`。`data` 在 L260 由 `json.loads(out_path.read_text(...))` 加载，是**函数内局部变量**。函数返回 `True` 后，`data` 被垃圾回收，`cell["safety"] = 0` 的修改**永远不持久化到磁盘**。

  因此 `cell["safety"] = 0` 是**死代码**——它不产生任何可观察的效果：
  1. `data` 是局部的，不返回、不保存
  2. 调用方（L311-314 / L588-590）在 `is_checkpoint_complete` 返回 True 后，通过 `load_existing_results(run_dir)` **重新从磁盘加载**，得到的结果**仍无 safety 字段**
  3. 下游 `aggregate_to_390` L462 用 `cell.get("safety", 0)` 容错读取，实际默认值来自 `.get()` 而非 `is_checkpoint_complete` 的 `cell["safety"] = 0`

  修复报告§2.2声称：
  > "`aggregate_to_390`（L460）已用 `cell.get("safety", 0)` 容错读取，修复后 `is_checkpoint_complete` 的默认行为与聚合逻辑一致。"

  这是**误导性声明**——`is_checkpoint_complete` 的 `cell["safety"] = 0` 对聚合逻辑**无任何影响**（修改丢失），一致性完全来自 `aggregate_to_390` 自身的 `.get("safety", 0)`。`cell["safety"] = 0` 这行代码可以删除而不改变任何行为。

  **该行的唯一实际效果**是阻止 `return False`（通过不返回），即改变了函数返回值。但 `cell["safety"] = 0` 这个赋值本身是死代码，真正的修复效果来自"不 return False"这一控制流变化。

- **代码证据**：
  ```python
  # run_e1a_l2_shift_full.py L256-282
  def is_checkpoint_complete(run_dir, seed, shift_names) -> bool:
      ...
      data = json.loads(out_path.read_text(encoding="utf-8"))  # L260: 局部变量
      ...
      for sn in shift_names:
          ...
          cell = seed_data[sn]          # L273: 指向 data 内部
          ...
          if "safety" not in cell:
              cell["safety"] = 0        # L281: 修改局部 data，函数返回后丢失
      return True                       # L282: data 未保存，修改丢失
  ```
  调用方 L311-314：
  ```python
  if not force and is_checkpoint_complete(run_dir, seed, shift_names):
      existing = load_existing_results(run_dir)  # 重新从磁盘加载，无 safety
      return existing[f"seed{seed}"]             # 返回无 safety 的结果
  ```
- **修复建议**：将 `cell["safety"] = 0` 改为 `pass`（明确表示"不视为不完整"），或直接删除整个 `if "safety" not in cell:` 块。若要真正持久化默认值，需在 `is_checkpoint_complete` 内保存 `data` 回磁盘（但不推荐——谓词函数不应有写副作用）。

---

### Attack-5
- **维度**：自相矛盾
- **严重度**：**轻微**
- **攻击**：`is_checkpoint_complete` 的 docstring（L248-255）声明：
  > "判据：...2. seed{N} 键下包含全部 13 档名，且每档含 ts 方法的 cal_ece（**安全率依赖项**）。"

  L277 注释也写：
  > "必须含 safety 字段（本脚本新增）"

  但 R6 修复将 safety 从**必需**改为**可选**（缺失时默认 0 而非 return False）。docstring 和注释仍声明 safety 为必需字段，与代码行为**自相矛盾**。后续维护者阅读 docstring 会误以为 safety 是完整性检查的必要条件，实际已放宽。

- **代码证据**：
  ```python
  # L277 注释（未更新）
  # 必须含 safety 字段（本脚本新增）
  # L280-281 代码（已放宽）
  if "safety" not in cell:
      cell["safety"] = 0  # 不 return False，safety 变为可选
  ```
- **修复建议**：更新 L277 注释为 `# safety 字段可选（R6修复）：缺失时默认0，不视为不完整`。更新 docstring L254 删除"安全率依赖项"或将 safety 标注为可选。

---

### Attack-6
- **维度**：量级错误
- **严重度**：**中等**
- **攻击**：`eval_l2_shift.py` **不计算 Brier reliability**（它只计算 `smooth_ece`，见 L144/L175），因此其产出的结果**永远不含 `safety` 字段**。当 run_e1a 复用 eval_l2_shift 的结果时，`aggregate_to_390` L462 `safety = cell.get("safety", 0)` 对所有 eval_l2_shift 产出的 cell 返回 0。

  在 390 矩阵聚合中，若部分 cell 来自 eval_l2_shift（safety=0 默认）部分来自 run_e1a（safety 实际计算），`safety_rate`（L501 `float(np.mean(v["safeties"]))`）会被**向下偏置**：

  $$\text{safety\_rate}_{\text{mixed}} = \frac{0 \cdot N_{\text{eval}} + \text{safety\_rate}_{\text{e1a}} \cdot N_{\text{e1a}}}{N_{\text{eval}} + N_{\text{e1a}}} < \text{safety\_rate}_{\text{e1a}}$$

  偏置幅度取决于混合比例。若 eval_l2_shift 产出占 50%，实际 safety_rate=0.7，混合后降为 0.35，**偏置达 50%**。

  修复报告§2.2声称"safety = 0 语义正确"并认可此默认值，但**未分析聚合偏置**，未在论文/CSV中声明哪些 cell 的 safety 是实际计算、哪些是默认填充。审稿人无法区分"TS 确实未改善"和"从未计算 Brier reliability"。

- **代码证据**：
  ```python
  # eval_l2_shift.py L144: 只算 ECE，不算 Brier reliability
  raw_ece = smooth_ece(_maxprob(ood_probs), _bin(ood_probs, ood_labels))
  # 无 raw_brier_rel / ts_brier_rel / safety 计算

  # aggregate_to_390 L462: 默认 0
  safety = cell.get("safety", 0)

  # L501: 聚合均值含偏置
  safety_rate = float(np.mean(v["safeties"]))
  ```
- **修复建议**：(1) 在 390 CSV 增加 `safety_source` 列（"computed" / "default"），明确标注每个 cell 的 safety 来源；(2) 在论文中声明混合偏置及其保守方向；(3) 或要求 eval_l2_shift 也计算 Brier reliability 和 safety（根本解决）。

---

### Attack-7
- **维度**：语义偏移
- **严重度**：**中等**
- **攻击**：`safety` 字段在 `run_e1a_l2_shift_full.py` L412 有明确定义：
  ```python
  safety = 1 if ts_brier_rel < raw_brier_rel else 0
  ```
  语义为"TS 是否改善了 Brier reliability"（二值实验结果）。

  R6 修复将"safety 字段缺失"默认为 `safety = 0`，即"TS 未改善 Brier reliability"。但 `eval_l2_shift.py` 不计算 Brier reliability，缺失的语义是"**从未计算**"，而非"**计算了且 TS 未改善**"。

  两种语义被静默混淆：
  - `safety = 0`（实际计算）：`ts_brier_rel >= raw_brier_rel`，TS 确实未改善
  - `safety = 0`（默认填充）：Brier reliability 从未计算，**不知道**TS 是否改善

  修复报告§2.2承认"保守估计"但将其包装为合理设计，未识别这是**语义偏移**：将"未知"（epistemic uncertainty）静默替换为"否定"（alethic fact）。在安全率矩阵这种二值聚合量中，"未知"应排除在聚合外或单独标注，而非默认为"否定"。

  这与 `evaluate_one_checkpoint` L370-372 的 `safety = 0` 默认值**语义不同**：
  - L372：`safety = 0` 是**计算前的临时默认值**，L412 会被实际计算覆盖
  - L281：`cell["safety"] = 0` 是**计算后的永久默认值**，不会被覆盖

  修复报告§2.2声称两者"一致"，实际语义不同。

- **代码证据**：
  ```python
  # run_e1a L412: safety 的真实语义
  safety = 1 if ts_brier_rel < raw_brier_rel else 0  # 实验结果

  # run_e1a L281 (R6修复): safety 的偏移语义
  cell["safety"] = 0  # "从未计算" 被等同于 "TS未改善"

  # eval_l2_shift.py: 不计算 Brier reliability，无 safety 字段
  # L144: raw_ece = smooth_ece(...)  # 只有 ECE，无 Brier
  ```
- **修复建议**：用 `safety = None` 或 `safety = "not_computed"` 表示"从未计算"，与 `safety = 0`（计算了且未改善）区分。`aggregate_to_390` 聚合时排除 `None` 或单独统计。

---

### Attack-8
- **维度**：边界失效
- **严重度**：**轻微**
- **攻击**：`is_checkpoint_complete` 函数名以 `is_` 开头，按 Python 命名约定暗示是**谓词函数**（pure function，无副作用，仅返回 bool）。但 R6 修复在 L281 引入了 `cell["safety"] = 0`，这是**修改输入数据的副作用**——虽然 `data` 是函数内局部加载的（L260），但 `cell` 是 dict 引用，赋值修改了 dict 内容。

  当前无害（`data` 是局部的，修改丢失），但违反了纯函数约定。若未来重构：
  1. 将 `data` 改为参数传入（避免重复加载）→ `cell["safety"] = 0` 会修改调用方的 dict
  2. 将 `data` 缓存到类属性 → 修改会跨调用泄漏
  3. 在 `is_checkpoint_complete` 后复用 `data` → 修改后的 `safety=0` 会被误读为实际值

- **代码证据**：
  ```python
  def is_checkpoint_complete(run_dir, seed, shift_names) -> bool:
      # 函数名 is_ 暗示谓词（无副作用）
      ...
      cell = seed_data[sn]
      if "safety" not in cell:
          cell["safety"] = 0  # 副作用：修改 dict 内容
      return True
  ```
- **修复建议**：将 `cell["safety"] = 0` 改为 `pass`（见 Attack-4），消除副作用。或若需保留默认值语义，用局部变量：`safety = cell.get("safety", 0)` 而非修改 `cell`。

---

## 攻击维度覆盖确认

| 维度 | 是否尝试 | 发现攻击点 | 编号 |
|------|----------|-----------|------|
| 1. 反例构造 | ✅ | 是（首次运行标记不写入） | Attack-1 |
| 2. 逻辑断链 | ✅ | 是（验证未覆盖首次运行路径） | Attack-2 |
| 3. 隐含假设 | ✅ | 是（硬编码vs常量DRY违反） | Attack-3 |
| 4. 边界失效 | ✅ | 是（死代码+谓词函数副作用） | Attack-4, Attack-8 |
| 5. 自相矛盾 | ✅ | 是（docstring与代码矛盾） | Attack-5 |
| 6. 量级错误 | ✅ | 是（聚合safety_rate向下偏置） | Attack-6 |
| 7. 语义偏移 | ✅ | 是（"从未计算"等同"未改善"） | Attack-7 |

**全部7个维度均已尝试，发现8个攻击点。**

---

## 与R5终审的对照

| R5终审判定 | R6修复 | R6反方验证结果 |
|-----------|--------|---------------|
| Attack-1（严重）：eval_l2_shift不写标记 | L196添加标记写入 | **未修复**——标记写入在条件块内，首次运行不写入（Attack-1致命） |
| Attack-7（中等）：safety不对称导致反复重跑 | L281放宽safety检查 | **部分修复**——return False改为不返回（修复重跑），但cell["safety"]=0是死代码（Attack-4），语义偏移（Attack-7），聚合偏置（Attack-6） |

**关键发现**：R6修复对 Attack-1 **未实际修复**——修复代码放置位置错误（在 `if out_path.exists()` 条件块内），首次运行路径标记不写入。这是R6修复的**致命缺陷**，需R7修复。

---

## R7必修项建议

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|--------|--------|------|------|---------|--------|
| **P0-致命** | Attack-1 | scripts/eval_l2_shift.py | L185后 | 在 `all_results[f"seed{seed}"] = seed_results` 后**无条件**写入 `all_results[f"seed{seed}"]["__seed_strategy__"] = "md5_v1"`，确保首次运行也写入标记 | 1行 |
| **P0-中等** | Attack-3 | scripts/eval_l2_shift.py | L196 | 硬编码 `"md5_v1"` 改为常量引用 `SEED_STRATEGY_VERSION`（在文件顶部定义或导入） | 2行 |
| **P0-中等** | Attack-4 | scripts/run_e1a_l2_shift_full.py | L280-281 | `cell["safety"] = 0` 改为 `pass`（消除死代码和副作用） | 1行 |
| **P0-中等** | Attack-6+7 | scripts/run_e1a_l2_shift_full.py | L462 / aggregate_to_390 | safety 默认值改为 `None`，聚合时排除或单独标注，CSV增加 `safety_source` 列 | 5-8行 |
| **P0-轻微** | Attack-5 | scripts/run_e1a_l2_shift_full.py | L277 / L254 | 更新docstring和注释，safety标注为可选 | 2行 |

**R7必修合计**：5项（1致命 + 3中等 + 1轻微），~11-14行改动

---

## 结论

R6-Phase1 P0-1正方修复存在 **1个致命缺陷**（Attack-1：标记写入位置错误，首次运行不写入标记）导致R5 Attack-1**未实际修复**。此外发现4个中等攻击点（DRY违反/死代码/聚合偏置/语义偏移）和2个轻微攻击点（docstring矛盾/纯函数副作用）。

**致命发现**：R6修复报告 `docs/p0r6_fix_p0_1.md` §3.3 声称"Attack-1 关闭✅"是**错误声明**——验证未覆盖首次运行路径，标记写入在 `if out_path.exists()` 条件块内（L187），首次运行时条件为 False，标记永远不写入。R6修复对最常见使用场景（首次运行）完全失效，需R7修复。

**判定**：❌ R6 P0-1修复**未通过**，需R7修复Attack-1（致命）后方可关闭。
