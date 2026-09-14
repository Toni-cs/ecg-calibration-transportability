# E5 实验脚本反方攻击报告

> **反方挑刺代理-E5 交付**。本报告对正方设计的 E5 实验脚本（`run_e5_inception_lite.py`）和 InceptionTime-Lite 模型（`inceptiontime_lite.py`）进行逐行审查，寻找架构合理性、训练公平性、代码正确性方面的致命/严重/轻微攻击。
> **攻击日期**：2026-09-09
> **攻击对象**：
> - `scripts/run_e5_inception_lite.py`（687 行，E5 实验主脚本）
> - `src/models/inceptiontime_lite.py`（214 行，InceptionTime-Lite 模型）
> - `src/models/baselines.py`（257 行，backbone 注册表）
> - `docs/Q2_UPGRADE_PROPOSAL_R5.md`（1313 行，R5 升级方案）
> **攻击代理**：反方挑刺代理-E5（GLM-5.2）
> **诚实原则**：对每条代码路径逐行验证，对每个声称定量复核，不放过任何死代码、隐含假设和边界失效。
> **攻击维度**：反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移（7 维度全覆盖）

---

## 0. 攻击审查概述

### 攻击数量统计

| 严重性 | 数量 | 编号 |
|--------|------|------|
| **致命（FATAL）** | 3 | F1, F2, F3 |
| **严重（SEVERE）** | 6 | S1, S2, S3, S4, S5, S6 |
| **中等（MODERATE）** | 5 | M1, M2, M3, M4, M5 |
| **轻微（MINOR）** | 4 | m1, m2, m3, m4 |
| **合计** | **18** | |

### 参数量复核结果

| 配置 | 实测参数量 | 目标区间 [200K, 500K] | 声称值 |
|------|-----------|----------------------|--------|
| InceptionTime-Lite (n_filters=48) | **315,846** | ✅ 在范围内 | ~310K（基本准确） |
| InceptionTime-Lite (n_filters=32, OOM Level 1) | **147,334** | ❌ **低于下界** | ~136K（基本准确，但未声明违规） |
| 原版 InceptionTime (baselines.py 默认 n_blocks=4, n_filters=32) | **192,646** | ❌ 低于下界 | ~192K（R5 声称） |

### 整体评估

E5 实验脚本存在 **3 个致命 bug**（OOM 备选链完全失效、迁移评估崩溃、参数审计虚假通过），**6 个严重问题**（OOM Level 1 违反参数约束、Level 3 变体是死代码、gradient checkpointing 损害 BN、架构家族自相矛盾等）。**当前代码无法正确执行完整 E5 实验**——2/6 迁移方向会崩溃，OOM 备选链是死代码永远不会被触发。

---

## 1. 致命攻击（FATAL）

### F1：4 级 OOM 备选链是完全死代码，永远不会被触发

**攻击维度**：逻辑断链 + 自相矛盾

**证据**：

`try_train_with_oom_fallback` 函数定义在第 154 行，实现了精心设计的 4 级 OOM 备选链（Level 1: 减通道 → Level 2: gradient checkpointing → Level 3: ResNet1D 变体 → Level 4: 诚实降级）。

```python
# 第 154 行：函数定义
def try_train_with_oom_fallback(
    train_fn, config, device, n_filters=48, use_checkpoint=False,
) -> Tuple[Any, dict]:
    """带 4 级 OOM 备选的训练尝试..."""
    levels = [
        (1, {"n_filters": 48, ...}, "原始配置..."),
        (1, {"n_filters": 32, ...}, "Level 1: n_filters 48→32..."),
        (2, {"n_filters": 32, "use_checkpoint": True}, "Level 2: + gradient checkpointing"),
        (3, {..., "arch": "resnet1d", "depth": 3, "width": 32}, "Level 3: ResNet1D 变体..."),
        ...
    ]
```

**但该函数从未被调用**。`grep` 搜索全文仅 1 处匹配（函数定义本身）。`main()` 函数（第 582-606 行）直接调用 `train_single`，OOM 处理是简单的 try/except：

```python
# 第 584-606 行：main() 的实际 OOM 处理
try:
    model, info = train_single(dataset, seed, args, device, ...)
except RuntimeError as e:
    if is_oom_error(e):
        print(f"[OOM] {dataset} seed={seed} 训练 OOM: {e}")
        oom_log["degraded_count"] += 1
        oom_log["max_level"] = max(oom_log["max_level"], 4)  # 直接跳到 Level 4!
```

