import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset
import wfdb
import ast
import os
from sklearn.model_selection import train_test_split
from tqdm import tqdm  # <--- [추가 1] 진행률 표시 라이브러리
from datasets.transforms.ecg_transforms import get_ptbxl_augmenter
# PTB-XL의 5개 Superclass 정의
# ID_CLASSES: 학습할 클래스 (Known)
# OOD_CLASSES: 모르는 클래스 (Unknown) - Unlabeled set에만 등장
ID_CLASSES = ['NORM', 'MI', 'CD']  
OOD_CLASSES = ['STTC', 'HYP']
ALL_CLASSES = ID_CLASSES + OOD_CLASSES

class PTBXLDataset(Dataset):
    def __init__(self, data, labels, transform=None, mode='labeled', augment_impl='ecg'):
        self.data = data
        self.labels = labels
        self.targets = labels
        
        self.transform = transform
        self.mode = mode  # 'labeled', 'unlabeled', 'test' 중 하나
        self.weak_aug = get_ptbxl_augmenter(augment_impl, 'weak')
        self.strong_aug = get_ptbxl_augmenter(augment_impl, 'strong')
        self.indices = list(range(len(self.data)))
    # PTBXLDataset 클래스 내부
    def set_index(self, indexes=None):
        # """
        # OpenMatch 등에서 특정 인덱스의 데이터만 사용하도록 설정하는 메서드
        # """
        if indexes is None:
            # 인덱스가 없으면(초기화 등) 전체 데이터를 사용하도록 복구
            self.indices = list(range(len(self.data))) # self.data나 self.samples 등 원본 데이터 리스트 변수명 확인 필요
        else:
            # [수정] 들어온 indexes가 텐서(GPU/CPU)라면 일반 파이썬 리스트로 변환
            if torch.is_tensor(indexes):
                indexes = indexes.cpu().tolist()
            elif isinstance(indexes, np.ndarray):
                indexes = indexes.tolist()
            
            # 리스트 안에 텐서가 섞여 있을 경우를 대비해 한 번 더 안전장치 (선택사항이나 권장)
            # indexes = [int(x) for x in indexes]
            # 전달받은 인덱스 리스트로 현재 사용할 인덱스 덮어쓰기
            self.indices = indexes

    # def __len__(self):
    #     return len(self.data)
    def __len__(self):
        # [수정 1] 전체 데이터 길이가 아니라, 현재 활성화된 인덱스 리스트의 길이를 반환해야 함
        return len(self.indices)

    def __getitem__(self, idx):
        # [수정 2] DataLoader가 요청한 idx를 실제 데이터의 인덱스(real_idx)로 변환
        real_idx = self.indices[idx]
        
        # [수정 3] self.data[idx] 가 아니라 self.data[real_idx]를 사용해야 함
        x = self.data[real_idx].transpose(1, 0).astype(np.float32)
        y = self.labels[real_idx]
        # # (채널, 시간) 형태로 변환 (12, 1000)
        # x = self.data[idx].transpose(1, 0).astype(np.float32)
        # y = self.labels[idx]
        # 공통 증강 생성
        w0 = self.weak_aug(x.copy()).astype(np.float32)
        w1 = self.weak_aug(x.copy()).astype(np.float32)
        s = self.strong_aug(x.copy()).astype(np.float32)
        # 3. 증강 생성
        w = self.weak_aug(x.copy()).astype(np.float32)
        s = self.strong_aug(x.copy()).astype(np.float32)
        # [핵심 수정] CaliMatch가 요구하는 딕셔너리 키(Key)에 맞춰서 반환
        if self.mode == 'unlabeled':
            x_w = self.weak_aug(x.copy())
            x_w_t = self.weak_aug(x.copy())
            x_s = self.strong_aug(x.copy())
            return {
                "idx_ulb": idx,
                "x_ulb_w": x_w.astype(np.float32),      
                "x_ulb_w_t": x_w_t.astype(np.float32),
                "x_ulb_s": x_s.astype(np.float32),
                "y_ulb": y,
                # [추가] FixMatch용 키 (Standard)
                "weak_img": x_w.astype(np.float32),
                "strong_img": x_s.astype(np.float32),
                "y": y,  # 일반적인 이름
                "idx": real_idx,         # 인덱스 (필수)
                
                # [IOMatch/FixMatch 공통]
                "weak_img": w,           # 가짜 라벨 생성용 (Weak)
                "strong_img": s,         # 학습 및 Loss 계산용 (Strong)
                
                # [호환성] 혹시 코드가 x_ulb_w 등을 찾을 경우를 대비
                "x_ulb_w": w,
                "x_ulb_s": s,
                
                "y": y,                  # Ground Truth (평가용)
                "y_ulb": y,
                "unlabel_y": y,

                # [SCOMatch 호환 키]
                "inputs_u_w": w,
                "inputs_u_s": s,
                "inputs_all_w": w,
                "inputs_all_s": s,
                "targets_u_eval": y
            }
        elif self.mode == 'labeled':
            x_lb = self.weak_aug(x.copy())
            return {
                "idx_lb": idx,
                "x_lb": x_lb.astype(np.float32),
                # [추가] FixMatch용 키
                "x": x_lb.astype(np.float32),
                "y_lb": y,
                "y": y,
                "idx": real_idx,
                "x_lb": w,               # Labeled 데이터는 보통 Weak Aug만 사용
                "x": w,                  # 호환성
                "y_lb": y,
                "y": y,

                # [SCOMatch 호환 키]
                "inputs_x": w,
                "targets_x": y
            }
        # [OpenMatch용 모드 추가]
        elif self.mode == 'train_lb': # Labeled 데이터 (Weak x 2)
            return {
                "idx_lb": idx,
                "x_lb_w_0": w0,
                "x_lb_w_1": w1,
                "y_lb": y
            }
        elif self.mode == 'train_ulb': # Unlabeled 데이터 (Weak x 2)
            return {
                "idx_ulb": idx,
                "x_ulb_w_0": w0,
                "x_ulb_w_1": w1,
                "y_ulb": y
            }
        elif self.mode == 'train_ulb_selected': # Selected Unlabeled (Weak + Strong)
            return {
                "x_ulb_w": w0,
                "x_ulb_s": s,
                "unlabel_y": y
            }

        elif self.mode == 'test':
            return {
                "idx": idx,
                "x": x.astype(np.float32),
                "y": y,
                "idx": real_idx,
                "x": x.astype(np.float32),
                "y": y
            }
        return x, y
    
