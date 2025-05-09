import torch
import torch.nn as nn
import torch.nn.functional as F

bn_eps = 1e-5
bn_momentum = 0.1


def _l2_normalize(d):
    # Normalizing per batch axis
    d_reshaped = d.view(d.shape[0], -1, *(1 for _ in range(d.dim() - 2)))
    d /= torch.norm(d_reshaped, dim=1, keepdim=True) + 1e-8
    return d


def get_r_adv_t(x, decoder1, decoder2, it=1, xi=1e-1, eps=10.0):

    # stop bn
    decoder1.eval()
    decoder2.eval()
    
    x_detached = x.detach()
    with torch.no_grad():
        pred = F.softmax((decoder1(x) + decoder2(x))/2, dim=1)

    d = torch.rand(x.shape).sub(0.5).to(x.device)
    d = _l2_normalize(d)

    # assist students to find the effective va-noise
    for _ in range(it):
        d.requires_grad_()
        pred_hat = (decoder1(x_detached + xi * d) + decoder2(x_detached + xi * d))/2
        logp_hat = F.log_softmax(pred_hat, dim=1)
        adv_distance = F.kl_div(logp_hat, pred, reduction='batchmean')
        adv_distance.backward()
        d = _l2_normalize(d.grad)
        decoder1.zero_grad()
        decoder2.zero_grad()

    r_adv = d * eps

    # reopen bn, but freeze other params.
    # https://discuss.pytorch.org/t/why-is-it-when-i-call-require-grad-false-on-all-my-params-my-weights-in-the-network-would-still-update/22126/16
    decoder1.train()
    decoder2.train()
    return r_adv


class upsample(nn.Module):
    def __init__(self, in_channels, out_channels, data_shape,
                 norm_act=nn.BatchNorm2d):
        super(upsample, self).__init__()
        self.data_shape = data_shape
        self.last_conv = nn.Sequential(nn.Conv2d(in_channels, in_channels, kernel_size=3, stride=1, padding=1, bias=False),
                                       norm_act(in_channels, momentum=bn_momentum),
                                       nn.ReLU(),
                                       nn.Conv2d(in_channels, in_channels, kernel_size=3, stride=1, padding=1, bias=False),
                                       norm_act(in_channels, momentum=bn_momentum),
                                       nn.ReLU())
        self.classifier = nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=True)

    def forward(self, x, data_shape=None):
        f = self.last_conv(x)
        pred = self.classifier(f)
        if self.training:
            h, w = self.data_shape[0], self.data_shape[1]
        else:
            if data_shape is not None:
                h, w = data_shape[0], data_shape[1]
            else:
                h, w = self.data_shape[0], self.data_shape[1]

        return F.interpolate(pred, size=(h, w), mode='bilinear', align_corners=True)


class DecoderNetwork(nn.Module):
    def __init__(self, num_classes,
                 data_shape,
                 conv_in_ch=256):

        super(DecoderNetwork, self).__init__()
        self.upsample = upsample(conv_in_ch, num_classes, norm_act=torch.nn.BatchNorm2d,
                                 data_shape=data_shape)
        self.business_layer = []
        self.business_layer.append(self.upsample.last_conv)
        self.business_layer.append(self.upsample.classifier)

    def forward(self, f, data_shape=None):
        pred = self.upsample(f, data_shape)
        return pred


class VATDecoderNetwork(nn.Module):
    def __init__(self, num_classes,
                 data_shape,
                 conv_in_ch=256):

        super(VATDecoderNetwork, self).__init__()
        self.upsample = upsample(conv_in_ch, num_classes, norm_act=torch.nn.BatchNorm2d,
                                 data_shape=data_shape)
        self.business_layer = []
        self.business_layer.append(self.upsample.last_conv)
        self.business_layer.append(self.upsample.classifier)

    def forward(self, f, data_shape=None, t_model=None):
        if t_model is not None:
            r_adv = get_r_adv_t(f, t_model[0], t_model[1], it=1, xi=1e-6, eps=2.0)
            f = f + r_adv

        pred = self.upsample(f, data_shape)
        return pred


