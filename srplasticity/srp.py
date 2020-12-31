"""
srp.py Module

This module contains classes for the implementation of the SRP model.
- deterministic SRP model
- probabilistic SRP model
- associated synaptic kernel (gaussian and multiexponential)
"""

from abc import ABC, abstractmethod
import numpy as np
from scipy.signal import lfilter

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# HELPER FUNCTIONS
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #


def _sigmoid(x, derivative=False):
    return x * (1 - x) if derivative else 1 / (1 + np.exp(-x))


def _convolve_spiketrain_with_kernel(spiketrain, kernel):
    # add 1 timestep to each spiketime, because efficacy increases AFTER a synaptic release)
    spktr = np.roll(spiketrain, 1)
    spktr[0] = 0  # In case last entry of the spiketrain was a spike
    return lfilter(kernel, 1, spktr)


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# EFFICIENCY KERNELS
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #


class EfficiencyKernel(ABC):

    """ Abstract Base class for a synaptic efficacy kernel"""

    def __init__(self, T=None, dt=0.1):

        self.T = T  # Length of the kernel in ms
        self.dt = dt  # timestep
        self.kernel = np.zeros(int(T / dt))

    @abstractmethod
    def _construct_kernel(self, *args):
        pass


class GaussianKernel(EfficiencyKernel):

    """
    An efficacy kernel from a sum of an arbitrary number of normalized gaussians
    """

    def __init__(self, amps, mus, sigmas, T=None, dt=0.1):
        """
        :param amps: list of floats: amplitudes.
        :param mus: list of floats: means.
        :param sigmas: list or 1: std deviations.
        :param T: length of synaptic kernel in ms.
        :param dt: timestep in ms. defaults to 0.1 ms.
        """

        # Check number of gaussians that make up the kernel
        assert (
            np.size(amps) == np.size(mus) == np.size(sigmas)
        ), "Unequal number of parameters"

        # Default T to largest mean + 5x largest std
        if T is None:
            T = np.max(mus) + 5 * np.max(sigmas)

        # Convert to 1D numpy arrays
        amps = np.atleast_1d(amps)
        mus = np.atleast_1d(mus)
        sigmas = np.atleast_1d(sigmas)

        super().__init__(T, dt)

        self._construct_kernel(amps, mus, sigmas)

    def _construct_kernel(self, amps, mus, sigmas):
        """ constructs the efficacy kernel """

        t = np.arange(0, self.T, self.dt)
        L = len(t)
        n = np.size(amps)  # number of gaussians

        self._all_gaussians = np.zeros((n, L))
        self.kernel = np.zeros(L)

        for i in range(n):
            a = amps[i]
            mu = mus[i]
            sig = sigmas[i]

            self._all_gaussians[i, :] = (
                a
                * np.exp(-((t - mu) ** 2) / 2 / sig ** 2)
                / np.sqrt(2 * np.pi * sig ** 2)
            )

        self.kernel = self._all_gaussians.sum(0)


class ExponentialKernel(EfficiencyKernel):

    """
    An efficacy kernel from a sum of an arbitrary number of Exponential decays
    """

    def __init__(self, taus, amps=None, T=None, dt=0.1):
        """
        :param taus: list of floats: exponential decays.
        :param amps: list of floats: amplitudes (optional, defaults to 1)
        :param T: length of synaptic kernel in ms.
        :param dt: timestep in ms. defaults to 0.1 ms.
        """

        if amps is None:
            amps = np.array([1] * np.size(taus))
        else:
            # Check number of exponentials that make up the kernel
            assert np.size(taus) == np.size(amps), "Unequal number of parameters"

        # Convert to 1D numpy arrays
        taus = np.atleast_1d(taus)
        amps = np.atleast_1d(amps)

        # Default T to 10x largest time constant
        if T is None:
            T = 10 * np.max(taus)

        super().__init__(T, dt)

        self._construct_kernel(amps, taus)

    def _construct_kernel(self, amps, taus):
        """ constructs the efficacy kernel """

        t = np.arange(0, self.T, self.dt)
        L = len(t)
        n = np.size(amps)  # number of gaussians

        self._all_exponentials = np.zeros((n, L))
        self.kernel = np.zeros(L)

        for i in range(n):
            tau = taus[i]
            a = amps[i]

            self._all_exponentials[i, :] = a / tau * np.exp(-t / tau)

        self.kernel = self._all_exponentials.sum(0)


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# SRP MODEL
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #


