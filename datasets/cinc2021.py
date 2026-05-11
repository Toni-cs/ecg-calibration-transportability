import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset
import os
from sklearn.model_selection import train_test_split
from tqdm import tqdm
from datasets.transforms.ecg_transforms import get_ptbxl_augmenter

# CINC 2021 Superclass
ID_CLASSES = ['Normal', 'Rhythm', 'CD']  
OOD_CLASSES = ['ST', 'Other']
ALL_CLASSES = ID_CLASSES + OOD_CLASSES

class CINC2021Dataset(Dataset):
    def __init__(self, data_paths, labels, transform=None, mode='labeled', augment_impl='ecg'):
        # data_paths: list of absolute paths to .npy files
        self.data_paths = data_paths
        self.labels = labels
        self.targets = labels
        
        self.transform = transform
        self.mode = mode 
        self.weak_aug = get_ptbxl_augmenter(augment_impl, 'weak')
        self.strong_aug = get_ptbxl_augmenter(augment_impl, 'strong')
        self.indices = list(range(len(self.data_paths)))

    def set_index(self, indexes=None):
        if indexes is None:
            self.indices = list(range(len(self.data_paths)))
        else:
            if torch.is_tensor(indexes):
                indexes = indexes.cpu().tolist()
            elif isinstance(indexes, np.ndarray):
                indexes = indexes.tolist()
            self.indices = indexes

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, idx):
        real_idx = self.indices[idx]
        
        filepath = self.data_paths[real_idx]
        # numpy.load reads the [12, 5000] array
        # ptbxl model expects transpose(1, 0) equivalent so it becomes [5000, 12]?
        # Wait, in ptbxl.py it did: x = self.data[real_idx].transpose(1, 0).astype(np.float32)
        # If PTBXL data was [N, 1000, 12], transpose(1,0) makes it [12, 1000]?? No, it makes [1000, 12] -> [12, 1000]?
        # Actually in ECGMatch shape is [12, 5000] so we don't transpose if model expects [12, 5000].
        # In run_SAFEECGMATCH.py resnet1d takes input [B, 12, seq_len]. 
        # CinC data is already [12, 5000]. PTBXL is [N, 5000, 12], so transpose(1, 0) was used per item? Wait, if item is [5000, 12], transpose(1,0) -> [12, 5000]. 
        # Since our CinC 2021 data is ALREADY [12, 5000], we DO NOT need to transpose.
        x = np.load(filepath).astype(np.float32)
        y = self.labels[real_idx]

        w0 = self.weak_aug(x.copy()).astype(np.float32)
        w1 = self.weak_aug(x.copy()).astype(np.float32)
        w = self.weak_aug(x.copy()).astype(np.float32)
        s = self.strong_aug(x.copy()).astype(np.float32)

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
                "weak_img": x_w.astype(np.float32),
                "strong_img": x_s.astype(np.float32),
                "y": y,  
                "idx": real_idx,         
                "x_ulb_w": w,
                "x_ulb_s": s,
                "y_ulb": y,
                "unlabel_y": y,
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
                "x": x_lb.astype(np.float32),
                "y_lb": y,
                "y": y,
                "idx": real_idx,
                "inputs_x": w,
                "targets_x": y
            }
        elif self.mode == 'train_lb': 
            return {
                "idx_lb": idx,
                "x_lb_w_0": w0,
                "x_lb_w_1": w1,
                "y_lb": y
            }
        elif self.mode == 'train_ulb': 
            return {
                "idx_ulb": idx,
                "x_ulb_w_0": w0,
                "x_ulb_w_1": w1,
                "y_ulb": y
            }
        elif self.mode == 'train_ulb_selected':
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
            }
        return x, y

def load_raw_cinc2021(root):
    print(f"Loading metadata from {root}")
    csv_path = os.path.join(root, 'metadata_single_label.csv')
    df = pd.read_csv(csv_path)
    
    # Generate full paths to .npy files using 'id' (record name)
    data_paths = np.array([os.path.join(root, 'data', f"{r}.npy") for r in df['id']])
    y_str = df['label'].values
    return data_paths, y_str, df

