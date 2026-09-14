# R6-Phase3 P0-1反反方审查报告

> **反反方代理**：R6-Phase3 P0-1反反方审查代理（GLM-5.2）
> **审查日期**：2026-09-10
> **审查对象**：`docs/p0r6_attack_p0_1.md` 中8个攻击点的成立性
> **审查方法**：逐行代码阅读 + 控制流追踪 + 数据流分析 + 反例验证
> **审查结论**：**8个攻击点全部成立**，R6 P0-1修复**未通过**，需R7修复

---

## 一、逐条裁决

### Attack-1（致命）：标记写入在条件块内，首次运行不写入

**裁决：✅ 成立（致命）**

**验证过程**：

实际阅读 `scripts/eval_l2_shift.py` L185-198（revision: bf771de9）：

```python
185:         all_results[f"seed{seed}"] = seed_results       # all_results 无标记
186:         out_path = run_dir / "l2_shift_results.json"
187:         if out_path.exists():                            # 首次运行: False
188:             existing = json.loads(out_path.read_text(encoding="utf-8"))
189:             sk = f"seed{seed}"
190:             if sk not in existing:
191:                 existing[sk] = {}
192:             existing[sk].update(seed_results)
193:             # P0-1 R6修复（Attack-1）：写入 per-seed seed_strategy 版本标记，
194:             # 与 run_e1a_l2_shift_full.py 一致，供 is_checkpoint_complete 校验，
195:             # 避免断点续传时新旧种子策略结果静默混用。
196:             existing[sk]["__seed_strategy__"] = "md5_v1"  # 在 if 块内！
197:             all_results = existing
198:         out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
```

**控制流追踪（首次运行）**：
1. L185: `all_results = {"seed42": {shift结果...}}`——**无 `__seed_strategy__` 标记**
2. L186: `out_path` 指向 `l2_shift_results.json`
3. L187: `out_path.exists()` → **False**（首次运行，文件不存在）
4. L188-197: 整块**跳过**，L196 标记写入**不执行**
5. L198: 保存 `all_results`（L185赋值的版本，**无标记**）

**对比 run_e1a_l2_shift_full.py L427-435 的正确模式**：
```python
427:     existing = load_existing_results(run_dir)          # 无条件加载
431:     existing[sk].update(seed_results)
433:     existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION  # 无条件写入
435:     out_path.write_text(json.dumps(existing, ...))     # 保存
```
`run_e1a` 的标记写入在条件块**外部**（无条件执行），`eval_l2_shift` 的标记写入在条件块**内部**。两脚本模式确实不一致。

**下游影响验证**：`is_checkpoint_complete` L268:
```python
268:     if seed_data.get("__seed_strategy__") != SEED_STRATEGY_VERSION:
269:         return False
```
首次运行产出的结果无标记 → `seed_data.get("__seed_strategy__")` 返回 `None` → `None != "md5_v1"` → `return False` → run_e1a 重跑。

**结论**：R6修复对首次运行路径完全失效，这正是R5 Attack-1要修复的bug。反方攻击成立。

---

### Attack-2（严重）：修复报告验证未覆盖首次运行路径

**裁决：✅ 成立（严重）**

**验证过程**：

Attack-1已确认成立——首次运行路径标记不写入。修复报告 `docs/p0r6_fix_p0_1.md` §3.3 声称"Attack-1 关闭✅"，但该结论仅基于续传路径验证（L192-197分支），未验证首次运行路径（L185-186 + L198分支）。

修复报告§2.1的代码对比只展示了"修改后（L192-197）"的续传分支代码，未展示首次运行分支的代码流。这是**验证覆盖不全**的逻辑断链——推理链条"添加标记写入 → 标记被写入 → run_e1a检查通过 → Attack-1关闭"中，"标记被写入"这一步仅在续传路径成立。

**结论**：修复报告的"Attack-1 关闭✅"声明是错误声明，验证不完整。反方攻击成立。

---

### Attack-3（中等）：硬编码"md5_v1" vs SEED_STRATEGY_VERSION常量

**裁决：✅ 成立（中等）**

**验证过程**：

实际代码对比：
```python
# run_e1a_l2_shift_full.py L140
SEED_STRATEGY_VERSION = "md5_v1"  # 常量定义

# run_e1a_l2_shift_full.py L433
existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION  # 常量引用

# eval_l2_shift.py L196（R6新增）
existing[sk]["__seed_strategy__"] = "md5_v1"  # 硬编码字符串
```

