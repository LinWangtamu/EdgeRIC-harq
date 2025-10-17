import math
import numpy as np
from collections import defaultdict, deque
from edgeric_messenger import EdgericMessenger
from optimizer import run_optimizer   # Must return (mu_vec, sigma2_vec)


class UEState:
    """Tracks per-UE metrics for VWD scheduling."""
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


class VWDPolicy:
    """
    Variance-Weighted Deficit (VWD) policy.
    - Manual q values (lowest RNTI → first q)
    - μ and σ² obtained from optimizer.py only when p changes > 5 %.
    """

    def __init__(self, manual_q, window_len=200, p_change_thresh=0.05):
        self._messenger = EdgericMessenger(socket_type="weights")
        self._states = defaultdict(lambda: UEState(window_len))
        self.manual_q = manual_q
        self.opt_update_period = 100     # fallback: force re-run every 100 TTIs
        self.last_opt_update_tti = None
        self.p_change_thresh = p_change_thresh

    # ---------------------------------------------------
    def _update_from_optimizer(self, rntis, p_vec):
        """Fetch μ, σ² from optimizer given current p and manual q."""
        q_vec = np.array(self.manual_q[:len(rntis)], dtype=float)
        mu_vec, sigma2_vec = run_optimizer(p_vec, q_vec)

        for i, rnti in enumerate(rntis):
            S = self._states[rnti]
            S.mu = float(max(mu_vec[i], 1e-6))
            S.sigma2 = float(max(sigma2_vec[i], 1e-6))

    # ---------------------------------------------------
    def step(self):
        ran_tti, ue_data = self._messenger.get_metrics(False)
        if not ue_data:
            return

        rntis = sorted(list(ue_data.keys()))
        n = len(rntis)

        # --- Update instantaneous metrics per UE ---
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

            # Update p_hat
            S.prev_p_hat = S.p_hat
            if S.tx_count > 0:
                S.p_hat = max(1e-6, min(1.0, S.ack_count / S.tx_count))
            else:
                S.p_hat = S.prev_p_hat

            # Detect large change
            if abs(S.p_hat - S.prev_p_hat) / max(S.prev_p_hat, 1e-6) > self.p_change_thresh:
                p_changed = True

            S.z_window.append(z)
            S.aoi = 1 if z == 1 else S.aoi + 1

        # --- Decide if optimizer should re-run ---
        run_opt = False
        if (self.last_opt_update_tti is None) or (ran_tti - self.last_opt_update_tti >= self.opt_update_period):
            run_opt = True
        elif p_changed:
            run_opt = True

        if run_opt:
            p_vec = np.array([self._states[r].p_hat for r in rntis])
            self._update_from_optimizer(rntis, p_vec)
            self.last_opt_update_tti = ran_tti

        # --- Compute deficit and weights ---
        weights = []
        for i, rnti in enumerate(rntis):
            S = self._states[rnti]
            mu, sigma2, p = S.mu, S.sigma2, max(S.p_hat, 1e-6)
            z_last = S.z_window[-1] if len(S.z_window) else 0

            mu_over_p = mu / p
            if z_last == 1:
                S.deficit += mu_over_p - (1.0 / p)
            else:
                S.deficit += mu_over_p

            denom = math.sqrt(max(sigma2, 1e-12) / (p * p))
            w = S.deficit / max(denom, 1e-9)
            weights.append((rnti, w))

        # --- Normalize weights and send ---
        ws = np.array([w for _, w in weights])
        ws = np.maximum(ws - ws.min(), 0)
        total = ws.sum()
        if total > 0:
            ws /= total
        else:
            ws[:] = 1.0 / len(ws)

        out = np.zeros(len(rntis) * 2)
        for i, (rnti, _) in enumerate(weights):
            out[i * 2] = rnti
            out[i * 2 + 1] = ws[i]

        self._messenger.send_scheduling_weight(ran_tti, out, False)

    # ---------------------------------------------------
    def poll_metrics(self):
        return self._messenger.get_metrics(False)

    @property
    def messenger(self):
        return self._messenger
