from mmseg.models.decode_heads import UPerHead
from mmseg.registry import MODELS


@MODELS.register_module()
class LayerBiasUPerHead(UPerHead):
    def __init__(
        self,
        in_channels,
        in_index,
        channels=512,
        scale_bias=(1.2, 1.1, 0.9, 0.8),
        **kwargs,
    ):
        super().__init__(
            in_channels=in_channels,
            in_index=in_index,
            channels=channels,
            **kwargs,
        )
        self.scale_bias = scale_bias

    def forward(self, inputs):
        return super().forward(inputs)
