import sys

import numpy as np
import pytest

import cupy
from cupy.cuda import driver
from cupy.cuda import runtime
from cupy import testing
import cupyx.scipy.signal

try:
    import scipy.signal  # NOQA
except ImportError:
    pass


@testing.parameterize(*testing.product({
    'size1': [(10,), (5, 10), (10, 3), (3, 4, 10)],
    'size2': [3, 4, 5, 10],
    'mode': ['full', 'same', 'valid'],
}))
@testing.with_requires('scipy')
class TestConvolveCorrelate:
    def _filter(self, func, dtype, xp, scp):
        in1 = testing.shaped_random(self.size1, xp, dtype)
        in2 = testing.shaped_random((self.size2,)*in1.ndim, xp, dtype)
        return getattr(scp.signal, func)(in1, in2, self.mode, method='direct')

    tols = {np.float32: 1e-5, np.complex64: 1e-5,
            np.float16: 1e-3, 'default': 1e-10}

    @testing.for_all_dtypes()
    @testing.numpy_cupy_allclose(atol=tols, rtol=tols, scipy_name='scp',
                                 accept_error=ValueError)
    def test_convolve(self, xp, scp, dtype):
        return self._filter('convolve', dtype, xp, scp)

    @testing.for_all_dtypes()
    @testing.numpy_cupy_allclose(atol=tols, rtol=tols, scipy_name='scp',
                                 accept_error=ValueError)
    def test_correlate(self, xp, scp, dtype):
        return self._filter('correlate', dtype, xp, scp)


@testing.parameterize(*testing.product({
    'size1': [(10,), (5, 10), (10, 3), (3, 4, 10)],
    'size2': [3, 4, 5, 10],
    'mode': ['full', 'same', 'valid'],
}))
@testing.with_requires('scipy')
class TestFFTConvolve:
    def _filter(self, func, dtype, xp, scp, **kwargs):
        in1 = testing.shaped_random(self.size1, xp, dtype)
        in2 = testing.shaped_random((self.size2,)*in1.ndim, xp, dtype)
        return getattr(scp.signal, func)(in1, in2, self.mode, **kwargs)

    tols = {np.float32: 1e-3, np.complex64: 1e-3,
            np.float16: 1e-3, 'default': 1e-8}

    def _hip_skip_invalid_condition(self):
        invalid_condition = [
            ('full', 3), ('full', 4), ('full', 5), ('full', 10),
            ('same', 3), ('same', 4), ('same', 5), ('same', 10),
            ('valid', 3), ('valid', 10)]
        if (runtime.is_hip and self.size1 == (3, 4, 10)
                and (self.mode, self.size2) in invalid_condition):
            pytest.xfail('ROCm/HIP may have a bug')

    @testing.for_all_dtypes()
    @testing.numpy_cupy_allclose(atol=tols, rtol=tols, scipy_name='scp',
                                 accept_error=ValueError)
    def test_fftconvolve(self, xp, scp, dtype):
        self._hip_skip_invalid_condition()
        return self._filter('fftconvolve', dtype, xp, scp)

    @testing.for_all_dtypes(no_bool=True)
    @testing.numpy_cupy_allclose(atol=tols, rtol=tols, scipy_name='scp',
                                 accept_error=ValueError)
    def test_convolve_fft(self, xp, scp, dtype):
        self._hip_skip_invalid_condition()
        return self._filter('convolve', dtype, xp, scp, method='fft')

    @testing.for_all_dtypes(no_bool=True)
    @testing.numpy_cupy_allclose(atol=tols, rtol=tols, scipy_name='scp',
                                 accept_error=ValueError)
    def test_correlate_fft(self, xp, scp, dtype):
        self._hip_skip_invalid_condition()
        return self._filter('correlate', dtype, xp, scp, method='fft')


def tupleid(shape):
    return ''.join(str(s) for s in shape)


