# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not
# use this file except in compliance with the License. A copy of the License
# is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

"""
Convolutional layers.
"""
from sockeye.config import Config
from . import utils
from . import constants as C

import mxnet as mx


class ConvolutionConfig(Config):
    """
    Configuration for a stack of convolutions with Gated Linear Units between layers, similar to Gehring et al. 2017.

    :param kernel_width: Kernel size for 1D convolution.
    :param num_hidden: Size of hidden representation after convolution.
    :param act_type: The type of activation to use.
    """
    def __init__(self,
                 kernel_width: int,
                 num_hidden: int,
                 act_type: str=C.GLU):
        super().__init__()
        self.kernel_width = kernel_width
        self.num_hidden = num_hidden
        utils.check_condition(act_type in C.CNN_ACTIVATION_TYPES, "Unknown activation %s." % act_type)
        self.act_type = act_type


class ConvolutionBlock:
    """
    A Convolution-GLU block consists of the 2 following sublayers:
    1. Dropout (optional)
    1. A Convolution (padded either both to the left and to the right or just to the left).
    2. An activation: Either a Gated Linear Unit or any other activation supported by MXNet.

    :param config: Configuration for Convolution block.
    :param pad_type: 'left' or 'centered'. 'left' only pads to the left (for decoding
           the target sequence). 'centered' pads on both sides (for encoding the source sequence).
    :param prefix: Name prefix for symbols of this block.
    """
    def __init__(self,
                 config: ConvolutionConfig,
                 pad_type: str,
                 prefix: str) -> None:
        self.prefix = prefix
        self.pad_type = pad_type
        self.config = config
        self.conv_weight = mx.sym.Variable("%sconv_weight" % prefix)
        self.conv_bias = mx.sym.Variable("%sconv_bias" % prefix)

    def __call__(self, data: mx.sym.Symbol,
                 data_length: mx.sym.Symbol,
                 seq_len: int,
                 skip_padding=False) -> mx.sym.Symbol:
        """
        :param data: Input data. Shape: (batch_size, seq_len, num_hidden).
        :param data_length: Vector with sequence lengths. Shape: (batch_size,).
        :param seq_len: Maximum sequence length.
        :return: Symbol(batch_size, seq_len, num_hidden)
        """
        if skip_padding:
            padding = None
        else:
            if self.pad_type == 'left':
                # we pad enough on both sides and later slice the extra padding from the right
                padding = (self.config.kernel_width - 1,)
            elif self.pad_type == 'centered':
                # we pad enough so that the output size is equal to the input size and we don't need to slice
                utils.check_condition(self.config.kernel_width % 2 == 1,
                                      "Only odd kernel widths supported, but got %d" % self.config.kernel_width)
                padding = (int((self.config.kernel_width - 1)/2),)
            else:
                raise ValueError("Unknown pad type %s" % self.pad_type)

        if self.config.act_type == "glu":
            num_hidden = 2 * self.config.num_hidden
        else:
            num_hidden = self.config.num_hidden

        # Apply masking (so that we properly have zero padding for variable sequence length batches)
        # Note: SequenceMask expects time-major data
        # (seq_len, batch_size, num_hidden)
        data = mx.sym.swapaxes(data, dim1=0, dim2=1)
        data = mx.sym.SequenceMask(data=data, sequence_length=data_length, use_sequence_length=True, value=0)

        #TODO: better to transpose or to set the layout in the convolution? Do a speed comparison...
        #TODO: does it make sense to implement convolutions for single time steps as FullyConnected (speed comparison...)
        # (batch_size,  num_hidden, seq_len)
        data = mx.sym.transpose(data, axes=(1, 2, 0))
        data_conv = mx.sym.Convolution(data=data,
                                       weight=self.conv_weight,
                                       bias=self.conv_bias,
                                       pad=padding,
                                       kernel=(self.config.kernel_width,),
                                       num_filter=num_hidden,
                                       layout="NCW")

        # (batch_size, 2 * num_hidden, seq_len)
        if not skip_padding and self.pad_type == 'left':
            data_conv = mx.sym.slice_axis(data=data_conv, axis=2, begin=0, end=seq_len)

        if self.config.act_type == "glu":
            # GLU
            # two times: (batch_size, num_hidden, seq_len)
            gate_a, gate_b = mx.sym.split(data_conv, num_outputs=2, axis=1)
            # (batch_size, num_hidden, seq_len)
            block_output = mx.sym.broadcast_mul(gate_a,
                                                mx.sym.Activation(data=gate_b, act_type="sigmoid"))
        else:
            #TODO: does it make sense to add layer normalization?
            # (batch_size, num_hidden, seq_len)
            block_output = mx.sym.Activation(data_conv, act_type=self.config.act_type)

        # (batch_size, seq_len, num_hidden)
        block_output = mx.sym.swapaxes(block_output, dim1=1, dim2=2)
        return block_output


