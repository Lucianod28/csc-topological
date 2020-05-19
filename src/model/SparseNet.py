import torch
import torch.nn as nn
import torch.nn.functional as F


class SparseNet(nn.Module):

    def __init__(self, K:int, M:int, F:int, S:int, R_lr:float=0.1, lmda:float=5e-3, device=None):
        super(SparseNet, self).__init__()
        self.K = K
        self.M = M
        self.R_lr = R_lr
        self.lmda = lmda
        # synaptic weights
        self.device = torch.device("cpu") if device is None else device
        conv_out_width = (self.M - 1) * S + (F-1) + 1
        self.U = nn.Linear(conv_out_width ** 2, self.M ** 2, bias=False).to(self.device)
        # responses
        self.R = None
        self.normalize_weights()
        # transpose convolution
        self.conv_trans = nn.ConvTranspose2d(in_channels=self.K, out_channels=1,
                kernel_size=F, stride=S).to(self.device)
        self.running_ista_loss = 0.

    def ista_(self, img_batch):
        # create R
        self.R = torch.zeros((img_batch.shape[0], self.K, self.M, self.M),
                requires_grad=True, device=self.device)
        converged = False
        # update R
        optim = torch.optim.SGD([{'params': self.R, "lr": self.R_lr}])
        # train
        self.ista_loss = 0.
        self.ista_loss_count = 0.
        while not converged:
            old_R = self.R.clone().detach()
            # pred
            conv_transed = self.conv_trans(self.R).reshape(img_batch.shape[0], -1)
            #print('deconvolved shape')
            #print(conv_transed.shape)
            pred = self.U(conv_transed)
            #print('pred shape')
            #print(pred.shape)
            # loss
            loss = ((img_batch - pred) ** 2).sum()
            self.ista_loss += loss.item()
            self.ista_loss_count += 1
            loss.backward()
            # update R in place
            optim.step()
            # zero grad
            self.zero_grad()
            # prox
            self.R.data = SparseNet.soft_thresholding_(self.R, self.lmda)
            # convergence
            #print(torch.norm(self.R - old_R) / torch.norm(old_R))
            converged = torch.norm(self.R - old_R) / torch.norm(old_R) < 0.01

    @staticmethod
    def soft_thresholding_(x, alpha):
        with torch.no_grad():
            rtn = F.relu(x - alpha) - F.relu(-x - alpha)
        return rtn.data

    def zero_grad(self):
        self.R.grad.zero_()
        self.U.zero_grad()

    def normalize_weights(self):
        with torch.no_grad():
            self.U.weight.data = F.normalize(self.U.weight.data, dim=0)

    def forward(self, img_batch):
        # first fit
        self.ista_(img_batch)
        # now predict again
        conv_transed = self.conv_trans(self.R).reshape(img_batch.shape[0], -1)
        pred = self.U(conv_transed)
        return pred

    def get_ista_loss(self):
        return self.ista_loss / self.ista_loss_count