**反例**：当 InceptionTime-Lite 在 RTX 5060 上 OOM 时：
- **声称行为**：自动降级到 n_filters=32 → gradient checkpointing → ResNet1D 变体 → 诚实报告
- **实际行为**：直接标记为 Level 4 降级，跳过 Level 1-3 的所有备选

**严重性**：**致命**——R5 方案 §3.2 E5 的 P2-8 修补（"OOM 备选方案具体化"）声称有 4 级备选链，但代码中该链是死代码。R5 的核心承诺之一（解决 N7 攻击）在代码层面完全未实现。

**反驳预判**：正方可能说"用户可以手动传 `--n-filters 32 --use-checkpoint`"。但这是手动操作，不是自动备选链。且即使手动操作，Level 3 的 ResNet1D 变体也是死代码（见 S3）。

---

### F2：2/6 迁移方向会崩溃（IndexError: 数组越界）

**攻击维度**：边界失效 + 反例构造

**证据**：

`eval_transfer_pair` 第 382 行计算 `num_classes`：
```python
num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
```

第 399 行用 `num_classes` 构造 one-hot 矩阵：
```python
one_hot_cal = np.eye(num_classes)[cal_labels]
```

但 `cal_labels` 来自 `source_info["cal_eval"]["labels"]`，其值域为 `[0, DATASET_NUM_CLASSES[source] - 1]`。

**反例**：迁移方向 `("ptbxl", "cpsc")`：
- `source = "ptbxl"`，`DATASET_NUM_CLASSES["ptbxl"] = 5`
- `target = "cpsc"`，`DATASET_NUM_CLASSES["cpsc"] = 4`
- `num_classes = min(5, 4) = 4`
- `cal_labels` 值域为 `[0, 4]`（5 类源域的 cal 集）
- `np.eye(4)` 只有 4 行（索引 0-3）
- 当 `cal_labels` 包含 4 时：**`IndexError: index 4 is out of bounds for axis 0 with size 4`**

**6 个迁移方向的崩溃分析**：

| 方向 | 源类数 | 目标类数 | num_classes | cal_labels 值域 | np.eye 行数 | 结果 |
|------|--------|---------|------------|----------------|------------|------|
| ptbxl→chapman | 5 | 5 | 5 | [0,4] | 5 | ✅ OK |
| **ptbxl→cpsc** | **5** | **4** | **4** | **[0,4]** | **4** | **❌ CRASH** |
| chapman→ptbxl | 5 | 5 | 5 | [0,4] | 5 | ✅ OK |
| **chapman→cpsc** | **5** | **4** | **4** | **[0,4]** | **4** | **❌ CRASH** |
| cpsc→ptbxl | 4 | 5 | 4 | [0,3] | 4 | ✅ OK |
| cpsc→chapman | 4 | 5 | 4 | [0,3] | 4 | ✅ OK |

**2/6 迁移方向会崩溃**，即 10/30 迁移实验无法完成。

**严重性**：**致命**——E5 实验的 30 迁移评估中有 10 个会崩溃，CSV 输出不完整。冒烟测试如果只测 ptbxl（5 类）不会发现此 bug，因为 ptbxl→ptbxl 不涉及类数不匹配。

**深层问题**：即使修复了 IndexError，5 类源模型 → 4 类目标域的语义本身就有问题：模型输出 5 维 logits，目标域只有 4 类标签，`argmax` 可能预测不存在的第 5 类，准确率被人为压低。脚本没有处理跨类数迁移的 logits 对齐问题。

---

### F3：参数量审计断言检查的是硬编码配置，而非实际运行配置

**攻击维度**：隐含假设 + 自相矛盾

**证据**：

`main()` 第 556-571 行的参数量审计：
```python
# 第 557 行：硬编码 n_filters=48
audit_model = build_inceptiontime_lite(in_channels=12, d_model=64, n_filters=48)
...
# 第 563-566 行：硬编码 backbone_type="inceptiontime_lite"（默认 n_filters=48）
full_model = ECGClassifier(
    in_channels=12, d_model=64, n_layers=3, num_classes=5,
    backbone_type="inceptiontime_lite",
)
full_params = sum(p.numel() for p in full_model.parameters())
# 第 569-570 行：断言
assert 200_000 <= full_params <= 500_000, \
    f"参数量 {full_params:,} 不在目标 200K-500K 内！"
```

**反例**：用户运行 `python scripts/run_e5_inception_lite.py --n-filters 32`：
- 审计断言检查的是 `n_filters=48` 的模型（315,846 参数）→ **断言通过** ✅
- 实际训练用的是 `n_filters=32` 的模型（147,334 参数）→ **低于 200K 下界** ❌
- 断言给出了虚假的安全感

