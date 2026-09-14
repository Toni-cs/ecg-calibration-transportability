# E5 实验脚本反反方裁决报告

> **反反方审查代理-E5 交付**。本报告对反方挑刺代理-E5 提出的 18 个攻击点（3 致命 + 6 严重 + 5 中等 + 4 轻微）逐条进行元审查，评估每个攻击是否为稻草人论证、是否误解正方意图、反例是否真的成立、攻击逻辑是否自洽。
> **裁决日期**：2026-09-09
> **审查对象**：`docs/adversarial_r1_attack_e5.md`（反方攻击报告）
> **被攻击代码**：
> - `scripts/run_e5_inception_lite.py`（687 行）
> - `src/models/inceptiontime_lite.py`（214 行）
> - `src/models/baselines.py`（257 行）
> - `docs/Q2_UPGRADE_PROPOSAL_R5.md`（1313 行）
> **审查代理**：反反方元审查者-E5（GLM-5.2）
> **审查原则**：对每个攻击点依次执行 5 维度审查（反例成立性 / 稻草人论证 / 误解前提 / 攻击逻辑自洽 / 严重程度夸大），给出裁决：成立 / 部分成立 / 驳回。

---

## 0. 裁决概述

### 裁决统计

| 裁决类别 | 数量 | 编号 |
|---------|------|------|
| **成立** | 10 | F1, F2, F3, S2, S4, M1, M4, m1, m2, m3 |
| **部分成立** | 7 | S1, S3, S5, S6, M2, M3, M5 |
| **驳回** | 1 | m4 |
| **合计** | **18** | |

### 严重程度校准

| 反方标注 | 实际严重性 | 编号 | 说明 |
|---------|-----------|------|------|
| 致命 | **致命** | F1, F2, F3 | 三个致命攻击均成立，反方未夸大 |
| 严重 | **严重** | S2, S4 | 成立的严重攻击 |
| 严重 | **中等** | S1, S3, S5, S6 | 被降级的严重攻击（影响被夸大或取决于未验证假设） |
| 中等 | **中等** | M1, M4 | 成立的中等攻击 |
| 中等 | **轻微~中等** | M2, M3 | 取决于采样率假设，需进一步验证 |
| 中等 | **轻微** | M5 | 死代码中的逻辑错误，实际影响为零 |
| 轻微 | **轻微** | m1, m2, m3 | 成立的轻微攻击 |
| 轻微 | **驳回** | m4 | 反方事实错误 |

### 整体评估

反方攻击报告质量**较高**：18 个攻击点中 10 个完全成立、7 个部分成立、仅 1 个被驳回（m4 的事实错误）。三个致命攻击（F1 死代码、F2 IndexError、F3 审计虚假通过）**均经独立验证确认成立**，反方未使用稻草人论证或夸大严重程度。反方在 m4 上犯了事实错误（声称 `ECGInceptionTimeLite` 不在 `__all__` 中，但实际在第 253 行明确列出），在 S1/S3/S5/S6 上有一定程度的严重性夸大。

**对正方的建议**：F1+F2+F3 三个致命 bug 必须在 E5 实验执行前修复，否则实验结果不可信。S2+S4 两个严重问题应在论文撰写前解决。其余部分成立的攻击可按优先级逐步修复。

---

## 1. 致命攻击裁决（FATAL）

### F1：4 级 OOM 备选链是完全死代码

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。`grep` 独立验证：`try_train_with_oom_fallback` 在全文仅 1 处匹配（第 154 行函数定义），无任何调用点。`main()` 第 582-606 行直接调用 `train_single`，OOM 处理是简单 try/except，直接 `oom_log["max_level"] = max(..., 4)` 跳到 Level 4。 |
| 稻草人论证 | ❌ 无。反方准确引用了代码行号和逻辑，未歪曲正方设计意图。 |
| 误解前提 | ❌ 无。反方正确理解了 `try_train_with_oom_fallback` 的设计意图（4 级备选链）和 `main()` 的实际行为（跳过 Level 1-3）。 |
| 攻击逻辑自洽 | ✅ 自洽。"函数定义了但从未调用 → 死代码 → R5 的 P2-8 修补承诺未实现"的推理链条完整。 |
| 严重程度夸大 | ❌ 未夸大。R5 方案 §3.2 E5 明确声称"4 级 OOM 备选方案"（P2-8 修补），代码中该链确实是死代码，这是 R5 核心承诺的未实现。 |

**裁决**：**成立**

**反驳预判的回应**：反方预判正方可能说"用户可以手动传 `--n-filters 32 --use-checkpoint`"。这个预判是合理的——手动操作确实不是自动备选链。但需补充：即使作为手动操作，`--n-filters 32` 会触发 S1（参数量违规），`--use-checkpoint` 会触发 S3（BN 双重更新），Level 3 的 ResNet1D 变体会触发 S2（block_layers 被忽略）。即手动操作路径也有问题。

