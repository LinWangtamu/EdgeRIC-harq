from scipy.optimize import minimize
import numpy as np

def objective_sigma2(sigma2, p, mu, alpha):
    F = alpha * (0.5 * ((sigma2 / mu**2) + (1 / mu)) + 0.5)
    return sum(F)

def constraint1_sigma2(sigma2, p, mu):
    # Constraint 1 only involves mu, which is fixed, so we just return 0 to comply with minimize API
    return 0  # No constraint for sigma2 from this

def constraint2_sigma2(sigma2, p, mu):
    lhs = sum(np.sqrt(sigma2 / p**2))
    rhs = np.sqrt(sum(mu / p * (1 / p - 1)))
    return rhs - lhs

def optimize_aoi_fixed_mu(p, q, alpha=None):
    N = len(p)
    if alpha is None:
        alpha = np.ones(N)

    mu = q  # Fix mu equal to q

    sigma2_init = np.ones(N) * 0.01  # Initial guess for sigma2
    bounds = [(1e-6, None)] * N  # Bounds on sigma2 only

    constraints = [
        {'type': 'eq', 'fun': constraint2_sigma2, 'args': (p, mu)}
    ]

    result = minimize(objective_sigma2, sigma2_init, args=(p, mu, alpha), constraints=constraints, bounds=bounds)

    sigma2 = result.x
    theoretical_aoi_per_ue = alpha * (0.5 * (sigma2 / mu**2 + 1 / mu) + 0.5)
    total_aoi = sum(theoretical_aoi_per_ue)

    print(f"Optimization results:")
    print(f"p: {np.round(p, 6)}")
    print(f"q (fixed mu): {np.round(mu, 6)}")
    print(f"sigma^2: {np.round(sigma2, 6)}")
    print(f"Theoretical AoI per UE: {np.round(theoretical_aoi_per_ue, 6)}")
    print(f"Total AoI (sum): {total_aoi:.6f}")
    print("-" * 50)

    return mu, sigma2, theoretical_aoi_per_ue, total_aoi

if __name__ == "__main__":
    P = np.array([0.876, 0.6595])
    Q = np.array([0.4515, 0.2939])
    optimize_aoi_fixed_mu(P, Q)