def load_raw_ptbxl(root, sampling_rate=100):
    """PTB-XL 원본 데이터 로드 및 전처리"""
    path = root # '/content/ptbxl/' 등
    
    # 1. 메타데이터 로드
    print(f"메타데이터 로딩 중... ({path})")
    df = pd.read_csv(os.path.join(path, 'ptbxl_database.csv'), index_col='ecg_id')

    # 다운스트림 작업을 위해 파싱
    df.scp_codes = df.scp_codes.apply(lambda x: ast.literal_eval(x))

    # 2. 라벨 변환 (Superclass)
    agg_df = pd.read_csv(os.path.join(path, 'scp_statements.csv'), index_col=0)
    agg_df = agg_df[agg_df.diagnostic == 1]

    def aggregate_diagnostic(y_dic):
        tmp = []
        for key in y_dic.keys():
            if key in agg_df.index:
                tmp.append(agg_df.loc[key].diagnostic_class)
        return list(set(tmp))

    df['diagnostic_superclass'] = df.scp_codes.apply(aggregate_diagnostic)
    
    # 4. 단일 라벨 데이터만 필터링 (실험 단순화)
    # 여러 병이 겹친 데이터는 헷갈리므로 제외합니다.
    df['label_len'] = df.diagnostic_superclass.apply(len)
    mask = df['label_len'] == 1
    df = df[mask].copy()

    filename_column = 'filename_hr' if int(sampling_rate) == 500 else 'filename_lr'
    filenames = df[filename_column].tolist()
    cache_path = os.path.join(path, f'ptbxl_single_label_{int(sampling_rate)}hz.npy')

    def load_and_cache_data(selected_filenames, selected_cache_path):
        print("파형 데이터 로딩 중... (약 2~3분 소요)")
        first_signal = wfdb.rdsamp(os.path.join(path, selected_filenames[0]))[0]
        data = np.empty((len(selected_filenames),) + first_signal.shape, dtype=np.float32)
        data[0] = first_signal.astype(np.float32, copy=False)

        for idx, filename in enumerate(tqdm(selected_filenames[1:], total=max(len(selected_filenames) - 1, 0))):
            signal = wfdb.rdsamp(os.path.join(path, filename))[0]
            data[idx + 1] = signal.astype(np.float32, copy=False)

        print(f"캐시 저장 중... ({selected_cache_path})")
        np.save(selected_cache_path, data)
        return np.load(selected_cache_path, mmap_mode='r')

    if os.path.exists(cache_path):
        try:
            print(f"캐시된 파형 데이터 로딩 중... ({cache_path})")
            X = np.load(cache_path, mmap_mode='r')
            if X.shape[0] != len(filenames):
                print("캐시 크기가 현재 단일 라벨 subset과 달라 재생성합니다.")
                X = load_and_cache_data(filenames, cache_path)
        except (OSError, ValueError):
            print("캐시를 읽는 중 문제가 발생해 다시 생성합니다.")
            X = load_and_cache_data(filenames, cache_path)
    else:
        X = load_and_cache_data(filenames, cache_path)

    # 리스트에서 문자열로 추출 ('['NORM']' -> 'NORM')
    y_str = df.diagnostic_superclass.apply(lambda x: x[0]).values
    
    return X, y_str, df