**修补方案**：
```python
# 方案 A（推荐）：将 try_train_with_oom_fallback 接线到 main()
for dataset in args.datasets:
    for seed in args.seeds:
        model, info = try_train_with_oom_fallback(
            train_fn=lambda params, dev: train_single(
                dataset, seed, args, dev,
                n_filters=params["n_filters"],
                use_checkpoint=params["use_checkpoint"],
            ),
            config={...}, device=device,
            n_filters=args.n_filters, use_checkpoint=args.use_checkpoint,
        )

# 方案 B（最小改动）：删除 try_train_with_oom_fallback，诚实声明 OOM 备选是手动操作
# 在 docstring 中明确："OOM 备选需手动传 --n-filters 32 --use-checkpoint"
```

---

### F2：2/6 迁移方向会崩溃（IndexError: 数组越界）

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。逐行验证：第 382 行 `num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])`，第 399 行 `one_hot_cal = np.eye(num_classes)[cal_labels]`。对于 `ptbxl→cpsc`：`num_classes = min(5, 4) = 4`，`cal_labels` 值域 `[0, 4]`（5 类源域），`np.eye(4)` 只有 4 行 → `cal_labels == 4` 时 `IndexError`。反方的 6 方向崩溃分析表正确：2/6 方向崩溃。 |
| 稻草人论证 | ❌ 无。反方准确引用了代码和类数配置。 |
| 误解前提 | ❌ 无。反方正确理解了 `cal_labels` 的来源（`source_info["cal_eval"]["labels"]`）和值域。 |
| 攻击逻辑自洽 | ✅ 自洽。"源类数 > 目标类数 → num_classes = min → np.eye 行数 < cal_labels 最大值 → IndexError"的推理链条完整。 |
| 严重程度夸大 | ❌ 未夸大。10/30 迁移实验崩溃确实是致命的，CSV 输出不完整。 |

**裁决**：**成立**

**深层问题确认**：反方指出的"即使修复 IndexError，5 类源模型 → 4 类目标域的语义问题"也成立（见 M4 裁决）。这不是夸大，而是真实的跨类数迁移设计缺陷。

**修补方案**：
```python
# 方案 A（推荐）：one_hot 用源类数构造，probs 截断到 num_classes
one_hot_cal = np.eye(DATASET_NUM_CLASSES[source])[cal_labels]  # 用源类数
# TS 拟合时只取前 num_classes 维
T = fit_temperature(cal_probs[:, :num_classes], one_hot_cal[:, :num_classes])
ood_probs_ts = apply_temperature(ood_probs[:, :num_classes], T)

# 方案 B：跳过跨类数迁移方向（诚实声明）
if DATASET_NUM_CLASSES[source] != DATASET_NUM_CLASSES[target]:
    print(f"[SKIP] {source}→{target}: 类数不匹配，跳过")
    return {"source": source, "target": target, "skipped": True, "reason": "class_count_mismatch"}
```

---

### F3：参数量审计断言检查的是硬编码配置

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。第 557 行 `build_inceptiontime_lite(in_channels=12, d_model=64, n_filters=48)` 硬编码 `n_filters=48`，第 563-566 行 `ECGClassifier(..., backbone_type="inceptiontime_lite")` 使用默认 `n_filters=48`。用户传 `--n-filters 32` 时，审计检查 315K（通过），实际训练用 147K（违规）。 |
| 稻草人论证 | ❌ 无。反方准确引用了硬编码的 48。 |
| 误解前提 | ❌ 无。反方正确区分了"审计配置"和"实际训练配置"。 |
| 攻击逻辑自洽 | ✅ 自洽。"审计用硬编码 48 → 用户改 n_filters → 审计不反映实际 → 虚假安全感"的推理链条完整。 |
| 严重程度夸大 | ⚠️ **轻微夸大**。反方标注"致命"，但实际影响有限：`train_single` 第 306-309 行有 WARN 打印（`n_params < 200_000` 时打印警告），所以用户运行时会看到警告。审计断言的虚假安全感是真实的，但不是完全无提示。降级为**严重**更准确。 |

**裁决**：**成立**（严重程度从致命降级为严重）

**修补方案**：
```python
# 用实际 args.n_filters 审计
audit_model = build_inceptiontime_lite(in_channels=12, d_model=args.d_model, n_filters=args.n_filters)
audit = audit_model.count_parameters()
# ...
full_model = build_model(
    num_classes=5, n_filters=args.n_filters,
    use_checkpoint=args.use_checkpoint, d_model=args.d_model, dropout=0.1,
)
full_params = sum(p.numel() for p in full_model.parameters())
assert 200_000 <= full_params <= 500_000, \
    f"参数量 {full_params:,} 不在目标 200K-500K 内！"
```

---

## 2. 严重攻击裁决（SEVERE）