@testing.with_requires('scipy')
class TestFFTConvolveFastShape:
    @pytest.mark.parametrize('mode', ['full', 'same', 'valid'])
    @pytest.mark.parametrize(('shape1', 'shape2'), [
        ((1,), (7,)),
        ((3,), (1,)),
        ((5, 4), (3, 1)),
        ((1, 1), (2, 4)),
        ((), ()),
        ((5, 1, 1), (1, 4, 1)),
    ], ids=tupleid)
    @testing.for_dtypes('efdFD')
    @testing.numpy_cupy_allclose(atol=1e-3, rtol=1e-3, scipy_name='scp')
    def test_fftconvolve1(self, xp, scp, dtype, shape1, shape2, mode):
        in1 = testing.shaped_random(shape1, xp, dtype)
        in2 = testing.shaped_random(shape2, xp, dtype)
        return scp.signal.fftconvolve(in1, in2, mode=mode)

    # SciPy says "For 'valid' mode, one must be at least as large as the
    # other in every dimension". So 'valid' is excluded from the testcases,
    # while SciPy fails to reject them.
    @pytest.mark.parametrize('mode', ['full', 'same'])
    @pytest.mark.parametrize(('shape1', 'shape2'), [
        ((5, 1), (1, 4)),
        ((5, 1, 1), (1, 4, 1)),
    ], ids=tupleid)
    @testing.for_dtypes('efdFD')
    @testing.numpy_cupy_allclose(atol=1e-3, rtol=1e-3, scipy_name='scp')
    def test_fftconvolve1_incomparable_shape(
            self, xp, scp, dtype, shape1, shape2, mode):
        in1 = testing.shaped_random(shape1, xp, dtype)
        in2 = testing.shaped_random(shape2, xp, dtype)
        return scp.signal.fftconvolve(in1, in2, mode=mode)

    @pytest.mark.parametrize('mode', ['full', 'same', 'valid'])
    @pytest.mark.parametrize(('shape1', 'shape2', 'axes'), [
        ((1, 4), (2, 4), (0,)),
        # ((3, 3), (3, 3), ()), => ValueError. Only reduced axes can be empty.
        ((2, 5, 5), (2, 1, 3), (1, 2)),
        ((2, 5, 5), (2, 1, 1), (1, 2)),
        ((1, 5, 5), (2, 1, 3), (1, 2)),  # broadcast
    ], ids=tupleid)
    @testing.for_dtypes('efdFD')
    @testing.numpy_cupy_allclose(atol=1e-3, rtol=1e-3, scipy_name='scp')
    def test_fftconvolve1_axes(
            self, xp, scp, dtype, shape1, shape2, axes, mode):
        in1 = testing.shaped_random(shape1, xp, dtype)
        in2 = testing.shaped_random(shape2, xp, dtype)
        return scp.signal.fftconvolve(in1, in2, mode=mode, axes=axes)


@testing.parameterize(*testing.product({
    'size1': [(10,), (5, 10), (10, 3), (3, 10, 15)],
    'size2': [3, 4, 5, 10, None],
    'mode': ['full', 'same', 'valid'],
}))
@testing.with_requires('scipy')
class TestOAConvolve:
    tols = {np.float32: 1e-3, np.complex64: 1e-3,
            np.float16: 1e-3, 'default': 1e-8}

    @testing.for_all_dtypes()
    @testing.numpy_cupy_allclose(atol=tols, rtol=tols, scipy_name='scp',
                                 accept_error=ValueError)
    def test_oaconvolve(self, xp, scp, dtype):
        if runtime.is_hip and self.size2 in [5, None]:
            pytest.xfail('ROCm/HIP may have a bug')
        in1 = testing.shaped_random(self.size1, xp, dtype)
        shape2 = self.size1 if self.size2 is None else (self.size2,)*in1.ndim
        in2 = testing.shaped_random(shape2, xp, dtype)
        return scp.signal.oaconvolve(in1, in2, self.mode)


