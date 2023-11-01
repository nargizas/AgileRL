from torch.utils.data import IterableDataset

from agilerl.components.replay_buffer import ReplayBuffer


class ReplayDataset(IterableDataset):
    """
    Iterable Dataset containing the ReplayBuffer which will be updated with new
    experiences during training

    :param buffer: Experience replay buffer
    :type buffer: agilerl.components.replay_buffer.ReplayBuffer()
    :param batch_size: Number of experiences to sample at a time, defaults to 256
    :type batch_size: int, optional
    """

    def __init__(self, buffer, batch_size=256):
        assert isinstance(buffer, ReplayBuffer), "Buffer must be agilerl ReplayBuffer."
        assert batch_size > 0, "Batch size must be greater than zero."
        self.buffer = buffer
        self.batch_size = batch_size

    def __iter__(self):
        yield self.buffer.sample(self.batch_size)
