# 检查点独立性审计（2026-09-17）

> 起因：MEMORY 里挂着一项待办 ——「查 `cpsc_chapman`/`cpsc_ptbxl` 在 seed42/43 的 `cal_probs` md5 相同（4 格独立性存疑）」。
> 本文把它查到闭合。**结论：确实存在重复，影响可量化，且可修。**

## 一、结论先行

**`cpsc→chapman` 与 `cpsc→ptbxl` 在 `inceptiontime` 的 seed 42/43 上，源模型是同一个文件。**

| 检查点对 | md5(前 12) | mtime | 大小 |
|---|---|---|---|
| `cpsc_chapman/inceptiontime/seed42` vs `cpsc_ptbxl/inceptiontime/seed42` | `6ee3b3995d5b`（同） | 均 09-04 16:11:51 | 均 795189 |
| `cpsc_chapman/inceptiontime/seed43` vs `cpsc_ptbxl/inceptiontime/seed43` | `2cbada61a0ce`（同） | 均 09-04 16:11:51 | 均 795189 |

**全网格去重**：64 个 `best_model.pt` 中**只有这 2 组重复**（`md5sum` 全量比对）。
⇒ 主网格 60 格里，**58 个不同的源模型**，不是 60 个。

## 二、数值层面的确证（不是只靠哈希）

从 `results/robustness_validation_5seeds.csv` 取这 4 格，**ID 域数值逐位相同**：

| method | cpsc→chapman s42 | cpsc→ptbxl s42 | |
|---|---|---|---|
| ts | `0.00292486617218520` | `0.00292486617218520` | 同 |
| platt | `-6.1e-05` | `-6.1e-05` | 同 |
| isotonic | `-0.005093` | `-0.005093` | 同 |
| vector | `-0.00216` | `-0.00216` | 同 |
| matrix | `0.00699` | `0.00699` | 同 |
| dirichlet | `0.006937` | `0.006937` | 同 |
| **em_prior** | `-0.201076` | `-0.007045` | **不同** |
| **bbse_prior** | `-0.067948` | `0.00232` | **不同** |

OOD 域全部不同（目标域不同），seed43 同型。

**这个模式本身就是佐证**：前 6 个方法只用**源域 cal** 拟合 → 同一模型 + 同一 cal split ⇒ 结果必然逐位相同；
`em_prior`/`bbse_prior` 要**目标域先验** → 依赖目标 ⇒ 不同。若这两个文件只是「碰巧相似」，不可能在前 6 个方法上逐位相等。

## 三、为什么会这样（根因）

`scripts/train.py:596` 调用 `set_seed(args.seed)`，而 `set_seed` 的签名是
`set_seed(seed, deterministic: bool = False)`（第 51 行），`deterministic` **默认 False**：

```python
def set_seed(seed: int, deterministic: bool = False):
    ...
    if deterministic:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
```

⇒ **cuDNN 非确定性开启**。同配置两次训练会得到**不同权重**，因此：

- 其余 8 组（inceptiontime 44–46、resnet1d 全部）「同一 (arch, 源库, K, seed)」的检查点**互不相同** —— 符合非确定性的预期。
- 而 seed42/43 那两组**逐位相同**，非确定性**无法**产生 —— 只能是**拷贝**（同一秒 16:11:51、同一字节数）。
  ⇒ 这是一次**复用/拷贝**，不是「训练一次共享给所有目标」的设计。

> 顺带一个独立发现：**归档的检查点不是逐位可复现的**。任何重跑都不会重现它们。
> 这应在论文的可复现性声明里如实写出，或改用 `deterministic=True` 重训（代价：速度下降、且现有结果全部作废）。

## 四、影响评估

