"""
ATRA MK1.2 - Affine Transformation Autoencoders

Building off of MK1.1, this model is much more compact, and efficient. 
I realized there was a lot I could do much easier using Keras' functional API, 
    So once I got the hang of that this model got much better.
MK1.2 will likely be finished when I have finished adding in all the basic elements of the transforming autoencoder,
    but not yet added in many intricacies or optimizations.

Features Added
    Display of sample autoencoder outputs
    Graphing of results
    Display of individual capsule outputs per sample
    Visual Entity Probabilities & Gating units

-Blake Edwards / Dark Element
"""
import sys
import numpy as np
#np.random.seed(420)#For ease of testing

import atra_base
from atra_base import *

from keras.datasets import mnist
from keras.layers import *
from keras.regularizers import l2
from keras.models import Model
from keras.utils import np_utils
from keras import backend as K

"""
First, we load and prepare our data
"""
(X_train, Y_train), (X_test, Y_test) = mnist.load_data()

"""
Convert to float32
"""
X_train = X_train.astype('float32')
X_test = X_test.astype('float32')

"""
Feature Scale
"""
X_train /= 255
X_test /= 255

"""
Create One-hot label matrices
"""
Y_train = np_utils.to_categorical(Y_train, 10)
Y_test = np_utils.to_categorical(Y_test, 10)

"""
Now that data is prepared, we start our model.
Since this isn't a normal Sequential Keras model, we have to define our own and then wrap it in Keras' Model API at the end.
We do this by defining a symbolic graph
"""
"""
Define inputs, 
    X as size (None, 28, 28) Since it is of type Input it automatically has a None axis at the front,
        and this will become (capsule_n, None, 28, 28).
        This results in our format of Capsule_N x Batch Size x Height x Width x Channels.
        Of course, we can easily manipulate the input dimensions to have (784,) or (28,28) or (784, 1, 1) or (28, 28, 1), and so on.
"""

capsule_n = 20
epochs = 50
mini_batch_size= 256
dropout_p = 0.0
regularization_rate = 0.00
activation_fn = "relu"
loss = "binary_crossentropy"
optimizer = "adadelta"
encoder_output_dim = [3,3]
input_dims = [28,28]

graph_output = False

flattened_output_dims = np.prod(input_dims)
flattened_encoder_output_dim = np.prod(encoder_output_dim)
capsule_output_dims = [capsule_n]
capsule_output_dims.extend(input_dims)
flattened_capsule_output_dims = np.prod(capsule_output_dims)

inputs = Input(shape=input_dims)
"""
First off, each capsule's hidden units are independent from one another.
This means we don't share the recognition units, so if we want to have n capsules easily,
    we have to make a MetaDense layer, so that we can say e.g. we want n groups of 20 hidden units, aka dense layers.
So our first model is only going to be testing this.
"""

"""
When we put our inputs through the introductory recognition hidden layer in each of our capsules when defining our model, 
    we will be looping through each capsule and applying the same input to a different dense layer each time.
Because we are putting the inputs, of shape (None, 28, 28) (where None = Mini batch size), 
    through these dense layers, we want to flatten our inputs first. So we do that here.
"""
flattened_inputs = Flatten()(inputs)

"""
Initialize output of our recognition hidden layer as a list
"""
capsule_outputs = []

"""
Then, thanks to Keras's functional model API, we can actually just loop through
    for each capsule, and apply an independent Dense Layer with activation function of our choice to the flattened inputs.
Since our model is more or less shaped like so:
    ----Input----
    / /   | ... \
   C C    C ... C
   | |    | ... |
   y y    y ... y
   \ \    | ... /
    ----Output---
We can represent our model by first copying our input into each capsule by creating a list of capsule outputs,
    Then looping through this list each time we add a layer to our model,
    Then finally merging the layers when we get our output at the end.
"""
for capsule_i in range(capsule_n):
    capsule_outputs.append(Dense(flattened_encoder_output_dim, activation=activation_fn, W_regularizer=l2(regularization_rate), name="capsule_%i_recognition_units1"%(capsule_i))(flattened_inputs))
    capsule_outputs[capsule_i] = Dropout(dropout_p)(capsule_outputs[capsule_i])

"""
Invariant Visual Entity Probabilities
    Each capsule learns to represent it's own visual entity, equivariantly. 
    However, it also needs a way to represent when it's visual entity is more or less present, in an invariant fashion. We do this with a simple 0-1 probability.
    Since each capsule has one scalar for the probability, we can easily just loop through and assign just as we did with the dense outputs.
    Our formula for each probability is just a normal dense layer, with the output as one.
"""
capsule_entity_probabilities = []
for capsule_i in range(capsule_n):
    capsule_entity_probabilities.append(Dense(1, activation=activation_fn, W_regularizer=l2(regularization_rate), name="capsule_%i_entity_probabilities"%(capsule_i))(capsule_outputs[capsule_i]))

"""
BEGIN DECODER
Currently, just one layer of generation units
"""
for capsule_i in range(capsule_n):
    capsule_outputs[capsule_i] = Dense(flattened_output_dims, activation=activation_fn, W_regularizer=l2(regularization_rate))(capsule_outputs[capsule_i])
    capsule_outputs[capsule_i] = Dropout(dropout_p, name="capsule_%i_generative_unit_outputs"%(capsule_i))(capsule_outputs[capsule_i])

