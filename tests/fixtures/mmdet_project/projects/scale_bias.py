import torch
from mmdet.registry import MODELS


@MODELS.register_module()
class ScaleBiasUnit(torch.nn.Module):
    def __init__(self, in_channels, out_channels=256, num_outs=5):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.num_outs = num_outs

    def forward(self, inputs):
        return tuple(inputs)
