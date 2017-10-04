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

import mxnet as mx
import numpy as np

import sockeye.layers
import sockeye.rnn


def test_layer_normalization():
    batch_size = 32
    num_hidden = 64
    x = mx.sym.Variable('x')
    x_nd = mx.nd.uniform(0, 10, (batch_size, num_hidden))
    x_np = x_nd.asnumpy()

    ln = sockeye.layers.LayerNormalization(num_hidden, prefix="")

    # test moments
    sym = mx.sym.Group(ln.moments(x))
    mean, var = sym.eval(x=x_nd)

    expected_mean = np.mean(x_np, axis=1, keepdims=True)
    expected_var = np.var(x_np, axis=1, keepdims=True)

    assert np.isclose(mean.asnumpy(), expected_mean).all()
    assert np.isclose(var.asnumpy(), expected_var).all()

    sym = ln.normalize(x)
    norm = sym.eval(x=x_nd,
                    _gamma=mx.nd.ones((num_hidden,)),
                    _beta=mx.nd.zeros((num_hidden,)))[0]

    expected_norm = (x_np - expected_mean) / np.sqrt(expected_var)

    assert np.isclose(norm.asnumpy(), expected_norm, atol=1.e-6).all()


def test_weight_normalization():
    pass
