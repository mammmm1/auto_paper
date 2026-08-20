from mmseg.registry import DATASETS


@DATASETS.register_module()
class PotsdamDataset:
    METAINFO = {
        "classes": ("impervious", "building", "low_vegetation", "tree", "car", "clutter"),
    }

    def __init__(self, data_root, pipeline=None):
        self.data_root = data_root
        self.pipeline = pipeline or []