**严重性**：**致命**——参数量审计是 E5 预注册要求的核心质量门控，但该门控只检查默认配置。OOM Level 1 备选（n_filters=32）产生的 147K 参数模型会静默通过审计，违反 [200K, 500K] 约束。

`train_single` 第 306-309 行有 WARN 打印但不会终止：
```python
if n_params < 200_000:
    print(f"[WARN] 参数量 {n_params:,} < 200K 目标下界")  # 只打印，不终止
```

---

## 2. 严重攻击（SEVERE）

### S1：OOM Level 1（n_filters=32）产生 147K 参数，违反 [200K, 500K] 约束

**攻击维度**：量级错误 + 边界失效

**证据**（实测计算）：

| 配置 | Backbone | Head | 全模型 | 在 [200K, 500K]? |
|------|---------|-----|--------|-----------------|
| n_filters=48（默认） | 309,120 | 6,726 | **315,846** | ✅ |
| n_filters=32（OOM Level 1） | 140,608 | 6,726 | **147,334** | ❌ **低于 200K** |

**反例**：当默认配置 OOM 时，R5 方案声称 Level 1 降级到 n_filters=32（"参数量 ~136K"）。但 136K < 200K 下界，这意味着 OOM 备选 Level 1 产生的模型**不在预注册的参数量目标区间内**。

**自相矛盾**：
- `inceptiontime_lite.py` 第 28 行：`若 OOM 改 32，参数量降至 ~136K`
- `inceptiontime_lite.py` 第 24 行：`Backbone 总计 ≈ 310K（在 200K-500K 目标内）`
- 136K 不在 200K-500K 内，但文档没有声明这一矛盾

**严重性**：**严重**——OOM 备选 Level 1 违反预注册约束。如果 Level 1 触发，实验结果的参数量对比不再公平（147K vs ResNet1D 258K vs InceptionTime 192K），且与"3 架构家族同量级"的 claim 矛盾。

---

### S2：OOM Level 3 的 ResNet1D 变体是死代码——depth/width 参数被忽略

**攻击维度**：逻辑断链 + 语义偏移

**证据**：

`build_model` 第 236-248 行，当 `arch_override == "resnet1d"` 时：
```python
if arch_override == "resnet1d":
    from src.models.baselines import ECGResNet1D
    block_layers_map = {3: (1, 1, 1), 5: (2, 2, 1), 7: (2, 2, 2, 1)}
    block_layers = block_layers_map.get(depth, (2, 2, 2, 2))  # 计算了但...
    model = ECGClassifier(
        in_channels=12, d_model=width or d_model, n_layers=2,  # ← block_layers 没传入!
        num_classes=num_classes, dropout=dropout,
        backbone_type="resnet1d",  # ← 用默认 ResNet1D，不是变体!
    )
    return model
```

`block_layers` 在第 241 行计算后**从未被使用**。`ECGClassifier` 构造的 ResNet1D 始终使用 `baselines.py` 的默认配置（`block_layers=(2,2,2,2)`, `base_width=16`），与 `depth`/`width` 参数完全无关。

**反例**：OOM 备选链中 3 个 Level 3 变体：
```python
(3, {..., "depth": 3, "width": 32}, "Level 3: ResNet1D 变体（depth=3, width=32）"),
(3, {..., "depth": 5, "width": 64}, "Level 3: ResNet1D 变体（depth=5, width=64）"),
(3, {..., "depth": 7, "width": 128}, "Level 3: ResNet1D 变体（depth=7, width=128）"),
```
这 3 个"不同变体"实际产生**完全相同的 ResNet1D 模型**（默认配置）。

**严重性**：**严重**——R5 方案 §3.2 E5 声称 Level 3 备选是"ResNet1D 不同超参变体（depth 3/5/7, width 32/64/128）"，但代码中这些变体不存在。加上 F1（备选链是死代码），Level 3 在两个层面失效。

---

### S3：gradient checkpointing 与 BatchNorm 不兼容——running stats 被双重更新

**攻击维度**：隐含假设 + 边界失效

**证据**：

`InceptionBlockLite.forward` 第 101-105 行：
```python
def forward(self, x):
    if self.use_checkpoint and self.training:
        return checkpoint(self._forward_impl, x, use_reentrant=False)
    return self._forward_impl(x)
```

`_forward_impl` 第 90-99 行包含 `self.bn(out)`（BatchNorm1d）。

**问题机制**：
1. **前向传播**：`checkpoint(fn, x)` 执行 `fn(x)`，BN 的 `running_mean`/`running_var` 被更新（因为 `model.training=True`）
2. **反向传播**：checkpoint 重新执行 `fn(x)` 以重计算中间激活（梯度检查点的核心机制），BN 的 `running_mean`/`running_var` **再次被更新**
3. 结果：每个训练 iteration 中 BN running stats 被更新 **2 次**，导致 running stats 偏离正确值

