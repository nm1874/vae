import os
import math
import torch
import torchvision
from torchvision import transforms
from torchvision.utils import save_image
from vae import VAE, vae_loss
import argparse
from torch import nn
# from models import VAE
from utils import make_gif, plot_elbocurve

input_size = 784

parser = argparse.ArgumentParser(description='VAE Example')

# parser.add_argument('--img-crop', type=int, default=148,
#                     help='size for center cropping (default: 148)')
parser.add_argument('--img-resize', type=int, default=28,
                    help='size for resizing (default: 28)')
parser.add_argument('--batch-size', type=int, default=128,
                    help='input batch size for training (default: 128)')
parser.add_argument('--epochs', type=int, default=200,
                    help='number of epochs to train (default: 200)')
parser.add_argument('--lr', type=float, default=1e-3,
                    help='learning rate (default: 1e-3)')
parser.add_argument('--valid-split', type=float, default=.2,
                    help='fraction of data for validation (default: 0.2)')
parser.add_argument('--kl-weight', type=float, default=1e-3,
                    help='weight of the KL loss (default: 1e-3)')
parser.add_argument('--filters', type=str, default='64, 128, 256, 512',
                    help=('number of filters for each conv. layer (default: '
                          + '\'64, 128, 256, 512\')'))
parser.add_argument('--kernel-sizes', type=str, default='3, 3, 3, 3',
                    help=('kernel sizes for each conv. layer (default: '
                          + '\'3, 3, 3, 3\')'))
parser.add_argument('--strides', type=str, default='2, 2, 2, 2',
                    help=('strides for each conv. layer (default: \'2, 2, 2, '
                          + '2\')'))
parser.add_argument('--latent-dim', type=int, default=128,
                    help='latent space dimension (default: 128)')
parser.add_argument('--batch-norm', type=int, default=1,
                    help=('whether to use or not batch normalization (default:'
                          + ' 1)'))
parser.add_argument('--seed', type=int, default=42,
                    help='random seed (default: 42)')
args = parser.parse_args()
args.filters = [int(item) for item in args.filters.split(',')]
args.kernel_sizes = [int(item) for item in args.kernel_sizes.split(',')]
args.strides = [int(item) for item in args.strides.split(',')]
args.batch_norm = bool(args.batch_norm)

# Device configuration
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# Build the data input pipeline
""" 
# this function might be helpful if you want to use binarized-MNIST in your experiments
# in this case, you shou set "transform=transforms.Compose([transforms.Lambda(binarize), transforms.ToTensor()])"
def binarize(greyscale_img):
    binary_img = greyscale_img.convert('1')
    return binary_img
"""

train_dataset = torchvision.datasets.MNIST(root='./data/MNIST', train=True, transform=transforms.ToTensor(), download=True)
test_dataset = torchvision.datasets.MNIST(root='./data/MNIST', train=False, transform=transforms.ToTensor(), download=True)
train_loader = torch.utils.data.DataLoader(dataset=train_dataset, batch_size=args.batch_size, shuffle=True)
test_loader = torch.utils.data.DataLoader(dataset=test_dataset, batch_size=args.batch_size, shuffle=False)


img_channels = 1
print('img_channels should be 1, actually is :', img_channels)

# Build the model by instantiating the class "VAE"
model = VAE(img_channels,
          args.img_resize,
          args.latent_dim,
          args.filters,
          args.kernel_sizes,
          args.strides,
          activation=nn.LeakyReLU,
          out_activation=nn.Tanh,
          batch_norm=args.batch_norm).to(device)
print(model)

def compute_elbo(x, reconst_x, mean, log_var):
    # ELBO(Evidence Lower Bound) is the objective of VAE, we train the model just to maximize the ELBO.
    
    reconst_error = -torch.nn.functional.binary_cross_entropy(reconst_x, x, reduction='sum')
    # see Appendix B from VAE paper: "Kingma and Welling. Auto-Encoding Variational Bayes. ICLR-2014."
    # -KL[q(z|x)||p(z)] = 0.5 * sum(1 + log(sigma^2) - mu^2 - sigma^2)
    kl_divergence = -0.5 * torch.sum(1 + log_var - mean.pow(2) - log_var.exp())
    elbo = (reconst_error - kl_divergence) / len(x)
    return elbo