### S1：OOM Level 1（n_filters=32）产生 147K 参数，违反 [200K, 500K] 约束

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。n_filters=32 时参数量 ~147K < 200K 下界，数学计算正确。 |
| 稻草人论证 | ❌ 无。反方准确引用了参数量推导。 |
| 误解前提 | ⚠️ **部分误解**。反方将 OOM 备选 Level 1 与主实验的公平对比要求混为一谈。OOM 备选的本质是"退路"——当默认配置 OOM 时，优先目标是"能跑"而非"公平对比"。R5 方案 §3.2 E5 的诚实声明已说"超参变体弱于新架构家族"。 |
| 攻击逻辑自洽 | ✅ 自洽。参数量违规的数学推导正确。 |
| 严重程度夸大 | ⚠️ **夸大**。反方标注"严重"，但 OOM 备选是退路不是主实验。如果默认配置不 OOM（RTX 5060 8GB 对 315K 模型可能足够），Level 1 永远不触发。真正的问题是文档没有诚实声明 Level 1 备选的参数量不在公平对比区间内，而非实验本身无效。降级为**中等**更准确。 |

**裁决**：**部分成立**（严重程度从严重降级为中等）

**修正后的实际影响**：文档矛盾确实存在（第 24 行说"在 200K-500K 目标内"，第 28 行说"降至 ~136K"但未声明违规），应在文档中诚实声明 Level 1 备选的参数量不在公平对比区间内。但这不影响主实验（n_filters=48）的有效性。

**修补方案**：
```python
# 在 inceptiontime_lite.py 第 28 行补充诚实声明
# Level 1: n_filters 64→48→32（本文件默认 48；若 OOM 改 32，参数量降至 ~136K）
# ⚠️ 注意：n_filters=32 时参数量 ~147K < 200K 下界，不在公平对比区间内。
#    Level 1 是 OOM 退路，产生的模型不参与架构公平对比，需在论文中诚实声明。
```

---

### S2：OOM Level 3 的 ResNet1D 变体是死代码——depth/width 参数被忽略

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。独立验证：`build_model` 第 240-241 行计算了 `block_layers_map` 和 `block_layers`，但第 243-247 行构造 `ECGClassifier` 时未传入 `block_layers`。`ECGClassifier` → `build_backbone("resnet1d", ...)` → `ECGResNet1D(in_channels, d_model, dropout)` 使用默认 `block_layers=(2,2,2,2)`。3 个 Level 3 变体确实产生相同的默认 ResNet1D。 |
| 稻草人论证 | ❌ 无。反方准确引用了 `block_layers` 的计算和未使用。 |
| 误解前提 | ❌ 无。 |
| 攻击逻辑自洽 | ✅ 自洽。 |
| 严重程度夸大 | ❌ 未夸大。Level 3 备选声称有 3 个不同变体但实际产生相同模型，这是真实的死代码。 |

**裁决**：**成立**

**修补方案**：
```python
# 方案 A：将 block_layers 和 width 传入 ResNet1D 构造
if arch_override == "resnet1d":
    from src.models.baselines import ECGResNet1D
    block_layers_map = {3: (1, 1, 1), 5: (2, 2, 1), 7: (2, 2, 2, 1)}
    block_layers = block_layers_map.get(depth, (2, 2, 2, 2))
    # 直接构造 ResNet1D backbone
    backbone = ECGResNet1D(
        in_channels=12, d_model=width or d_model,
        block_layers=block_layers, dropout=dropout,
    )
    # 包装成 ECGClassifier（需支持外部 backbone 注入）
    model = ECGClassifier(...)
    model.backbone = backbone
    return model

# 方案 B：删除 Level 3 备选（如果 ResNet1D 变体不是关键需求）
```

---

### S3：gradient checkpointing 与 BatchNorm 不兼容——running stats 被双重更新

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ⚠️ **部分成立**。`InceptionBlockLite.forward` 第 101-105 行确实在 `self.training` 时用 `checkpoint(self._forward_impl, x, use_reentrant=False)`，`_forward_impl` 包含 `self.bn(out)`。gradient checkpointing 确实会在反向传播时重新执行 `_forward_impl`，导致 BN running stats 被更新两次。这是 PyTorch 的已知行为。 |
| 稻草人论证 | ❌ 无。反方准确描述了 checkpoint 机制。 |
| 误解前提 | ❌ 无。 |
| 攻击逻辑自洽 | ✅ 自洽。 |
| 严重程度夸大 | ⚠️ **夸大**。反方说"BN running stats 累积了 100 epochs 的更新量"、"迁移性能异常"——这有些夸大。BN running stats 是 momentum=0.1 的 EMA，双重更新会让 stats 收敛到略不同的值（等效于 momentum≈0.19），但不会"污染"到完全错误，也不会导致"迁移性能异常"。实际影响是轻微的校准偏差，不是"性能异常"。降级为**中等**更准确。 |

**裁决**：**部分成立**（严重程度从严重降级为中等）

**修正后的实际影响**：BN running stats 会有轻微偏差（等效 momentum 略大），可能轻微影响校准评估，但不会导致"异常"或"不可信"。不过这确实是一个应该修复的 bug。