`use_reentrant=False` 修复的是 autograd 的 reentrant 问题，**不修复 BN running stats 双重更新问题**。这是 PyTorch gradient checkpointing + BN 的已知陷阱。

**反例**：启用 `--use-checkpoint`（OOM Level 2）后，训练 50 epochs 的 BN running stats 累积了 100 epochs 的更新量。迁移评估时 `model.eval()` 使用被污染的 running stats，导致迁移性能异常。

**严重性**：**严重**——OOM Level 2 备选产生的模型 BN 统计不正确，迁移评估结果不可信。且此问题不会报错，只会静默降低性能，难以察觉。

**反驳预判**：正方可能说"checkpoint 只在 OOM 时启用"。但 OOM Level 2 是 R5 方案明确声称的备选，其正确性应该被保证。

---

### S4：架构家族独立性 claim 自相矛盾——inceptiontime_lite.py 与 R5 方案矛盾

**攻击维度**：自相矛盾 + 语义偏移

**证据**：

**inceptiontime_lite.py 第 12-17 行**（正方代码注释）：
```
架构家族独立性论证（正方立场）：
  架构家族的区分在于归纳偏置，而非深度：
  - ResNet1D：串行残差 + 逐级降采样（VGG/ResNet 范式）
  - BiMamba：选择性状态空间 + 双向扫描（SSM 范式）
  - InceptionTime-Lite：多尺度并行卷积 + bottleneck + maxpool 旁路（Inception 范式）
  三者在特征提取机制上正交，3 blocks vs 6 blocks 是深度选择，不改变家族归属。
```

**R5 方案 §3.2 E5 第 383-385 行**（正方方案文档）：
```
- **超参变体**：InceptionTime-Lite (3 blocks, ~200K-500K 参数) 是 InceptionTime 的超参变体
  （减少 Inception module 数量），**不是独立的架构家族**
```

**R5 方案 §4.2 C4 第 526 行**：
```
- **新增**：2 架构家族 + 1 超参变体方法对比（E5 结果，P1-4 诚实声明）
```

**矛盾**：
- `inceptiontime_lite.py` 声称 InceptionTime-Lite 是**独立架构家族**（"三者在特征提取机制上正交"）
- R5 方案声称 InceptionTime-Lite 是**超参变体，不是独立架构家族**

**严重性**：**严重**——代码注释与方案文档直接矛盾。如果 InceptionTime-Lite 是独立家族，则 R5 的"2 架构家族 + 1 超参变体"诚实声明是假的；如果是超参变体，则代码注释的"独立性论证"是假的。两者不能同时为真。

---

### S5："Lite" 命名误导——InceptionTime-Lite (315K) 比原版 InceptionTime (192K) 参数更多

**攻击维度**：语义偏移 + 量级错误

**证据**（实测）：

| 模型 | n_blocks | n_filters | 全模型参数量 |
|------|---------|-----------|------------|
| InceptionTime-Lite ("Lite") | 3 | **48** | **315,846** |
| 原版 InceptionTime (baselines.py 默认) | 4 | 32 | 192,646 |

InceptionTime-Lite 的参数量（315K）是原版 InceptionTime（192K）的 **1.64 倍**。"Lite" 暗示更轻量，但实际更重。

**原因**：InceptionTime-Lite 减少了 blocks（3 vs 4），但增加了 n_filters（48 vs 32）。每个 block 的参数量与 n_filters² 成正比，n_filters 从 32→48 增加了 2.25 倍，超过了 blocks 从 4→3 减少的 0.75 倍。

**严重性**：**严重**——"Lite" 命名造成认知误导。审稿人看到 "InceptionTime-Lite" 会预期更少参数，但实际更多。如果论文中用 "Lite" 描述此架构，审稿人可能质疑命名的诚实性。

---

### S6："3 vs 6 blocks" 对比是虚假的——代码库原版 InceptionTime 默认 4 blocks

**攻击维度**：隐含假设 + 语义偏移

**证据**：

`inceptiontime_lite.py` 第 5 行：
```
- 3 个 Inception module（原始 InceptionTime 6 个，简化为 3 个）
```

`inceptiontime_lite.py` 第 117 行：
```
- 默认 n_blocks=3（vs 原始 4，vs InceptionTime 原文 6）
```

`baselines.py` 第 188 行（实际代码库中的 InceptionTime）：
```python
n_blocks: int = 4,  # ← 代码库默认是 4，不是 6
```