def _split_ptbxl_indices(df, y_str, args):
    split_protocol = getattr(args, 'ptbxl_split_protocol', 'random_811')

    if split_protocol == 'official_strat_fold':
        valid_fold = int(getattr(args, 'ptbxl_valid_fold', 9))
        test_fold = int(getattr(args, 'ptbxl_test_fold', 10))
        strat_folds = df['strat_fold'].to_numpy()

        val_mask = strat_folds == valid_fold
        test_mask = strat_folds == test_fold
        train_mask = ~(val_mask | test_mask)

        train_idxs = np.where(train_mask)[0]
        val_idxs = np.where(val_mask)[0]
        test_idxs = np.where(test_mask)[0]
        return train_idxs, val_idxs, test_idxs

    indices = np.arange(len(y_str))
    try:
        train_idxs, temp_idxs, y_train, y_temp = train_test_split(
            indices, y_str, test_size=0.2, stratify=y_str, random_state=42
        )
        val_idxs, test_idxs, _, _ = train_test_split(
            temp_idxs, y_temp, test_size=0.5, stratify=y_temp, random_state=42
        )
    except ValueError:
        # Fallback if stratify fails (e.g., ningbo has only 1 'CD' sample)
        train_idxs, temp_idxs, y_train, y_temp = train_test_split(
            indices, y_str, test_size=0.2, random_state=42
        )
        val_idxs, test_idxs, _, _ = train_test_split(
            temp_idxs, y_temp, test_size=0.5, random_state=42
        )
    return train_idxs, val_idxs, test_idxs


def _build_strict_mismatch_unlabeled(id_indices, ood_indices, mismatch_ratio):
    ul_id_idxs = np.array(id_indices, dtype=int)

    ul_ood_idxs = np.array(ood_indices, dtype=int)

    if len(ul_id_idxs) > 0:
        n_id = len(ul_id_idxs)
        target_n_ood = int(n_id * mismatch_ratio / (1 - mismatch_ratio))

        if len(ul_ood_idxs) >= target_n_ood:
            np.random.shuffle(ul_ood_idxs)
            ul_ood_idxs = ul_ood_idxs[:target_n_ood]
        else:
            if mismatch_ratio > 0:
                new_n_id = int(len(ul_ood_idxs) * (1 - mismatch_ratio) / mismatch_ratio)
                np.random.shuffle(ul_id_idxs)
                ul_id_idxs = ul_id_idxs[:new_n_id]

    unlabeled_idxs = np.concatenate([ul_id_idxs, ul_ood_idxs])
    np.random.shuffle(unlabeled_idxs)
    return unlabeled_idxs, ul_id_idxs, ul_ood_idxs, 0