**修补方案**：
```python
# 方案 A：gradient checkpointing 时冻结 BN running stats 更新
def _forward_impl(self, x: torch.Tensor) -> torch.Tensor:
    z = x
    if self.bottleneck is not None:
        z = self.bottleneck(x)
    branches = [conv(z) for conv in self.convs]
    branches.append(self.pool(self.maxpool(z)))
    out = torch.cat(branches, dim=1)
    if self.use_bn:
        if self.use_checkpoint and self.training:
            # checkpoint 模式下冻结 BN running stats 更新
            with torch.no_grad():
                out = self.bn(out)
        else:
            out = self.bn(out)
    return self.activation(out)

# 方案 B：用 GroupNorm/LayerNorm 替代 BN（不受 checkpoint 影响）
# 方案 C：checkpoint 时用 functional BN 手动控制 running stats 更新
```

---

### S4：架构家族独立性 claim 自相矛盾——inceptiontime_lite.py 与 R5 方案矛盾

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。`inceptiontime_lite.py` 第 12-17 行说"三者在特征提取机制上正交"（独立家族论证），R5 方案 §3.2 E5 第 383-385 行说"不是独立的架构家族"（超参变体）。两者确实矛盾。 |
| 稻草人论证 | ❌ 无。反方准确引用了双方原文。 |
| 误解前提 | ❌ 无。 |
| 攻击逻辑自洽 | ✅ 自洽。"代码说 A，方案说 ¬A，两者不能同时为真"的推理完整。 |
| 严重程度夸大 | ❌ 未夸大。代码注释与方案文档的直接矛盾确实是严重问题。 |

**裁决**：**成立**

**修补方案**：建议以 R5 方案为准（超参变体），修改 `inceptiontime_lite.py` 注释：
```python
# 架构家族定位（与 R5 方案 §3.2 E5 一致）：
#   InceptionTime-Lite 是 InceptionTime 的超参变体（减少 Inception module 数量），
#   不是独立的架构家族。本研究的架构稳健性声称基于：
#   - 架构家族 1：InceptionTime (4 blocks, ~192K 参数)
#   - 架构家族 2：ResNet1D-Wide (不同 depth/width)
#   - 超参变体：InceptionTime-Lite (3 blocks, ~315K 参数)
#   3 blocks vs 4 blocks 是深度选择，保留 InceptionTime 的归纳偏置
#   （多尺度并行卷积 + bottleneck + maxpool 旁路）。
```

---

### S5："Lite" 命名误导——InceptionTime-Lite (315K) 比原版 InceptionTime (192K) 参数更多

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。InceptionTime-Lite (n_filters=48, 3 blocks) ≈ 315K，原版 InceptionTime (n_filters=32, 4 blocks) ≈ 192K。315K > 192K，"Lite" 暗示更轻量但实际更重。 |
| 稻草人论证 | ❌ 无。参数量对比正确。 |
| 误解前提 | ⚠️ **部分误解**。"Lite" 在这里的语义是"深度简化"（3 blocks vs 4 blocks），不是"参数量更少"。反方将"Lite"等同于"参数量更少"是一种语义假设。 |
| 攻击逻辑自洽 | ✅ 自洽。n_filters 32→48 增加 2.25 倍，blocks 4→3 减少 0.75 倍，净增加 1.69 倍。 |
| 严重程度夸大 | ⚠️ **夸大**。反方说"审稿人可能质疑命名的诚实性"——这取决于论文如何描述。如果论文明确报告参数量（315K vs 192K），命名误导的影响有限。"Lite" 在深度学习文献中常指"深度简化"而非严格"参数量更少"（如 MobileNetLite、ResNetLite 等）。降级为**中等**更准确。 |

**裁决**：**部分成立**（严重程度从严重降级为中等）

**修补方案**：
```python
# 方案 A：在论文中明确报告参数量，消除命名歧义
# "InceptionTime-Lite (3 blocks, 315K params) vs InceptionTime (4 blocks, 192K params)"
# 方案 B：改名为 InceptionTime-Shallow（强调深度简化而非轻量）
# 方案 C：调整 n_filters=32 使参数量真正低于原版（但会触发 S1 的 147K 违规）
```

---

### S6："3 vs 6 blocks" 对比是虚假的——代码库原版 InceptionTime 默认 4 blocks

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ⚠️ **部分成立**。`baselines.py` 第 188 行确认 `ECGInceptionTime` 默认 `n_blocks=4`。`inceptiontime_lite.py` 第 5 行说"原始 InceptionTime 6 个"（指论文原文），第 117 行说"vs 原始 4，vs InceptionTime 原文 6"（同时标注代码库 4 和论文 6）。 |
| 稻草人论证 | ⚠️ **部分稻草人**。反方说"E5 声称'3 vs 6 blocks 是深度选择'时，实际对比是'3 vs 4 blocks'"——但第 117 行已经诚实标注了"vs 原始 4"（代码库默认）。反方忽略了第 117 行的双重标注，只引用第 5 行。 |
| 误解前提 | ⚠️ **部分误解**。第 5 行的"原始 InceptionTime 6 个"是指 InceptionTime **论文**（Ismail Fawaz 2020）的配置，这是正确的——论文原文确实用 6 blocks。代码库的 `ECGInceptionTime` 默认 4 blocks 是代码库的选择，不是论文原文。 |
| 攻击逻辑自洽 | ⚠️ **部分断链**。反方说"3 vs 4 的深度减少只有 25%，远不如 3 vs 6 的 50% 显著"——但这是两个不同的对比基线（代码库 vs 论文原文），E5 实验的对比基线是代码库中的 `ECGInceptionTime`（4 blocks），第 117 行已诚实标注。 |
| 严重程度夸大 | ⚠️ **夸大**。第 117 行已诚实标注"vs 原始 4，vs InceptionTime 原文 6"，反方忽略了这个标注。降级为**轻微**更准确。 |