@testing.parameterize(*(testing.product({
    'size1': [(5, 10), (10, 7)],
    'size2': [(3, 2), (3, 3), (2, 2), (10, 10), (11, 11)],
    'mode': ['full', 'same', 'valid'],
    'boundary': ['fill'],
    'fillvalue': [0, 1, -1],
}) + testing.product({
    'size1': [(5, 10), (10, 7)],
    'size2': [(3, 2), (3, 3), (2, 2), (10, 10), (11, 11)],
    'mode': ['full', 'same', 'valid'],
    'boundary': ['wrap', 'symm'],
    'fillvalue': [0],
})))
@testing.with_requires('scipy')
class TestConvolveCorrelate2D:
    def _filter(self, func, dtype, xp, scp):
        if self.mode == 'full' and self.boundary != 'fill':
            # See https://github.com/scipy/scipy/issues/12685
            pytest.skip('broken in scipy')
        if np.dtype(dtype).kind == 'u' and self.fillvalue < 0:
            pytest.skip('fillvalue overflow')
        in1 = testing.shaped_random(self.size1, xp, dtype)
        in2 = testing.shaped_random(self.size2, xp, dtype)
        return getattr(scp.signal, func)(in1, in2, self.mode, self.boundary,
                                         self.fillvalue)

    tols = {np.float32: 5e-4, np.complex64: 5e-4,
            np.float16: 1e-3, 'default': 1e-10}

    @testing.for_all_dtypes()
    @testing.numpy_cupy_allclose(atol=tols, rtol=tols, scipy_name='scp',
                                 accept_error=ValueError)
    def test_convolve2d(self, xp, scp, dtype):
        return self._filter('convolve2d', dtype, xp, scp)

    @testing.for_all_dtypes()
    @testing.numpy_cupy_allclose(atol=tols, rtol=tols, scipy_name='scp',
                                 accept_error=ValueError)
    def test_correlate2d(self, xp, scp, dtype):
        return self._filter('correlate2d', dtype, xp, scp)


@testing.with_requires('scipy')
class TestConvolve2DEdgeCase:

    @testing.numpy_cupy_allclose(atol=1e-5, rtol=1e-5, scipy_name='scp')
    def test_convolve2d_1(self, xp, scp):
        # see cupy/cupy#5989
        from scipy import misc
        ascent = misc.ascent()
        if xp is cupy:
            ascent = xp.asarray(ascent)
        scharr = xp.array(
            [[-3-3j, 0-10j, +3-3j],
             [-10+0j, 0+0j, +10+0j],
             [-3+3j, 0+10j, +3+3j]])  # Gx + j*Gy
        return scp.signal.convolve2d(
            ascent, scharr, boundary='symm', mode='same')

    @testing.numpy_cupy_allclose(atol=1e-5, rtol=1e-5, scipy_name='scp')
    def test_convolve2d_2(self, xp, scp):
        # see cupy/cupy#6047
        a = xp.array([[257]], dtype="uint64")
        b = xp.array([[1]], dtype="uint8")
        return scp.signal.convolve2d(a, b, mode="same")

    @testing.numpy_cupy_allclose(atol=1e-5, rtol=1e-5, scipy_name='scp')
    def test_convolve2d_3(self, xp, scp):
        # see cupy/cupy#6047
        a = xp.array([[257]], dtype="uint64")
        b = xp.array([[1]], dtype="uint8")
        return scp.signal.convolve2d(b, a, mode="same")