def _build_approx_all_data_unlabeled(
    id_indices,
    ood_indices,
    labeled_count,
    unlabeled_multiplier,
):
    ul_id_idxs = np.array(id_indices, dtype=int)
    ul_ood_unique = np.array(ood_indices, dtype=int)

    base_unlabeled_total = len(ul_id_idxs) + len(ul_ood_unique)
    target_unlabeled_total = max(
        base_unlabeled_total,
        int(round(labeled_count * unlabeled_multiplier)),
    )
    extra_ood_needed = max(0, target_unlabeled_total - base_unlabeled_total)

    if extra_ood_needed > 0 and len(ul_ood_unique) > 0:
        extra_ood_idxs = np.random.choice(ul_ood_unique, size=extra_ood_needed, replace=True)
    else:
        extra_ood_idxs = np.array([], dtype=int)

    ul_ood_idxs = np.concatenate([ul_ood_unique, extra_ood_idxs])
    unlabeled_idxs = np.concatenate([ul_id_idxs, ul_ood_idxs])
    np.random.shuffle(unlabeled_idxs)
    return unlabeled_idxs, ul_id_idxs, ul_ood_idxs, extra_ood_needed


def _build_fixed_volume_mismatch_unlabeled(
    id_indices,
    ood_indices,
    labeled_count,
    unlabeled_multiplier,
    mismatch_ratio
):
    ul_id_idxs = np.array(id_indices, dtype=int)
    ul_ood_unique = np.array(ood_indices, dtype=int)

    target_unlabeled_total = int(round(labeled_count * unlabeled_multiplier))
    target_ood_count = int(round(target_unlabeled_total * mismatch_ratio))
    target_id_count = target_unlabeled_total - target_ood_count

    if target_id_count <= len(ul_id_idxs):
        np.random.shuffle(ul_id_idxs)
        ul_id_idxs = ul_id_idxs[:target_id_count]
    else:
        extra_id = np.random.choice(ul_id_idxs, size=target_id_count - len(ul_id_idxs), replace=True)
        ul_id_idxs = np.concatenate([ul_id_idxs, extra_id])

    if target_ood_count <= len(ul_ood_unique):
        np.random.shuffle(ul_ood_unique)
        ul_ood_idxs = ul_ood_unique[:target_ood_count]
    else:
        extra_ood = np.random.choice(ul_ood_unique, size=target_ood_count - len(ul_ood_unique), replace=True)
        ul_ood_idxs = np.concatenate([ul_ood_unique, extra_ood])

    unlabeled_idxs = np.concatenate([ul_id_idxs, ul_ood_idxs])
    np.random.shuffle(unlabeled_idxs)
    return unlabeled_idxs, ul_id_idxs, ul_ood_idxs, max(0, target_ood_count - len(ul_ood_unique))


def _build_all_train_unique_unlabeled(id_indices, ood_indices):
    ul_id_idxs = np.array(id_indices, dtype=int)
    ul_ood_idxs = np.array(ood_indices, dtype=int)

    unlabeled_idxs = np.concatenate([ul_id_idxs, ul_ood_idxs])
    np.random.shuffle(unlabeled_idxs)
    return unlabeled_idxs, ul_id_idxs, ul_ood_idxs, 0


def _build_ptbxl_unlabeled_indices(args, id_indices, ood_indices, labeled_count):
    split_mode = getattr(args, 'ptbxl_split_mode', 'strict_mismatch')
    if split_mode == 'all_train_unique':
        return _build_all_train_unique_unlabeled(
            id_indices=id_indices,
            ood_indices=ood_indices,
        )

    if split_mode == 'fixed_volume_mismatch':
        return _build_fixed_volume_mismatch_unlabeled(
            id_indices=id_indices,
            ood_indices=ood_indices,
            labeled_count=labeled_count,
            unlabeled_multiplier=getattr(args, 'ptbxl_unlabeled_multiplier', 99.0),
            mismatch_ratio=args.mismatch_ratio,
        )

    if split_mode == 'approx_all_data':
        return _build_approx_all_data_unlabeled(
            id_indices=id_indices,
            ood_indices=ood_indices,
            labeled_count=labeled_count,
            unlabeled_multiplier=getattr(args, 'ptbxl_unlabeled_multiplier', 99.0),
        )

    return _build_strict_mismatch_unlabeled(
        id_indices=id_indices,
        ood_indices=ood_indices,
        mismatch_ratio=args.mismatch_ratio,
    )

# def get_ptbxl(args, root='./ptbxl/'):
#     """CaliMatch 학습을 위한 데이터 분할 함수"""
#     X, y_str = load_raw_ptbxl(root)
    
#     # 클래스 문자열을 정수 인덱스로 변환 (ID 클래스만 0, 1, 2... 부여)
#     class_to_idx = {cls: i for i, cls in enumerate(ID_CLASSES)}
    