**裁决**：**部分成立**（严重程度从严重降级为轻微）

**修正后的实际影响**：第 117 行已诚实标注了代码库默认 4 blocks 和论文原文 6 blocks 的双重对比。第 5 行的"原始 InceptionTime 6 个"是指论文原文，这是正确的。反方略夸大了这个问题——代码注释并非只说"3 vs 6"，而是同时标注了"3 vs 4"和"3 vs 6"。

**修补方案**：将第 5 行的"原始 InceptionTime 6 个"改为"原始 InceptionTime 论文 6 个（代码库默认 4 个）"，消除歧义。

---

## 3. 中等攻击裁决（MODERATE）

### M1：冒烟测试不减少 seeds/datasets——docstring 与代码矛盾

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。第 46 行 docstring 说"1 种子"，第 534-541 行代码保留全部种子。 |
| 稻草人论证 | ❌ 无。 |
| 误解前提 | ❌ 无。反方注意到第 535 行注释诚实说明了实际行为。 |
| 攻击逻辑自洽 | ✅ 自洽。 |
| 严重程度夸大 | ❌ 未夸大。反方标注"中等"并指出"代码注释诚实说明了这一行为，只是 docstring 误导"，评估准确。 |

**裁决**：**成立**

**修补方案**：修复 docstring：
```python
# 冒烟测试（合成数据，2 epoch，默认保留全部种子/数据集）
# 如需快速冒烟可显式传 --seeds 42 --datasets ptbxl
python scripts/run_e5_inception_lite.py --smoke --seeds 42 --datasets ptbxl
```

---

### M2：kernel 23 覆盖 230ms 的 claim 依赖隐含的 100Hz 采样率假设

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ⚠️ **取决于实际采样率**。230ms = 23/100Hz 确实假设 100Hz。但 PTB-XL 有 100Hz 和 500Hz 两个版本，CPSC2018 通常是 500Hz。如果项目使用 PTB-XL 100Hz 版本，则假设成立。 |
| 稻草人论证 | ❌ 无。反方准确指出了隐含假设。 |
| 误解前提 | ⚠️ **部分误解**。反方说"PTB-XL 常用 500Hz"——但 PTB-XL 的标准版本是 100Hz（500Hz 是高分辨率版本）。许多 ECG 研究使用 100Hz 版本。 |
| 攻击逻辑自洽 | ✅ 自洽。 |
| 严重程度夸大 | ⚠️ **取决于采样率**。如果项目用 100Hz，攻击不成立；如果用 500Hz，攻击成立。 |

**裁决**：**部分成立**（需进一步验证实际采样率）

**修补方案**：在脚本中显式声明采样率假设，或从数据元数据中读取采样率：
```python
# 在 docstring 中声明
# 采样率假设：PTB-XL 100Hz, Chapman 100Hz, CPSC 500Hz（需从数据元数据验证）
# kernel 23 在 100Hz 下覆盖 230ms，在 500Hz 下覆盖 46ms
```

---

### M3：3 blocks 的感受野计算被忽略——实际 RF 可能不足以覆盖完整心电周期

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ⚠️ **取决于采样率**。3 blocks RF = 3×23 - 2 = 67。100Hz: 670ms（够），500Hz: 134ms（可能不够）。同 M2。 |
| 稻草人论证 | ❌ 无。RF 计算正确。 |
| 误解前提 | ❌ 无。 |
| 攻击逻辑自洽 | ✅ 自洽。 |
| 严重程度夸大 | ⚠️ **取决于采样率**。 |

**裁决**：**部分成立**（同 M2，需验证采样率）

**修补方案**：同 M2。如果采样率是 500Hz，可考虑增加 kernel size 或 blocks 数。

---

### M4：跨类数迁移的 logits 维度不匹配——5 类模型 → 4 类目标域语义错误

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。5 类源模型输出 5 维 logits，4 类目标域标签值域 [0, 3]。`argmax` 可能输出 4（不存在的类），被计为错误，人为压低准确率。 |
| 稻草人论证 | ❌ 无。 |
| 误解前提 | ❌ 无。 |
| 攻击逻辑自洽 | ✅ 自洽。 |
| 严重程度夸大 | ❌ 未夸大。反方标注"中等"并指出"10 个涉及类数不匹配"，评估准确。 |

**裁决**：**成立**

**修补方案**：同 F2 的修补方案——截断 logits 到 min 类数，或重映射类标签。

---