**矛盾**：
- 第 5 行说"原始 InceptionTime 6 个"——这是 InceptionTime **论文**的配置
- 第 117 行说"vs 原始 4"——这是 **代码库**的配置
- 代码库中 `ECGInceptionTime` 默认 `n_blocks=4`

**问题**：E5 实验的对比基线是代码库中的 `ECGInceptionTime`（4 blocks），不是论文中的 InceptionTime（6 blocks）。当 E5 声称"3 vs 6 blocks 是深度选择"时，实际对比是"3 vs 4 blocks"。"3 vs 4" 的深度减少只有 25%，远不如 "3 vs 6" 的 50% 显著。

**严重性**：**严重**——架构对比的深度差异被夸大。如果审稿人发现实际对比是 3 vs 4（而非声称的 3 vs 6），可能质疑实验设计的诚实性。

---

## 3. 中等攻击（MODERATE）

### M1：冒烟测试不减少 seeds/datasets——docstring 与代码矛盾

**攻击维度**：自相矛盾

**证据**：

第 46 行 docstring：
```
# 冒烟测试（合成数据，2 epoch，1 种子）
python scripts/run_e5_inception_lite.py --smoke
```

第 534-541 行实际代码：
```python
if args.smoke:
    # 冒烟模式：只设置训练超参，seeds/datasets 保留命令行值（默认全部）
    args.epochs = 2
    args.limit = 240 if args.limit is None else args.limit
    args.bootstrap = 200
    print(f"[冒烟模式] epochs=2, limit={args.limit}, bootstrap=200, "
          f"seeds={args.seeds}, datasets={args.datasets}")
```

**矛盾**：docstring 说"1 种子"，代码说"seeds/datasets 保留命令行值（默认全部）"。`--smoke` 不传额外参数时，会运行 **5 种子 × 3 数据集 = 15 模型 + 30 迁移**，每个 2 epochs。这不是"冒烟测试"。

**严重性**：中等——用户按 docstring 运行 `--smoke` 会得到远超预期的运行时间。但代码注释（第 535 行）诚实说明了这一行为，只是 docstring 误导。

---

### M2：kernel 23 覆盖 230ms 的 claim 依赖隐含的 100Hz 采样率假设

**攻击维度**：隐含假设

**证据**：

`inceptiontime_lite.py` 第 7 行：
```
(a) 多尺度并行卷积（kernel 5/11/23 同时捕获短/中/长时程特征）
```

`run_e5_inception_lite.py` 第 38 行：
```
A3: "3 blocks 多尺度是否充分"——缓解：kernel 23 在 seq_len=1000 下覆盖 ~230ms
```

**隐含假设**：`230ms = 23 samples / 100 Hz`。这假设采样率为 100 Hz。

**反例**：
- PTB-XL 常用 500 Hz：kernel 23 覆盖 `23/500 = 46ms`，不足以覆盖 T 波（~160ms）
- CPSC2018 常用 500 Hz：同上
- 如果 seq_len=1000 对应 500 Hz × 2s = 1000 samples，则 kernel 23 只覆盖 46ms

**严重性**：中等——kernel 23 在 500 Hz 下可能不足以覆盖 ECG 的长时程特征（T 波）。claim "3 blocks 足以捕获 ECG 关键多尺度特征"（H1 假设）在 500 Hz 采样率下可能不成立。脚本没有声明或验证采样率。

---

### M3：3 blocks 的感受野计算被忽略——实际 RF 可能不足以覆盖完整心电周期

**攻击维度**：量级错误

**证据**：

3 个 InceptionBlockLite 串联，每个 block 的最大 kernel 为 23。由于时间维不降采样（`seq_out == seq_len`），感受野（RF）线性增长：

- Block 1 后：RF = 23
- Block 2 后：RF = 23 + 23 - 1 = 45
- Block 3 后：RF = 45 + 23 - 1 = 67

在 100 Hz 下：67 samples = 670ms（覆盖一个心动周期 ~600ms，勉强够）
在 500 Hz 下：67 samples = 134ms（**不足以覆盖完整 P-QRS-T 复合波**）

**对比原版 InceptionTime（4 blocks）**：
- 4 blocks 后：RF = 4 × 23 - 3 = 89
- 500 Hz 下：89 samples = 178ms（仍不足以覆盖完整心动周期，但比 3 blocks 好 33%）

**严重性**：中等——3 blocks 的感受野在 500 Hz 下可能不足以捕获跨心电周期的特征。这影响 H1 假设（"3 blocks 足以捕获 ECG 关键多尺度特征"）的成立。

