from scipy.optimize import minimize
import numpy as np

# ===========================================================
# Objective function: minimize total AoI + soft penalty
# ===========================================================
def objective_sigma2(sigma2, p, mu, alpha, q, m_vec=None, penalty_weight=1.0):
    """
    Objective = sum_i alpha_i * [ h_i + penalty_weight * (q_i - m_i)^2 ]
    where h_i = 0.5 * (sigma2_i/mu_i^2 + 1/mu_i) + 0.5
    """
    # Base AoI term
    h_i = 0.5 * ((sigma2 / mu**2) + (1 / mu)) + 0.5
    F = alpha * h_i

    # Add soft constraint penalty if m_vec is provided
    if m_vec is not None:
        diff = q - m_vec
        penalty = np.where(diff > 0, diff**2, 0)  # penalize only if throughput < target
        F += alpha * penalty_weight * penalty

    return np.sum(F)

# ===========================================================
# Constraints (same as before)
# ===========================================================
def constraint1_sigma2(sigma2, p, mu):
    # Constraint 1 only involves mu (fixed), so just return 0 to comply with minimize API
    return 0

def constraint2_sigma2(sigma2, p, mu):
    lhs = np.sum(np.sqrt(sigma2 / p**2))
    rhs = np.sqrt(np.sum(mu / p * (1 / p - 1)))
    return rhs - lhs

# ===========================================================
# Main optimizer function
# ===========================================================
def optimize_aoi_fixed_mu(p, q, alpha=None, m_vec=None, penalty_weight=1.0, verbose=False):
    """
    Optimizes sigma^2 for given p, q (fixed mu = q), and optionally includes throughput penalties.

    Parameters
    ----------
    p : np.array
        Success probabilities per UE
    q : np.array
        Throughput thresholds per UE (used as mu)
    alpha : np.array, optional
        Weighting factors for UEs
    m_vec : np.array, optional
        Measured throughput values (count(Z==1)/TTIs)
    penalty_weight : float
        Multiplier for penalty term importance
    verbose : bool
        Print optimization results if True
    """
    N = len(p)
    if alpha is None:
        alpha = np.ones(N)

    mu = q  # Fix mu equal to q (hard assumption)

    # Initial guess and bounds
    sigma2_init = np.ones(N) * 0.01
    bounds = [(1e-6, None)] * N

    constraints = [
        {'type': 'eq', 'fun': constraint2_sigma2, 'args': (p, mu)}
    ]

    # Run optimizer
    result = minimize(
        objective_sigma2,
        sigma2_init,
        args=(p, mu, alpha, q, m_vec, penalty_weight),
        constraints=constraints,
        bounds=bounds
    )

    sigma2 = result.x
    h_i = 0.5 * (sigma2 / mu**2 + 1 / mu) + 0.5

    # Include penalty if m_vec is provided
    if m_vec is not None:
        diff = q - m_vec
        penalty = np.where(diff > 0, diff**2, 0)
        total_obj = np.sum(alpha * (h_i + penalty_weight * penalty))
    else:
        penalty = np.zeros_like(q)
        total_obj = np.sum(alpha * h_i)

    if verbose:
        print(f"Optimization results:")
        print(f"p: {np.round(p, 6)}")
        print(f"q (fixed mu): {np.round(mu, 6)}")
        print(f"sigma^2: {np.round(sigma2, 6)}")
        print(f"Theoretical AoI per UE: {np.round(h_i, 6)}")
        if m_vec is not None:
            print(f"Measured throughput m: {np.round(m_vec, 6)}")
            print(f"Penalty per UE: {np.round(penalty, 6)}")
        print(f"Total Objective (AoI + penalty): {total_obj:.6f}")
        print("-" * 60)

    return mu, sigma2, h_i, total_obj

# ===========================================================
# Standalone test
# ===========================================================
if __name__ == "__main__":
    P = np.array([0.876, 0.6595])
    Q = np.array([0.4515, 0.2939])
    M = np.array([0.40, 0.25])  # example measured throughput
    optimize_aoi_fixed_mu(P, Q, m_vec=M, penalty_weight=1.0, verbose=True)