### M5：`try_train_with_oom_fallback` 的 Level 1 报告逻辑错误

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。第 183 行条件 `level > 0 or params["n_filters"] != 48`，第一个条目 `(1, {"n_filters": 48, ...})` 的条件 = `True or False` = `True`，会对原始配置打印 "Level 1 触发"。 |
| 稻草人论证 | ❌ 无。 |
| 误解前提 | ❌ 无。 |
| 攻击逻辑自洽 | ✅ 自洽。 |
| 严重程度夸大 | ⚠️ **夸大**。反方标注"中等"，但此函数是死代码（F1 已确认），实际影响为零。反方自己也说"虽然此函数是死代码（F1），但逻辑错误本身存在"——如果未来有人接线此函数才会出问题。降级为**轻微**更准确。 |

**裁决**：**部分成立**（严重程度从中等降级为轻微，因为死代码中的逻辑错误实际影响为零）

**修补方案**：修复条件逻辑（如果接线此函数）：
```python
# 只对非原始配置报告 OOM 备选
is_original = (params["n_filters"] == 48 and not params.get("use_checkpoint", False))
if not is_original:
    report_oom_level(level, desc)
```

---

## 4. 轻微攻击裁决（MINOR）

### m1：`n_layers=3` 在 `build_model` 中被忽略

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。`build_model` 第 251 行传 `n_layers=3`，但 `build_backbone` 对 "inceptiontime_lite" 调用 `build_inceptiontime_lite(in_channels, d_model, dropout)` 忽略 `n_layers`。`ECGInceptionTimeLite.__init__` 硬编码 `n_blocks=3`（有 assert）。 |
| 稻草人论证 | ❌ 无。 |
| 误解前提 | ❌ 无。 |
| 攻击逻辑自洽 | ✅ 自洽。 |
| 严重程度夸大 | ❌ 未夸大。反方标注"轻微"准确。 |

**裁决**：**成立**

**修补方案**：删除 `n_layers=3` 或注释说明它是 no-op（`n_blocks` 在 `ECGInceptionTimeLite` 中硬编码）。

---

### m2：双重 dropout——backbone 和 head 各一层

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。`ECGClassifier` 第 66 行传 `dropout=0.1` 给 `build_backbone`（backbone 末尾有 `nn.Dropout(0.1)`），第 75 行 `nn.Dropout(dropout)` 在 classifier head。两处 dropout 叠加。 |
| 稻草人论证 | ❌ 无。 |
| 误解前提 | ⚠️ **轻微误解**。反方说"实际 dropout 率高于 0.1"——但两处 dropout 的叠加效果不是简单相加（0.1+0.1=0.2），而是 `(1 - (1-0.1)×(1-0.1)) = 0.19`，略低于 0.2。 |
| 攻击逻辑自洽 | ✅ 自洽。 |
| 严重程度夸大 | ❌ 未夸大。反方标注"轻微"准确。 |

**裁决**：**成立**

**修补方案**：删除 backbone 末尾的 dropout（或设为 0），只保留 head 的 dropout。

---

### m3：`count_parameters` 方法不包含 head 参数

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ✅ **成立**。`ECGInceptionTimeLite.count_parameters` 只审计 backbone 参数，不含 head。脚本第 567-568 行单独计算 `full_params` 补充了 head。 |
| 稻草人论证 | ❌ 无。 |
| 误解前提 | ❌ 无。反方注意到脚本补充了 head 参数。 |
| 攻击逻辑自洽 | ✅ 自洽。 |
| 严重程度夸大 | ❌ 未夸大。 |

**裁决**：**成立**

**修补方案**：在 `count_parameters` 的 docstring 中明确说明"只含 backbone，不含 head"。

---

### m4：`baselines.py` 的 `__all__` 在 import 之后定义

**5 维度审查**：

| 维度 | 评估 |
|------|------|
| 反例成立性 | ❌ **不成立**。反方声称"`ECGInceptionTimeLite` 不在 `__all__` 中"，但**独立验证**`baselines.py` 第 249-254 行：`__all__ = ["ECGResNet1D", "ECGInceptionTime", "build_backbone", "ECGInceptionTimeLite"]`——`ECGInceptionTimeLite` **明确在** `__all__` 中（第 253 行）。反方的事实声称是错误的。 |
| 稻草人论证 | ✅ **稻草人**。反方攻击的是一个不存在的问题——`ECGInceptionTimeLite` 已在 `__all__` 中，`from baselines import *` 会正常导入。 |
| 误解前提 | ✅ **误解**。反方可能只看了第 257 行的 `from .inceptiontime_lite import ECGInceptionTimeLite` 而忽略了第 253 行的 `__all__` 已包含此项。 |
| 攻击逻辑自洽 | ❌ **不自洽**。反方说"`__all__` 应列出所有公开符号"——`__all__` 确实列出了 `ECGInceptionTimeLite`，反方的核心声称与事实矛盾。 |
| 严重程度夸大 | N/A（攻击本身不成立）。 |

**裁决**：**驳回**（反方事实错误）

