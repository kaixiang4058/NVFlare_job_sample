import torch
import torch.nn as nn
from typing import List

from timm import create_model
from networks.module import DecoderBlock
from networks.initialize import initialize_decoder

class Unet(nn.Module):
    def __init__(self, encoder_name='resnest26d', classes=2, decoder_channels=(256, 128, 64)):
        super().__init__()

        self.encoder = create_model(
            encoder_name, features_only=True, in_chans=3, pretrained=True)

        encoder_channels = self.encoder.feature_info.channels()[::-1][:4]

        self.decoder = UnetDecoder(
            encoder_channels=encoder_channels,
            decoder_channels=decoder_channels,
        )

        channel = decoder_channels[-1]
        self.representer = nn.Sequential(
            nn.Conv2d(channel, channel, kernel_size=3, stride=1, padding=1, bias=True),
            nn.BatchNorm2d(channel),
            nn.ReLU(inplace=True),
            nn.Dropout2d(0.1),
            nn.Conv2d(channel, channel, kernel_size=3, stride=1, padding=1, bias=True),
            nn.BatchNorm2d(channel),
            nn.ReLU(inplace=True),
            nn.Dropout2d(0.1),
            nn.Conv2d(channel, channel, kernel_size=1)
        )

        self.classifier = nn.Sequential(
            nn.Conv2d(channel, channel, kernel_size=3, stride=1, padding=1, bias=True),
            nn.BatchNorm2d(channel),
            nn.ReLU(inplace=True),
            nn.Dropout2d(0.1),
            nn.Conv2d(channel, channel, kernel_size=3, stride=1, padding=1, bias=True),
            nn.BatchNorm2d(channel),
            nn.ReLU(inplace=True),
            nn.Dropout2d(0.1),
            nn.Conv2d(channel, classes, kernel_size=1, stride=1, padding=0, bias=True),
        )

        initialize_decoder(self.representer)
        initialize_decoder(self.classifier)

    def forward(self, inputs):
        x = self.encoder(inputs)
        x.reverse()
        x = self.decoder(x)

        pred = self.classifier(x)
        rep = self.representer(x)

        return {
            "pred" : pred,
            "rep" : rep
        }

class UnetDecoder(nn.Module):

    def __init__(
            self,
            encoder_channels,
            decoder_channels=(256, 128, 64),
            act_layer=nn.ReLU,
            norm_layer=nn.BatchNorm2d,
            block=DecoderBlock,
    ):
        super().__init__()

        conv_args = dict(norm_layer=norm_layer, act_layer=act_layer)

        in_channels = [in_chs + skip_chs for in_chs, skip_chs in zip(
            [encoder_channels[0]] + list(decoder_channels[:-1]),
            list(encoder_channels[1:]))]
        out_channels = decoder_channels

        self.blocks = nn.ModuleList()
        for in_chs, out_chs in zip(in_channels, out_channels):
            self.blocks.append(block(in_chs, out_chs, **conv_args))

        initialize_decoder(self.blocks)

    def forward(self, x: List[torch.Tensor]):
        skips = x[1:]
        x = x[0]
        for i, b in enumerate(self.blocks):
            x = b(x, skips[i])

        return x