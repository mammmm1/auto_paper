_base_ = ["./faster-rcnn_r50_fpn.py"]

model = dict(
    type="FasterRCNN",
    backbone=dict(
        type="SwinTransformer",
        embed_dims=96,
        out_indices=(0, 1, 2, 3),
    ),
    neck=dict(
        type="ScaleBiasUnit",
        in_channels=[96, 192, 384, 768],
        out_channels=256,
        num_outs=5,
    ),
    roi_head=dict(
        type="StandardRoIHead",
        bbox_head=dict(type="Shared2FCBBoxHead", num_classes=15),
    ),
)

train_dataloader = dict(dataset=dict(type="DOTADataset"))