class DetSRP:
    def __init__(self, kernel, baseline, nlin=_sigmoid, dt=0.1):
        """
        Initialization method for the deterministic SRP model.

        :param kernel: Numpy Array or instance of `EfficiencyKernel`. Synaptic STP kernel.
        :param baseline: Float. Baseline parameter
        :param nlin: nonlinear function. defaults to sigmoid function
        """

        self.dt = dt
        self.nlin = nlin
        self.mu_baseline = baseline

        if isinstance(kernel, EfficiencyKernel):
            assert (
                self.dt == kernel.dt
            ), "Timestep of model and efficacy kernel do not match"
            self.mu_kernel = kernel.kernel
        else:
            self.mu_kernel = np.array(kernel)

    def run(self, spiketrain, return_all=False):

        filtered_spiketrain = self.mu_baseline + _convolve_spiketrain_with_kernel(
            spiketrain, self.mu_kernel
        )
        nonlinear_readout = self.nlin(filtered_spiketrain)
        efficacytrain = nonlinear_readout * spiketrain
        efficacies = efficacytrain[np.where(spiketrain == 1)[0]]

        if return_all:
            return {
                "filtered_spiketrain": filtered_spiketrain,
                "nonlinear_readout": nonlinear_readout,
                "efficacytrain": efficacytrain,
                "efficacies": efficacies
            }

        else:
            return efficacytrain, efficacies


class ProbSRP(DetSRP):
    def __init__(
        self, mu_kernel, mu_baseline, sigma_kernel=None, sigma_baseline=None, **kwargs
    ):
        """
        Initialization method for the probabilistic SRP model.

        :param mu_kernel: Numpy Array or instance of `EfficiencyKernel`. Mean kernel.
        :param mu_baseline: Float. Mean Baseline parameter
        :param sigma_kernel: Numpy Array or instance of `EfficiencyKernel`. Variance kernel.
        :param sigma_baseline: Float. Variance Baseline parameter
        :param **kwargs: Keyword arguments to be passed to constructor method of `DetSRP`
        """

        super().__init__(mu_kernel, mu_baseline, **kwargs)

        # If not provided, set sigma kernel to equal the mean kernel
        if sigma_kernel is None:
            self.sigma_kernel = self.mu_kernel
            self.sigma_baseline = self.mu_baseline
        else:
            if isinstance(sigma_kernel, EfficiencyKernel):
                assert (
                    self.dt == sigma_kernel.dt
                ), "Timestep of model and variance kernel do not match"
                self.sigma_kernel = sigma_kernel.kernel
            else:
                self.sigma_kernel = np.array(sigma_kernel)

            self.sigma_baseline = sigma_baseline

    def run_spiketrain(self, spiketrain, ntrials=1):

        spiketimes = np.where(spiketrain == 1)[0]
        efficacytrains = np.zeros((ntrials, len(spiketrain)))

        mean = self.nlin(
            self.mu_baseline
            + _convolve_spiketrain_with_kernel(spiketrain, self.mu_kernel)
        ) * spiketrain
        sigma = self.nlin(
            self.mu_baseline
            + _convolve_spiketrain_with_kernel(spiketrain, self.mu_kernel)
        ) * spiketrain

        # Sampling from gamma distribution
        efficacies = self._sample(mean[spiketimes], sigma[spiketimes], ntrials)
        efficacytrains[:, spiketimes] = efficacies

        return efficacies, efficacytrains

    def _sample(self, mean, sigma, ntrials):
        """
        Samples `ntrials` response amplitudes from a gamma distribution given mean and sigma
        """

        return np.random.gamma(shape=mean ** 2 / sigma ** 2,
                               scale=sigma ** 2 / mean,
                               size=(ntrials, len(np.atleast_1d(mean))))