确认：`eval_l2_shift.py` L196 使用硬编码字符串 `"md5_v1"`，而 `run_e1a_l2_shift_full.py` 使用常量 `SEED_STRATEGY_VERSION`。这是DRY违反——两处定义同一值，未来版本升级时不同步。

**结论**：反方攻击成立。虽当前不影响正确性，但维护风险真实存在。

---

### Attack-4（中等）：cell["safety"]=0是死代码

**裁决：✅ 成立（中等）**

**验证过程**：

实际阅读 `run_e1a_l2_shift_full.py` L256-282（revision: 3acec431）：

```python
256:     out_path = run_dir / "l2_shift_results.json"
260:         data = json.loads(out_path.read_text(encoding="utf-8"))  # 局部变量
266:     seed_data = data[sk]                                        # 指向 data 内部
273:         cell = seed_data[sn]                                    # 指向 data[sk][sn]
280:         if "safety" not in cell:
281:             cell["safety"] = 0                                  # 修改局部 data
282:     return True                                                 # data 未保存
```

**数据流追踪**：
1. L260: `data` 是 `json.loads` 返回的局部dict，函数内有效
2. L273: `cell` 是 `data[sk][sn]` 的引用（Python dict是引用语义）
3. L281: `cell["safety"] = 0` 修改 `data` 内部的dict
4. L282: `return True` —— `data` 未写回磁盘，函数返回后 `data` 被垃圾回收

**调用方验证**（L311-314）：
```python
311:     if not force and is_checkpoint_complete(run_dir, seed, shift_names):
312:         existing = load_existing_results(run_dir)  # 重新从磁盘加载
314:         return existing[f"seed{seed}"]             # 返回磁盘数据，无 safety
```
调用方在 `is_checkpoint_complete` 返回后，通过 `load_existing_results` **重新从磁盘加载**，得到的结果**仍无 safety 字段**。L281的修改完全丢失。

**下游聚合验证**（L462）：
```python
462:             safety = cell.get("safety", 0)  # 容错读取，默认0来自.get()
```
聚合逻辑的默认值来自 `.get("safety", 0)`，而非 `is_checkpoint_complete` 的 `cell["safety"] = 0`。L281对聚合逻辑**无任何影响**。

**结论**：`cell["safety"] = 0` 是死代码——不产生任何可观察的数据效果。真正的修复效果来自"不 return False"这一控制流变化。反方攻击成立。

---

### Attack-5（轻微）：docstring与代码矛盾

**裁决：✅ 成立（轻微）**

**验证过程**：

实际阅读 `run_e1a_l2_shift_full.py` L248-281：

```python
254:     2. seed{N} 键下包含全部 13 档名，且每档含 ts 方法的 cal_ece（安全率依赖项）。
...
277:         # 必须含 safety 字段（本脚本新增）
278:         # P0-1 R6修复（Attack-7）：旧结果（如 eval_l2_shift.py 产出）可能缺 safety，
279:         # 缺失时默认 0 而非视为不完整，避免两脚本交替运行时反复重跑。
280:         if "safety" not in cell:
281:             cell["safety"] = 0
```

- L254 docstring：声明 safety 为"安全率依赖项"（暗示必需）
- L277 注释：`# 必须含 safety 字段`（明确声明必需）
- L280-281 代码：`if "safety" not in cell: cell["safety"] = 0`（实际为可选，缺失时默认0）

docstring和注释声明 safety 必需，但代码已放宽为可选。**自相矛盾确认**。

**结论**：反方攻击成立。后续维护者阅读docstring会误以为safety是完整性检查的必要条件。

---

### Attack-6（中等）：eval_l2_shift不计算Brier，safety默认0向下偏置聚合

**裁决：✅ 成立（中等）**

**验证过程**：

**eval_l2_shift.py 不计算 Brier reliability**：
```python
# L144: 只算 ECE
144:             raw_ece = smooth_ece(_maxprob(ood_probs), _bin(ood_probs, ood_labels))
# 全文搜索：无 raw_brier_rel / ts_brier_rel / safety 计算
# method_results（L152-180）不含 safety 字段
```

