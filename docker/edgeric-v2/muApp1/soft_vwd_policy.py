import csv
import json
import os
import numpy as np
from collections import defaultdict
from newoptimizer import optimize_aoi_fixed_mu  # Existing optimizer for h_i

class VWDPolicy:
    def __init__(self, manual_q=None, penalty_weight=1.0):
        """
        manual_q : list or array of throughput thresholds q_i
        penalty_weight : optional scalar multiplier for penalty term
        """
        self.p_history = defaultdict(list)
        self.ack_history = defaultdict(list)
        self.attempt_history = defaultdict(list)
        self.Z_history = defaultdict(list)
        self.q = np.array(manual_q) if manual_q is not None else None
        self.optim_params = None
        self.last_update_tti = 0
        self.penalty_weight = penalty_weight   # <---- NEW PARAMETER
        self.log_file_path = os.path.join(os.path.dirname(__file__), "vwd_policy_decisions.csv")
        self._init_log_file()

    def step(self, rantti, uedata):
        """
        Main function called each TTI. Returns scheduling weights.
        """
        rntis = sorted(uedata.keys())
        numues = len(rntis)

        # -------------------------------
        # Update per-UE transmission stats
        # -------------------------------
        for idx, rnti in enumerate(rntis):
            metrics = uedata[rnti]
            ul_harq_ack = int(metrics.get('ul_harq_ack', 0))
            ul_tx_attempt = int(metrics.get('ul_tx_attempt', 1))
            self.ack_history[rnti].append(ul_harq_ack)
            self.attempt_history[rnti].append(ul_tx_attempt)
            self.Z_history[rnti].append(ul_harq_ack)

        # Compute running success probability p_i
        p_vec = np.array([
            sum(self.ack_history[rnti]) / max(sum(self.attempt_history[rnti]), 1)
            for rnti in rntis
        ])

        # -------------------------------
        # Throughput constraint vector q
        # -------------------------------
        if self.q is None or len(self.q) != numues:
            raise ValueError("Manual q vector must be set and match UE count")

        # -------------------------------
        # Compute optimizer parameters
        # -------------------------------
        if (self.optim_params is None) or (rantti - self.last_update_tti > 100):
            mu, sigma2, _, _ = optimize_aoi_fixed_mu(p_vec, self.q)
            self.optim_params = {'mu': mu, 'sigma2': sigma2}
            self.last_update_tti = rantti

        mu_vec = self.optim_params['mu']
        sigma2_vec = self.optim_params['sigma2']

        # -------------------------------
        # Compute empirical throughput m_i
        # -------------------------------
        m_vec = np.array([
            sum(self.Z_history[rnti]) / max(len(self.Z_history[rnti]), 1)
            for rnti in rntis
        ])

        # -------------------------------
        # Compute AoI (theoretical h_i)
        # -------------------------------
        h_vec = 0.5 * ((sigma2_vec / (mu_vec ** 2)) + (1 / mu_vec)) + 0.5

        # -------------------------------
        # Add penalty term C(q_i - m_i)
        # -------------------------------
        diff = self.q - m_vec
        penalty = np.where(diff > 0, diff ** 2, 0)     # penalty only if below target
        total_cost = h_vec + self.penalty_weight * penalty  # <---- NEW OBJECTIVE

        # -------------------------------
        # Compute VWD deficit
        # -------------------------------
        d_vec = np.zeros(numues)
        for i, rnti in enumerate(rntis):
            t = len(self.Z_history[rnti])
            Z_sum = sum(self.Z_history[rnti])
            mu_i, sigma2_i = mu_vec[i], sigma2_vec[i]
            d_vec[i] = (t * mu_i - Z_sum) / (np.sqrt(sigma2_i) + 1e-9)

            # Include cost influence: lower cost -> higher priority
            d_vec[i] -= total_cost[i]  # <---- NEW MODIFICATION (combine both)

        # -------------------------------
        # One-hot scheduling decision
        # -------------------------------
        weights = np.zeros((numues, 2))
        for i, rnti in enumerate(rntis):
            weights[i, 0] = rnti
        max_i = np.argmax(d_vec)
        weights[max_i, 1] = 1.0

        # -------------------------------
        # Logging
        # -------------------------------
        self._log_decision(rantti, rntis, uedata, weights, h_vec, penalty, total_cost)
        return weights

    # ---------------------------------------------------------------
    # Logging helpers
    # ---------------------------------------------------------------
    def _init_log_file(self):
        if not os.path.exists(self.log_file_path):
            with open(self.log_file_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['tti', 'rnti', 'weight', 'h_i', 'penalty', 'total_cost', 'metrics'])

    def _log_decision(self, tti, rntis, uedata, weights, h_vec, penalty, total_cost):
        rows = []
        for idx, rnti in enumerate(rntis):
            metrics = dict(uedata.get(rnti, {}))
            rows.append([
                tti,
                rnti,
                float(weights[idx, 1]),
                float(h_vec[idx]),
                float(penalty[idx]),
                float(total_cost[idx]),
                json.dumps(metrics, sort_keys=True)
            ])
        with open(self.log_file_path, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(rows)
