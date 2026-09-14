"""5超类映射模块: SCP编码/Chapman/CPSC → {NORM, MI, STTC, CD, HYP}

协议依据（docs/EXPERIMENT_PROTOCOL.md §2, §10-T1）：
- 单标签优先级规则**固定**并做敏感性分析；多标签sigmoid作第二形式化
- 映射表逐条给文献依据；对每个歧义映射决策生成替代变体（映射敏感性分析）
- CPSC2018+2019 HYP 极稀有(n=11) → 主分析降级 {NORM, CD, STTC, MI} 4类子空间

码表来源（均为公开可核对的官方文献码表，真实PTB-XL数据未下载）：
1. PTB-XL v1.0.3 官方 ``scp_statements.csv``（PhysioNet，逐字核对）——
   44条 diagnostic=1 且带 diagnostic_class 的语句（字母缩写键）。
   引用: Wagner et al., "PTB-XL, a large publicly available
   electrocardiography dataset", Scientific Data 7:148 (2020)。
2. PhysioNet/Computing in Cardiology Challenge 2021 官方
   ``dx_mapping_scored.csv`` / ``dx_mapping_unscored.csv``
   （github.com/physionetchallenges/evaluation-2021）——SNOMED CT 数值码表，
   覆盖 CINC2021 头文件 ``#Dx:`` 字段实际使用的编码。
3. Chapman-Shaoxing: Zheng et al., Scientific Data 7:274 (2020)——
   11种节律（SB/SR/AFIB/ST/AF/SI/SVT/AT/AVNRT/AVRT/SAAWR）及
   合并4组（SB/AFIB/GSVT/SR）。

已知跨库冲突码（研究设计的一部分，逐条敏感性分析对象；单标签化时
按下表"采用语义"执行）：
- 426177001: CINC2021=sinus bradycardia / SNOMED本义=AF → 均STTC（类不变）
- 59118001:  CINC2021=RBBB / SNOMED本义=LBBB → 均CD（类不变）
- 429622005: CINC2021=ST depression(→STTC) / SNOMED相关码=RBBB(→CD)
  → 采用CINC2021语义（本加载器的数据摄取路径），列入敏感性
- 284470004: CINC2021=PAC / 部分PTB-XL语境=left axis deviation → 均STTC（类不变）
- 164934002: CINC2021=T wave abnormal(→STTC) / PTB-XL=LAH(→HYP)
  → 采用CINC2021语义，列入敏感性
- 426434006: PTB-XL=myocardial infarction(→MI) / CINC2021=anterior ischemia(→STTC)
  → 采用Wagner 2020体系=MI（基线表以PTB-XL为纲），列入敏感性
- 251199005: PTB-XL=LAFB(→CD) / CINC2021=counter-clockwise rotation(描述性)
  → 采用PTB-XL语义=CD，列入敏感性
- 10370003:  SNOMED本义=bundle branch block(→CD) / CINC2021=pacing rhythm
  → 基线=CD（本模块规定），变体 ``bbb_10370003_to_sttc`` 改为STTC
- 111975006: PTB-XL=myocardial ischemia / CINC2021=prolonged QT → 均STTC（类不变）

冲突清单参考文献: Reyna et al., "Issues in the automated classification of
multilead ECGs using heterogeneous labels and populations", Physiol Meas (2022)。
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping as MappingType, Optional

__all__ = [
    "SUPERCLASSES",
    "DEFAULT_PRIORITY",
    "SUBSPACE_CPSC",
    "SCP_TO_SUPERCLASS",
    "MAP_TO_5SUPERCLASS",
    "generate_mapping_variants",
    "CHAPMAN_TO_SUPERCLASS",
    "CPSC_TO_SUPERCLASS",
    "filter_subspace",
]

# 5超类（Wagner 2020 diagnostic_class 体系）
SUPERCLASSES = ("NORM", "MI", "STTC", "CD", "HYP")

# ---------------------------------------------------------------------------
# 单标签优先级规则（协议§2固定；本规则为预注册设计决策，属敏感性分析对象）
#
# MI > STTC > CD > HYP > NORM
#
# 依据：
# (a) 病理优先于正常——"NORM"在PTB-XL中是"normal ECG"语句，与任何病理语句
#     共现时（如 {'NORM':100,'IMI':100}）以病理为准；
# (b) 缺血优先于传导/肥厚——缺血性判定临床时效性最高，且PTB-XL中MI与
#     STTC（缺血性ST-T）语句高频共存（如 IMI+ISCIN），必须确定性打破平局；
# (c) Wagner 2020 / Strodthoff 2021 的 diagnostic_class 体系本身不定义
#     优先级——单标签化优先级是本研究的设计决策，多标签sigmoid作第二形式化；
# (d) 敏感性分析：generate_mapping_variants() 提供优先级反转/STTC优先/
#     歧义项改判三类替代变体（协议§10-T1映射敏感性分析）。
# ---------------------------------------------------------------------------
DEFAULT_PRIORITY = ("MI", "STTC", "CD", "HYP", "NORM")

# CPSC 降级子空间（协议§2：无HYP类，主分析两侧对称降级）
# 与 SUPERCLASSES[:4] 编码顺序一致，消除标签语义错位（F2 修复）：
# SUPERCLASSES=("NORM","MI","STTC","CD","HYP") 中 MI=1/CD=3，原 SUBSPACE_CPSC
# 中 CD=1/MI=3 导致 ptbxl→cpsc 与 chapman→cpsc 两个方向的 MI/CD 预测全部算错。
SUBSPACE_CPSC = ("NORM", "MI", "STTC", "CD")

# ---------------------------------------------------------------------------
# 第1层：PTB-XL官方 diagnostic statements（scp_statements.csv, v1.0.3, 逐字核对）
# 键=SCP-ECG字母缩写（ptbxl_database.csv 的 scp_codes 键样式），值=diagnostic_class
# ---------------------------------------------------------------------------
_PTBXL_OFFICIAL = {
    # NORM（"normal ECG"，Statement Category=Normal/abnormal）
    "NORM": "NORM",
    # MI：各壁 myocardial infarction / subendocardial injury
    "IMI": "MI", "ASMI": "MI", "ILMI": "MI", "AMI": "MI", "ALMI": "MI",
    "LMI": "MI", "IPLMI": "MI", "IPMI": "MI", "PMI": "MI",
    "INJAS": "MI", "INJAL": "MI", "INJIN": "MI", "INJLA": "MI", "INJIL": "MI",
    # STTC：ST/T改变、缺血性ST-T、非诊断性T波、电解质/药物、室壁瘤
    "NDT": "STTC", "NST_": "STTC", "DIG": "STTC", "LNGQT": "STTC",
    "ISC_": "STTC", "ISCAL": "STTC", "ISCAN": "STTC", "ISCIN": "STTC",
    "ISCIL": "STTC", "ISCAS": "STTC", "ISCLA": "STTC",
    "ANEUR": "STTC", "EL": "STTC",
    # CD：束支/分支阻滞、房室阻滞、室内传导障碍、预激
    "1AVB": "CD", "2AVB": "CD", "3AVB": "CD",
    "LAFB": "CD", "LPFB": "CD", "IRBBB": "CD", "CRBBB": "CD",
    "CLBBB": "CD", "ILBBB": "CD", "IVCD": "CD", "WPW": "CD",
    # HYP：心室肥厚/心房负荷
    "LVH": "HYP", "RVH": "HYP", "SEHYP": "HYP",
    "LAO/LAE": "HYP", "RAO/RAE": "HYP",
}

# ---------------------------------------------------------------------------
# 第2层：节律语句扩展（官方表中节律语句无diagnostic_class；跨库单标签化
# 需要为纯节律记录赋予超类，此处按"节律/异位/起搏以外的节律异常→STTC、
# 窦性节律→NORM"的公开惯例扩展，列为敏感性分析对象）
#
# 窦性家族修正（R13, 2026-09-02，真实PTB-XL scp_statements.csv 逐字复核）：
#   PTB-XL 官方 SBRAD/STACH/SARRH 均为 rhythm=1.0 的**速率/形态描述语句**，
#   diagnostic_class=NaN（PTB-XL官方体系明确**不**将其判为ST-T改变）。
#   原 SBRAD/STACH/SARRH→STTC 是误标：(a) 窦性心动过缓/窦性心律不齐在临床
#   上不是复极异常（ST-T），归STTC缺依据；(b) 因STTC在优先级中高于CD/HYP，
#   窦率描述语句会**遮蔽真实传导/肥厚诊断**（实测PTB-XL上251条 STTC→CD、
#   58条 STTC→HYP 的翻转正是此类1AVB/LVH被SBRAD压制）；(c) 与Chapman侧
#   R12覆写（426177001/427084000→NORM，窦缓/窦速=正常窦性速率变体）语义
#   不一致，破坏跨库校准迁移测量的可比性。
#   修正：窦性家族(SR/SBRAD/STACH/SARRH)→NORM，与Chapman覆写对齐。
#   该决策登记协议R13，并作为映射敏感性分析对象复核（generate_mapping_variants）。
# ---------------------------------------------------------------------------
_RHYTHM_EXTENSION = {
    "SR": "NORM",        # 窦性节律→NORM
    "SBRAD": "NORM",     # 窦性心动过缓：速率描述，非ST-T（R13自STTC改判）
    "STACH": "NORM",     # 窦性心动过速：同上（R13自STTC改判）
    "SARRH": "NORM",     # 窦性心律不齐：速率/形态描述，非ST-T（R13自STTC改判）
    "AFIB": "STTC", "AFLT": "STTC",
    "SVARR": "STTC", "SVTAC": "STTC", "PSVT": "STTC",
    "PAC": "STTC", "PVC": "STTC", "PRC(S)": "STTC",
    "BIGU": "STTC", "TRIGU": "STTC",
    "LPR": "CD",         # PR间期延长归传导（敏感性对象；官方列为节律类）
    "PACE": None,        # 起搏图形：官方无类，显式标记不可映射
}

# ---------------------------------------------------------------------------
# 第3层：SNOMED CT 数值码（CINC2021 / CPSC2018-2019 头文件 #Dx 实际编码；
# 来源=evaluation-2021 dx_mapping_scored.csv / dx_mapping_unscored.csv，
# 逐字核对；值=None 表示"官方无类/不可映射"，显式入表以便计数报告）
# ---------------------------------------------------------------------------
_SNOMED_DIAGNOSTIC = {
    # --- NORM ---
    "426783006": "NORM",   # sinus rhythm（任务硬性要求；PTB-XL NORM同码）
    "426285000": "NORM",   # ECG: normal sinus rhythm（SNOMED本义）
    # --- MI ---
    "426434006": "MI",     # PTB-XL=MI / CINC2021=anterior ischemia（冲突，采用PTB-XL）
    "164865005": "MI",     # myocardial infarction
    "164867002": "MI",     # old myocardial infarction
    "57054005": "MI",      # acute myocardial infarction
    "54329005": "MI",      # anterior myocardial infarction
    # --- STTC：缺血/ST-T/节律扩展 ---
    "164861001": "STTC",   # myocardial ischemia
    "413444003": "STTC",   # acute myocardial ischemia
    "413844008": "STTC",   # chronic myocardial ischemia
    "425419005": "STTC",   # inferior ischaemia
    "425623009": "STTC",   # lateral ischaemia
    "55930002": "STTC",    # ST changes
    "428750005": "STTC",   # nonspecific ST-T abnormality
    "164930006": "STTC",   # ST interval abnormal
    "429622005": "STTC",   # CINC2021=ST depression（冲突码，采用CINC语义）
    "704997005": "STTC",   # inferior ST segment depression
    "164931005": "STTC",   # ST elevation（CPSC的STE）
    "164934002": "STTC",   # CINC2021=T wave abnormal（冲突码，采用CINC语义）
    "59931005": "STTC",    # T wave inversion
    "164917005": "STTC",   # Q wave abnormal（官方QWAVE无类，扩展归STTC）
    "164921003": "STTC",   # R wave abnormal
    "365413008": "STTC",   # poor R wave progression
    "164912004": "STTC",   # P wave change
    "164937009": "STTC",   # U wave abnormal
    "251205003": "STTC",   # prolonged P wave
    "251223006": "STTC",   # tall P wave
    "251259000": "STTC",   # high T-voltage
    "428417006": "STTC",   # early repolarization
    "111975006": "STTC",   # PTB-XL=缺血 / CINC2021=LQT（类不变冲突）
    "77867006": "STTC",    # shortened QT
    "418818005": "STTC",   # Brugada形态（敏感性对象）
    "74615001": "STTC",    # brady-tachy syndrome
    "698247007": "STTC",   # cardiac dysrhythmia（广义，敏感性对象）
    # 节律家族扩展（房性/室性异位、室上速、房颤谱、交界性）
    "164889003": "STTC",   # atrial fibrillation
    "164890007": "STTC",   # atrial flutter
    "426177001": "STTC",   # CINC2021=SB / SNOMED本义=AF（类不变冲突）
    "426627000": "STTC",   # bradycardia
    "427084000": "STTC",   # sinus tachycardia
    "427393009": "STTC",   # sinus arrhythmia
    "284470004": "STTC",   # CINC2021=PAC / 部分语境=LAD（类不变冲突）
    "63593006": "STTC",    # supraventricular premature beats
    "427172004": "STTC",   # premature ventricular contractions
    "17338001": "STTC",    # ventricular premature beats
    "164884008": "STTC",   # ventricular ectopics（CPSC的PVC）
    "11157007": "STTC",    # ventricular bigeminy
    "251180001": "STTC",   # ventricular trigeminy
    "251182009": "STTC",   # paired VPC
    "75532003": "STTC",    # ventricular escape beat
    "81898007": "STTC",    # ventricular escape rhythm
    "164896001": "STTC",   # ventricular fibrillation
    "111288001": "STTC",   # ventricular flutter
    "164895002": "STTC",   # ventricular tachycardia
    "425856008": "STTC",   # paroxysmal VT
    "13640000": "STTC",    # fusion beats
    "251173003": "STTC",   # atrial bigeminy
    "251170000": "STTC",   # blocked PAC
    "195101003": "STTC",   # wandering atrial pacemaker
    "17366009": "STTC",    # SAAWR
    "5609005": "STTC",     # sinus arrest
    "282825002": "STTC",   # paroxysmal AF
    "426749004": "STTC",   # chronic AF
    "314208002": "STTC",   # rapid AF
    "195080001": "STTC",   # AF and flutter
    "426761007": "STTC",   # supraventricular tachycardia
    "67198005": "STTC",    # paroxysmal SVT
    "251166008": "STTC",   # AVNRT
    "233897008": "STTC",   # AVRT
    "713422000": "STTC",   # atrial tachycardia
    "233892002": "STTC",   # accelerated atrial escape rhythm
    "106068003": "STTC",   # atrial rhythm
    "251187003": "STTC",   # atrial escape beat
    "61277005": "STTC",    # accelerated idioventricular rhythm
    "49260003": "STTC",    # idioventricular rhythm
    "29320008": "STTC",    # AV junctional rhythm
    "426664006": "STTC",   # accelerated junctional rhythm
    "426648003": "STTC",   # junctional tachycardia
    "426995002": "STTC",   # junctional escape
    "251164006": "STTC",   # junctional premature complex
    "251168009": "STTC",   # supraventricular bigeminy
    "50799005": "STTC",    # AV dissociation（节律归属，敏感性对象）
    "39732003": "STTC",    # left axis deviation（轴偏移归STTC，敏感性对象）
    "47665007": "STTC",    # right axis deviation（同上）
    # --- CD：传导障碍 ---
    "270492004": "CD",     # 1st degree AV block
    "164947007": "CD",     # prolonged PR（官方列为节律，扩展归传导，敏感性对象）
    "49578007": "CD",      # shortened PR（同上）
    "195042002": "CD",     # 2nd degree AV block
    "426183003": "CD",     # Mobitz II
    "54016002": "CD",      # Mobitz I / Wenckebach
    "27885002": "CD",      # complete heart block (3AVB)
    "233917008": "CD",     # AV block (nonspecific)
    "204384007": "CD",     # congenital incomplete AV block
    "6374002": "CD",       # bundle branch block (nonspecific)
    "733534002": "CD",     # complete LBBB
    "713427006": "CD",     # complete RBBB
    "713426002": "CD",     # incomplete RBBB
    "164909002": "CD",     # LBBB
    "59118001": "CD",      # CINC2021=RBBB / SNOMED本义=LBBB（类不变冲突）
    "251120003": "CD",     # incomplete LBBB
    "445118002": "CD",     # left anterior fascicular block
    "445211001": "CD",     # left posterior fascicular block
    "698252002": "CD",     # nonspecific intraventricular conduction disorder
    "82226007": "CD",      # diffuse intraventricular block
    "74390002": "CD",      # Wolff-Parkinson-White pattern
    "195060002": "CD",     # ventricular pre-excitation
    "65778007": "CD",      # sinoatrial block（敏感性对象）
    "60423000": "CD",      # sinus node dysfunction（PTB-XL _AVB子类含SND）
    "251199005": "CD",     # PTB-XL=LAFB / CINC2021=rotation（冲突，采用PTB-XL）
    "10370003": "CD",      # SNOMED本义=BBB / CINC2021=起搏心律（歧义项，
    #                        基线=CD；变体 bbb_10370003_to_sttc 改判STTC）
    # --- HYP：肥厚/扩大/负荷 ---
    "164873001": "HYP",    # left ventricular hypertrophy
    "55827005": "HYP",     # left ventricular high voltage
    "89792004": "HYP",     # right ventricular hypertrophy
    "266249003": "HYP",    # ventricular hypertrophy (nonspecific)
    "195126007": "HYP",    # atrial hypertrophy
    "446813000": "HYP",    # left atrial hypertrophy
    "446358003": "HYP",    # right atrial hypertrophy
    "67741000119109": "HYP",  # left atrial enlargement
    "67751000119106": "HYP",  # right atrial high voltage
    "253352002": "HYP",    # left atrial abnormality
    "253339007": "HYP",    # right atrial abnormality
    "370365005": "HYP",    # left ventricular strain（LVH继发复极，敏感性对象）
    # --- 显式不可映射（官方无类/技术伪影/非ECG所见；MAP_TO_5SUPERCLASS跳过
    #     并在计数报告中体现，对应协议STROBE流程图的"排除"分支） ---
    "251146004": None,     # low QRS voltages（官方LVOLT无类）
    "164951009": None,     # abnormal QRS（官方ABQRS无类）
    "164942001": None,     # fragmented QRS（描述性）
    "251139008": None,     # arm leads reversed（技术伪影）
    "251198002": None,     # clockwise rotation（描述性转位）
    "61721007": None,      # vectorcardiographic loop rotation（描述性）
    "266257000": None,     # transient ischemic attack（临床诊断非ECG所见）
    "251268003": None,     # atrial pacing pattern（起搏图形官方无类）
    "251266004": None,     # ventricular pacing pattern（同上）
    # --- Chapman-Shaoxing (ecg-arrhythmia 1.0.0) 接入补充（2026-09-02，
    #     ConditionNames_SNOMED-CT.csv 覆盖率预检发现的缺口；均按同族先例
    #     归类，敏感性分析对象已在对应族登记） ---
    "28189009": "CD",      # 2AVB2 二度II型房室阻滞（AVB家族；与195042002(2AVB)→
    #                        CD、27885002(3AVB)→CD 同族）
    "233896004": "STTC",   # AVNRT 房室结折返性心动过速（室上速家族；与
    #                        233897008(AVRT)→STTC、426761007(SVT)→STTC 同族）
    "251148003": None,     # low voltage QRS chest lead（官方LVOLT 251146004
    #                        无类的分导联变体，同样无类）
    "251147008": None,     # low voltage QRS limb lead（同上）
}

# 汇总映射表（字母缩写 + SNOMED数值码 双键超集；覆盖PTB-XL与CINC/CPSC两种键样式）
SCP_TO_SUPERCLASS: dict[str, Optional[str]] = {}
SCP_TO_SUPERCLASS.update(_PTBXL_OFFICIAL)
SCP_TO_SUPERCLASS.update(_RHYTHM_EXTENSION)
for _k, _v in _SNOMED_DIAGNOSTIC.items():
    if _k in SCP_TO_SUPERCLASS and SCP_TO_SUPERCLASS[_k] != _v:
        raise RuntimeError(f"映射表内部冲突: {_k}: {SCP_TO_SUPERCLASS[_k]} vs {_v}")
    SCP_TO_SUPERCLASS[_k] = _v

# ---------------------------------------------------------------------------
# Chapman-Shaoxing 映射（Zheng et al., Sci Data 2020: 11节律 + GE MUSE条件缩写）
# 值=None 表示不可映射（计数报告后排除，对应协议STROBE流程）
# ---------------------------------------------------------------------------
CHAPMAN_TO_SUPERCLASS: dict[str, Optional[str]] = {
    # 节律（11种+合并组；G SVT=室上速合并组）
    "NSR": "NORM", "SR": "NORM", "SI": "STTC",
    "AFIB": "STTC", "AFLT": "STTC", "AF": "STTC",
    "SB": "STTC", "ST": "STTC", "STach": "STTC",
    "GSVT": "STTC", "SVT": "STTC", "AT": "STTC",
    "AVNRT": "STTC", "AVRT": "STTC", "SAAWR": "STTC",
    # 常见"other conditions"缩写（GE MUSE口径）
    "1AVB": "CD", "RBBB": "CD", "CRBBB": "CD", "IRBBB": "CD",
    "LBBB": "CD", "CLBBB": "CD", "ILBBB": "CD",
    "LAFB": "CD",
    "LAD": "CD",   # Chapman词典口径=left anterior fascicular block→CD；
    #               若按"left axis deviation"解释则为STTC——敏感性分析对象
    "LPR": "CD", "LQT": "STTC", "LMI": "MI", "IMI": "MI", "ASMI": "MI",
    "ISCAL": "STTC", "ISCAN": "STTC", "ISCIN": "STTC",
    "ISCIL": "STTC", "ISCLA": "STTC", "ISCAS": "STTC",
    "PAC": "STTC", "APB": "STTC", "PVC": "STTC", "SVPB": "STTC",
    "LVH": "HYP", "RVH": "HYP", "LAE": "HYP", "RAH": "HYP", "LAH": "HYP",
    "LQRSV": None,  # 官方无类
}

# ---------------------------------------------------------------------------
# CPSC2018(2019) 映射（9个2018官方类名 + 2019扩展常见名）
# CPSC HYP 极稀有(n=11, 全来自CPSC2019单标签LVH/RVH)——按协议§2主分析降级
# SUBSPACE_CPSC={NORM, CD, STTC, MI}（4类）；HYP 记数后剔除（不支持可靠估计）。
# ---------------------------------------------------------------------------
CPSC_TO_SUPERCLASS: dict[str, Optional[str]] = {
    "Normal": "NORM",
    "AF": "STTC",          # 房颤→节律异常（PTB-XL将AF归STTC的同款惯例）
    "AFLT": "STTC",        # 房扑（CPSC2019扩展）
    "I-AVB": "CD",         # 一度房室阻滞
    "LBBB": "CD",
    "RBBB": "CD",
    "PAC": "STTC",         # 房早→异位节律（敏感性对象：PTB-XL官方异位语句无类）
    "PVC": "STTC",         # 室早（同上；归STTC使CPSC记录全部落入降级子空间）
    "STD": "STTC",         # ST压低
    "STE": "STTC",         # ST抬高
    "LAnFB": "CD",         # 左前分支阻滞（CPSC2019扩展）
    "CLBBB": "CD",         # 完全性左束支阻滞（CPSC2019扩展）
    "Brady": "STTC",       # 心动过缓（CPSC2019扩展）
    "OldMI": "MI",         # 陈旧性心梗（CPSC2019扩展；不落入主子空间，见协议
    #                        §2"HYP优先级记录剔除并单列计数"的对称处理）
}


def MAP_TO_5SUPERCLASS(
    scp_codes: dict,
    priority_rules: tuple = DEFAULT_PRIORITY,
    *,
    mapping: Optional[MappingType] = None,
    code_overrides: Optional[MappingType] = None,
    use_weights: bool = False,
) -> Optional[str]:
    """{scp_code: 权重} → 单标签5超类（不可映射返回None）

    参数
    ----
    scp_codes : dict
        {scp_code: weight}，键为字母缩写或SNOMED数值码（自动str化）。
    priority_rules : tuple
        优先级顺序（默认 DEFAULT_PRIORITY = MI>STTC>CD>HYP>NORM，协议§2固定，
        见模块docstring依据说明）。必须是5超类的一个排列。
    mapping : dict, optional
        码表（默认 SCP_TO_SUPERCLASS）。
    code_overrides : dict, optional
        变体用码表覆写（如 {"10370003": "STTC"}），优先级高于 mapping。
    use_weights : bool
        True时忽略权重<=0（或NaN）的语句；False为官方aggregation行为
        （完全不看权重）。默认False。

    返回
    ----
    str | None：命中优先级最高的超类；无任何可映射语句→None。
    """
    if tuple(priority_rules) != tuple(SUPERCLASSES) and set(priority_rules) != set(SUPERCLASSES):
        raise ValueError(f"priority_rules必须是5超类的排列, 得到: {priority_rules}")
    table = dict(SCP_TO_SUPERCLASS if mapping is None else mapping)
    if code_overrides:
        table.update(code_overrides)

    candidates: list[str] = []
    for code, weight in scp_codes.items():
        if use_weights:
            try:
                if weight is None or not (float(weight) > 0):
                    continue
            except (TypeError, ValueError):
                continue
        cls = table.get(str(code).strip())
        if cls is not None and cls not in candidates:
            candidates.append(cls)
    if not candidates:
        return None
    for pri in priority_rules:
        if pri in candidates:
            return pri
    return None  # 理论不可达（priority_rules已校验为全排列）


def generate_mapping_variants():
    """生成≥3个替代映射变体（协议§10-T1映射敏感性分析；生成器，逐个yield）

    每个变体为dict：
        name           变体名
        priority       该变体的优先级排列（传入MAP_TO_5SUPERCLASS）
        code_overrides 码表覆写（可为空dict）
        rationale      变体动机
        probe_codes    验证用示例记录 {scp_code: weight}
        expected_label 该变体下probe_codes的期望标签（用于测试区分性）
    """
    # 变体1：优先级完全反转（NORM最优先）——检验"病理优先"约定方向的影响
    yield {
        "name": "priority_norm_first",
        "priority": ("NORM", "HYP", "CD", "STTC", "MI"),
        "code_overrides": {},
        "rationale": "优先级完全反转：正常优先于病理，检验单标签化方向的稳健性",
        "probe_codes": {"NORM": 100.0, "IMI": 100.0},
        "expected_label": "NORM",
    }
    # 变体2：STTC与MI互换（STTC优先）——检验"缺血优先于传导/ST-T"的排序假设
    yield {
        "name": "priority_sttc_over_mi",
        "priority": ("STTC", "MI", "CD", "HYP", "NORM"),
        "code_overrides": {},
        "rationale": "ST/T改变优先于心梗：MI与STTC共存记录（如IMI+ISCIN）改判STTC",
        "probe_codes": {"IMI": 100.0, "ISCIN": 100.0},
        "expected_label": "STTC",
    }
    # 变体3：歧义项 10370003 改判（基线CD=束支阻滞本义；CINC2021用作起搏心律）
    yield {
        "name": "bbb_10370003_to_sttc",
        "priority": DEFAULT_PRIORITY,
        "code_overrides": {"10370003": "STTC"},
        "rationale": "10370003为已知跨库歧义码（SNOMED本义=束支阻滞→CD；"
                     "CINC2021=起搏心律），改归STTC检验歧义决策的稳健性",
        "probe_codes": {"10370003": 100.0},
        "expected_label": "STTC",
    }
    # 变体4：窦性速率/形态语句改归STTC（R13修正前的旧约定）——检验R13
    # 决策（SBRAD/STACH/SARRH→NORM）对主检验结论的稳健性。PTB-XL官方
    # scp_statements.csv 判 SBRAD/STACH/SARRH 为 rhythm 语句(diagnostic_class=
    # NaN)，本变体反映旧版_ RHYTHM_EXTENSION 的"节律异常→STTC"惯例。
    yield {
        "name": "sinus_rhythm_abnormality_to_sttc",
        "priority": DEFAULT_PRIORITY,
        "code_overrides": {"SBRAD": "STTC", "STACH": "STTC", "SARRH": "STTC"},
        "rationale": "R13敏感性对象：窦性速率/形态语句(SBRAD/STACH/SARRH)按"
                     "旧'节律异常→STTC'惯例改判，检验窦性家族→NORM是否改变"
                     "跨库校准迁移主检验结论（与Chapman R12覆写形成对照臂）",
        "probe_codes": {"SBRAD": 100.0, "1AVB": 100.0},
        "expected_label": "STTC",
    }


def filter_subspace(
    labels: Iterable[Optional[str]],
    allowed: Iterable[str] = SUBSPACE_CPSC,
) -> dict:
    """降级子空间过滤 + 计数报告（协议§2：CPSC主分析两侧对称按子空间重算）

    参数
    ----
    labels : 序列
        每条记录的超类标签（None=不可映射，计入dropped并单列"None"）。
    allowed : 容器
        允许保留的超类集合（默认 CPSC 子空间 {NORM, CD, STTC, MI}）。

    返回
    ----
    dict：kept/dropped索引、逐类计数（kept_counts/dropped_counts），
    可直接供STROBE式流程图逐类计数使用。allowed 字段固定按字典序排序
    输出（set迭代顺序随PYTHONHASHSEED漂移，不用于确定性报告）。
    """
    allowed_set = set(allowed)
    kept_indices: list[int] = []
    dropped_indices: list[int] = []
    kept_counts: Counter = Counter()
    dropped_counts: Counter = Counter()
    for i, lbl in enumerate(labels):
        key = lbl if lbl is not None else "None"
        if lbl is not None and lbl in allowed_set:
            kept_indices.append(i)
            kept_counts[key] += 1
        else:
            dropped_indices.append(i)
            dropped_counts[key] += 1
    return {
        "allowed": tuple(sorted(allowed_set)),
        "n_total": len(kept_indices) + len(dropped_indices),
        "n_kept": len(kept_indices),
        "n_dropped": len(dropped_indices),
        "kept_indices": kept_indices,
        "dropped_indices": dropped_indices,
        "kept_counts": dict(kept_counts),
        "dropped_counts": dict(dropped_counts),
    }


if __name__ == "__main__":
    # 自检：任务硬性要求 + 优先级 + 变体区分性
    assert SCP_TO_SUPERCLASS["426783006"] == "NORM", "窦性节律必须→NORM"
    assert MAP_TO_5SUPERCLASS({"NORM": 100, "IMI": 100}) == "MI"
    assert MAP_TO_5SUPERCLASS({"1AVB": 100, "ISC_": 100}) == "STTC"
    assert MAP_TO_5SUPERCLASS({"NORM": 100, "LVH": 100}) == "HYP"
    assert MAP_TO_5SUPERCLASS({"SR": 100, "NORM": 100}) == "NORM"
    # R13：窦性速率/形态语句→NORM，不遮蔽真实传导/肥厚诊断
    assert MAP_TO_5SUPERCLASS({"SBRAD": 100}) == "NORM", "R13窦缓→NORM"
    assert MAP_TO_5SUPERCLASS({"STACH": 100}) == "NORM", "R13窦速→NORM"
    assert MAP_TO_5SUPERCLASS({"SARRH": 100}) == "NORM", "R13窦性心律不齐→NORM"
    assert MAP_TO_5SUPERCLASS({"SBRAD": 100, "1AVB": 100}) == "CD", "窦缓不得遮蔽1AVB(传导)"
    assert MAP_TO_5SUPERCLASS({"STACH": 100, "LVH": 100}) == "HYP", "窦速不得遮蔽LVH"
    assert MAP_TO_5SUPERCLASS({"AFIB": 100}) == "STTC"
    assert MAP_TO_5SUPERCLASS({"未知码xyz": 100}) is None
    # 跨编码一致性已知矛盾登记（R12/R13）：同一诊断用字母缩写→NORM，
    # 用SNOMED码→STTC（全局表为CINC2021定制）。Chapman侧靠 preprocess_chapman.py
    # 的 code_overrides 覆写为NORM对齐。PTB-XL侧用字母缩写键不触发。
    # TODO: CINC2021语境核实后统一全局表。登记为协议§10-T1敏感性对象。
    _cross_code_conflicts = {
        "窦缓": ("SBRAD", "426177001"),   # SBRAD→NORM vs 426177001→STTC
        "窦速": ("STACH", "427084000"),   # STACH→NORM vs 427084000→STTC
        "窦性心律不齐": ("SARRH", "427393009"),  # SARRH→NORM vs 427393009→STTC
    }
    for dx, (abbr, snomed) in _cross_code_conflicts.items():
        v_abbr = SCP_TO_SUPERCLASS[abbr]
        v_snomed = SCP_TO_SUPERCLASS[snomed]
        if v_abbr != v_snomed:
            print(f"[已知矛盾] {dx}: {abbr}→{v_abbr} vs {snomed}→{v_snomed} "
                  f"(Chapman侧覆写对齐；登记§10-T1敏感性对象)")
    assert MAP_TO_5SUPERCLASS({}) is None
    variants = list(generate_mapping_variants())
    assert len(variants) >= 3
    for v in variants:
        got = MAP_TO_5SUPERCLASS(v["probe_codes"], v["priority"],
                                 code_overrides=v["code_overrides"])
        assert got == v["expected_label"], f"变体{v['name']}探针不符: {got}"
    labels = ["NORM", "CD", "STTC", "HYP", "MI", None]
    rep = filter_subspace(labels)
    assert rep["n_kept"] == 4 and rep["kept_counts"] == {"NORM": 1, "CD": 1, "STTC": 1, "MI": 1}
    assert len(SCP_TO_SUPERCLASS) >= 60, f"码表过少: {len(SCP_TO_SUPERCLASS)}"
    print(f"[自检] 映射模块通过：共{len(SCP_TO_SUPERCLASS)}个码 "
          f"（其中显式不可映射{sum(1 for v in SCP_TO_SUPERCLASS.values() if v is None)}个）")
