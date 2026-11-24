import numpy as np
from math import comb
from functools import lru_cache
from scipy.constants import R as scipy_R
from scipy.signal import savgol_filter, whittaker_henderson, firwin, filtfilt
from scipy.sparse import diags
from scipy.sparse.linalg import factorized
import pywt
from pybaselines import Baseline

DEBUG = False

def normalize(data, y_min, y_max):
    if y_max != y_min:
        normalized_data = (data - y_min) / (y_max - y_min)
    else:
        raise ZeroDivisionError("Minimum and maximum are equal.")
    return normalized_data

# find index of the selected value in numpy array
def find_indexes(x1,x2,array):

    # Get the absolute difference between all values in the array and the selected value, and get the index of the minimum value which will be the value closest to the selection
    xmin = np.abs(array - x1).argmin()
    xmax = np.abs(array - x2).argmin()

    if xmin > xmax:
        # Correct for non-inclusive selection by returning the next index for xmax
        return xmax, xmin+1

    return xmin, xmax+1

def get_maximum(x1, x2, x_array, y_array):
    
    xmin,xmax = find_indexes(x1,x2,x_array)

    #define ypoints that are important for peak picking
    ypoints = y_array[xmin:xmax]

    #get index of maximum
    if ypoints.size == 0:
        ind = None

    else:
        maxval = ypoints.max()
        # get index of maximum value in array
        ind = np.where(ypoints==maxval)[0][0]

    if ind is None:
        if DEBUG: print("Selection resulted in zero-size array")
        return
    
    maximum = xmin+ind

    #x value of maximum
    max_x_val = x_array[maximum]

    #get y value for maximum
    max_y_val = y_array[maximum]

    return max_x_val, max_y_val

def get_minimum(x1, x2, x_array, y_array):

    xmin,xmax = find_indexes(x1,x2,x_array)

    #define ypoints that are important for peak picking
    ypoints = y_array[xmin:xmax]

    #get index of maximum
    if ypoints.size == 0:
        ind = None

    else:
        minval = ypoints.min()
        # get index of maximum value in array
        ind = np.where(ypoints==minval)[0][0]

    if ind is None:
        if DEBUG: print("Selection resulted in zero-size array")
        return
    
    minimum = xmin+ind

    #x value of maximum
    min_x_val = x_array[minimum]

    #get y value for maximum
    min_y_val = y_array[minimum]

    return min_x_val, min_y_val

# Lorentzian Fit for 1 Peak
def lorentzian(x, amp1, cen1, wid1):
    return (amp1*wid1**2/((x-cen1)**2+wid1**2))


# Sigmoidal function with constant baseline
def sigmoidal_constant_baseline(x:float, A:float, B:float, H:float, tm:float):
    T = x + 273.15 # Calculate temperature in Kelvin
    Tm = tm + 273.15 # Calculate temperature in Kelvin
    dG = (1000*H) * (1-(T / Tm)) # Unit of H: kJ/mol
    K = np.exp( -dG / (scipy_R * T))
    return A + (B-A) / (1+K)

# Sigmoidal function with linear baseline
def sigmoidal_linear_baseline(x:float, a:float, b:float, c:float, d:float, H:float, tm:float):
    A = a * x + b
    B = c * x + d
    return sigmoidal_constant_baseline(x, A, B, H, tm)

# Sigmoidal function with quadratic baseline
def sigmoidal_quadratic_baseline(x:float, a:float, b:float, c:float, d:float, e:float, f:float, H:float, tm:float):
    A = a * x**2 + b * x + c
    B = d * x**2 + e * x + f
    return sigmoidal_constant_baseline(x, A, B, H, tm)

def vant_hoff(x:float, A:float, B:float, H:float, tm:float):
    T = x + 273.15 # Calculate temperature in Kelvin
    Tm = tm + 273.15 # Calculate temperature in Kelvin
    K = np.exp( (1000 * H / scipy_R) * (1 / Tm - 1 / T) )
    return B + A * -( (1000*H / (scipy_R*T**2) ) * ( K/((1+K)**2) ) )

