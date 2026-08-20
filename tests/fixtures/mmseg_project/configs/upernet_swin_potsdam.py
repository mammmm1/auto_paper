_base_ = [
    "../_base_/models/upernet_swin.py",
    "../_base_/datasets/potsdam.py",
]

crop_size = (512, 512)

model = dict(
    type="EncoderDecoder",
    data_preprocessor=dict(
        type="SegDataPreProcessor",
        mean=[123.675, 116.28, 103.53],
        std=[58.395, 57.12, 57.375],
        bgr_to_rgb=True,
        size=crop_size,
        pad_val=0,
        seg_pad_val=255,
    ),
    backbone=dict(
        type="SwinTransformer",
        embed_dims=96,
        out_indices=(0, 1, 2, 3),
    ),
    decode_head=dict(
        type="LayerBiasUPerHead",
        in_channels=[96, 192, 384, 768],
        in_index=[0, 1, 2, 3],
        channels=512,
        pool_scales=(1, 2, 3, 6),
        num_classes=6,
        align_corners=False,
        loss_decode=dict(type="CrossEntropyLoss", use_sigmoid=False, loss_weight=1.0),
    ),
    auxiliary_head=dict(
        type="FCNHead",
        in_channels=384,
        in_index=2,
        channels=256,
        num_classes=6,
        align_corners=False,
    ),
)

train_dataloader = dict(
    dataset=dict(
        type="PotsdamDataset",
        pipeline=[dict(type="RandomCrop", crop_size=crop_size)],
    )
)