"""
We then apply our invariant visual entity probabilities to each capsule's outputs, before getting the final summed output.
    Since we are combining the outputs of two layers into one output (and not models, otherwise we would use Merge(capitalized)), we are doing this with a merge layer.
    Since this merge is our own special operation, a scalar multiplication, we use lambda for it.
        We do this simply with x[0] * x[1], since it's just cA, if c is a scalar and A is a matrix.
        The output shape is "not including the batch size" according to the Keras documentation, so we get the int_shape of our original capsule output,
            then get all but the first dimension, via [1:].
    And that's it!
    I would use K.shape, but the tensors it returns are not iterable, and this needs an iterable argument passed.
"""
for capsule_i in range(capsule_n):
    capsule_outputs[capsule_i] = merge([capsule_entity_probabilities[capsule_i], capsule_outputs[capsule_i]], mode=lambda x: x[0]*x[1], output_shape=K.int_shape(capsule_outputs[capsule_i])[1:], name="capsule_%i_gating_unit_outputs"%(capsule_i))

"""
With the atomic capsule model complete, we merge all our outputs together to get the atomic_capsule_outputs, initially with concatenation.
"""
atomic_capsule_outputs = merge([capsule_output for capsule_output in capsule_outputs], mode='concat')

"""
We then reshape so as to get the image outputs, of the same shape as our labels / inputs
"""
atomic_capsule_outputs = Reshape(capsule_output_dims, name="atomic_capsule_outputs")(atomic_capsule_outputs)

"""
Note: The dimensions / axes are (Mini batches, Capsules, ...)
Assign our final output value(s) to the sum of our atomic_capsule_outputs values over the capsule axis, axis 1
    We can't just insert random theano / tensorflow operations into our Keras model. 
    Because of this, we have to put them inside a lambda layer, and then apply that lambda layer to our input to get our output.
    That is what we do here, summing over axis 1 for the given atomic_capsule_outputs tensor
"""
composite_capsule_output = Lambda(lambda atomic_capsule_outputs: K.sum(atomic_capsule_outputs, axis=1))(atomic_capsule_outputs)

"""
With our inputs and outputs, create a Keras Model.
"""
model = Model(input=inputs, output=composite_capsule_output)

"""
Train the model and get results
"""
model.compile(loss=loss, optimizer=optimizer, metrics=["accuracy"])
results = model.fit(X_train, X_train, nb_epoch=epochs, batch_size=mini_batch_size, shuffle=True)

"""
Get individual capsule model so we can see outputs of individual capsules
"""
individual_capsule_model = Model(input=model.input, output=model.get_layer("atomic_capsule_outputs").output)

"""
Get individual capsule visual entity probability models so we can see probabilities between samples
"""
individual_capsule_entity_probability_models = []
for capsule_i in range(capsule_n):
    individual_capsule_entity_probability_models.append(Model(input=model.input, output=model.get_layer("capsule_%i_entity_probabilities"%(capsule_i)).output))

"""
Get sample inputs and outputs
"""
display_test_n = 16
sample_inputs = X_test[:display_test_n]
sample_outputs = model.predict(sample_inputs)
sample_individual_capsule_outputs = individual_capsule_model.predict(sample_inputs)

"""
In order to get our individual capsule visual entity probability outputs
    we first loop through and get predictions for each model, our scalars for each capsule
This will result in a list of shape (capsule_n, display_test_n, 1), 
    which we then convert to a np array and remove the extra dimension.
"""
sample_individual_capsule_entity_probabilities = []
for capsule_i in range(capsule_n):
    sample_individual_capsule_entity_probabilities.append(individual_capsule_entity_probability_models[capsule_i].predict(sample_inputs))
sample_individual_capsule_entity_probabilities = np.array(sample_individual_capsule_entity_probabilities)
sample_individual_capsule_entity_probabilities = np.squeeze(sample_individual_capsule_entity_probabilities)

"""
Concatenate each into their own column
"""
sample_inputs = get_concatenated_col(sample_inputs)
sample_outputs = get_concatenated_col(sample_outputs)

"""
Get our individual capsule outputs in the following way:
    Since sample_individual_capsule_outputs is of shape (display_test_n, capsule_n, h, w),
        we loop through display_test_n for each row, and capsule_n for each column.
"""
disp_individual_capsule_outputs = []
for sample_capsule_outputs in sample_individual_capsule_outputs:
    """
    Get the row of outputs for each sample, and append it
    """
    disp_individual_capsule_outputs.append(get_concatenated_row(sample_capsule_outputs))

"""
Then combine all our rows into a column, giving us all our outputs in the format we want.
"""
disp_individual_capsule_outputs = get_concatenated_col(disp_individual_capsule_outputs)


"""
Get a comparison image by concatenating the columns alongside each other, then display
"""
comparison_img = get_concatenated_row((sample_inputs, sample_outputs, disp_individual_capsule_outputs))

"""
Do 1-image so we get black on white background, instead of white on black
"""
#disp_img_fullscreen(comparison_img)
disp_img_fullscreen(1-comparison_img)

"""
Print the visual entity probabilities for each capsule
"""
print sample_individual_capsule_entity_probabilities.transpose()

"""
Graph our loss and accuracy
"""
if graph_output:
    graph_results(results.history["loss"], results.history["acc"])
