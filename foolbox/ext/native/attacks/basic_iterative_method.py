import numpy as np
import eagerpy as ep

from ..utils import flatten
from ..utils import atleast_kd


def clip_l2_norms(x: ep.Tensor, norm) -> ep.Tensor:
    norms = flatten(x).square().sum(axis=-1).sqrt()
    norms = ep.maximum(norms, 1e-12)  # avoid divsion by zero
    factor = ep.minimum(1, norm / norms)  # clipping -> decreasing but not increasing
    factor = atleast_kd(factor, x.ndim)
    return x * factor


def normalize_l2_norms(x: ep.Tensor) -> ep.Tensor:
    norms = flatten(x).square().sum(axis=-1).sqrt()
    norms = ep.maximum(norms, 1e-12)  # avoid divsion by zero
    factor = 1 / norms
    factor = atleast_kd(factor, x.ndim)
    return x * factor


class L2BasicIterativeAttack:
    """L2 Basic Iterative Method"""

    def __init__(self, model):
        self.model = model

    def __call__(
        self,
        inputs,
        labels,
        *,
        rescale=False,
        epsilon=2.0,
        step_size=0.4,
        num_steps=10,
    ):
        def loss_fn(inputs: ep.Tensor, labels: ep.Tensor) -> ep.Tensor:
            logits = ep.astensor(self.model.forward(inputs.tensor))
            return ep.crossentropy(logits, labels).sum()

        if rescale:
            min_, max_ = self.model.bounds()
            scale = (max_ - min_) * np.sqrt(np.prod(inputs.shape[1:]))
            epsilon = epsilon * scale
            step_size = step_size * scale

        x = ep.astensor(inputs)
        y = ep.astensor(labels)
        assert x.shape[0] == y.shape[0]
        assert y.ndim == 1

        x0 = x

        for _ in range(num_steps):
            _, gradients = ep.value_and_grad(loss_fn, x, y)
            gradients = normalize_l2_norms(gradients)
            x = x + step_size * gradients
            x = x0 + clip_l2_norms(x - x0, epsilon)
            x = ep.clip(x, *self.model.bounds())

        return x.tensor


class LinfinityBasicIterativeAttack:
    """L-infinity Basic Iterative Method"""

    def __init__(self, model):
        self.model = model

    def __call__(
        self,
        inputs,
        labels,
        *,
        rescale=False,
        epsilon=0.3,
        step_size=0.05,
        num_steps=10,
        random_start=False,
    ):
        def loss_fn(inputs: ep.Tensor, labels: ep.Tensor) -> ep.Tensor:
            logits = ep.astensor(self.model.forward(inputs.tensor))
            return ep.crossentropy(logits, labels).sum()

        if rescale:
            min_, max_ = self.model.bounds()
            scale = max_ - min_
            epsilon = epsilon * scale
            step_size = step_size * scale

        x = ep.astensor(inputs)
        y = ep.astensor(labels)
        assert x.shape[0] == y.shape[0]
        assert y.ndim == 1

        x0 = x

        if random_start:
            x = x + ep.uniform(x, x.shape, -epsilon, epsilon)
            x = ep.clip(x, *self.model.bounds())

        for _ in range(num_steps):
            _, gradients = ep.value_and_grad(loss_fn, x, y)
            gradients = gradients.sign()
            x = x + step_size * gradients
            x = x0 + ep.clip(x - x0, -epsilon, epsilon)
            x = ep.clip(x, *self.model.bounds())

        return x.tensor