#     # 데이터 분할을 위한 인덱스 저장소
#     id_indices = {c: [] for c in ID_CLASSES}
#     ood_indices = {c: [] for c in OOD_CLASSES}

#     for i, label in enumerate(y_str):
#         if label in ID_CLASSES:
#             id_indices[label].append(i)
#         elif label in OOD_CLASSES:
#             ood_indices[label].append(i)

#     # --- 1. Labeled Train Set 만들기 ---
#     # 각 ID 클래스당 n_label_per_class 개수만큼 뽑기
#     labeled_idxs = []
#     unlabeled_pool_idxs = [] # 남은 ID 데이터는 Unlabeled 후보

#     for c in ID_CLASSES:
#         idxs = np.array(id_indices[c])
#         np.random.shuffle(idxs)
#         # 라벨 데이터 뽑기
#         labeled_idxs.extend(idxs[:args.n_label_per_class])
#         # 나머지는 Unlabeled 풀에 넣기
#         unlabeled_pool_idxs.extend(idxs[args.n_label_per_class:])
    
#     # --- 2. Unlabeled Train Set 만들기 (OOD 섞기) ---
#     # 전체 Unlabeled 개수 설정 (예: 라벨 데이터의 5배~10배)
#     # 여기서는 남은 데이터 전체를 활용하되 비율을 맞춥니다.
    
#     # ID 데이터 (Unlabeled용)
#     ul_id_idxs = np.array(unlabeled_pool_idxs)
    
#     # OOD 데이터 (전체 OOD 데이터 모으기)
#     ul_ood_idxs = []
#     for c in OOD_CLASSES:
#         ul_ood_idxs.extend(ood_indices[c])
#     ul_ood_idxs = np.array(ul_ood_idxs)

#     # Mismatch Ratio 적용
#     # 목표: Total Unlabeled 중 ratio 만큼이 OOD여야 함
#     # 수식: n_ood = ratio * total -> n_ood = (ratio / (1-ratio)) * n_id
    
#     n_id = len(ul_id_idxs)
#     target_n_ood = int(n_id * args.mismatch_ratio / (1 - args.mismatch_ratio))
    
#     # OOD 데이터가 충분하면 자르고, 부족하면 ID를 줄여서 비율 맞춤
#     if len(ul_ood_idxs) >= target_n_ood:
#         np.random.shuffle(ul_ood_idxs)
#         ul_ood_idxs = ul_ood_idxs[:target_n_ood]
#     else:
#         # OOD가 부족한 경우, 비율을 맞추기 위해 ID 데이터를 줄임
#         new_n_id = int(len(ul_ood_idxs) * (1 - args.mismatch_ratio) / args.mismatch_ratio)
#         np.random.shuffle(ul_id_idxs)
#         ul_id_idxs = ul_id_idxs[:new_n_id]

#     unlabeled_idxs = np.concatenate([ul_id_idxs, ul_ood_idxs])
#     np.random.shuffle(unlabeled_idxs) # 섞기

#     # --- 3. 데이터셋 객체 생성 ---
#     # Labeled Set
#     x_labeled = X[labeled_idxs]
#     y_labeled = np.array([class_to_idx[y_str[i]] for i in labeled_idxs])
#     # [수정] mode 설정 ('labeled')
#     train_labeled_dataset = PTBXLDataset(x_labeled, y_labeled, mode='labeled')

#     # Unlabeled Set (라벨은 평가용으로 넣어두지만 학습땐 안 씀 / OOD는 -1로 처리)
#     x_unlabeled = np.copy(X[unlabeled_idxs])
#     y_unlabeled = []
#     for i in unlabeled_idxs:
#         label = y_str[i]
#         if label in ID_CLASSES:
#             y_unlabeled.append(class_to_idx[label])
#         else:
#             y_unlabeled.append(-1) # OOD Label
#     y_unlabeled = np.array(y_unlabeled)
    
#     # Validation / Test Set (ID 클래스만 평가하거나, OOD 포함하여 평가)
#     # 여기서는 간단히 남은 데이터나 별도 split을 사용해야 하지만, 
#     # 편의상 Labeled Set에서 제외된 데이터 중 일부를 Validation으로 씁니다.
#     # (실제 연구에선 train_test_split을 맨 처음에 하는게 좋습니다)
    