---

### M4：跨类数迁移的 logits 维度不匹配——5 类模型 → 4 类目标域语义错误

**攻击维度**：语义偏移 + 边界失效

**证据**：

即使修复了 F2 的 IndexError，`eval_transfer_pair` 在 5 类源 → 4 类目标迁移时仍有语义问题：

第 394-396 行：
```python
tgt_eval = evaluate(model, tgt_loader, device, compute_calibration=False)
ood_probs = tgt_eval["probs"]  # shape: (N, 5) ← 5 维输出
ood_labels = tgt_eval["labels"]  # shape: (N,) ← 值域 [0, 3]
```

第 405 行：
```python
correct_mask = (ood_probs.argmax(axis=1) == ood_labels).astype(float)
```

**问题**：`ood_probs.argmax(axis=1)` 可能输出 4（第 5 类），但 `ood_labels` 最大为 3。模型预测了一个在目标域不存在的类，被计为错误。这人为压低了迁移准确率。

**反例**：源域 ptbxl 有 5 类（NORM, MI, STTC, CD, HYP），目标域 cpsc 有 4 类（NORM, CD, STTC, MI，无 HYP）。模型可能对某些样本预测 HYP（类 4），但在目标域 HYP 不存在，这些预测被计为错误，即使模型在源域的判断是正确的。

**严重性**：中等——跨类数迁移的准确率不可直接比较。E5 的 30 迁移实验中，10 个涉及类数不匹配，其准确率被人为压低，可能误导结论。

---

### M5：`try_train_with_oom_fallback` 的 Level 1 报告逻辑错误——对原始配置也打印 "Level 1 触发"

**攻击维度**：逻辑断链

**证据**：

第 183 行：
```python
report_oom_level(level, desc) if level > 0 or params["n_filters"] != 48 else None
```

备选链第一个条目：
```python
(1, {"n_filters": 48, "use_checkpoint": False}, "原始配置（n_filters=48, no checkpoint）"),
```

条件 `level > 0 or params["n_filters"] != 48` = `1 > 0 or 48 != 48` = `True or False` = `True`

→ 对**原始配置**也调用 `report_oom_level(1, "原始配置...")`，打印 "[OOM 备选] Level 1 触发: 原始配置"

**问题**：原始配置不是 OOM 备选，但日志说 "Level 1 触发"，误导用户以为 OOM 已发生。

**严重性**：中等——虽然此函数是死代码（F1），但逻辑错误本身存在。如果未来有人接线此函数，会产出误导性日志。

---

## 4. 轻微攻击（MINOR）

### m1：`n_layers=3` 在 `build_model` 中被忽略，造成混淆

**证据**：`build_model` 第 251 行传 `n_layers=3` 给 `ECGClassifier`，但 `build_backbone` 对 `inceptiontime_lite` 忽略 `n_layers`。`n_layers=3` 看似设置 block 数，实际是 no-op。`n_blocks=3` 在 `ECGInceptionTimeLite.__init__` 中硬编码且有 assert。

**严重性**：轻微——不影响正确性，但代码可读性差。

---

### m2：双重 dropout——backbone 和 head 各一层

**证据**：`build_model` 传 `dropout=0.1` 给 `ECGClassifier`，后者传给 `build_backbone` → `build_inceptiontime_lite` → `ECGInceptionTimeLite`（backbone 末尾有 `nn.Dropout(0.1)`）。同时 `ECGClassifier.classifier` 也有 `nn.Dropout(0.1)`。两处 dropout 叠加，实际 dropout 率高于 0.1。

**严重性**：轻微——可能轻微影响训练动态，但不会导致错误。

---

### m3：`count_parameters` 方法不包含 head 参数

**证据**：`ECGInceptionTimeLite.count_parameters` 只审计 backbone 参数（blocks + proj + norm = 309K），不含 head（6.7K）。脚本单独计算 `full_params` 补充了 head，但 `count_parameters` 的输出可能误导读者认为总参数量是 309K 而非 315K。

**严重性**：轻微——审计信息不完整，但不影响实验正确性。

---

### m4：`baselines.py` 的 `__all__` 在 import 之后定义

**证据**：`baselines.py` 第 249-254 行定义 `__all__`，第 257 行在 `__all__` 之后 `from .inceptiontime_lite import ECGInceptionTimeLite`。`ECGInceptionTimeLite` 不在 `__all__` 中，但被 import 到模块命名空间。这不符合 Python 惯例（`__all__` 应列出所有公开符号）。

**严重性**：轻微——不影响功能，但 `from baselines import *` 不会导入 `ECGInceptionTimeLite`。