**run_e1a_l2_shift_full.py 聚合默认0**：
```python
462:             safety = cell.get("safety", 0)      # eval_l2_shift结果默认0
501:         safety_rate = float(np.mean(v["safeties"]))  # 聚合均值含偏置
```

**偏置分析**：若390矩阵中部分cell来自eval_l2_shift（safety=0默认）部分来自run_e1a（safety实际计算），`safety_rate` 被向下偏置：

$$\text{safety\_rate}_{\text{mixed}} = \frac{0 \cdot N_{\text{eval}} + \text{safety\_rate}_{\text{e1a}} \cdot N_{\text{e1a}}}{N_{\text{eval}} + N_{\text{e1a}}} < \text{safety\_rate}_{\text{e1a}}$$

**注意**：当前由于Attack-1成立（首次运行不写标记），run_e1a会重跑eval_l2_shift产出的结果并计算safety，偏置暂不显现。但**一旦Attack-1修复**（标记写入移到条件块外），eval_l2_shift产出的结果会被run_e1a视为完整而复用，偏置就会显现。因此Attack-6是Attack-1修复后的**次生风险**。

**结论**：反方攻击成立。eval_l2_shift不计算Brier reliability，其结果safety默认0会向下偏置聚合。

---

### Attack-7（中等）："从未计算"被静默等同"TS未改善"

**裁决：✅ 成立（中等）**

**验证过程**：

**safety 的真实语义**（run_e1a L412）：
```python
412:                     safety = 1 if ts_brier_rel < raw_brier_rel else 0
```
语义：TS是否改善了Brier reliability（二值实验结果）。
- `safety = 0`：计算了，TS确实未改善（`ts_brier_rel >= raw_brier_rel`）
- `safety = 1`：计算了，TS改善了

**R6修复的偏移语义**（L281）：
```python
281:             cell["safety"] = 0  # "从未计算" 被默认为 0
```
当eval_l2_shift产出（不计算Brier）时，safety字段缺失，R6默认为0。但缺失的语义是"**从未计算**"（epistemic uncertainty），而非"**计算了且TS未改善**"（alethic fact）。

**两种语义混淆**：
- `safety = 0`（实际计算）：TS确实未改善
- `safety = 0`（默认填充）：Brier reliability从未计算，**不知道**TS是否改善

**与L372对比**：
```python
372:         safety = 0  # 计算前临时默认，L412会被实际计算覆盖
```
L372是**临时默认值**（会被覆盖），L281是**永久默认值**（不会被覆盖）。修复报告§2.2声称两者"一致"，实际语义不同。

**结论**：反方攻击成立。将"未知"静默替换为"否定"是语义偏移。

---

### Attack-8（轻微）：谓词函数中修改dict，违反纯函数约定

**裁决：✅ 成立（轻微）**

**验证过程**：

`is_checkpoint_complete` 函数名以 `is_` 开头，按Python命名约定（PEP 8）暗示是**谓词函数**（pure function，无副作用，仅返回bool）。

但L281引入了 `cell["safety"] = 0`，这是**修改dict内容的副作用**：
```python
279:         def is_checkpoint_complete(run_dir, seed, shift_names) -> bool:
...
281:             cell["safety"] = 0  # 副作用：修改 dict 内容
282:     return True
```

虽然 `data` 是函数内局部加载的（L260），当前修改丢失（见Attack-4），但违反了纯函数约定。若未来重构：
1. 将 `data` 改为参数传入 → `cell["safety"] = 0` 会修改调用方的dict
2. 将 `data` 缓存到类属性 → 修改会跨调用泄漏
3. 在 `is_checkpoint_complete` 后复用 `data` → 修改后的 `safety=0` 会被误读为实际值

**结论**：反方攻击成立。当前无害但重构脆弱。

---

## 二、裁决汇总

