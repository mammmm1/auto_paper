from mmdet.registry import DATASETS


@DATASETS.register_module()
class DOTADataset:
    def __init__(self, data_root, pipeline=None):
        self.data_root = data_root
        self.pipeline = pipeline or []

    def __getitem__(self, index):
        raise IndexError(index)