**反驳理由**：
1. `baselines.py` 第 253 行明确将 `"ECGInceptionTimeLite"` 列入 `__all__`
2. `from baselines import *` 会正常导入 `ECGInceptionTimeLite`
3. 反方声称"`ECGInceptionTimeLite` 不在 `__all__` 中"是直接的事实错误
4. 虽然第 257 行的 import 在 `__all__` 定义之后，但这不影响功能——Python 的 `from module import *` 根据 `__all__` 列表导出，与 import 语句的位置无关（只要在 `from module import *` 执行前已定义即可）

---

## 5. 对 R5 方案 P2-8 修补的裁决

反方在 §7 对 P2-8 修补的裁决表：

| P2-8 声称 | 反方裁决 | 元审查裁决 |
|----------|---------|-----------|
| Level 1: n_filters 64→32 | 部分实现，参数违规 | **部分成立**：参数违规真实（S1），但反方忽略 R5 方案原文是"64→32"而代码默认已是 48，实际是"48→32"。这是 R5 方案与代码的配置不一致，但 Level 1 机制本身已实现。 |
| Level 2: gradient checkpointing | 实现了，但与 BN 不兼容 | **部分成立**：BN 双重更新真实（S3），但影响被夸大（不会"污染"或"异常"）。 |
| Level 3: ResNet1D depth 3/5/7, width 32/64/128 | 未实现 | **成立**：block_layers 被忽略（S2），3 个变体产生相同模型。 |
| Level 4: 诚实报告 | 实现了 | **成立**：main 的 except 块确实实现了 Level 4。 |
| 4 级自动降级链 | 未实现 | **成立**：try_train_with_oom_fallback 是死代码（F1）。 |

**元审查总结**：反方对 P2-8 的裁决基本准确，但 Level 1 和 Level 2 的影响被轻微夸大。P2-8 修补在代码层面确实未真正解决 N7 攻击——4 级备选链只有 Level 4 实际工作，Level 1-3 全部失效。这一核心结论成立。

---

## 6. 对 E5 实验可行性的裁决

### 6.1 当前代码能否完成 E5 实验？

**反方裁决**：不能（F2 崩溃 + F1 死代码 + F3 虚假审计）

**元审查裁决**：**部分成立**

- **F2（2/6 迁移方向崩溃）**：**成立**。10/30 迁移实验会因 IndexError 崩溃，CSV 输出不完整。这是真实的致命问题。
- **F1（OOM 备选链死代码）**：**成立但条件性**。只有当默认配置 OOM 时才会触发问题。如果 RTX 5060 8GB 能容纳 315K 模型（batch_size=16, seq_len=1000），则 F1 不影响实际运行。但作为代码质量问题，死代码确实存在。
- **F3（审计虚假通过）**：**成立但条件性**。只有当用户手动传 `--n-filters 32` 时才会触发。默认配置下审计正确。但 `train_single` 有 WARN 打印，不是完全无提示。

**结论**：如果默认配置不 OOM 且用户不手动改 n_filters，E5 实验可以完成 15 训练 + 20 迁移（6 方向中 4 个不崩溃），但 10/30 迁移实验会崩溃（F2）。**F2 是必须修复的致命 bug**，F1 和 F3 是应该修复的严重问题。

### 6.2 冒烟测试能否通过？

**反方裁决**：可能通过，但不保证完整实验也能通过

**元审查裁决**：**成立**。反方分析准确：
- 冒烟测试默认运行全部 5 种子 × 3 数据集（M1）
- 如果只测 ptbxl（5 类），不会触发 F2
- 2 epochs 不足以发现 S3 的 BN stats 问题
- 冒烟测试不测迁移评估（如果数据不存在），不会发现 F2

---

## 7. 修复优先级排序（元审查版本）

| 优先级 | 修复 | 对应攻击 | 反方优先级 | 元审查调整 |
|--------|------|---------|-----------|-----------|
| **P0** | 修复 F2：跨类数迁移的 logits 对齐 | F2, M4 | P0 | 一致 |
| **P0** | 修复 F1：将 `try_train_with_oom_fallback` 接线到 main 或删除 | F1 | P0 | 一致 |
| **P1** | 修复 F3：参数审计用实际 `args.n_filters` | F3 | P0 | 降为 P1（有 WARN 提示） |
| **P1** | 修复 S2：将 `block_layers` 传入 ResNet1D 构造 | S2 | P1 | 一致 |
| **P1** | 修复 S4：统一代码注释与 R5 方案的架构家族说法 | S4 | P1 | 一致 |
| **P2** | 修复 S1：文档声明 Level 1 参数量不在公平对比区间 | S1 | P1 | 降为 P2（OOM 退路非主实验） |
| **P2** | 修复 S3：gradient checkpointing 时冻结 BN running stats | S3 | P1 | 降为 P2（影响被夸大） |
| **P2** | 修复 M1：冒烟测试 docstring | M1 | P2 | 一致 |
| **P2** | 修复 M2/M3：声明采样率假设 | M2, M3 | P2 | 一致 |
| **P3** | 修复 S5：论文明确报告参数量或改名 | S5 | P1 | 降为 P3（命名歧义影响有限） |
| **P3** | 修复 S6：第 5 行补充"代码库默认 4" | S6 | P2 | 降为 P3（第 117 行已标注） |
| **P3** | 修复 m1/m2/m3：代码可读性 | m1, m2, m3 | P3 | 一致 |
| **P3** | 修复 M5：死代码中的逻辑错误（如果接线） | M5 | P2 | 降为 P3（死代码） |
| **驳回** | m4：无需修复（反方事实错误） | m4 | P3 | 驳回 |