| 编号 | 严重度 | 裁决 | 验证依据 |
|------|--------|------|---------|
| Attack-1 | **致命** | ✅ 成立 | 实读eval_l2_shift.py L185-198，L196在L187 if块内，首次运行L187为False，标记不写入 |
| Attack-2 | **严重** | ✅ 成立 | Attack-1成立的逻辑推论，修复报告仅验证续传路径 |
| Attack-3 | **中等** | ✅ 成立 | 实读L196硬编码"md5_v1" vs L140常量SEED_STRATEGY_VERSION，DRY违反 |
| Attack-4 | **中等** | ✅ 成立 | 实读L260-282，data局部变量，L281修改丢失，调用方L312重新加载 |
| Attack-5 | **轻微** | ✅ 成立 | 实读L254/L277声明必需 vs L280-281代码可选，自相矛盾 |
| Attack-6 | **中等** | ✅ 成立 | 实读eval_l2_shift.py L144只算ECE，run_e1a L462默认0，L501聚合偏置 |
| Attack-7 | **中等** | ✅ 成立 | 实读L412真实语义 vs L281偏移语义，"从未计算"等同"未改善" |
| Attack-8 | **轻微** | ✅ 成立 | is_前缀暗示谓词，L281修改dict是副作用，违反纯函数约定 |

**全部8个攻击点均成立。反方攻击报告质量高，所有攻击点经代码实证确认。**

---

## 三、成立攻击点的修补方案

### 修补Attack-1（致命，必修）

**文件**：`scripts/eval_l2_shift.py`
**行号**：L185-198
**改动**：将标记写入移到 `if out_path.exists():` 块**外部**，确保首次运行也写入标记。

**改动前**：
```python
        all_results[f"seed{seed}"] = seed_results
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

**改动后**：
```python
        all_results[f"seed{seed}"] = seed_results
        all_results[f"seed{seed}"]["__seed_strategy__"] = SEED_STRATEGY_VERSION  # 无条件写入标记
        out_path = run_dir / "l2_shift_results.json"
        if out_path.exists():
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            sk = f"seed{seed}"
            if sk not in existing:
                existing[sk] = {}
            existing[sk].update(seed_results)
            existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION  # 续传也写入
            all_results = existing
        out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
```

**验证点**：首次运行（L187为False）时，L185后无条件写入标记，L198保存的 `all_results` 含标记。

---

### 修补Attack-3（中等，必修）

**文件**：`scripts/eval_l2_shift.py`
**行号**：文件顶部 + L196
**改动**：定义常量 `SEED_STRATEGY_VERSION`，L196改为常量引用。

**改动内容**：
1. 在文件顶部（L24后）添加：
```python
# P0-1 R7修复（Attack-3）：与 run_e1a_l2_shift_full.py 共享的种子策略版本
SEED_STRATEGY_VERSION = "md5_v1"
```
2. L196 改为：
```python
            existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION
```

**更好方案**：提取到 `src/data/l2_shifts.py` 共享模块，两脚本统一导入（避免两处定义）。但最小修复用本脚本内常量即可。

---

### 修补Attack-4 + Attack-8（中等+轻微，必修）

**文件**：`scripts/run_e1a_l2_shift_full.py`
**行号**：L277-281
**改动**：将 `cell["safety"] = 0` 改为 `pass`，消除死代码和副作用。

**改动前**：
```python
        # 必须含 safety 字段（本脚本新增）
        # P0-1 R6修复（Attack-7）：旧结果（如 eval_l2_shift.py 产出）可能缺 safety，
        # 缺失时默认 0 而非视为不完整，避免两脚本交替运行时反复重跑。
        if "safety" not in cell:
            cell["safety"] = 0
```

**改动后**：
```python
        # safety 字段可选（R7修复）：缺失时不视为不完整，聚合时由 .get("safety", 0) 容错
        # 注意：此处不修改 cell（避免谓词函数副作用），默认值在 aggregate_to_390 L462 处理
        if "safety" not in cell:
            pass  # 缺失safety不视为不完整，聚合时默认0
```

**效果**：消除死代码（Attack-4）+ 消除副作用（Attack-8）+ 更新注释（部分Attack-5）。

---

### 修补Attack-5（轻微，必修）

**文件**：`scripts/run_e1a_l2_shift_full.py`
**行号**：L254（docstring）
**改动**：更新docstring，safety标注为可选。

**改动前**：
```python
    2. seed{N} 键下包含全部 13 档名，且每档含 ts 方法的 cal_ece（安全率依赖项）。
```

**改动后**：
```python
    2. seed{N} 键下包含全部 13 档名，且每档含 ts 方法的 cal_ece。
       safety 字段可选（R7修复）：缺失时聚合默认0，不视为不完整。
