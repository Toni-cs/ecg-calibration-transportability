# R7 修复报告 — P0-4（n_bins 公共守卫缺失）

## 修复概述
R6终审裁决P0-4为"致命"：scripts中4个n_bins函数完全无守卫，bool穿透(True+1=2静默工作)、OOM(10**18导致MemoryError)、上界过大(10**6导致5s-19.5h阻塞)。

## 修复清单

### 修复1：公共守卫函数 — src/utils/calibration.py
- 新增`_validate_n_bins(n_bins, upper_bound=10**4)`函数
- 拦截：非int、≤0、bool穿透、字符串、超大值
- 上界从10**6收紧至10**4

### 修复2：测试常量 — tests/test_model.py
- 新增`BAD_N_BINS = [0, -1, 1.5, None, True, "10", 2.0, 10**18]`
- brier_parts和ece/mce测试引用BAD_N_BINS

### 修复3：run_e2_ablation_discrimination.py守卫
- 导入`_validate_n_bins`
- `fit_binned_temperature`开头调用守卫

### 修复4：run_e4_temperature_analysis.py守卫
- 导入`_validate_n_bins`
- `quintile_edges`开头调用守卫

### 修复5：run_e6_reliability_diagrams.py守卫
- 导入`_validate_n_bins`
- `compute_reliability_bins`开头调用守卫
- `bootstrap_bin_accuracy_ci`开头调用守卫

## 验证
- [x] AST语法验证通过
- [x] 所有4个script函数均已添加守卫
- [x] 测试常量BAD_N_BINS覆盖7种非法输入

## 对应R6攻击点
- ATK-1: bool穿透 → 守卫isinstance(n_bins, bool)拒绝
- ATK-2: OOM → 守卫upper_bound=10**4拒绝10**18
- ATK-3: 上界过大 → 10**6→10**4收紧