def _split_cinc2021_indices(y_str, args):
    indices = np.arange(len(y_str))
    
    # 8:1:1 split mapping
    train_idxs, temp_idxs, y_train, y_temp = train_test_split(
        indices, y_str, test_size=0.2, stratify=y_str, random_state=42
    )
    val_idxs, test_idxs, _, _ = train_test_split(
        temp_idxs, y_temp, test_size=0.5, stratify=y_temp, random_state=42
    )
    return train_idxs, val_idxs, test_idxs

def get_cinc2021(args, root):
    data_paths, y_str, df = load_raw_cinc2021(root)
    augment_impl = getattr(args, 'ptbxl_augment', 'ecg')
    
    local_id_classes = getattr(args, 'cinc_id_classes', None)
    if not local_id_classes:
        local_id_classes = ID_CLASSES
    local_ood_classes = getattr(args, 'cinc_ood_classes', None)
    if not local_ood_classes:
        local_ood_classes = OOD_CLASSES

    class_to_idx = {cls: i for i, cls in enumerate(local_id_classes)}
    ood_label_idx = len(local_id_classes)

    # --- EXACT NUMBERS OVERRIDE FOR 60% OOD (fixed_volume_mismatch) ---
    if getattr(args, 'ptbxl_split_mode', '') == 'fixed_volume_mismatch' and getattr(args, 'mismatch_ratio', 0.0) == 0.6:
        rs = np.random.RandomState(42)
        
        all_id_indices = np.where(np.isin(y_str, local_id_classes))[0]
        all_ood_indices = np.where(np.isin(y_str, local_ood_classes))[0]
        
        id_by_class = {c: np.where(y_str == c)[0] for c in local_id_classes}
        
        # Stratified Val: 4277, Test: 4276 (same as baseline but from new classes)
        val_idxs, test_idxs, train_id_idxs = [], [], []
        # Calculate exactly how many items per class to draw to reach 4277 and 4276
        total_id_count = len(all_id_indices)
        for c in local_id_classes:
            c_idxs = id_by_class[c].copy()
            rs.shuffle(c_idxs)
            fraction = len(c_idxs) / total_id_count
            n_val = int(round(4277 * fraction))
            n_test = int(round(4276 * fraction))
            val_idxs.extend(c_idxs[:n_val])
            test_idxs.extend(c_idxs[n_val : n_val+n_test])
            train_id_idxs.extend(c_idxs[n_val+n_test:])
            
        # Adjust rounding errors for Val/Test to be exactly 4277 / 4276
        rs.shuffle(val_idxs)
        rs.shuffle(test_idxs)
        if len(val_idxs) > 4277:
            train_id_idxs.extend(val_idxs[4277:])
            val_idxs = val_idxs[:4277]
        elif len(val_idxs) < 4277:
            diff = 4277 - len(val_idxs)
            val_idxs.extend(train_id_idxs[:diff])
            train_id_idxs = train_id_idxs[diff:]
            
        if len(test_idxs) > 4276:
            train_id_idxs.extend(test_idxs[4276:])
            test_idxs = test_idxs[:4276]
        elif len(test_idxs) < 4276:
            diff = 4276 - len(test_idxs)
            test_idxs.extend(train_id_idxs[:diff])
            train_id_idxs = train_id_idxs[diff:]
            
        labeled_idxs = []
        unlabeled_id_pool = []
        
        # Pull exactly n_label_per_class per class from train_id_idxs
        for c in local_id_classes:
            c_idxs = [idx for idx in train_id_idxs if y_str[idx] == c]
            rs.shuffle(c_idxs)
            n_take = min(len(c_idxs), getattr(args, 'n_label_per_class', 104))
            labeled_idxs.extend(c_idxs[:n_take])
            unlabeled_id_pool.extend(c_idxs[n_take:])
            
        rs.shuffle(unlabeled_id_pool)
        ul_id_idxs = np.array(unlabeled_id_pool[:12331], dtype=int)
        
        # OOD pool
        rs.shuffle(all_ood_indices)
        ul_ood_idxs = np.array(all_ood_indices[:18495], dtype=int)
        
        unlabeled_idxs = np.concatenate([ul_id_idxs, ul_ood_idxs])
        np.random.shuffle(unlabeled_idxs)
        val_idxs = np.array(val_idxs)
        test_idxs = np.array(test_idxs)

    else:
        train_idxs, val_idxs, test_idxs = _split_cinc2021_indices(y_str, args)

        id_indices = {c: [] for c in local_id_classes}
        ood_indices = {c: [] for c in local_ood_classes}

        for idx in train_idxs:
            label = y_str[idx]
            if label in local_id_classes:
                id_indices[label].append(idx)
            elif label in local_ood_classes:
                ood_indices[label].append(idx)

        labeled_idxs = []
        unlabeled_pool_idxs = []

        for c in local_id_classes:
            idxs = np.array(id_indices[c])
            np.random.shuffle(idxs)
            n_take = min(len(idxs), args.n_label_per_class)
            labeled_idxs.extend(idxs[:n_take])
            unlabeled_pool_idxs.extend(idxs[n_take:]) 

        ul_ood_idxs = []
        for c in local_ood_classes:
            ul_ood_idxs.extend(ood_indices[c])
            
        ul_id_idxs = np.array(unlabeled_pool_idxs, dtype=int)
        ul_ood_idxs = np.array(ul_ood_idxs, dtype=int)
        
        target_n_ood = len(ul_ood_idxs)
        ratio = args.mismatch_ratio
        
        if ratio > 0:
            target_n_id = int(target_n_ood * (1 - ratio) / ratio)
        else:
            target_n_id = len(ul_id_idxs)
            target_n_ood = 0
            ul_ood_idxs = np.array([])
            
        if len(ul_id_idxs) >= target_n_id:
            np.random.shuffle(ul_id_idxs)
            ul_id_idxs = ul_id_idxs[:target_n_id]
        else:
            pass
            
        unlabeled_idxs = np.concatenate([ul_id_idxs, ul_ood_idxs])
        np.random.shuffle(unlabeled_idxs)

    # 3. 객체 생성
    paths_lb = data_paths[labeled_idxs]
    y_lb = np.array([class_to_idx[y_str[i]] for i in labeled_idxs])
    train_labeled_dataset = CINC2021Dataset(paths_lb, y_lb, mode='labeled', augment_impl=augment_impl)

    paths_ulb = data_paths[unlabeled_idxs]
    y_ulb = []
    for i in unlabeled_idxs:
        label = y_str[i]
        if label in local_id_classes:
            y_ulb.append(class_to_idx[label])
        else:
            y_ulb.append(ood_label_idx)
    y_ulb = np.array(y_ulb)
    train_unlabeled_dataset = CINC2021Dataset(paths_ulb, y_ulb, mode='unlabeled', augment_impl=augment_impl)

    # Val Set
    paths_val = data_paths[val_idxs]
    y_val_raw = y_str[val_idxs]
    mask_val = np.isin(y_val_raw, local_id_classes)
    paths_val = paths_val[mask_val]
    y_val = np.array([class_to_idx[lbl] for lbl in y_val_raw[mask_val]])
    val_dataset = CINC2021Dataset(paths_val, y_val, mode='test', augment_impl=augment_impl)

    # Test Set
    paths_test = data_paths[test_idxs]
    y_test_raw = y_str[test_idxs]
    mask_test = np.isin(y_test_raw, local_id_classes)
    paths_test = paths_test[mask_test]
    y_test = np.array([class_to_idx[lbl] for lbl in y_test_raw[mask_test]])
    test_dataset = CINC2021Dataset(paths_test, y_test, mode='test', augment_impl=augment_impl)

    open_test_dataset = test_dataset

    print(f"[CINC-2021] Train Labeled: {len(labeled_idxs)}")
    print(f"[CINC-2021] Train Unlabeled: {len(unlabeled_idxs)} (Target Ratio: {args.mismatch_ratio})")
    print(f"[CINC-2021] Train Unlabeled Composition: ID={len(ul_id_idxs)}, OOD={len(ul_ood_idxs)}, OOD Fraction={len(ul_ood_idxs) / max(len(unlabeled_idxs), 1):.4f}")
    print(f"[CINC-2021] Validation: {len(val_dataset)}")
    print(f"[CINC-2021] Test: {len(test_dataset)}")
    
    return train_labeled_dataset, train_unlabeled_dataset, val_dataset, test_dataset, open_test_dataset