#     # 임시: ID 데이터 중 일부를 떼서 Test로 사용 (데모용)
#     # 실제로는 load_raw_ptbxl 단계에서 미리 test set을 분리해두는 것이 정석입니다.
#     # [수정] mode 설정 ('unlabeled')
#     train_unlabeled_dataset = PTBXLDataset(x_unlabeled, y_unlabeled, mode='unlabeled')
#     # [수정] Validation/Test는 'test' 모드로 설정 (단순 반환)
#     val_dataset = PTBXLDataset(x_labeled, y_labeled, mode='test')
#     test_dataset = PTBXLDataset(x_labeled, y_labeled, mode='test')
    
#     # [Validation] - ID 클래스만
#     val_indices = []
    
#     print(f"[PTB-XL] Labeled: {len(labeled_idxs)} (ID only)")
#     print(f"[PTB-XL] Unlabeled: {len(unlabeled_idxs)} (ID: {len(ul_id_idxs)}, OOD: {len(ul_ood_idxs)})")
#     print(f"[PTB-XL] Mismatch Ratio: {len(ul_ood_idxs)/len(unlabeled_idxs):.2f} (Target: {args.mismatch_ratio})")

#     return train_labeled_dataset, train_unlabeled_dataset, val_dataset, test_dataset
def load_raw_cinc2021(root, dataset_name):
    import os
    import numpy as np
    import pandas as pd
    base_dir = os.fspath(root)
    x_path = os.path.join(base_dir, f"{dataset_name}_X.npy")
    csv_path = os.path.join(base_dir, f"{dataset_name}_metadata.csv")
    
    print(f"Loading CINC2021 {dataset_name} from {x_path}")
    X = np.load(x_path)
    df = pd.read_csv(csv_path)
    y_str = df['label'].to_numpy()
    return X, y_str, df