# Gaussian fit
def gaussian(x:float, A:float, B:float, w:float, Tm:float):
    return B + A * np.exp(-( (x-Tm)**2 ) / (2 * (w**2) )) # A: Amplitude, B: Offset, w: RMS width, Tm: Maximum

# Michaelis Menten equation
def michaelis_menten(x:float, Km:float, vmax:float):
    return (vmax * x) / (Km + x)

# Emancipator and Kroll (1993) method for calculating dimensional and relative nonlinearity
def emancipator_kroll_nonlinearity(x, y):
    """
    Calculate dimensional and relative nonlinearity of a given dataset using the method described by Emancipator and Kroll (1993).
    
    x, y: 1D numpy arrays of the same length representing the data points.
    degree: Degree of the polynomial to fit the data (default is 3).
    """

    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    if x.ndim != 1 or y.ndim != 1:
        raise ValueError("Input arrays must be 1D.")

    if x.size != y.size:
        raise ValueError("Input arrays must have the same length.")

    if x.size < 4:
        raise ValueError("Input arrays must have at least 4 elements.")

    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Input arrays must contain only finite numbers.")

    if np.any(np.diff(x) <= 0):
        raise ValueError("x values must be strictly increasing.")

    if np.ptp(y) == 0:
        raise ValueError("y values must not be constant.")

    if np.std(x) <= 0:
        raise ValueError("Standard deviation of x values must be greater than zero.")

    mean = np.mean(x)
    std = np.std(x)
    
    x_scaled = (x - mean) / std

    x_l = x_scaled[0]
    x_u = x_scaled[-1]

    # Fit a polynomial of the specified degree to the data

    bic = np.inf
    best_degree = 2

    for degree in range(2, x.size-1):
        try:
            nonlinear_function = np.polynomial.polynomial.Polynomial.fit(x_scaled, y, degree).convert()
            y_fit = nonlinear_function(x_scaled)
            bic_iteration = bayesian_information_criterion(y, y_fit, degree + 2)  # +2 for the constant and estimated residual variance
            if bic_iteration < bic:
                bic = bic_iteration
                best_degree = degree
                best_nonlinear_function = nonlinear_function
            else:
                break  # Stop if BIC starts to increase. Generally searching the global minimum would be better, but this is a good compromise between speed and accuracy.
                       # Furthermore, the BIC is only used to aid in calculating the quantitative nonlinearity which is only meant to be a diagnostic measure.
        except Exception as e:
            raise RuntimeError(f"Polynomial fitting failed for degree {degree}: {e}")

    nonlinear_function = best_nonlinear_function

    x_var = np.polynomial.Polynomial([0, 1])  # Represents the "x"

    nonlinear_function_times_x = nonlinear_function * x_var

    integral_from_xl_to_xu = nonlinear_function.integ(lbnd=x_l)(x_u)
    integral_of_x_times_function_from_xl_to_xu = nonlinear_function_times_x.integ(lbnd=x_l)(x_u)

    b_value_numerator = ((x_u - x_l) * integral_of_x_times_function_from_xl_to_xu) - (1/2 * (x_u**2 - x_l**2) * integral_from_xl_to_xu)
    b_value_denominator = (1/3 * (x_u - x_l) * (x_u**3 - x_l**3)) - (1/4 * (x_u**2 - x_l**2)**2)

    # Check for division by zero in b_value_denominator
    if b_value_denominator == 0:
        raise ValueError("The denominator for calculating b_value is zero, leading to division by zero.")

    b_value = b_value_numerator / b_value_denominator

    a_value_numerator = integral_from_xl_to_xu - (1/2 * (x_u**2 - x_l**2) * b_value)
    a_value_denominator = (x_u - x_l)

    # Check for division by zero in a_value_denominator
    if a_value_denominator == 0:
        raise ValueError("The denominator for calculating a_value is zero, leading to division by zero.")
    
    a_value = a_value_numerator / a_value_denominator

    linear_function = np.polynomial.Polynomial([a_value, b_value])

    nonlinear_linear_deviation_function = (nonlinear_function - linear_function)**2

    dimensional_nonlinearity = np.sqrt(nonlinear_linear_deviation_function.integ(lbnd=x_l)(x_u) / (x_u - x_l))

    y_from_nonlinear_function = nonlinear_function(x_scaled)

    fitted_response_range = np.ptp(y_from_nonlinear_function)

    if fitted_response_range == 0:
        raise ValueError("The difference between the nonlinear function evaluated at the endpoints is zero, leading to division by zero in relative nonlinearity calculation.")

    relative_nonlinearity = dimensional_nonlinearity / fitted_response_range

    x_scaled_of_x = np.polynomial.Polynomial([-mean / std, 1 / std])  # Scaling polynomial to convert back to original x values

    nonlinear_function_in_x = nonlinear_function(x_scaled_of_x)

    return {"dimensional": dimensional_nonlinearity, 
            "relative": relative_nonlinearity, 
            "polynomial_degree": best_degree, 
            "bic": bic,
            "polynomial_coefficients": nonlinear_function_in_x.coef}