@testing.parameterize(*testing.product({
    'mode': ['valid', 'same', 'full']
}))
class TestChooseConvMethod:

    @testing.for_dtypes('efdFD')
    def test_choose_conv_method1(self, dtype):
        a = testing.shaped_arange((10000,), cupy, dtype)
        b = testing.shaped_arange((5000,), cupy, dtype)
        assert cupyx.scipy.signal.choose_conv_method(
            a, b, mode=self.mode) == 'fft'

    @testing.for_dtypes('efdFD')
    def test_choose_conv_method2(self, dtype):
        a = testing.shaped_arange((5000,), cupy, dtype)
        b = testing.shaped_arange((10000,), cupy, dtype)
        assert cupyx.scipy.signal.choose_conv_method(
            a, b, mode=self.mode) == 'fft'

    @testing.for_int_dtypes()
    def test_choose_conv_method_int(self, dtype):
        a = testing.shaped_arange((10,), cupy, dtype)
        b = testing.shaped_arange((5,), cupy, dtype)
        assert cupyx.scipy.signal.choose_conv_method(
            a, b, mode=self.mode) == 'direct'

    @testing.for_all_dtypes()
    def test_choose_conv_method_ndim(self, dtype):
        a = testing.shaped_arange((3, 4, 5), cupy, dtype)
        b = testing.shaped_arange((1, 2), cupy, dtype)
        with pytest.raises(NotImplementedError):
            cupyx.scipy.signal.choose_conv_method(a, b, mode=self.mode)

    @testing.for_all_dtypes()
    def test_choose_conv_method_zero_dim(self, dtype):
        a = testing.shaped_arange((), cupy, dtype)
        b = testing.shaped_arange((5,), cupy, dtype)
        with pytest.raises(NotImplementedError):
            cupyx.scipy.signal.choose_conv_method(a, b, mode=self.mode)


@testing.parameterize(*testing.product({
    'im': [(10,), (5, 10), (10, 3), (3, 4, 10)],
    'mysize': [3, 4, (3, 4, 5)],
    'noise': [False, True],
}))
@testing.with_requires('scipy')
class TestWiener:
    tols = {np.float32: 1e-5, np.complex64: 1e-5,
            np.float16: 1e-3, 'default': 1e-10}

    @testing.for_all_dtypes()
    @testing.numpy_cupy_allclose(atol=tols, rtol=tols, scipy_name='scp')
    def test_wiener(self, xp, scp, dtype):
        im = testing.shaped_random(self.im, xp, dtype)
        mysize = self.mysize
        if isinstance(mysize, tuple):
            mysize = mysize[:im.ndim]
        noise = (testing.shaped_random(self.im, xp, dtype)
                 if self.noise else None)
        out = scp.signal.wiener(im, mysize, noise)
        # Always returns float64 or complex128 data  in both scipy and
        # cupyx.scipy. Per-datatype tolerances are based on the output
        # data type but quality is based on input data type (if floating point)
        assert out.dtype == (np.complex128 if out.dtype.kind == 'c' else
                             np.float64)
        return out.astype(dtype, copy=False) if dtype in self.tols else out


@testing.parameterize(*testing.product({
    'a': [(10,), (5, 10), (10, 3), (3, 4, 10)],
    'domain': [3, 4, (3, 3, 5)],
    'rank': [0, 1, 2],
}))
@testing.with_requires('scipy')
class TestOrderFilter:
    @testing.for_all_dtypes(no_float16=True, no_bool=True, no_complex=True)
    @testing.numpy_cupy_allclose(atol=1e-8, rtol=1e-8, scipy_name='scp',
                                 accept_error=ValueError)  # for even kernels
    def test_order_filter(self, xp, scp, dtype):
        a = testing.shaped_random(self.a, xp, dtype)
        d = self.domain
        d = d[:a.ndim] if isinstance(d, tuple) else (d,)*a.ndim
        domain = testing.shaped_random(d, xp) > 0.25
        rank = min(self.rank, domain.sum())
        return scp.signal.order_filter(a, domain, rank)


