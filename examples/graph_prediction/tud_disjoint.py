"""
This example shows how to perform graph classification with a simple Graph
Isomorphism Network.
This is an example of TensorFlow 2's imperative style for model declaration.
"""

import numpy as np
import tensorflow as tf
from tensorflow.keras.layers import Dense, Dropout
from tensorflow.keras.losses import CategoricalCrossentropy
from tensorflow.keras.metrics import CategoricalAccuracy
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam

from spektral.data import DisjointLoader
from spektral.datasets import tudataset
from spektral.layers import GINConv, GlobalAvgPool

################################################################################
# PARAMETERS
################################################################################
learning_rate = 1e-3  # Learning rate
channels = 128        # Hidden units
layers = 3            # GIN layers
epochs = 10           # Number of training epochs
batch_size = 32       # Batch size

################################################################################
# LOAD DATA
################################################################################
dataset = tudataset.TUDataset('PROTEINS', clean=True)

# Parameters
F = dataset.F          # Dimension of node features
n_out = dataset.n_out  # Dimension of the target

# Train/test split
idxs = np.random.permutation(len(dataset))
split = int(0.9 * len(dataset))
dataset_tr, dataset_te = dataset[:split], dataset[split:]


################################################################################
# BUILD MODEL
################################################################################
class GIN0(Model):
    def __init__(self, channels, n_layers):
        super().__init__()
        self.conv1 = GINConv(channels, epsilon=0, mlp_hidden=[channels, channels])
        self.convs = []
        for i in range(1, n_layers):
            self.convs.append(
                GINConv(channels, epsilon=0, mlp_hidden=[channels, channels]))
        self.pool = GlobalAvgPool()
        self.dense1 = Dense(channels, activation='relu')
        self.dropout = Dropout(0.5)
        self.dense2 = Dense(n_out, activation='softmax')

    def call(self, inputs, **kwargs):
        x, a, i = inputs
        x = self.conv1([x, a])
        for conv in self.convs:
            x = conv([x, a])
        x = self.pool([x, i])
        x = self.dense1(x)
        x = self.dropout(x)
        return self.dense2(x)


# Build model
model = GIN0(channels, layers)
opt = Adam(lr=learning_rate)
loss_fn = CategoricalCrossentropy()
acc_fn = CategoricalAccuracy()


################################################################################
# FIT MODEL
################################################################################
@tf.function(
    input_signature=((tf.TensorSpec((None, F), dtype=tf.float64),
                      tf.SparseTensorSpec((None, None), dtype=tf.int64),
                      tf.TensorSpec((None,), dtype=tf.int64)),
                     tf.TensorSpec((None, n_out), dtype=tf.float64)),
    experimental_relax_shapes=True)
def train_step(inputs, target):
    with tf.GradientTape() as tape:
        predictions = model(inputs, training=True)
        loss = loss_fn(target, predictions)
        loss += sum(model.losses)
    gradients = tape.gradient(loss, model.trainable_variables)
    opt.apply_gradients(zip(gradients, model.trainable_variables))
    acc = acc_fn(target, predictions)
    return loss, acc


print('Fitting model')
current_batch = 0
model_lss = model_acc = 0
loader_tr = DisjointLoader(dataset_tr, batch_size=batch_size, epochs=epochs)
for batch in loader_tr:
    lss, acc = train_step(*batch)

    model_lss += lss.numpy()
    model_acc += acc.numpy()
    current_batch += 1
    if current_batch == loader_tr.steps_per_epoch:
        model_lss /= loader_tr.steps_per_epoch
        model_acc /= loader_tr.steps_per_epoch
        print('Loss: {}. Acc: {}'.format(model_lss, model_acc))
        model_lss = model_acc = 0
        current_batch = 0

################################################################################
# EVALUATE MODEL
################################################################################
print('Testing model')
model_lss = model_acc = 0
loader_te = DisjointLoader(dataset_te, batch_size=batch_size, epochs=1)
for batch in loader_te:
    inputs, target = batch
    predictions = model(inputs, training=False)
    model_lss += loss_fn(target, predictions)
    model_acc += acc_fn(target, predictions)
model_lss /= loader_te.steps_per_epoch
model_acc /= loader_te.steps_per_epoch
print('Done. Test loss: {}. Test acc: {}'.format(model_lss, model_acc))
