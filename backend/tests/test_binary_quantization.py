"""Reference rounding rules for the future firmware encoder."""

import numpy as np

from scripts.verify_binary_quantization import quantize


def test_half_steps_round_away_from_zero_and_preserve_shape():
    values = np.array([[0, 0.0005, -0.0005], [1.2345, -1.2345, 6.0]])
    expected = np.array([[0, 0.001, -0.001], [1.235, -1.235, 6.0]])
    np.testing.assert_array_equal(quantize(values), expected)