---

## 5. 攻击维度全覆盖验证

### 5.1 反例构造 ✅
- F2：构造了 ptbxl→cpsc 迁移的具体崩溃反例
- S1：构造了 n_filters=32 的参数量违规反例（147K < 200K）
- M4：构造了 5 类模型预测不存在类的语义错误反例

### 5.2 逻辑断链 ✅
- F1：OOM 备选链定义了但从未调用（定义→使用的断链）
- S2：`block_layers` 计算了但从未使用（计算→使用的断链）
- M5：Level 1 报告条件逻辑错误

### 5.3 隐含假设 ✅
- F3：假设用户不会改 n_filters（审计只检查默认配置）
- S3：假设 gradient checkpointing 与 BN 兼容（实际不兼容）
- M2：假设采样率为 100Hz（kernel 23 覆盖 230ms 的隐含假设）

### 5.4 边界失效 ✅
- F2：5 类源 → 4 类目标的边界（np.eye 越界）
- S1：n_filters=32 时参数量低于 200K 下界
- S3：gradient checkpointing 下 BN running stats 双重更新

### 5.5 自相矛盾 ✅
- S4：代码说"独立家族" vs 方案说"超参变体"
- S5："Lite" 命名 vs 实际更重（315K > 192K）
- M1：docstring 说"1 种子" vs 代码保留全部种子

### 5.6 量级错误 ✅
- S1：147K 不在 [200K, 500K] 内
- S5：315K > 192K（"Lite" 比 "full" 更重）
- M3：3 blocks 的 RF=67，500Hz 下仅 134ms

### 5.7 语义偏移 ✅
- S2："depth 3/5/7, width 32/64/128" 的 ResNet1D 变体不存在
- S6："3 vs 6 blocks" 实际是 "3 vs 4 blocks"
- M4：5 类 logits vs 4 类 labels 的语义不匹配

---

## 6. 攻击汇总与优先级排序

| 编号 | 严重性 | 攻击点 | 影响 | 修复难度 |
|------|--------|--------|------|---------|
| **F1** | **致命** | OOM 备选链是死代码 | OOM 时直接 Level 4 降级，跳过 Level 1-3 | 中（需接线到 main） |
| **F2** | **致命** | 2/6 迁移方向崩溃 | 10/30 迁移实验无法完成 | 中（需处理跨类数迁移） |
| **F3** | **致命** | 参数审计检查错误配置 | OOM Level 1 静默违规 | 低（用实际 n_filters 审计） |
| **S1** | **严重** | OOM Level 1 参数量 147K < 200K | 备选模型违反约束 | 中（需调整参数或放宽约束） |
| **S2** | **严重** | Level 3 ResNet1D 变体是死代码 | depth/width 被忽略 | 低（传入 block_layers） |
| **S3** | **严重** | gradient checkpointing + BN 不兼容 | BN stats 被污染 | 高（需冻结 BN 或用其他归一化） |
| **S4** | **严重** | 架构家族 claim 自相矛盾 | 代码 vs 方案矛盾 | 低（统一说法） |
| **S5** | **严重** | "Lite" 命名误导 | 315K > 192K | 低（改名或调整参数） |
| **S6** | **严重** | "3 vs 6" 实际是 "3 vs 4" | 深度差异被夸大 | 低（修正文档） |
| **M1** | 中等 | 冒烟测试不减种子 | --smoke 运行全量 | 低（修复 docstring 或代码） |
| **M2** | 中等 | kernel 230ms 假设 100Hz | 500Hz 下覆盖不足 | 中（需验证采样率） |
| **M3** | 中等 | 3 blocks RF 在 500Hz 不足 | 感受野 134ms | 中（需增加 blocks 或 kernel） |
| **M4** | 中等 | 跨类数迁移语义错误 | 准确率被人为压低 | 中（需 logits 对齐） |
| **M5** | 中等 | Level 1 报告逻辑错误 | 误导性日志 | 低（修条件） |
| **m1** | 轻微 | n_layers=3 被忽略 | 代码混淆 | 低（删除或注释） |
| **m2** | 轻微 | 双重 dropout | 轻微影响训练 | 低（删除一处） |
| **m3** | 轻微 | count_parameters 不含 head | 审计不完整 | 低（补充 head） |
| **m4** | 轻微 | __all__ 不含 ECGInceptionTimeLite | import * 不完整 | 低（补充） |

---

## 7. 对 R5 方案 P2-8 修补的攻击

R5 方案 §3.2 E5 声称 P2-8 修补（"OOM 备选方案具体化"）解决了 N7 攻击。本审查发现：

