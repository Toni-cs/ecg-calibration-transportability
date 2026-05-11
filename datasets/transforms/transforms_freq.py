import torch

def to_frequency_domain(x):
    """
    시간 도메인 시계열 데이터를 주파수 도메인(진폭)으로 변환합니다.
    입력: x (B, C, L)
    출력: amplitude (B, C, L // 2 + 1)
    """
    # 실수형 FFT 수행 (Real FFT)
    fft_repr = torch.fft.rfft(x, dim=-1)
    # 진폭(Amplitude)만 추출 (Phase는 구조적 정보 보존을 위해 배제하거나 필요시 concat 가능)
    amplitude = torch.abs(fft_repr)
    
    return amplitude

def freq_strong_aug(amplitude, mask_ratio=0.15):
    """
    주파수 도메인의 진폭에 대해 Strong Augmentation (Frequency Masking)을 수행합니다.
    """
    B, C, L = amplitude.shape
    aug_amp = amplitude.clone()
    
    mask_len = int(L * mask_ratio)
    if mask_len == 0:
        return aug_amp
        
    for i in range(B):
        # 무작위로 마스킹할 시작 주파수 대역 선택
        start = torch.randint(0, L - mask_len, (1,)).item()
        aug_amp[i, :, start:start+mask_len] = 0.0 # 진폭을 0으로 만들어 정보 차단
        
    return aug_amp