@testing.parameterize(*testing.product({
    'volume': [(10,), (5, 10), (10, 5), (5, 6, 10)],
    'kernel_size': [3, 4, (3, 3, 5)],
}))
@testing.with_requires('scipy>=1.7.0')
class TestMedFilt:
    @testing.for_all_dtypes()
    @testing.numpy_cupy_allclose(atol=1e-8, rtol=1e-8, scipy_name='scp',
                                 accept_error=ValueError)  # for even kernels
    def test_medfilt(self, xp, scp, dtype):
        if sys.platform == 'win32':
            pytest.xfail('medfilt broken for Scipy 1.7.0 in windows')
        volume = testing.shaped_random(self.volume, xp, dtype)
        kernel_size = self.kernel_size
        if isinstance(kernel_size, tuple):
            kernel_size = kernel_size[:volume.ndim]
        return scp.signal.medfilt(volume, kernel_size)


@testing.parameterize(*testing.product({
    'input': [(5, 10), (10, 5)],
    'kernel_size': [3, 4, (3, 5)],
}))
@testing.with_requires('scipy>=1.7.0')
class TestMedFilt2d:
    @testing.for_all_dtypes()
    @testing.numpy_cupy_allclose(atol=1e-8, rtol=1e-8, scipy_name='scp',
                                 accept_error=ValueError)  # for even kernels
    def test_medfilt2d(self, xp, scp, dtype):
        if sys.platform == 'win32':
            pytest.xfail('medfilt2d broken for Scipy 1.7.0 in windows')
        input = testing.shaped_random(self.input, xp, dtype)
        kernel_size = self.kernel_size
        return scp.signal.medfilt2d(input, kernel_size)