| P2-8 声称 | 代码实际 | 裁决 |
|----------|---------|------|
| Level 1: n_filters 64→32 | n_filters 48→32（默认已是 48），且 32 产生 147K < 200K | **部分实现，参数违规** |
| Level 2: gradient checkpointing | 实现了，但与 BN 不兼容（S3） | **实现但有 bug** |
| Level 3: ResNet1D depth 3/5/7, width 32/64/128 | depth/width 被忽略，3 个变体产生相同模型（S2） | **未实现** |
| Level 4: 诚实报告 | 实现了（main 的 except 块） | **实现** |
| 4 级自动降级链 | `try_train_with_oom_fallback` 是死代码，从未调用（F1） | **未实现** |

**裁决**：P2-8 修补在代码层面 **未真正解决 N7 攻击**。4 级备选链只有 Level 4（诚实报告）实际工作，Level 1-3 全部失效（死代码 / 参数违规 / BN bug / 变体不存在）。

---

## 8. 对 E5 实验可行性的整体评估

### 8.1 当前代码能否完成 E5 实验？

**不能**。具体原因：

1. **2/6 迁移方向会崩溃**（F2）：ptbxl→cpsc 和 chapman→cpsc 会因 IndexError 崩溃，10/30 迁移实验无法完成。
2. **OOM 备选链不工作**（F1+S1+S2+S3）：如果默认配置 OOM，没有可用的自动备选（Level 1 违规，Level 2 有 BN bug，Level 3 是死代码，只有 Level 4 诚实降级可用）。
3. **参数审计虚假通过**（F3）：如果用户手动传 `--n-filters 32`，审计不会发现参数量违规。

### 8.2 冒烟测试能否通过？

**可能通过，但不保证完整实验也能通过**：
- 冒烟测试默认运行全部 5 种子 × 3 数据集（M1），如果数据不存在会 skip
- 如果只测 ptbxl（5 类），不会触发 F2 的跨类数崩溃
- 2 epochs 足以发现 BN stats 问题（S3），因为 running stats 偏差在 2 epochs 内可能不明显
- 冒烟测试不测迁移评估（如果数据不存在），不会发现 F2

### 8.3 修复建议（反方视角）

| 优先级 | 修复 | 对应攻击 |
|--------|------|---------|
| P0 | 修复 F2：跨类数迁移的 logits 对齐（截断到 min 类数或重映射） | F2, M4 |
| P0 | 修复 F1：将 `try_train_with_oom_fallback` 接线到 main | F1 |
| P0 | 修复 F3：参数审计用实际 `args.n_filters` 而非硬编码 48 | F3 |
| P1 | 修复 S1：OOM Level 1 改用 n_filters=40（~220K，在范围内）或放宽下界 | S1 |
| P1 | 修复 S2：将 `block_layers` 传入 ResNet1D 构造 | S2 |
| P1 | 修复 S3：gradient checkpointing 时冻结 BN running stats 更新 | S3 |
| P1 | 修复 S4：统一代码注释与 R5 方案的架构家族说法 | S4 |
| P2 | 修复 M1：冒烟测试默认 `--seeds 42 --datasets ptbxl` | M1 |
| P2 | 修复 S6：修正 "3 vs 6" 为 "3 vs 4"（代码库实际默认） | S6 |

---

## 9. 结论

E5 实验脚本存在 **3 个致命 bug** 和 **6 个严重问题**，当前代码**无法正确完成 E5 实验**。

**核心问题**：
1. **OOM 备选链完全失效**（F1+S1+S2+S3）——R5 方案 P2-8 修补的核心承诺在代码层面未实现
2. **迁移评估崩溃**（F2）——2/6 迁移方向因类数不匹配而 IndexError
3. **参数审计虚假通过**（F3）——检查硬编码配置而非实际配置

**对 R5 方案的影响**：
- P2-8 修补（"OOM 备选方案具体化"）**未真正解决 N7 攻击**——4 级备选链只有 Level 4 实际工作
- E5 的 30 迁移实验中至少 10 个无法完成，CSV 输出不完整
- 架构家族独立性 claim（S4）在代码和方案间自相矛盾

**正方需在 E5 实验执行前修复 F1+F2+F3 三个致命 bug**，否则实验结果不可信。S1-S6 六个严重问题也应在论文撰写前解决，否则审稿人可能质疑实验的严谨性。

---

**攻击报告结束。**

反方挑刺代理-E5 已尝试全部 7 个攻击维度，找到 3 个致命攻击、6 个严重攻击、5 个中等攻击、4 个轻微攻击。E5 实验脚本在当前状态下**无法正确执行完整实验**。
