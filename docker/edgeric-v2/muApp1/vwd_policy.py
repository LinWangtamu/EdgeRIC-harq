# ============================================================
# vwd_policy.py — Clean production version (no console prints)
# ============================================================
import math
import numpy as np
from collections import defaultdict, deque
from scipy.optimize import minimize
from edgeric_messenger import EdgericMessenger


# ------------------------------------------------------------
# Per-UE state tracker
# ------------------------------------------------------------
class UEState:
    def __init__(self, window_len=200):
        self.ack_count = 0
        self.tx_count = 0
        self.p_hat = 0.5
        self.prev_p_hat = 0.5
        self.z_window = deque(maxlen=window_len)
        self.deficit = 0.0
        self.mu = 0.1
        self.sigma2 = 1e-2
        self.aoi = 1


# ------------------------------------------------------------
# Optimizer utilities
# ------------------------------------------------------------
def compute_feasible_q(p):
    """Find feasible uniform q satisfying q < p_i and Σ(q/p_i) < 1."""
    q_from_sum_constraint = 1 / np.sum(1 / p)
    q_from_individual_constraint = np.min(p)
    return min(q_from_sum_constraint, q_from_individual_constraint)


def objective(vars, p, alpha):
    mu, sigma2 = vars[:len(p)], vars[len(p):]
    F = alpha * (0.5 * ((sigma2 / mu**2) + (1 / mu)) + 0.5)
    return np.sum(F)


def constraint_sum_mu_p(vars, p):
    mu = vars[:len(p)]
    return 1 - np.sum(mu / p)


def constraint_variance_consistency(vars, p):
    mu, sigma2 = vars[:len(p)], vars[len(p):]
    lhs = np.sum(np.sqrt(sigma2 / p**2))
    rhs = np.sqrt(np.sum(mu / p * (1 / p - 1)))
    return rhs - lhs


def throughput_constraint(vars, q):
    mu = vars[:len(q)]
    return mu - q


def run_optimizer(p, q, alpha=None):
    """Solve for μ and σ² given current p and throughput floor q."""
    p = np.array(p, dtype=float)
    N = len(p)
    if alpha is None:
        alpha = np.ones(N)

    mu_init = np.array([1 / (N * p_i) for p_i in p])
    sigma2_init = np.ones(N) * 0.01
    vars_init = np.concatenate([mu_init, sigma2_init])
    bounds = [(1e-6, None)] * (2 * N)

    constraints = [
        {"type": "eq", "fun": constraint_sum_mu_p, "args": (p,)},
        {"type": "eq", "fun": constraint_variance_consistency, "args": (p,)},
        {"type": "ineq", "fun": throughput_constraint, "args": (q,)}
    ]

    res = minimize(objective, vars_init, args=(p, alpha),
                   constraints=constraints, bounds=bounds)

    mu = np.maximum(res.x[:N], q + 1e-3)
    sigma2 = np.maximum(res.x[N:], 1e-6)
    return mu, sigma2


# ------------------------------------------------------------
# Main Variance-Weighted Deficit (VWD) Policy
# ------------------------------------------------------------
class VWDPolicy:
    """
    Variance-Weighted Deficit scheduling policy (VWD).
    Computes μ and σ² internally and sends normalized weights to gNB.
    """

    def __init__(self, manual_q=None, window_len=200, p_change_thresh=0.05):
        self._messenger = EdgericMessenger(socket_type="weights")
        self._states = defaultdict(lambda: UEState(window_len))
        self.manual_q = manual_q
        self.window_len = window_len
        self.p_change_thresh = p_change_thresh
        self.opt_update_period = 100
        self.last_opt_update_tti = None

    # --------------------------------------------------------
    def _update_from_optimizer(self, rntis, p_vec):
        """Recalculate μ and σ² from current p̂ vector."""
        n = len(rntis)
        if self.manual_q is None:
            q_star = compute_feasible_q(p_vec)
            q_vec = np.full(n, q_star)
        else:
            q_vec = np.array(self.manual_q[:n], dtype=float)

        mu_vec, sigma2_vec = run_optimizer(p_vec, q_vec)
        for i, rnti in enumerate(rntis):
            S = self._states[rnti]
            S.mu = float(max(mu_vec[i], 1e-6))
            S.sigma2 = float(max(sigma2_vec[i], 1e-6))

    # --------------------------------------------------------
    def step(self):
        """Fetch metrics, compute new weights, and send scheduling decision."""
        ran_tti, ue_data = self._messenger.get_metrics(False)
        if not ue_data:
            return

        rntis = sorted(list(ue_data.keys()))
        n = len(rntis)

        # ---- Update instantaneous UE stats ----
        p_changed = False
        for rnti in rntis:
            data = ue_data[rnti]
            harq_ack = bool(data.get("ul_harq_ack", False))
            tx_attempt = bool(data.get("ul_tx_attempt", False))
            z = 1 if (harq_ack and tx_attempt) else 0

            S = self._states[rnti]
            if tx_attempt:
                S.tx_count += 1
                if harq_ack:
                    S.ack_count += 1

            S.prev_p_hat = S.p_hat
            S.p_hat = (S.ack_count / S.tx_count) if S.tx_count > 0 else S.prev_p_hat
            S.p_hat = float(np.clip(S.p_hat, 1e-6, 1.0))

            if abs(S.p_hat - S.prev_p_hat) / max(S.prev_p_hat, 1e-6) > self.p_change_thresh:
                p_changed = True

            S.z_window.append(z)
            S.aoi = 1 if z == 1 else S.aoi + 1

        # ---- Re-run optimizer if needed ----
        run_opt = False
        if (self.last_opt_update_tti is None) or \
           (ran_tti - self.last_opt_update_tti >= self.opt_update_period) or \
           p_changed:
            run_opt = True

        if run_opt:
            p_vec = np.array([self._states[r].p_hat for r in rntis])
            self._update_from_optimizer(rntis, p_vec)
            self.last_opt_update_tti = ran_tti

        # ---- Compute deficit & normalized weights ----
        weights = []
        for i, rnti in enumerate(rntis):
            S = self._states[rnti]
            mu, sigma2, p = S.mu, S.sigma2, S.p_hat
            z_last = S.z_window[-1] if len(S.z_window) else 0

            mu_over_p = mu / p
            if z_last == 1:
                S.deficit += mu_over_p - (1.0 / p)
            else:
                S.deficit += mu_over_p

            denom = math.sqrt(max(sigma2, 1e-12) / (p * p))
            w = S.deficit / max(denom, 1e-9)
            weights.append((rnti, w))

        # ---- Normalize and send ----
        ws = np.array([w for _, w in weights])
        ws = np.maximum(ws - ws.min(), 0)
        total = ws.sum()
        ws = ws / total if total > 0 else np.ones_like(ws) / len(ws)

        out = np.zeros(n * 2)
        for i, (rnti, _) in enumerate(weights):
            out[i * 2] = rnti
            out[i * 2 + 1] = ws[i]

        self._messenger.send_scheduling_weight(ran_tti, out, False)

    # --------------------------------------------------------
    def poll_metrics(self):
        """Optional: read current metrics (for monitoring)."""
        return self._messenger.get_metrics(False)

    @property
    def messenger(self):
        return self._messenger