@testing.with_requires('scipy')
class TestLFilter:
    @pytest.mark.parametrize('size', [11, 20, 32, 51, 64, 120, 128, 250])
    @pytest.mark.parametrize('fir_order', [1, 2, 3, 4, 5])
    @pytest.mark.parametrize('iir_order', [0, 1, 2, 3, 4, 5])
    @testing.for_all_dtypes_combination(
        no_float16=True, no_bool=True, names=('in_dtype', 'const_dtype'))
    @testing.numpy_cupy_allclose(scipy_name='scp', rtol=5e-3, type_check=False)
    def test_fir_iir_order(self, size, fir_order, iir_order,
                           in_dtype, const_dtype, xp, scp):
        out_dtype = xp.result_type(in_dtype, const_dtype)
        if xp.dtype(out_dtype).kind in {'i', 'u'}:
            pytest.skip()
        if (
            runtime.is_hip and driver.get_build_version() < 5_00_00000
            and iir_order > 0
        ):
            # ROCm 4.3 raises in Module.get_function()
            pytest.skip()
        x_scale = 0.5 if xp.dtype(in_dtype).kind not in {'i', 'u'} else 1

        x = testing.shaped_random((size,), xp, in_dtype, scale=x_scale)
        b = testing.shaped_random((fir_order,), xp, dtype=const_dtype, scale=1)
        a = testing.shaped_random((iir_order,), xp, dtype=const_dtype, scale=1)
        a = xp.r_[1, a]
        a = a.astype(const_dtype)

        res = scp.signal.lfilter(b, a, x)
        res = xp.nan_to_num(res, nan=xp.nan, posinf=xp.nan, neginf=xp.nan)
        return res

    @pytest.mark.parametrize('size', [11, 20, 32, 51, 64, 120])
    @pytest.mark.parametrize('fir_order', [1, 2, 3])
    @pytest.mark.parametrize('iir_order', [0, 1, 2, 3])
    @pytest.mark.parametrize('axis', [0, 1, 2, 3])
    @testing.for_all_dtypes_combination(
        no_float16=True, no_bool=True, names=('in_dtype', 'const_dtype'))
    @testing.numpy_cupy_array_almost_equal(
        scipy_name='scp', decimal=5, type_check=False)
    def test_fir_iir_order_ndim(
            self, size, fir_order, iir_order, axis, in_dtype,
            const_dtype, xp, scp):
        out_dtype = xp.result_type(in_dtype, const_dtype)
        if xp.dtype(out_dtype).kind in {'i', 'u'}:
            pytest.skip()
        if (
            runtime.is_hip and driver.get_build_version() < 5_00_00000
            and iir_order > 0
        ):
            # ROCm 4.3 raises in Module.get_function()
            pytest.skip()

        x_scale = 0.5 if xp.dtype(in_dtype).kind not in {'i', 'u'} else 1
        c_scale = 0.2 if xp.dtype(const_dtype).kind not in {'i', 'u'} else 1

        x = testing.shaped_random((4, 5, 3, size), xp, in_dtype, scale=x_scale)
        b = testing.shaped_random(
            (fir_order,), xp, dtype=const_dtype, scale=c_scale)
        a = testing.shaped_random(
            (iir_order,), xp, dtype=const_dtype, scale=c_scale)
        a = xp.r_[1, a]
        a = a.astype(const_dtype)

        res = scp.signal.lfilter(b, a, x, axis=axis)
        res = xp.nan_to_num(res, nan=xp.nan, posinf=xp.nan, neginf=xp.nan)
        return res

    @pytest.mark.parametrize('size', [11, 20, 32, 51, 64, 120, 128, 250])
    @pytest.mark.parametrize('fir_order', [1, 2, 3, 4, 5])
    @pytest.mark.parametrize('iir_order', [0, 1, 2, 3, 4, 5])
    @testing.for_all_dtypes_combination(
        no_float16=True, no_bool=True, names=('in_dtype', 'const_dtype'))
    @testing.numpy_cupy_array_almost_equal(
        scipy_name='scp', decimal=5, type_check=False)
    def test_fir_iir_zi(self, size, fir_order, iir_order,
                        in_dtype, const_dtype, xp, scp):
        out_dtype = xp.result_type(in_dtype, const_dtype)
        if xp.dtype(out_dtype).kind in {'i', 'u'}:
            pytest.skip()
        if (
            runtime.is_hip and driver.get_build_version() < 5_00_00000
            and iir_order > 0
        ):
            # ROCm 4.3 raises in Module.get_function()
            pytest.skip()

        x_scale = 0.5 if xp.dtype(in_dtype).kind not in {'i', 'u'} else 1
        c_scale = 0.2 if xp.dtype(const_dtype).kind not in {'i', 'u'} else 1

        x = testing.shaped_random((size,), xp, in_dtype, scale=x_scale)
        b = testing.shaped_random(
            (fir_order,), xp, dtype=const_dtype, scale=c_scale)
        a = testing.shaped_random(
            (iir_order,), xp, dtype=const_dtype, scale=c_scale)
        a = xp.r_[1, a]
        a = a.astype(const_dtype)

        zi = testing.shaped_random(
            (b.size + a.size - 2,), xp, in_dtype, scale=x_scale)
        if xp is not cupy:
            zi = scp.signal.lfiltic(
                b, a, zi[-iir_order:][::-1], zi[:fir_order - 1][::-1])

        res, _ = scp.signal.lfilter(b, a, x, zi=zi)
        res = xp.nan_to_num(res, nan=xp.nan, posinf=xp.nan, neginf=xp.nan)
        return res

    @pytest.mark.parametrize('size', [11, 20, 32, 51, 64, 120])
    @pytest.mark.parametrize('fir_order', [1, 2, 3])
    @pytest.mark.parametrize('iir_order', [0, 1, 2, 3])
    @pytest.mark.parametrize('axis', [0, 1, 2, 3])
    @testing.for_all_dtypes_combination(
        no_float16=True, no_bool=True, names=('in_dtype', 'const_dtype'))
    @testing.numpy_cupy_array_almost_equal(
        scipy_name='scp', decimal=5, type_check=False)
    def test_fir_iir_zi_ndim(
            self, size, fir_order, iir_order, axis, in_dtype,
            const_dtype, xp, scp):
        out_dtype = xp.result_type(in_dtype, const_dtype)
        if xp.dtype(out_dtype).kind in {'i', 'u'}:
            pytest.skip()
        if (
            runtime.is_hip and driver.get_build_version() < 5_00_00000
            and iir_order > 0
        ):
            # ROCm 4.3 raises in Module.get_function()
            pytest.skip()

        x_scale = 0.5 if xp.dtype(in_dtype).kind not in {'i', 'u'} else 1
        c_scale = 0.2 if xp.dtype(const_dtype).kind not in {'i', 'u'} else 1

        x = testing.shaped_random((4, 5, 3, size), xp, in_dtype, scale=x_scale)
        b = testing.shaped_random(
            (fir_order,), xp, dtype=const_dtype, scale=c_scale)
        a = testing.shaped_random(
            (iir_order,), xp, dtype=const_dtype, scale=c_scale)
        a = xp.r_[1, a]
        a = a.astype(const_dtype)

        zi_shape = list(x.shape)
        zi_shape[axis] = fir_order + iir_order - 1
        zi = testing.shaped_random(zi_shape, xp, dtype=in_dtype)

        if xp is not cupy:
            zi = xp.moveaxis(zi, axis, -1)
            zi_m_shape = zi.shape
            zi = zi.reshape(
                int(np.prod(zi_m_shape[:-1])),
                fir_order + iir_order - 1).copy()
            zi = xp.concatenate([
                scp.signal.lfiltic(
                    b, a, z[-iir_order:][::-1], z[:fir_order - 1][::-1])
                for z in zi])
            zi = zi.reshape(zi_m_shape[:-1] + (-1,))
            zi = xp.moveaxis(zi, -1, axis)

        res, _ = scp.signal.lfilter(b, a, x, zi=zi, axis=axis)
        res = xp.nan_to_num(res, nan=xp.nan, posinf=xp.nan, neginf=xp.nan)
        return res

    @pytest.mark.parametrize('fir_order', [1, 2, 3])
    @pytest.mark.parametrize('iir_order', [0, 1, 2, 3])
    @testing.numpy_cupy_array_almost_equal(scipy_name='scp', decimal=5)
    def test_lfiltic(self, fir_order, iir_order, xp, scp):
        x = testing.shaped_random((20,), xp)
        b = testing.shaped_random((fir_order,), xp, scale=0.3)
        a = testing.shaped_random((iir_order,), xp, scale=0.3)
        a = xp.r_[1, a]

        zi = testing.shaped_random((fir_order + iir_order - 1,), xp)
        zi = scp.signal.lfiltic(b, a, zi[-iir_order:], zi[:fir_order - 1])

        out, _ = scp.signal.lfilter(b, a, x, zi=zi)
        return out

    @pytest.mark.parametrize('fir_order', [1, 2, 3])
    @pytest.mark.parametrize('iir_order', [1, 2, 3])
    @testing.numpy_cupy_array_almost_equal(scipy_name='scp', decimal=5)
    def test_lfilter_zi(self, fir_order, iir_order, xp, scp):
        x = xp.ones(20)
        b = testing.shaped_random((fir_order,), xp, scale=0.3)
        a = testing.shaped_random((iir_order,), xp, scale=0.3)
        a = xp.r_[1, a]

        zi = scp.signal.lfilter_zi(b, a)
        out, _ = scp.signal.lfilter(b, a, x, zi=zi)
        return out


