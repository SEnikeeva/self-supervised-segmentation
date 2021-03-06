import torch.nn as nn
import torch
from torch.nn import functional as f


class DenseCL(nn.Module):

    def __init__(self, backbone_q, backbone_k, dict_size=65536, dim=128, m=0.999, tau=0.2, is_cuda=True):

        super(DenseCL, self).__init__()

        self.dim = dim
        self.m = m
        self.tau = tau
        self.is_cuda = is_cuda

        self.encoder_q = backbone_q
        self.encoder_k = backbone_k

        for param_q, param_k in zip(self.encoder_q.parameters(), self.encoder_k.parameters()):
            param_k.data.copy_(param_q.data)
            param_k.requires_grad = False

        self.dict_size = dict_size

        # dim x dict_size for multiplication
        self.register_buffer("queue_g", torch.randn(dim, self.dict_size))
        self.register_buffer("queue_d", torch.randn(dim, self.dict_size))
        self.queue_g = f.normalize(self.queue_g, dim=0)
        self.queue_d = f.normalize(self.queue_d, dim=0)

        self.register_buffer("ptr", torch.zeros(1, dtype=torch.long))

    @torch.no_grad()
    def momentum_update_key_encoders(self):
        for param_q, param_k in zip(self.encoder_q.parameters(), self.encoder_k.parameters()):
            param_k.data = param_k.data * self.m + param_q.data * (1. - self.m)

    @torch.no_grad()
    def update_queues(self, k_g, k_d):
        k_d = f.normalize(k_d.mean(dim=2), dim=1)  # global average pooling
        batch_size = k_g.shape[0]

        ptr = int(self.ptr)
        if ptr + batch_size > self.dict_size:
            part_size = self.dict_size - ptr
            self.queue_g[:, ptr:] = k_g.T[:, :part_size]
            self.queue_g[:, :batch_size - part_size] = k_g.T[:, part_size:]
            self.queue_d[:, ptr:] = k_d.T[:, :part_size]
            self.queue_d[:, :batch_size - part_size] = k_d.T[:, part_size:]
            ptr = batch_size - part_size
        else:
            self.queue_g[:, ptr:ptr + batch_size] = k_g.T
            self.queue_d[:, ptr:ptr + batch_size] = k_d.T
            ptr = (ptr + batch_size) % self.dict_size  # move pointer

        self.ptr[0] = ptr

    # TODO: add shuffle
    def forward(self, in_q, in_k):

        bs = in_k.size(0)
        g_q, d_q, feat_q = self.encoder_q(in_q)
        g_q = f.normalize(g_q, dim=1)  # l2 normalized feature vector
        d_q = d_q.view(bs, d_q.size(1), -1)
        feat_q = feat_q.view(bs, feat_q.size(1), -1)
        d_q = f.normalize(d_q, dim=1)  # l2 normalized feature vector

        with torch.no_grad():

            self.momentum_update_key_encoders()
            g_k, d_k, feat_k = self.encoder_k(in_k)
            g_k = f.normalize(g_k, dim=1)  # l2 normalized feature vector
            d_k = d_k.view(bs, d_k.size(1), -1)
            d_k = f.normalize(d_k, dim=1)  # l2 normalized feature vector
            feat_k = feat_k.view(bs, feat_k.size(1), -1)

            feat_k = f.normalize(feat_k, dim=1)  # l2 normalized feature vector
            feat_q = f.normalize(feat_q, dim=1)  # l2 normalized feature vector

            cosine = torch.einsum('bqi,bqj->bij', feat_k, feat_q)  # the cosine similarity matrix
            match_idx = cosine.argmax(dim=1)
            d_q = d_q.gather(2, match_idx.unsqueeze(1).expand(-1, self.dim, -1))

        output_pos_g = torch.einsum('bd,bd->b', [g_q, g_k]).view(bs, 1)
        output_neg_g = torch.einsum('bd,dq->bq', [g_q, self.queue_g.clone().detach()])
        output_g = torch.concat((output_pos_g, output_neg_g), dim=1) / self.tau
        if self.is_cuda:
            target_g = torch.zeros(output_g.size(0), dtype=torch.long).cuda()
        else:
            target_g = torch.zeros(output_g.size(0), dtype=torch.long)

        output_pos_d = torch.einsum('bdz,bdz->bz', [d_k, d_q]).view(bs, 1, d_q.size(-1))
        output_neg_d = torch.einsum('bdz,dq->bqz', [d_q, self.queue_d.clone().detach()])
        output_d = torch.concat((output_pos_d, output_neg_d), dim=1) / self.tau
        if self.is_cuda:
            target_d = torch.zeros((output_d.size(0), output_d.size(-1)), dtype=torch.long).cuda()
        else:
            target_d = torch.zeros((output_d.size(0), output_d.size(-1)), dtype=torch.long)

        self.update_queues(g_k, d_k)
        return output_g, target_g, output_d, target_d