def bayesian_information_criterion(y_exp, y_fit, num_params):

    y_exp = np.asarray(y_exp, dtype=np.float64)
    y_fit = np.asarray(y_fit, dtype=np.float64)

    if y_exp.ndim != 1 or y_fit.ndim != 1:
        raise ValueError("Input arrays must be 1D.")

    if y_exp.size != y_fit.size:
        raise ValueError("Input arrays must have the same length.")

    if y_exp.size == 0:
        raise ValueError("Input arrays must not be empty.")

    if not np.all(np.isfinite(y_exp)) or not np.all(np.isfinite(y_fit)):
        raise ValueError("Input arrays must contain only finite numbers.")

    n = y_exp.size
    SS_res = np.sum((y_exp - y_fit) ** 2)
    if SS_res <= 0:
        raise ValueError("Residual sum of squares must be positive for BIC calculation.")
    bic = n * np.log(SS_res / n) + num_params * np.log(n)
    
    return bic

def R_square(y_exp, y_fit):
    SS_res = sum((y_exp - y_fit)**2)
    SS_tot = sum((y_exp - np.mean(y_exp))**2)
    if SS_tot == 0:
        print("Total sum of squares is zero, cannot compute R-squared.")
        return np.nan
    return float(1 - (SS_res / SS_tot))

def return_fit_param(popt, pcov, c_index:int):
    value = popt[c_index]
    error = np.sqrt(np.diag(pcov))[c_index]
    return float(value), float(error)



def smooth_savitzky_golay(signal, window_length:int = 23, polyorder:int = 6):

    signal = np.asarray(signal, dtype=np.float64)

    if signal.size == 0:
        raise ValueError("Input array must not be empty.")

    if not np.all(np.isfinite(signal)):
        raise ValueError("Input array must contain only finite numbers.")
    
    return savgol_filter(signal, window_length, polyorder)


def smooth_whittaker(signal, d:int = 2):
    signal = np.asarray(signal, dtype=np.float64)

    if signal.size == 0:
            raise ValueError("Input array must not be empty.")
    
    if not np.all(np.isfinite(signal)):
        raise ValueError("Input array must contain only finite numbers.")
    
    return whittaker_henderson(signal, order=d).x

def smooth_FIR_low_pass(signal, numtaps:int = 31, cutoff_freq:float = 0.1):

    signal = np.asarray(signal, dtype=np.float64)

    if signal.size == 0:
        raise ValueError("Input array must not be empty.")

    if not np.all(np.isfinite(signal)):
        raise ValueError("Input array must contain only finite numbers.")

    if numtaps <= 0 or not isinstance(numtaps, int):
        raise ValueError("numtaps must be a positive integer.")

    # Get the FIR filter coefficients using the window method
    fir_coefficients = firwin(numtaps, cutoff_freq)

    return filtfilt(fir_coefficients, [1], signal)