def get_ptbxl(args, root='./ptbxl/'):
    dataset_name = getattr(args, 'data', 'ptbxl').lower()
    if dataset_name in ['chapman', 'georgia', 'ningbo']:
        sampling_rate = 100
        X, y_str, df = load_raw_cinc2021(root, dataset_name)
    else:
        sampling_rate = getattr(args, 'ptbxl_sampling_rate', 100)
        X, y_str, df = load_raw_ptbxl(root, sampling_rate=sampling_rate)
    
    augment_impl = getattr(args, 'ptbxl_augment', 'ecg')
    
    class_to_idx = {cls: i for i, cls in enumerate(ID_CLASSES)}
    ood_label_idx = len(ID_CLASSES)
    train_idxs, val_idxs, test_idxs = _split_ptbxl_indices(df, y_str, args)

    # 2. Train 데이터 안에서 Labeled / Unlabeled 나누기
    id_indices = {c: [] for c in ID_CLASSES}
    ood_indices = {c: [] for c in OOD_CLASSES}

    # Train 데이터만 가지고 인덱스 분류
    for idx in train_idxs:
        label = y_str[idx]
        if label in ID_CLASSES:
            id_indices[label].append(idx)
        elif label in OOD_CLASSES:
            ood_indices[label].append(idx)

    # Labeled Set 추출
    labeled_idxs = []
    unlabeled_pool_idxs = []

    for c in ID_CLASSES:
        idxs = np.array(id_indices[c])
        np.random.shuffle(idxs)
        # Train 데이터가 부족할 경우를 대비해 min 사용
        n_take = min(len(idxs), args.n_label_per_class)
        labeled_idxs.extend(idxs[:n_take])
        unlabeled_pool_idxs.extend(idxs[n_take:]) # 나머지는 Unlabeled 후보

    ul_ood_idxs = []
    for c in OOD_CLASSES:
        ul_ood_idxs.extend(ood_indices[c])

    unlabeled_idxs, ul_id_idxs, ul_ood_idxs, extra_ood_needed = _build_ptbxl_unlabeled_indices(
        args=args,
        id_indices=unlabeled_pool_idxs,
        ood_indices=ul_ood_idxs,
        labeled_count=len(labeled_idxs),
    )
    
    # 3. 데이터셋 객체 생성
    # [Train - Labeled]
    x_labeled = X[labeled_idxs]
    y_labeled = np.array([class_to_idx[y_str[i]] for i in labeled_idxs])
    train_labeled_dataset = PTBXLDataset(
        x_labeled,
        y_labeled,
        mode='labeled',
        augment_impl=augment_impl,
    )

    # [Train - Unlabeled]
    x_unlabeled = np.copy(X[unlabeled_idxs])
    y_unlabeled = []
    for i in unlabeled_idxs:
        label = y_str[i]
        if label in ID_CLASSES:
            y_unlabeled.append(class_to_idx[label])
        else:
            y_unlabeled.append(ood_label_idx)
    y_unlabeled = np.array(y_unlabeled)
    train_unlabeled_dataset = PTBXLDataset(
        x_unlabeled,
        y_unlabeled,
        mode='unlabeled',
        augment_impl=augment_impl,
    )

    # [Validation] - ID 클래스만 남김 (평가의 공정성 위해 OOD 제외)
    x_val = X[val_idxs]
    y_val_raw = y_str[val_idxs]
    # Val 데이터 중 ID 클래스인 것만 필터링
    mask_val = np.isin(y_val_raw, ID_CLASSES)
    x_val = x_val[mask_val]
    y_val = np.array([class_to_idx[lbl] for lbl in y_val_raw[mask_val]])
    
    val_dataset = PTBXLDataset(
        x_val,
        y_val,
        mode='test',
        augment_impl=augment_impl,
    )

    # [Test] - ID 클래스만 사용
    x_test = X[test_idxs]
    y_test_raw = y_str[test_idxs]
    mask_test = np.isin(y_test_raw, ID_CLASSES)
    x_test = x_test[mask_test]
    y_test = np.array([class_to_idx[lbl] for lbl in y_test_raw[mask_test]])

    test_dataset = PTBXLDataset(
        x_test,
        y_test,
        mode='test',
        augment_impl=augment_impl,
    )

    if getattr(args, 'ptbxl_open_test_mode', 'heldout') == 'test':
        open_test_dataset = test_dataset
        open_test_id_count = len(test_dataset)
        open_test_ood_count = 0
    else:
        # [Open Test] - held-out test split의 ID + OOD 전체를 유지
        x_open_test = X[test_idxs]
        y_open_test_raw = y_str[test_idxs]
        y_open_test = np.array(
            [class_to_idx.get(label, ood_label_idx) for label in y_open_test_raw]
        )
        open_test_dataset = PTBXLDataset(
            x_open_test,
            y_open_test,
            mode='test',
            augment_impl=augment_impl,
        )
        open_test_id_count = int(mask_test.sum())
        open_test_ood_count = int((~mask_test).sum())

    print(f"[PTB-XL] Train Labeled: {len(labeled_idxs)}")
    print(
        f"[PTB-XL] Sampling Rate: {sampling_rate}Hz | "
        + f"Split Protocol: {getattr(args, 'ptbxl_split_protocol', 'random_811')}"
    )
    split_mode = getattr(args, 'ptbxl_split_mode', 'strict_mismatch')
    if split_mode == 'all_train_unique':
        print(
            f"[PTB-XL] Train Unlabeled: {len(unlabeled_idxs)} "
            + "(all unique train samples; no OOD duplication)"
        )
    else:
        print(
            f"[PTB-XL] Train Unlabeled: {len(unlabeled_idxs)} "
            + f"(Target Ratio: {args.mismatch_ratio}, Split Mode: {split_mode})"
        )
    print(
        f"[PTB-XL] Train Unlabeled Composition: ID={len(ul_id_idxs)}, "
        + f"OOD={len(ul_ood_idxs)}, OOD Fraction={len(ul_ood_idxs) / max(len(unlabeled_idxs), 1):.4f}"
    )
    if extra_ood_needed > 0:
        print(f"[PTB-XL] Extra OOD duplicates added for approx_all_data: {extra_ood_needed}")
    print(f"[PTB-XL] Validation: {len(val_dataset)}")
    print(f"[PTB-XL] Test: {len(test_dataset)}")
    print(
        f"[PTB-XL] Open Test: {len(open_test_dataset)} "
        + f"(ID: {open_test_id_count}, OOD: {open_test_ood_count})"
    )
    
    return (
        train_labeled_dataset,
        train_unlabeled_dataset,
        val_dataset,
        test_dataset,
        open_test_dataset,
    )