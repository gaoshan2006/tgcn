from __future__ import print_function
import argparse
import torch
import torch.nn as nn
from tgcn.nn.gcn import TGCNCheb, TGCNCheb_H, GCNCheb, gcn_pool
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
import numpy as np
import autograd.numpy as npa
# from data import load_mnist
from load.data_hcp import load_hcp_example
import gcn.graph as graph
import gcn.coarsening as coarsening
import sklearn.metrics


def perm_data_time(x, indices):
    """
    Permute data matrix, i.e. exchange node ids,
    so that binary unions form the clustering tree.
    """
    if indices is None:
        return x

    N, M, Q = x.shape
    Mnew = len(indices)
    assert Mnew >= M
    xnew = np.empty((N, Mnew, Q))
    for i,j in enumerate(indices):
        # Existing vertex, i.e. real data.
        if j < M:
            xnew[:, i, :] = x[:, j, :]
        # Fake vertex because of singeltons.
        # They will stay 0 so that max pooling chooses the singelton.
        # Or -infty ?
        else:
            xnew[:, i, :] = np.zeros((N, Q))
    return xnew


def load_hcp_tcgn(device):

    time_series, labels, As = load_hcp_example()

    normalized_laplacian = True
    coarsening_levels = 4

    graphs, perm = coarsening.coarsen(As[0], levels=coarsening_levels, self_connections=False)
    # L = [graph.laplacian(A, normalized=normalized_laplacian) for A in graphs]
    L = [torch.tensor(graph.rescale_L(graph.laplacian(A, normalized=normalized_laplacian).todense(), lmax=2),
                      dtype=torch.float).to(device) for A in graphs]

    # idx_train = range(17*512)
    idx_train = range(int(0.8*time_series.shape[0]))
    print('Size of train set: {}'.format(len(idx_train)))

    idx_test = range(len(idx_train), time_series.shape[0])
    print('Size of test set: {}'.format(len(idx_test)))
    # idx_train = range(5*512)
    # idx_test = range(len(idx_train), 10*512)

    train_data = time_series[idx_train]
    train_labels = labels[idx_train]
    test_data = time_series[idx_test]
    test_labels = labels[idx_test]

    train_data = perm_data_time(train_data, perm)
    test_data = perm_data_time(test_data, perm)


    return L, train_data, test_data, train_labels, test_labels


# def get_mnist_data_tgcn(perm):
#
#     N, train_data, train_labels, test_data, test_labels = load_mnist()
#
#     H = 12
#
#     train_data = np.transpose(np.tile(train_data, (H, 1, 1)), axes=[1, 2, 0])
#     test_data = np.transpose(np.tile(test_data, (H, 1, 1)), axes=[1, 2, 0])
#
#     idx_train = range(2*512)
#     idx_test = range(2*512)
#
#     train_data = train_data[idx_train]
#     train_labels = train_labels[idx_train]
#     test_data = test_data[idx_test]
#     test_labels = test_labels[idx_test]
#
#     train_data = perm_data_time(train_data, perm)
#     test_data = perm_data_time(test_data, perm)
#
#     del perm
#
#     return train_data, test_data, train_labels, test_labels


