# Copyright 2016 Louis Kirsch. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

import tensorflow as tf
import numpy as np


class Wav2LetterModel:

  def __init__(self, input_size, num_classes, learning_rate, learning_rate_decay_factor, max_gradient_norm,
               log_dir, use_relu, run_name, momentum):
    """
    Create a new Wav2Letter model

    Args:
      input_size: the number of values per time step
      num_classes: the number of output classes (vocabulary_size + 1 for blank label)
      learning_rate: the inital learning rate
      learning_rate_decay_factor: the factor to multiple the learning rate with when it should be decreased
      max_gradient_norm: the maximum gradient norm to apply, otherwise clipping is applied
      log_dir: the directory to log to for use of tensorboard
      use_relu: if True, use relu instead of tanh
    """
    self.input_size = input_size

    activation_fnc = tf.nn.relu if use_relu else tf.nn.tanh

    # Define input placeholders
    # inputs is of dimension [batch_size, max_time, input_size]
    self.inputs = tf.placeholder(tf.float32, [None, None, input_size], name='inputs')
    self.sequence_lengths = tf.placeholder(tf.int32, [None], name='sequence_lengths')
    self.labels = tf.sparse_placeholder(tf.int32, name='labels')

    # Define non-trainables
    self.global_step = tf.Variable(0, trainable=False)
    self.learning_rate = tf.Variable(float(learning_rate), trainable=False, dtype=tf.float32, name='learning_rate')
    self.learning_rate_decay_op = self.learning_rate.assign(
                                   tf.mul(self.learning_rate, learning_rate_decay_factor, name='learning_rate_decay'))

    # Variable summaries
    tf.scalar_summary('learning_rate', self.learning_rate)

    def convolution(value, filter_width, stride, input_channels, out_channels, apply_non_linearity=True):
      try:
        convolution.layer_id += 1
      except AttributeError:
        convolution.layer_id = 1

      with tf.name_scope('convolution_layer_{}'.format(convolution.layer_id)) as layer:
        # Filter and bias
        initial_filter = tf.truncated_normal([filter_width, input_channels, out_channels], stddev=0.01)
        filters = tf.Variable(initial_filter, name='filters')
        bias = tf.Variable(tf.constant(0.0, shape=[out_channels]), name='bias')

        # Apply convolution
        convolution_out = tf.nn.conv1d(value, filters, stride, 'SAME', use_cudnn_on_gpu=True, name='convolution')

        # Create summary
        with tf.name_scope('summaries'):
          # add depth of 1 (=grayscale) leading to shape [filter_width, input_channels, 1, out_channels]
          kernel_with_depth = tf.expand_dims(filters, 2)

          # to tf.image_summary format [batch_size=out_channels, height=filter_width, width=input_channels, channels=1]
          kernel_transposed = tf.transpose(kernel_with_depth, [3, 0, 1, 2])

          # this will display random 3 filters from all the output channels
          tf.image_summary(layer + 'filters', kernel_transposed, max_images=3)
          tf.histogram_summary(layer + 'filters', filters)

          tf.image_summary(layer + 'bias', tf.reshape(bias, [1, 1, out_channels, 1]))
          tf.histogram_summary(layer + 'bias', bias)

        # Add bias
        convolution_out += bias

        if apply_non_linearity:
          # Add non-linearity
          activations = activation_fnc(convolution_out, name='activation')
          tf.histogram_summary(layer + 'activation', activations)
          return activations, out_channels
        else:
          return convolution_out, out_channels

    # The first layer scales up from input_size channels to 250 channels
    # One striding layer of output size [batch_size, max_time / 2, 250]
    outputs, channels = convolution(self.inputs, 48, 2, input_size, 250)

    # 7 layers without striding of output size [batch_size, max_time / 2, 250]
    for layer_idx in range(7):
      outputs, channels = convolution(outputs, 7, 1, channels, channels)

    # 1 layer with high kernel width and output size [batch_size, max_time / 2, 2000]
    outputs, channels = convolution(outputs, 32, 1, channels, channels * 8)

    # 1 fully connected layer of output size [batch_size, max_time / 2, 2000]
    outputs, channels = convolution(outputs, 1, 1, channels, channels)

    # 1 fully connected layer of output size [batch_size, max_time / 2, num_classes]
    # We must not apply a non linearity in this last layer
    outputs, channels = convolution(outputs, 1, 1, channels, num_classes, False)

    # transpose logits to size [max_time / 2, batch_size, num_classes]
    self.logits = tf.transpose(outputs, (1, 0, 2))

    # Generate summary image for logits [batch_size=batch_size, height=num_classes, width=max_time / 2, channels=1]
    tf.image_summary('logits', tf.expand_dims(tf.transpose(outputs, (0, 2, 1)), 3))
    tf.histogram_summary('logits', outputs)

    # Define loss and optimizer
    with tf.name_scope('training'):
      self.cost = tf.nn.ctc_loss(self.logits, self.labels, self.sequence_lengths // 2)
      self.avg_loss = tf.reduce_mean(self.cost, name='average_loss')
      tf.scalar_summary('loss', self.avg_loss)
      optimizer = tf.train.MomentumOptimizer(self.learning_rate, momentum, name='optimizer')
      gvs = optimizer.compute_gradients(self.avg_loss)
      gradients, trainables = zip(*gvs)
      clipped_gradients, norm = tf.clip_by_global_norm(gradients, max_gradient_norm, name='clip_gradients')
      self.update = optimizer.apply_gradients(zip(clipped_gradients, trainables),
                                              global_step=self.global_step, name='apply_gradients')

    # Decoding
    with tf.name_scope('decoding'):
      # TODO use beam search here later
      self.decoded, self.log_probabilities = tf.nn.ctc_greedy_decoder(self.logits, self.sequence_lengths // 2)

    # Initializing the variables
    self.init = tf.initialize_all_variables()

    # Create saver
    self.saver = tf.train.Saver(tf.all_variables())

    # Create summary writers
    self.merged_summaries = tf.merge_all_summaries()
    if run_name:
      run_name += '_'
    self.train_writer = tf.train.SummaryWriter('{}/{}train'.format(log_dir, run_name))
    self.dev_writer = tf.train.SummaryWriter('{}/{}dev'.format(log_dir, run_name))

  def init_session(self, sess, init_variables=True):
    """
    Initialize a new session for the model.

    Args:
      sess: session to initalize
      init_variables: whether to initialize all variables

    """
    if init_variables:
      sess.run(self.init)

    self.train_writer.add_graph(sess.graph)
    self.dev_writer.add_graph(sess.graph)

  def _get_inputs_feed_item(self, input_list):
    """
    Generate the tensor from `input_list` to feed into the network

    Args:
      input_list: a list of numpy arrays of shape [time, input_size]

    Returns: tuple (input_tensor, sequence_lengths, max_time)

    """
    sequence_lengths = np.array([inp.shape[0] for inp in input_list])
    max_time = sequence_lengths.max()
    input_tensor = np.zeros((len(input_list), max_time, self.input_size))

    # Fill input tensor
    for idx, inp in enumerate(input_list):
      input_tensor[idx, :inp.shape[0], :] = inp

    return input_tensor, sequence_lengths, max_time

  @staticmethod
  def _get_labels_feed_item(label_list, max_time):
    """
    Generate the tensor from 'label_list' to feed as labels into the network

    Args:
      label_list: a list of encoded labels (ints)
      max_time: the maximum time length of `label_list`

    Returns: the SparseTensorValue to feed into the network

    """

    label_shape = np.array([len(label_list), max_time], dtype=np.int)
    label_indices = []
    label_values = []
    for labelIdx, label in enumerate(label_list):
      for idIdx, identifier in enumerate(label):
        label_indices.append([labelIdx, idIdx])
        label_values.append(identifier)
    label_indices = np.array(label_indices, dtype=np.int)
    label_values = np.array(label_values, dtype=np.int)
    return tf.SparseTensorValue(label_indices, label_values, label_shape)

  def step(self, sess, input_list, label_list, update=True, decode=False, summary=False):
    """
    Evaluate the graph, you may update weights, decode audio or generate a summary

    Args:
      sess: tensorflow session
      input_list: spectrogram inputs, list of Tensors [time, input_size]
      label_list: identifiers from vocabulary, list of list of int32
      update: should the network be trained
      decode: should the decoding be performed and returned
      summary: should the summary be generated

    Returns: avg_loss, decoded (optional), update (optional), summary (optional)

    """
    if label_list is not None and len(input_list) != len(label_list):
      raise ValueError('Input list must have same length as label list')

    input_tensor, sequence_lengths, max_time = self._get_inputs_feed_item(input_list)

    input_feed = {
      self.inputs: input_tensor,
      self.sequence_lengths: sequence_lengths,
    }
    output_feed = []

    if label_list is not None:
      labels = self._get_labels_feed_item(label_list, max_time)
      input_feed[self.labels] = labels
      output_feed.append(self.avg_loss)

    if decode:
      output_feed.append(self.decoded[0])

    if update:
      output_feed.append(self.update)

    if summary:
      output_feed.append(self.merged_summaries)

    return sess.run(output_feed, feed_dict=input_feed)