---

## 8. 对反方攻击质量的元评估

### 8.1 反方攻击的优点

1. **代码行号准确**：反方引用的代码行号经独立验证全部正确
2. **反例构造严谨**：F2 的 6 方向崩溃分析表、S1 的参数量计算、S2 的 block_layers 追踪都经独立验证成立
3. **攻击维度全覆盖**：7 个攻击维度（反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移）均有覆盖
4. **诚实原则**：反方在 M1 中主动指出"代码注释诚实说明了这一行为"，在 M5 中主动指出"虽然此函数是死代码"，体现了审查的诚实性
5. **深层问题挖掘**：F2 不仅指出 IndexError，还指出跨类数迁移的语义问题（M4），体现了深度

### 8.2 反方攻击的不足

1. **m4 事实错误**：声称 `ECGInceptionTimeLite` 不在 `__all__` 中，但实际在第 253 行明确列出。这是直接的事实错误，应驳回。
2. **S6 忽略双重标注**：第 117 行已诚实标注"vs 原始 4，vs InceptionTime 原文 6"，反方只引用第 5 行，忽略了第 117 行的双重标注。
3. **S1/S3 严重性夸大**：S1 的 OOM 备选是退路非主实验，S3 的 BN 双重更新不会导致"污染"或"异常"。
4. **M2/M3 未验证采样率**：反方假设 500Hz 但未验证项目实际使用的采样率。PTB-XL 有 100Hz 版本。
5. **S5 语义假设**："Lite" 等同于"参数量更少"是一种语义假设，在深度学习文献中"Lite"常指"深度简化"。

### 8.3 反方攻击的整体质量评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 事实准确性 | 8/10 | m4 事实错误，其余准确 |
| 逻辑严谨性 | 9/10 | 推理链条完整，无重大断链 |
| 严重性校准 | 7/10 | S1/S3/S5/S6/M5 有一定程度夸大 |
| 攻击覆盖度 | 10/10 | 7 维度全覆盖，18 个攻击点 |
| 诚实性 | 9/10 | 主动指出代码注释的诚实说明 |
| **综合** | **8.4/10** | **高质量攻击报告，核心攻击成立** |

---

## 9. 结论

### 9.1 裁决汇总

反方攻击报告质量**较高**，18 个攻击点中：
- **10 个完全成立**（F1, F2, F3, S2, S4, M1, M4, m1, m2, m3）
- **7 个部分成立**（S1, S3, S5, S6, M2, M3, M5）——攻击有道理但严重程度被夸大或取决于未验证假设
- **1 个驳回**（m4）——反方事实错误

### 9.2 对正方的建议

**必须修复（P0）**：
1. **F2**：跨类数迁移的 IndexError——10/30 迁移实验会崩溃，这是最紧急的 bug
2. **F1**：OOM 备选链死代码——接线到 main 或删除并诚实声明

**应该修复（P1）**：
3. **F3**：参数审计用实际 `args.n_filters`
4. **S2**：将 `block_layers` 传入 ResNet1D 构造
5. **S4**：统一代码注释与 R5 方案的架构家族说法

**建议修复（P2-P3）**：其余部分成立的攻击按优先级逐步修复

### 9.3 对反方的反馈

反方攻击报告整体质量高，核心攻击（F1/F2/F3）均经独立验证成立，未使用稻草人论证。但在以下方面可改进：
1. **m4 事实错误**：`ECGInceptionTimeLite` 已在 `__all__` 中（第 253 行），应驳回
2. **S6 忽略双重标注**：第 117 行已诚实标注"vs 原始 4"，不应只引用第 5 行
3. **S1/S3 严重性夸大**：OOM 备选是退路非主实验，BN 双重更新不会导致"异常"
4. **M2/M3 未验证采样率**：应先确认项目实际使用的采样率再下结论

### 9.4 对 R5 方案的影响

- **P2-8 修补（OOM 备选方案）**：在代码层面**未真正解决 N7 攻击**——4 级备选链只有 Level 4 实际工作。这一反方核心结论**成立**。
- **E5 实验可行性**：当前代码**无法正确完成完整 E5 实验**（F2 导致 10/30 迁移崩溃）。这一反方核心结论**成立**。
- **架构家族 claim**：代码注释与方案文档的矛盾（S4）**成立**，需统一说法。

**正方需在 E5 实验执行前至少修复 F1+F2**，否则实验结果不可信。F3+S2+S4 应在论文撰写前修复。

---

**裁决报告结束。**

反反方元审查者-E5 已对 18 个攻击点逐条执行 5 维度审查，裁决 10 个成立、7 个部分成立、1 个驳回。反方攻击报告整体质量高（8.4/10），核心致命攻击均成立，但在 m4 上有事实错误，在 S1/S3/S5/S6/M5 上有严重性夸大。