def smooth_wavelet(signal, wavelet:str = "db4"):

    signal = np.asarray(signal, dtype=np.float64)

    if signal.size == 0:
        raise ValueError("Input array must not be empty.")

    if not np.all(np.isfinite(signal)):
        raise ValueError("Input array must contain only finite numbers.")

    # Perform wavelet decomposition
    coeffs = pywt.wavedec(signal, wavelet)

    # Since the noise is expected to be independent Gaussian noise, we can calculate the threshold using the universal threshold method
    sigma = np.median(np.abs(coeffs[-1])) / 0.6745  # Estimate noise level from the detail coefficients
    threshold = sigma * np.sqrt(2 * np.log(len(signal)))  # Universal threshold

    # Apply soft thresholding to the detail coefficients
    coeffs_thresholded = [coeffs[0]] + [pywt.threshold(c, threshold, mode="garrote") for c in coeffs[1:]]

    smooth_signal = pywt.waverec(coeffs_thresholded, wavelet)

    return smooth_signal[:signal.size]  # Return the smoothed signal with the same length as the input

@lru_cache(maxsize=4)
def _sass_operator_setup(n:int, K:int, d:int, fc:float):
    def filter_matrix(order, length, sign):
        coefficients = [
            sign ** (order - index) * comb(order, index)
            for index in range(order + 1)
        ]
        return diags(
            coefficients,
            offsets=np.arange(order + 1),
            shape=(length - order, length),
            dtype=np.float64,
            format="csc",
        )

    # Equations (19), (20), and (22): P, Q, and alpha.
    P = filter_matrix(d, n, -1)
    Q = filter_matrix(d, n, 1)
    cutoff_freq = np.pi * fc
    alpha = 1 / np.tan(cutoff_freq / 2) ** (2 * d)

    # Equations (8), (9), and (16): A, H, and G=I-H.
    A = (Q.T @ Q + alpha * (P.T @ P)).tocsc()
    solve_A = factorized(A)

    # Equations (27)-(30): P=P1*D, where u=D*x1 is sparse.
    P1 = filter_matrix(d - K, n - K, -1)

    # These products are reused by every SASS operator application.
    R_operator = (P.T @ P1).tocsc()
    RT_operator = (P1.T @ P).tocsc()

    return R_operator, Q, RT_operator, alpha, solve_A


@lru_cache(maxsize=4)
def _sass_lipschitz(n:int, K:int, d:int, fc:float):
    R_operator, _, RT_operator, alpha, solve_A = _sass_operator_setup(
        n, K, d, fc
    )

    def R_times(vector):
        return alpha * solve_A(R_operator @ vector)

    def RT_times(vector):
        return alpha * (RT_operator @ solve_A(vector))

    probe = np.random.default_rng(0).normal(size=n - K)
    probe /= np.linalg.norm(probe)
    for _ in range(30):
        probe = RT_times(R_times(probe))
        probe_norm = np.linalg.norm(probe)
        if probe_norm == 0:
            raise RuntimeError("Unable to estimate the SASS operator norm.")
        probe /= probe_norm

    return max(
        float(np.dot(probe, RT_times(R_times(probe)))),
        np.finfo(float).eps,
    )