class NetTGCN(nn.Module):

    def __init__(self, L):
        super(NetTGCN, self).__init__()
        # f: number of input filters
        # g: number of output layers
        # k: order of chebyshev polynomials
        # c: number of classes
        # n: number of vertices at coarsening level

        f1, g1, k1, h1 = 1, 96, 10, 15
        self.tgcn1 = TGCNCheb_H(L[0], f1, g1, k1, h1)

        self.drop1 = nn.Dropout(0.1)

        g2, k2 = 96, 10
        # self.tgcn2 = TGCNCheb_H(L[0], g1, g2, k2, h1)
        self.gcn2 = GCNCheb(L[0], g1, g2, k2)

        self.dense1_bn = nn.BatchNorm1d(50)
        # n1 = L[0].shape[0]
        # # n2 = L[0].shape[0]
        # c = 6
        # self.fc1 = nn.Linear(n1 * g1, c)

        n2 = L[0].shape[0]
        d = 200
        self.fc1 = nn.Linear(n2 * g2, d)

        self.dense1_bn = nn.BatchNorm1d(d)
        self.drop2 = nn.Dropout(0.5)

        c = 6
        self.fc2 = nn.Linear(d, c)




    def forward(self, x):
        x = torch.tensor(npa.real(npa.fft.fft(x.to('cpu').numpy(), axis=2))).to('cuda')
        # x = torch.tensor(npa.real(npa.fft.fft(x.to('cpu').numpy(), axis=2))).to('cuda')
        x = self.tgcn1(x)
        x = F.relu(x)
        x = self.drop1(x)
        #x = gcn_pool(x)
        x = self.gcn2(x)
        x = F.relu(x)
        # x = self.dense1_bn(x)
        x = x.view(x.shape[0], -1)
        x = self.fc1(x)
        # x = F.relu(x)
        x = self.dense1_bn(x)
        x = F.relu(x)
        x = self.drop2(x)
        x = self.fc2(x)

        return F.log_softmax(x, dim=1)


# def create_graph():
#     def grid_graph(m, corners=False):
#         z = graph.grid(m)
#         dist, idx = graph.distance_sklearn_metrics(z, k=number_edges, metric=metric)
#         A = graph.adjacency(dist, idx)
#
#         # Connections are only vertical or horizontal on the grid.
#         # Corner vertices are connected to 2 neightbors only.
#         if corners:
#             import scipy.sparse
#             A = A.toarray()
#             A[A < A.max() / 1.5] = 0
#             A = scipy.sparse.csr_matrix(A)
#             print('{} edges'.format(A.nnz))
#
#         print("{} > {} edges".format(A.nnz // 2, number_edges * m ** 2 // 2))
#         return A
#
#     number_edges = 8
#     metric = 'euclidean'
#     normalized_laplacian = True
#     coarsening_levels = 4
#
#     A = grid_graph(28, corners=False)
#     # A = graph.replace_random_edges(A, 0)
#     graphs, perm = coarsening.coarsen(A, levels=coarsening_levels, self_connections=False)
#     # L = [graph.laplacian(A, normalized=normalized_laplacian) for A in graphs]
#     L = [torch.tensor(graph.rescale_L(graph.laplacian(A, normalized=normalized_laplacian).todense(), lmax=2),
#                       dtype=torch.float).to(device) for A in graphs]
#     # graph.plot_spectrum(L)
#     del A
#
#     return L, perm


def train(args, model, device, train_loader, optimizer, epoch):
    model.train()
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        target = torch.argmax(target, dim=1)
        k = 1.
        w = torch.tensor([1., k, k, k, k, k]).to(device)
        loss = F.nll_loss(output, target, weight=w)
        loss.backward()
        optimizer.step()
        if batch_idx % args.log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, batch_idx * len(data), len(train_loader.dataset),
                       100. * batch_idx / len(train_loader), loss.item()))


def test(args, model, device, test_loader):
    model.eval()
    test_loss = 0
    correct = 0
    cm = 0
    preds = torch.empty(0, dtype=torch.long).to(device)
    targets = torch.empty(0, dtype=torch.long).to(device)
    with torch.no_grad():
        for data_t, target_t in test_loader:
            data = data_t.to(device)
            target = target_t.to(device)
            output = model(data)
            target = torch.argmax(target, dim=1)
            test_loss += F.nll_loss(output, target, reduction='sum').item()  # sum up batch loss
            pred = output.max(1, keepdim=True)[1]  # get the index of the max log-probability
            preds = torch.cat((pred, preds))
            targets = torch.cat((target, targets))
            # cm = sklearn.metrics.confusion_matrix(target, pred)
            cm += sklearn.metrics.confusion_matrix(target.to('cpu').numpy(), pred.to('cpu').numpy())
            correct += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader.dataset)

    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct, len(test_loader.dataset),
        100. * correct / len(test_loader.dataset)))
    print(cm)
    print(cm.sum())
    print(sklearn.metrics.classification_report(targets.to('cpu').numpy(), preds.to('cpu').numpy()))