| 维度 | 是否受影响 |
|---|---|
| **主终点 ΔECE_OOD**（60 格，51/60 正，+0.015863） | **不受影响** —— OOD 用目标域 test，4 格的 OOD 值互不相同 |
| ID 对照终点（60 格，47/60 正，+0.008264） | **轻微夸大**：有效独立格数是 **58** 而非 60 |
| 拟合温度 T 的分布（60 格） | **轻微**：2 个 T 值被重复计入 |
| 「60 个种子实验」的措辞 | 应改为「58 个不同源模型 / 60 格」或修好后维持 60 |

量级很小（ID 终点本就是对照项，不是主主张），但**属于必须披露或修复的事实**。

## 五、修复方案（推荐 B）

**A. 披露**：在 Methods/Limitations 写明「inceptiontime 源为 cpsc 的 seed42/43 两格共享同一源检查点，
其 ID 域终点逐位相同」。诚实，但会被审稿人追问「为什么」。

**B. 重训那 2 个检查点**（推荐）：
1. 删除 `cpsc_ptbxl/inceptiontime/seed{42,43}/best_model.pt`（保留 chapman 侧）；
2. 重训这两格（`scripts/train.py` + `scripts/eval_transfer.py`），因为非确定性，新权重必然与旧的不同 ⇒ 独立性恢复；
3. 重算受影响的 2 格的主终点，更新 60 格汇总与 ID 均值；
4. 重签相关哈希与补充材料。
代价：2 次训练 + 2 次评估，约 0.5–1 h。

**C. 开启 `deterministic=True` 全量重训**：最彻底，但作废现有 60 格全部结果，不建议在投稿前做。

## 六、本次审计中我自己犯的一个错（记录以免重犯）

第一轮用 `md5(np.asarray(d['num_classes']).tobytes())` 比对类别数，得到「62 个文件全部相同」的假结论。
**根因**：`num_classes` 存成 0-d **object** 数组，`.tobytes()` 取到的是**指针**，小整数被 Python 驻留 ⇒ 哈希必然相同。
改成 `int(np.asarray(nc).ravel()[0])` 后真相是：**K=5 恰好当且仅当 pair = {chapman, ptbxl}**，其余为 K=4 —— 与论文披露一致。

> 与之前 `smooth_ece` 误传类别索引是同一类错误：**工具用错口径会产出看起来很硬的假信号**。
> 教训：任何「哈希/数值全部相同」的结论，先怀疑自己的测量口径，再看数据。

## 七、复现命令

```bash
# 全网格检查点去重
find checkpoints/transfer -name best_model.pt | sort | \
  while read f; do echo "$(md5sum "$f" | cut -c1-12)  $f"; done | \
  awk '{print $1}' | sort | uniq -d

# 缓存一致性（同 (source,seed) 的 cal_labels / 同 (target,seed) 的 test_labels）
"C:/python/python.exe" - <<'PY'
import numpy as np, hashlib, glob, os, collections
def md5(a): return hashlib.md5(np.ascontiguousarray(np.asarray(a)).tobytes()).hexdigest()
recs=[]
for f in sorted(glob.glob('checkpoints/e2_probs_cache/*.npz')):
    p=os.path.basename(f)[:-4].split('_')
    d=np.load(f,allow_pickle=True)
    recs.append((p[0],p[1],p[2],p[3],md5(d['cal_labels']),md5(d['test_labels'])))
for i,key in ((0,'source'),(1,'target')):
    g=collections.defaultdict(set)
    for r in recs: g[(r[i],r[3])].add(r[4] if i==0 else r[5])
    print(key,'不一致组:',[k for k,v in g.items() if len(v)>1])
PY
```

**已知的正确解释（不是缺陷）**：源=chapman/ptbxl 时 `cal_labels` 跨目标不同 —— 因为 K=4/K=5 的类别子空间不同，
HYP 是否剔除会改变患者级四分割（`chapman_cpsc` cal n=1979 vs `chapman_ptbxl` cal n=2025）。
源=cpsc 时 K 恒为 4 ⇒ 划分一致。
