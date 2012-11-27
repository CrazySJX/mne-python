import numpy as np
from numpy.testing import assert_array_almost_equal
from nose.tools import assert_true, assert_raises

from mne.connectivity import spectral_connectivity
from mne.connectivity.spectral import _CohEst

from mne import SourceEstimate
from mne.filter import band_pass_filter

sfreq = 100.
n_signals = 3
n_epochs = 30
n_times = 1000

tmin = 0.
tmax = (n_times - 1) / sfreq

data = np.random.randn(n_epochs, n_signals, n_times)

# simulate connectivity from 5Hz..15Hz
fstart, fend = 5.0, 15.0
for i in xrange(n_epochs):
    data[i, 1, :] = band_pass_filter(data[i, 0, :], sfreq, fstart, fend)
    # add some noise, so the spectrum is not exactly zero
    data[i, 1, :] += 1e-2 * np.random.randn(n_times)


def _stc_gen(data, sfreq, tmin):
    """Simulate a SourceEstimate generator"""
    vertices = [np.arange(data.shape[1]), np.empty(0)]
    for d in data:
        stc = SourceEstimate(data=d, vertices=vertices,
                             tmin=tmin, tstep=1 / float(sfreq))
        yield stc


def test_spectral_connectivity():
    """Test frequency-domain connectivity methods"""

    # First we test some invalid parameters:
    assert_raises(ValueError, spectral_connectivity, data, method='notamethod')

    # test invalid fmin fmax settings
    assert_raises(ValueError, spectral_connectivity, data, fmin=10, fmax=5)
    assert_raises(ValueError, spectral_connectivity, data, fmin=(0, 11),
                  fmax=(5, 10))
    assert_raises(ValueError, spectral_connectivity, data, fmin=(11,),
                  fmax=(12, 15))

    methods = ('coh', 'imcoh', 'cohy', 'pli', 'pli2_unbiased', 'wpli',
               'wpli2_debiased')

    for spectral_mode in ['multitaper', 'fft']:
        for method in methods:
            if method == 'coh' and spectral_mode == 'multitaper':
                # only check adaptive estimation for coh to reduce test time
                check_adaptive = [False, True]
            else:
                check_adaptive = [False]
            for adaptive in check_adaptive:
                con, freqs, n, _ = spectral_connectivity(data, method=method,
                        spectral_mode=spectral_mode, indices=None, sfreq=sfreq,
                        mt_adaptive=adaptive, mt_low_bias=True)

                # test the simulated signal
                if method == 'coh':
                    idx = np.searchsorted(freqs, (fstart + 1, fend - 1))
                    # we see something for zero-lag
                    assert_true(np.all(con[1, 0, idx[0]:idx[1]] > 0.95))

                    idx = np.searchsorted(freqs, (fstart - 1, fend + 1))
                    assert_true(np.all(con[1, 0, :idx[0]] < 0.25))
                    assert_true(np.all(con[1, 0, idx[1]:] < 0.25))
                elif method == 'cohy':
                    idx = np.searchsorted(freqs, (fstart + 1, fend - 1))
                    # imaginary coh will be zero
                    assert_true(np.all(np.imag(con[1, 0, idx[0]:idx[1]])
                                < 0.05))
                    # we see something for zero-lag
                    assert_true(np.all(np.abs(con[1, 0, idx[0]:idx[1]])
                                > 0.95))

                    idx = np.searchsorted(freqs, (fstart - 1, fend + 1))
                    assert_true(np.all(np.abs(con[1, 0, :idx[0]]) < 0.25))
                    assert_true(np.all(np.abs(con[1, 0, idx[1]:]) < 0.25))
                elif method == 'imcoh':
                    idx = np.searchsorted(freqs, (fstart + 1, fend - 1))
                    # imaginary coh will be zero
                    assert_true(np.all(con[1, 0, idx[0]:idx[1]] < 0.05))
                    idx = np.searchsorted(freqs, (fstart - 1, fend + 1))
                    assert_true(np.all(con[1, 0, :idx[0]] < 0.25))
                    assert_true(np.all(con[1, 0, idx[1]:] < 0.25))

                # compute same connections using indices and 2 jobs,
                # also add a second method
                indices = np.tril_indices(n_signals, -1)

                methods = (method, _CohEst)
                stc_data = _stc_gen(data, sfreq, tmin)
                con2, freqs2, n2, _ = spectral_connectivity(stc_data,
                        method=methods, spectral_mode=spectral_mode,
                        indices=indices, sfreq=sfreq, mt_adaptive=adaptive,
                        mt_low_bias=True, tmin=tmin, tmax=tmax, n_jobs=2)

                assert_true(isinstance(con2, list))
                assert_true(len(con2) == 2)

                if method == 'coh':
                    assert_array_almost_equal(con2[0], con2[1])

                con2 = con2[0]  # only keep the first method

                # we get the same result for the probed connections
                assert_array_almost_equal(freqs, freqs2)
                assert_array_almost_equal(con[indices], con2)
                assert_true(n == n2)

                # compute same connections for two bands, fskip=1, and f. avg.
                fmin = (0, sfreq / 4)
                fmax = (sfreq / 4, sfreq / 2)
                con3, freqs3, n3, _ = spectral_connectivity(data, method=method,
                        spectral_mode=spectral_mode, indices=indices,
                        sfreq=sfreq, fmin=fmin, fmax=fmax, fskip=1,
                        faverage=True, mt_adaptive=adaptive, mt_low_bias=True)

                assert_true(isinstance(freqs3, list))
                assert_true(len(freqs3) == len(fmin))
                for i in range(len(freqs3)):
                    assert_true(np.all((freqs3[i] >= fmin[i])
                                       & (freqs3[i] <= fmax[i])))

                # average con2 "manually" and we get the same result
                for i in range(len(freqs3)):
                    freq_idx = np.searchsorted(freqs2, freqs3[i])
                    con2_avg = np.mean(con2[:, freq_idx], axis=1)
                    assert_array_almost_equal(con2_avg, con3[:, i])