```

---

### 修补Attack-6 + Attack-7（中等+中等，必修）

**文件**：`scripts/run_e1a_l2_shift_full.py`
**行号**：L462 + aggregate_to_390 + CSV输出
**改动**：用 `safety = None` 表示"从未计算"，聚合时排除或单独标注，CSV增加 `safety_source` 列。

**方案A（最小修复，推荐）**：在780详细CSV增加 `safety_source` 列，明确标注每个cell的safety来源。

**改动内容**：
1. L462 改为：
```python
            safety = cell.get("safety", None)  # None 表示从未计算
            safety_source = "computed" if "safety" in cell else "default"
```
2. L470-484（780行）增加 `safety_source` 字段：
```python
            rows_780.append({
                ...
                "safety": safety if safety is not None else 0,  # CSV中0表示未计算
                "safety_source": safety_source,  # 新增列
            })
```
3. L491 聚合时区分：
```python
            agg[key]["safeties"].append(safety if safety is not None else 0)
            agg[key]["safety_sources"].append(safety_source)  # 新增追踪
```
4. L621-625（780 CSV fieldnames）增加 `"safety_source"`：
```python
    write_csv(rows_780, OUT_CSV_780, [
        "direction", "source", "target", "arch", "seed", "shift", "shift_type",
        "raw_ece", "raw_brier_rel", "ts_brier_rel", "ts_delta_ece",
        "brier_rel_improvement", "safety", "safety_source",
    ])
