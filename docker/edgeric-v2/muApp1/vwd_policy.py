from edgeric_messenger import EdgericMessenger


class VWDPolicy:
    """
    Placeholder for the upcoming VWD scheduling policy.

    The policy only subscribes to the RT-E2 metrics feed so that future
    logic can consume UE measurements on demand.
    """

    def __init__(self) -> None:
        # Reuse the existing messenger so we listen to the same RT-E2 feed
        # the other schedulers rely on. We still bind a weights socket so the
        # surrounding infrastructure remains unchanged once the policy is
        # fleshed out.
        self._messenger = EdgericMessenger(socket_type="weights")

    def poll_metrics(self):
        """
        Fetch the most recent RT-E2 report. Returns the RAN TTI and a dict
        keyed by RNTI with the UE metrics we will later consume.
        """
        ran_tti, ue_data = self._messenger.get_metrics(False)
        return ran_tti, ue_data

    @property
    def messenger(self) -> EdgericMessenger:
        """Expose the messenger for future weight publication."""
        return self._messenger