# Select the optimizer
learning_rate = 1e-3
optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

# Create a folder to store the experiment results if it doesn't exist
results_dir = 'results/MNIST'
if not os.path.exists(results_dir):
    os.makedirs(results_dir)

# Save samples generated by the model before training
counter = 0
z = torch.randn((25, model.latent_dim)).to(device)
generated_imgs = model.decoder(z).view(-1, 1, 28, 28)
save_image(generated_imgs, os.path.join(results_dir, 'samples-0.png'), nrow=5)

# Start training
num_epochs = args.epochs
train_elbo = []
test_elbo = []
for epoch in range(1, num_epochs + 1):
    kl_weight=1e-3
    model.train()   # optional, only useful when your model includes BatchNorm layers or Dropout layers
    #switch: model == vae
    for i, (X, _) in enumerate(train_loader):
        # foward pass
        X = X.to(device)
        Xrec, z_mean, z_logvar = model(X)
        loss, reconst_loss, kl_loss = vae_loss(Xrec, X, z_mean, z_logvar,
                                                   kl_weight=kl_weight)
        n_gen=args.batch_size
        
        # backprop and optimize
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        
        # print the average loss on batches
        if (i + 1) % 100 == 0:
            print('Epoch {}/{}, Batch {}/{}, Aver_Loss: {:.2f}'.format(
                epoch, num_epochs, i + 1, math.ceil(len(train_dataset) / args.batch_size), loss.item()))
            
        # save samples generated by the model at the early training
        if epoch == 1:
            if (i + 1) == 10 or (i + 1) == 50 or (i + 1) == 100 or (i + 1) == 300 or (i + 1) == 500:
                counter += 1
                z = torch.randn((n_gen, model.latent_dim)).to(device)
                generated_imgs = model.decoder(z).view(-1, 1, 28, 28)
                save_image(generated_imgs, os.path.join(results_dir, 'samples-{}.png'.format(counter)), nrow=5)

    with torch.no_grad():
        model.eval()   # optional, corresponding to "model.train()"  
        # elbo_curve on training-set
        total_elbo = 0.
        for i, (X, _) in enumerate(train_loader):
            X = X.to(device)
            Xrec, z_mean, z_logvar = model(X)
            total_elbo += vae_loss(Xrec, X, z_mean, z_logvar,
                                       kl_weight=kl_weight)[0]
            
        aver_elbo = total_elbo / (i + 1)
        print('....train loss = {:.3f}'.format(aver_elbo.item()))
        train_elbo.append(aver_elbo)
        
        # elbo_curve on test-set
        total_elbo = 0.
        for i, (X, _) in enumerate(test_loader):
            X = X.to(device)
            Xrec, z_mean, z_logvar = model(X)
            total_elbo += vae_loss(Xrec, X, z_mean, z_logvar,
                                           kl_weight=kl_weight)[0]

        aver_test_elbo = total_elbo / (i + 1)
        test_elbo.append(aver_test_elbo)
        # save samples generated by the model at different training stages
        if epoch == 2 or epoch == 3 or epoch == 5 or epoch == 8 or epoch == 12 or epoch == 20:
            counter += 1
            ##add n_gen
            z = torch.randn((n_gen, model.latent_dim)).to(device)
            generated_imgs = model.decoder(z).view(-1, 1, 28, 28)
            save_image(generated_imgs, os.path.join(results_dir, 'samples-{}.png'.format(counter)), nrow=5)
        if epoch % 30 == 0:
            counter += 1
            ##add n_gen
            z = torch.randn((n_gen, model.latent_dim)).to(device)
            generated_imgs = model.decoder(z).view(-1, 1, 28, 28)
            save_image(generated_imgs, os.path.join(results_dir, 'samples-{}.png'.format(counter)), nrow=5)


# Save the trained model's parameters
paras_dir = 'trained_parameters'
if not os.path.exists(paras_dir):
    os.makedirs(paras_dir)
torch.save(model.state_dict(), os.path.join(paras_dir, 'mnist_zdim{}.pkl'.format(latent_size)))

# Make a GIF using the samples generated by the model during training
make_gif(results_dir, counter + 1)

# Plot the elbo-curve on both the training set and the test set
plot_elbocurve(train_elbo, test_elbo, latent_size, results_dir)