```

**方案B（根本修复）**：要求eval_l2_shift也计算Brier reliability和safety。改动量大，不推荐R7做。

**方案C（折中）**：在论文/CSV header声明混合偏置及其保守方向。最小但不够透明。

**推荐**：方案A，~8行改动，透明可审计。

---

## 四、不成立攻击点的反驳

**无。** 全部8个攻击点均经代码实证确认成立，无需反驳。

---

## 五、R6 P0-1总体判定

### 判定：❌ **不通过**

**理由**：

1. **致命缺陷未修复**：Attack-1确认成立——R6修复将标记写入放在 `if out_path.exists():` 条件块内（L187条件，L196写入），首次运行时文件不存在，条件为False，标记永远不写入。R6修复对最常见使用场景（首次运行）完全失效，这正是R5 Attack-1要修复的bug。

2. **修复报告错误声明**：`docs/p0r6_fix_p0_1.md` §3.3 声称"Attack-1 关闭✅"是错误声明——验证仅覆盖续传路径，未覆盖首次运行路径（Attack-2）。

3. **次生风险**：Attack-6/7在Attack-1修复后会显现——eval_l2_shift产出的结果（无safety）会被run_e1a复用，safety默认0向下偏置聚合，且"从未计算"被静默等同"TS未改善"。

4. **代码质量问题**：Attack-3（DRY违反）、Attack-4（死代码）、Attack-5（docstring矛盾）、Attack-8（纯函数副作用）均确认成立，虽非致命但需R7清理。

**关键发现**：R6修复代码放置位置错误（标记写入在条件块内），是**单行缩进错误**导致的致命缺陷。修复本意是"无条件写入标记"，实际实现是"条件写入标记"。这是典型的**意图与实现偏差**。

---

## 六、R7必修项清单

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 | 验证方法 |
|--------|--------|------|------|---------|--------|---------|
| **P0-致命** | Attack-1 | scripts/eval_l2_shift.py | L185后 | 在 `all_results[f"seed{seed}"] = seed_results` 后**无条件**写入 `all_results[f"seed{seed}"]["__seed_strategy__"] = SEED_STRATEGY_VERSION`，确保首次运行也写入标记 | 1行 | 删除l2_shift_results.json后首次运行eval_l2_shift，检查产出文件含 `__seed_strategy__` 标记 |
| **P0-中等** | Attack-3 | scripts/eval_l2_shift.py | 顶部+L196 | 定义 `SEED_STRATEGY_VERSION = "md5_v1"` 常量，L196改为常量引用（或从共享模块导入） | 2行 | grep确认eval_l2_shift.py无硬编码"md5_v1"字符串 |
| **P0-中等** | Attack-4+8 | scripts/run_e1a_l2_shift_full.py | L280-281 | `cell["safety"] = 0` 改为 `pass`，消除死代码和副作用 | 1行 | 单元测试：is_checkpoint_complete不修改输入dict |
| **P0-中等** | Attack-6+7 | scripts/run_e1a_l2_shift_full.py | L462+L470+L621 | safety默认改None，780 CSV增加 `safety_source` 列（"computed"/"default"），聚合时区分 | 5-8行 | 检查780 CSV含safety_source列，eval_l2_shift产出的cell标注"default" |
| **P0-轻微** | Attack-5 | scripts/run_e1a_l2_shift_full.py | L254+L277 | 更新docstring和注释，safety标注为可选 | 2行 | 阅读docstring确认与代码一致 |

**R7必修合计**：5项（1致命 + 3中等 + 1轻微），~11-14行改动

---

## 七、R7验证清单

修复完成后需验证以下路径均正确写入标记：

1. **首次运行路径**：删除 `l2_shift_results.json` → 运行 `eval_l2_shift.py` → 检查产出文件含 `__seed_strategy__` 标记
2. **续传路径**：已有 `l2_shift_results.json` → 运行 `eval_l2_shift.py` → 检查标记保留
3. **多seed首次运行**：删除文件 → 运行 `--seeds 42 43` → 检查seed42和seed43均有标记
4. **run_e1a复用路径**：eval_l2_shift产出 → 运行 `run_e1a_l2_shift_full.py` → 检查不重跑（is_checkpoint_complete返回True）
5. **safety_source标注**：eval_l2_shift产出的cell在780 CSV中标注 `safety_source=default`，run_e1a产出的标注 `safety_source=computed`
6. **谓词函数无副作用**：调用 `is_checkpoint_complete` 后，输入dict内容不变

---

## 八、与R5终审的对照

| R5终审判定 | R6修复 | R6反方验证 | R6反反方验证 | R7必修 |
|-----------|--------|-----------|-------------|--------|
| Attack-1（严重）：eval_l2_shift不写标记 | L196添加标记写入 | **未修复**——标记在条件块内，首次运行不写入（Attack-1致命） | ✅确认成立 | P0-致命：标记写入移到条件块外 |
| Attack-7（中等）：safety不对称导致反复重跑 | L281放宽safety检查 | 部分修复——return False改为不返回（修复重跑），但cell["safety"]=0是死代码（Attack-4），语义偏移（Attack-7），聚合偏置（Attack-6） | ✅确认成立 | P0-中等：cell["safety"]=0改pass + safety_source列 |

**关键发现**：R6修复对 Attack-1 **未实际修复**——修复代码放置位置错误（在 `if out_path.exists()` 条件块内），首次运行路径标记不写入。这是R6修复的**致命缺陷**，需R7修复。

---

## 九、结论

R6-Phase2 P0-1反方攻击报告 `docs/p0r6_attack_p0_1.md` 中的 **8个攻击点全部成立**，经逐行代码实证确认：

1. **Attack-1（致命）**：eval_l2_shift.py L196标记写入在L187 `if out_path.exists():` 条件块内，首次运行时条件为False，标记永远不写入。R6修复对首次运行路径完全失效。
2. **Attack-2（严重）**：修复报告验证未覆盖首次运行路径，"Attack-1 关闭✅"是错误声明。
3. **Attack-3（中等）**：硬编码"md5_v1" vs 常量SEED_STRATEGY_VERSION，DRY违反。
4. **Attack-4（中等）**：cell["safety"]=0修改局部dict，函数返回后丢失，是死代码。
5. **Attack-5（轻微）**：docstring仍声明safety必需，与代码矛盾。
6. **Attack-6（中等）**：eval_l2_shift不计算Brier，safety默认0向下偏置聚合。
7. **Attack-7（中等）**："从未计算"被静默等同"TS未改善"，语义偏移。
8. **Attack-8（轻微）**：谓词函数中修改dict，违反纯函数约定。

**R6 P0-1总体判定：❌ 不通过**

**R7必修**：5项（1致命 + 3中等 + 1轻微），~11-14行改动。核心修复是将eval_l2_shift.py的标记写入移到条件块外部（1行改动），其余为代码质量清理。

**反方攻击报告质量评价**：高质量。所有攻击点均经代码实证确认，无过度攻击或误报。反例构造具体可执行，代码证据准确，修复建议可行。反方代理成功发现了R6修复的致命缺陷（标记写入位置错误），避免了R5 Attack-1被错误关闭。