@testing.with_requires('scipy')
class TestDeconvolve:
    @pytest.mark.parametrize('order', [1, 2, 3])
    @testing.numpy_cupy_array_almost_equal(scipy_name='scp', decimal=3)
    def test_deconvolve(self, order, xp, scp):
        x = testing.shaped_random((20,), xp)
        b = testing.shaped_random((order,), xp, scale=0.3)
        o = scp.signal.convolve(x, b)
        return scp.signal.deconvolve(o, b)


@testing.with_requires('scipy')
class TestFiltFilt:
    @pytest.mark.parametrize('size', [11, 20, 32, 51, 64, 120, 128, 250])
    @pytest.mark.parametrize('fir_order', [1, 2, 3])
    @pytest.mark.parametrize('iir_order', [1, 2, 3])
    @pytest.mark.parametrize('method', ['pad', 'gust'])
    @pytest.mark.parametrize('padtype', ['odd', 'even', 'constant', None])
    @testing.for_all_dtypes_combination(
        no_float16=True, no_bool=True, names=('in_dtype', 'const_dtype'))
    @testing.numpy_cupy_allclose(scipy_name='scp', rtol=5e-3,
                                 type_check=False, accept_error=True)
    def test_filtfilt_1d(self, size, fir_order, iir_order, method, padtype,
                         in_dtype, const_dtype, xp, scp):
        out_dtype = xp.result_type(in_dtype, const_dtype)
        if xp.dtype(out_dtype).kind in {'i', 'u'}:
            pytest.skip()
        if (
            runtime.is_hip and driver.get_build_version() < 5_00_00000
            and iir_order > 0
        ):
            # ROCm 4.3 raises in Module.get_function()
            pytest.skip()
        x_scale = 0.1 if xp.dtype(in_dtype).kind not in {'i', 'u'} else 1
        c_scale = 0.1 if xp.dtype(const_dtype).kind not in {'i', 'u'} else 1

        x = testing.shaped_random((size,), xp, in_dtype, scale=x_scale)
        b = testing.shaped_random(
            (fir_order,), xp, dtype=const_dtype, scale=c_scale)
        a = testing.shaped_random(
            (iir_order,), xp, dtype=const_dtype, scale=c_scale)
        a = xp.r_[1, a]
        a = a.astype(const_dtype)

        res = scp.signal.filtfilt(b, a, x, method=method, padtype=padtype)
        res = xp.nan_to_num(res, nan=xp.nan, posinf=xp.nan, neginf=xp.nan)
        return res

    @pytest.mark.parametrize('size', [11, 20, 32, 51, 64, 120])
    @pytest.mark.parametrize('fir_order', [1, 2, 3])
    @pytest.mark.parametrize('iir_order', [1, 2, 3])
    @pytest.mark.parametrize('axis', [0, 1, 2, 3])
    @pytest.mark.parametrize('method', ['pad', 'gust'])
    @pytest.mark.parametrize('padtype', ['odd', 'even', 'constant', None])
    @testing.for_all_dtypes_combination(
        no_float16=True, no_bool=True, names=('in_dtype', 'const_dtype'))
    @testing.numpy_cupy_array_almost_equal(
        scipy_name='scp', decimal=5, type_check=False, accept_error=True)
    def test_filtfilt_ndim(
            self, size, fir_order, iir_order, axis, method, padtype, in_dtype,
            const_dtype, xp, scp):
        out_dtype = xp.result_type(in_dtype, const_dtype)
        if xp.dtype(out_dtype).kind in {'i', 'u'}:
            pytest.skip()
        if (
            runtime.is_hip and driver.get_build_version() < 5_00_00000
            and iir_order > 0
        ):
            # ROCm 4.3 raises in Module.get_function()
            pytest.skip()

        x_scale = 0.1 if xp.dtype(in_dtype).kind not in {'i', 'u'} else 1
        c_scale = 0.1 if xp.dtype(const_dtype).kind not in {'i', 'u'} else 1

        x = testing.shaped_random((4, 5, 3, size), xp, in_dtype, scale=x_scale)
        b = testing.shaped_random(
            (fir_order,), xp, dtype=const_dtype, scale=c_scale)
        a = testing.shaped_random(
            (iir_order,), xp, dtype=const_dtype, scale=c_scale)
        a = xp.r_[1, a]
        a = a.astype(const_dtype)

        res = scp.signal.filtfilt(b, a, x, axis=axis,
                                  method=method, padtype=padtype)
        res = xp.nan_to_num(res, nan=xp.nan, posinf=xp.nan, neginf=xp.nan)
        return res