def smooth_sass(signal, lambda_:float = 30.0, K:int = 1, d:int = 1,
                fc:float = 0.25, max_iterations:int = 500,
                tolerance:float = 1e-6):
    """Apply the SASS formulation from Selesnick (2017).

    The paper defines P(z)=(1-z^-1)^d, Q(z)=(1+z^-1)^d and
    alpha=1/tan^(2d)(fc*pi/2). It then minimizes equation (42) over
    the sparse vector u=D*x1, using x_hat=H*y+R*u.

    ``fc`` is normalized so that 1 corresponds to the Nyquist frequency.
    """

    y = np.asarray(signal, dtype=np.float64)

    if y.ndim != 1:
        raise ValueError("Input signal must be one-dimensional.")
    if y.size == 0:
        raise ValueError("Input array must not be empty.")
    if not np.all(np.isfinite(y)):
        raise ValueError("Input array must contain only finite numbers.")
    if not isinstance(K, int) or K < 1:
        raise ValueError("K must be a positive integer.")
    if not isinstance(d, int) or d < K:
        raise ValueError("d must be an integer greater than or equal to K.")
    if y.size <= d:
        raise ValueError("Input signal is too short for the selected d.")
    if lambda_ < 0 or not np.isfinite(lambda_):
        raise ValueError("lambda_ must be finite and non-negative.")
    if not 0 < fc < 1:
        raise ValueError("fc must be between 0 and 1.")
    if not isinstance(max_iterations, int) or max_iterations < 1:
        raise ValueError("max_iterations must be a positive integer.")
    if tolerance <= 0 or not np.isfinite(tolerance):
        raise ValueError("tolerance must be finite and positive.")

    n = y.size

    R_operator, Q, RT_operator, alpha, solve_A = _sass_operator_setup(
        n, K, d, fc
    )

    # Equation (9): H*y, and equation (16): G*y=(I-H)y.
    H_y = solve_A(Q.T @ (Q @ y))
    G_y = y - H_y

    # Equations (39)-(42): x_hat=H*y+R*u and the l1 sparse least-squares
    # objective, with R = alpha*A^-1*P.T*P1.
    def R_times(vector):
        return alpha * solve_A(R_operator @ vector)

    def RT_times(vector):
        return alpha * (RT_operator @ solve_A(vector))

    # Equation (42) is solved with FISTA, one of the solvers explicitly
    # listed by the paper for this standard l1 sparse least-squares problem.
    # FISTA is implemented as suggested by Beck and Teboulle (2009)
    
    # Estimate the Lipschitz constant of the SASS operator R^T R using the
    # power method. It depends only on the signal length and filter settings.
    u = np.zeros(n - K)
    accelerated_u = u.copy()
    momentum = 1.0
    lipschitz = _sass_lipschitz(n, K, d, fc)

    # Iterate FISTA until convergence or until the maximum number of iterations is reached.
    inverse_lipschitz = 1 / lipschitz
    threshold = lambda_ * inverse_lipschitz
    for _ in range(max_iterations):
        residual = R_times(accelerated_u) - G_y
        gradient = RT_times(residual)
        proximal_input = accelerated_u - gradient * inverse_lipschitz
        next_u = np.sign(proximal_input) * np.maximum(
            np.abs(proximal_input) - threshold,
            0,
        )
        next_momentum = (1 + np.sqrt(1 + 4 * momentum**2)) / 2
        accelerated_u = next_u + (
            (momentum - 1) / next_momentum
        ) * (next_u - u)

        if np.linalg.norm(next_u - u) <= tolerance * max(1, np.linalg.norm(u)):
            u = next_u
            break
        u = next_u
        momentum = next_momentum

    # Finally, compute the smoothed signal x_hat using the SASS formulation.
    x_hat = H_y + R_times(u)
    return x_hat

# A simple helper function to simply access all smothing methods in one place.
def smooth_signal(signal, method:str = "none", **kwargs):
    if method == "None":
        return signal
    elif method == "Savitzky-Golay":
        return smooth_savitzky_golay(signal, **kwargs)
    elif method == "Whittaker":
        return smooth_whittaker(signal, **kwargs)
    elif method == "FIR low-pass filtering":
        return smooth_FIR_low_pass(signal, **kwargs)
    elif method == "Wavelet filtering":
        return smooth_wavelet(signal, **kwargs)
    elif method == "Sparsity-assisted signal smoothing":
        return smooth_sass(signal, **kwargs)
    else:
        raise ValueError(f"Unknown smoothing method: {method}")