# class Dataset(torch.utils.data.Dataset):
#   'Characterizes a dataset for PyTorch'
#   def __init__(self, list_IDs, labels):
#         'Initialization'
#         self.labels = labels
#         self.list_IDs = list_IDs
#
#   def __len__(self):
#         'Denotes the total number of samples'
#         return len(self.list_IDs)
#
#   def __getitem__(self, index):
#         'Generates one sample of data'
#         # Select sample
#         X = torch.tensor(self.list_IDs[index])
#         # Load data and get label
#         y = self.labels[index]
#
#         return X, y


class Dataset(torch.utils.data.Dataset):
  'Characterizes a dataset for PyTorch'
  def __init__(self, images, labels):
        'Initialization'
        self.labels = labels
        self.images = images

  def __len__(self):
        'Denotes the total number of samples'
        return len(self.images)

  def __getitem__(self, index):
        'Generates one sample of data'
        # Select sample
        # X = torch.tensor(self.images[index], dtype=torch.float)
        X = self.images[index].astype('float32')
        # Load data and get label
        y = self.labels[index].astype('float32')

        return X, y


def main():
    # Training settings
    parser = argparse.ArgumentParser(description='PyTorch MNIST Example')
    parser.add_argument('--batch-size', type=int, default=512, metavar='N',
                        help='input batch size for training (default: 64)')
    parser.add_argument('--test-batch-size', type=int, default=1000, metavar='N',
                        help='input batch size for testing (default: 1000)')
    parser.add_argument('--epochs', type=int, default=50, metavar='N',
                        help='number of epochs to train (default: 10)')
    parser.add_argument('--lr', type=float, default=0.01, metavar='LR',
                        help='learning rate (default: 0.01)')
    parser.add_argument('--momentum', type=float, default=0.5, metavar='M',
                        help='SGD momentum (default: 0.5)')
    parser.add_argument('--no-cuda', action='store_true', default=False,
                        help='disables CUDA training')
    parser.add_argument('--seed', type=int, default=1, metavar='S',
                        help='random seed (default: 1)')
    parser.add_argument('--log-interval', type=int, default=10, metavar='N',
                        help='how many batches to wait before logging training status')

    parser.add_argument('--save-model', action='store_true', default=False,
                        help='For Saving the current Model')
    args = parser.parse_args()
    use_cuda = not args.no_cuda and torch.cuda.is_available()

    torch.manual_seed(args.seed)

    device = torch.device("cuda" if use_cuda else "cpu")

    # kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}
    # X = torch.einsum("nm,qmhf->qnhf", self.L, X)

    L, train_images, test_images, train_labels, test_labels = load_hcp_tcgn(device)

    training_set = Dataset(train_images, train_labels)
    train_loader = torch.utils.data.DataLoader(training_set, batch_size=args.batch_size)

    validation_set = Dataset(test_images, test_labels)
    test_loader = torch.utils.data.DataLoader(validation_set, batch_size=args.batch_size)


    # L_tensor = list()
    # for m in L:
    #     coo = m.tocoo()
    #     values = coo.data
    #     indices = np.vstack((coo.row, coo.col))
    #
    #     i = torch.LongTensor(indices)
    #     v = torch.FloatTensor(values)
    #     shape = coo.shape
    #
    #     m_tensor = torch.sparse.FloatTensor(i, v, torch.Size(shape)).to_dense()
    #     L_tensor.append(m_tensor)
    model = NetTGCN(L).to(device)

    optimizer = optim.SGD(model.parameters(), lr=args.lr, momentum=args.momentum)

    for epoch in range(1, args.epochs + 1):
        train(args, model, device, train_loader, optimizer, epoch)
        test(args, model, device, test_loader)

    if args.save_model:
        torch.save(model.state_dict(), "mnist_cnn.pt")


if __name__ == '__main__':
    main()



