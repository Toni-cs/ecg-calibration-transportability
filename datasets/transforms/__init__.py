from __future__ import annotations

from .ecg_transforms import *


class SemiAugment:
	def __init__(self, *args, **kwargs):
		pass

	def __call__(self, x):
		return x


class TestAugment:
	def __init__(self, *args, **kwargs):
		pass

	def __call__(self, x):
		return x