def lmv_baseline(
    signal,
    window_size: int = 5,
    snr_threshold: float = 2.5,
    tolerance: float = 1e-4,
    max_iterations: int = 1000,
):
    """Estimate a chromatographic baseline using the LMV-RSA method 
    described by H.-Y. Fu, H.-D. Li, Y.-J. Yu, B. Wang, P. Lu, H.-P. Cui, P.-P. Liu and Y.-B. She (2016).

    Local minima are used as initial baseline points. Points that are likely
    to belong to peaks are iteratively replaced by the median of a moving
    window, while a second estimate removes outliers from the first
    derivative. The lower of both estimates is linearly interpolated over
    the complete signal.
    """
    signal = np.asarray(signal, dtype=np.float64)

    # Check whether the signal is a 1D numpy array and contains valid values
    if signal.ndim != 1:
        raise ValueError("Input signal must be one-dimensional.")
    if signal.size == 0:
        raise ValueError("Input array must not be empty.")
    if not np.all(np.isfinite(signal)):
        raise ValueError("Input array must contain only finite numbers.")
    if not isinstance(window_size, (int, np.integer)) or window_size < 1:
        raise ValueError("window_size must be a positive integer.")
    if not np.isfinite(snr_threshold) or snr_threshold <= 0:
        raise ValueError("snr_threshold must be finite and positive.")
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance must be finite and positive.")
    if not isinstance(max_iterations, (int, np.integer)) or max_iterations < 1:
        raise ValueError("max_iterations must be a positive integer.")

    # If the signal is too short, return a copy of the original signal
    if signal.size < 3:
        return signal.copy()

    # Get the local minima indices and subsequently values. By checking the equation c_i-1 > c_i < c_i+1 presented in the paper.
    minimum_positions = np.flatnonzero(
        (signal[1:-1] < signal[:-2]) & (signal[1:-1] < signal[2:])
    ) + 1
    if minimum_positions.size == 0:
        return np.full(signal.size, signal.min(), dtype=np.float64)

    minimum_vector = signal[minimum_positions].copy()
    if minimum_vector.size == 1:
        return np.full(signal.size, minimum_vector[0], dtype=np.float64)

    # Estimate the noise level of the signal using the median absolute deviation equation in the first order derivative of the minimum vector x
    def noise_level(min_vector):
        # First order derivative of the minimum vector is estimated using numpy.diff().
        derivative = np.diff(min_vector)
        if derivative.size == 0:
            return 0.0
        median_derivative = np.median(derivative)
        return 1.483 * np.median(np.abs(derivative - median_derivative))

    # First estimate: reject high-SNR minimum values with a moving window.
    optimized_minimum_vector = minimum_vector.copy()
    minimum_count = optimized_minimum_vector.size
    if minimum_count < window_size:
        window_starts = None
    else:
        half_window = window_size // 2
        window_starts = np.maximum(
            np.arange(minimum_count) - half_window,
            0,
        )
        window_starts = np.minimum(window_starts, minimum_count - window_size)
        window_offsets = np.arange(window_size)

    for _ in range(max_iterations):
        # Check the current noise level, if it is zero, no more iterations are needed.
        noise = noise_level(optimized_minimum_vector)
        if noise == 0:
            break

        # Update the optimized values by replacing high-SNR points with the median of their local window.
        new_minimum_vector = optimized_minimum_vector.copy()
        if window_starts is None:
            window_medians = np.full(
                minimum_count,
                np.median(optimized_minimum_vector),
            )
        else:
            window_medians = np.median(
                optimized_minimum_vector[
                    window_starts[:, np.newaxis] + window_offsets
                ],
                axis=1,
            )

        snr_window = np.abs(
            (optimized_minimum_vector - window_medians) / noise
        )
        snr_increment = np.zeros(minimum_count, dtype=np.float64)
        snr_increment[1:] = np.abs(
            (optimized_minimum_vector[1:] - optimized_minimum_vector[:-1])
            / noise
        )
        update_mask = np.maximum(snr_window, snr_increment) > snr_threshold
        new_minimum_vector[update_mask] = window_medians[update_mask]

        # Calculate the change and check whether convergence is reached. If the relative change is below the tolerance, convergence has been reached.
        relative_change = np.linalg.norm(new_minimum_vector - optimized_minimum_vector)
        relative_change /= max(np.linalg.norm(optimized_minimum_vector), 1.0)
        optimized_minimum_vector = new_minimum_vector
        if relative_change < tolerance:
            break

    # Second estimate: replace points associated with unusually large
    # first-derivative changes by interpolation between retained points.
    new_minimum_vector_for_interpolation = minimum_vector.copy()
    for _ in range(max_iterations):
        
        derivative = np.diff(new_minimum_vector_for_interpolation)
        outlier_derivatives = (np.abs(derivative) > snr_threshold)
        # Get the positions of outliers in the original minimum vector. The +1 is necessary because the derivative is one element shorter than the original minimum vector.
        outlier_positions = np.flatnonzero(outlier_derivatives) + 1
        if outlier_positions.size == 0:
            interpolated_minimum_vector = new_minimum_vector_for_interpolation.copy()
            break
        # Get all positions without outliers
        retained_positions = np.setdiff1d(
            np.arange(new_minimum_vector_for_interpolation.size), outlier_positions
        )

        # If there are enough retained positions for interpolation and if there are outliers. Do interpolation of the values of the minimum vector.
        if retained_positions.size >= 2 and outlier_positions.size:
            new_minimum_vector_for_interpolation = np.interp(np.arange(new_minimum_vector_for_interpolation.size),
                                                             retained_positions,
                                                             new_minimum_vector_for_interpolation[retained_positions],
                                                        )
            interpolated_minimum_vector = new_minimum_vector_for_interpolation.copy()
        else:
            interpolated_minimum_vector = new_minimum_vector_for_interpolation.copy()
            break

    # Get the element-wise minimum of the two baseline minimum point estimates.
    optimized_minimum_vector = np.minimum(optimized_minimum_vector, interpolated_minimum_vector)

    # Now estimating the background drift stage by linear interpolation of the optimized minimum vector over the entire signal.
    baseline = np.interp(
        np.arange(signal.size),
        minimum_positions,
        optimized_minimum_vector,
    )
    return baseline
    
def get_baseline(signal, method:str = "none", **kwargs):

    # Check whether the input signal is a 1D numpy array
    signal = np.asarray(signal, dtype=np.float64)

    if signal.ndim != 1:
        raise ValueError("Input signal must be one-dimensional.")

    if signal.size == 0:
        raise ValueError("Input array must not be empty.")

    if not np.all(np.isfinite(signal)):
        raise ValueError("Input array must contain only finite numbers.")

    if method == "None":
        return np.zeros_like(signal)
    
    # Asymmetrical Least Squares (AsLS) baseline correction
    elif method == "asLS":
        baseline, params = Baseline().asls(signal, **kwargs)
        return baseline

    # Asymmetric Reweighted Penalized Least Squares (arPLS) baseline correction
    elif method == "arPLS":
        baseline, params = Baseline().arpls(signal, **kwargs)
        return baseline

    # Asymmetric Iteratively Reweighted Penalized Least Squares (airPLS) baseline correction
    elif method == "airPLS":
        baseline, params = Baseline().airpls(signal, **kwargs)
        return baseline

    # Polynomial baseline with a non-quadratic cost function (Backcor) baseline correction
    elif method == "Backcor":
        baseline, params = Baseline().penalized_poly(signal, **kwargs)
        return baseline

    elif method == "Mixture model":
        baseline, params = Baseline().mixture_model(signal, **kwargs)
        return baseline

    elif method == "Local minimum values":
        return lmv_baseline(signal, **kwargs)
    
    else:
        raise ValueError(f"Unknown baseline correction method: {method}")