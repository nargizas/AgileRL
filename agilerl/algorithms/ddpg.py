import copy
import inspect
import random
import warnings

import dill
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from agilerl.networks.evolvable_cnn import EvolvableCNN
from agilerl.networks.evolvable_mlp import EvolvableMLP
from agilerl.wrappers.make_evolvable import MakeEvolvable


class DDPG:
    """The DDPG algorithm class. DDPG paper: https://arxiv.org/abs/1509.02971

    :param state_dim: State observation dimension
    :type state_dim: list[int]
    :param action_dim: Action dimension
    :type action_dim: int
    :param one_hot: One-hot encoding, used with discrete observation spaces
    :type one_hot: bool
    :param max_action: Upper bound of the action space, defaults to 1
    :type max_action: float, optional
    :param min_action: Lower bound of the action space, defaults to -1
    :type min_action: float, optional
    :param expl_noise: Standard deviation for Gaussian exploration noise
    :param expl_noise: float, optional
    :param index: Index to keep track of object instance during tournament selection and mutation, defaults to 0
    :type index: int, optional
    :param net_config: Network configuration, defaults to mlp with hidden size [64,64]
    :type net_config: dict, optional
    :param batch_size: Size of batched sample from replay buffer for learning, defaults to 64
    :type batch_size: int, optional
    :param lr_actor: Learning rate for actor optimizer, defaults to 1e-4
    :type lr_actor: float, optional
    :param lr_critic: Learning rate for critic optimizer, defaults to 1e-3
    :type lr_critic: float, optional
    :param learn_step: Learning frequency, defaults to 5
    :type learn_step: int, optional
    :param gamma: Discount factor, defaults to 0.99
    :type gamma: float, optional
    :param tau: For soft update of target network parameters, defaults to 1e-3
    :type tau: float, optional
    :param mut: Most recent mutation to agent, defaults to None
    :type mut: str, optional
    :param policy_freq: Frequency of critic network updates compared to policy network, defaults to 2
    :type policy_freq: int, optional
    :param actor_network: Custom actor network, defaults to None
    :type actor_network: nn.Module, optional
    :param critic_network: Custom critic network, defaults to None
    :type critic_network: nn.Module, optional
    :param device: Device for accelerated computing, 'cpu' or 'cuda', defaults to 'cpu'
    :type device: str, optional
    :param accelerator: Accelerator for distributed computing, defaults to None
    :type accelerator: accelerate.Accelerator(), optional
    :param wrap: Wrap models for distributed training upon creation, defaults to True
    :type wrap: bool, optional
    """

    def __init__(
        self,
        state_dim,
        action_dim,
        one_hot,
        max_action=1,
        min_action=-1,
        expl_noise=0.1,
        index=0,
        net_config={"arch": "mlp", "h_size": [64, 64]},
        batch_size=64,
        lr_actor=1e-4,
        lr_critic=1e-3,
        learn_step=5,
        gamma=0.99,
        tau=1e-3,
        mut=None,
        policy_freq=2,
        actor_network=None,
        critic_network=None,
        device="cpu",
        accelerator=None,
        wrap=True,
    ):
        assert isinstance(
            state_dim, (list, tuple)
        ), "State dimension must be a list or tuple."
        assert isinstance(
            action_dim, (int, np.integer)
        ), "Action dimension must be an integer."
        assert isinstance(
            one_hot, bool
        ), "One-hot encoding flag must be boolean value True or False."
        assert isinstance(
            max_action, (float, int, np.floating, np.integer)
        ), "Max action must be a float or integer."
        assert isinstance(
            min_action, (float, int, np.floating, np.integer)
        ), "Min action must be a float or integer."
        assert max_action > min_action, "Max action must be greater than min action."
        assert max_action > 0, "Max action must be greater than zero."
        assert min_action <= 0, "Min action must be less than or equal to zero."
        assert isinstance(
            expl_noise, (float, int)
        ), "Exploration noise rate must be a float."
        assert (
            expl_noise >= 0
        ), "Exploration noise must be greater than or equal to zero."
        assert isinstance(index, int), "Agent index must be an integer."
        assert isinstance(batch_size, int), "Batch size must be an integer."
        assert batch_size >= 1, "Batch size must be greater than or equal to one."
        assert isinstance(lr_actor, float), "Actor learning rate must be a float."
        assert lr_actor > 0, "Actor learning rate must be greater than zero."
        assert isinstance(lr_critic, float), "Critic learning rate must be a float."
        assert lr_critic > 0, "Critic learning rate must be greater than zero."
        assert isinstance(learn_step, int), "Learn step rate must be an integer."
        assert learn_step >= 1, "Learn step must be greater than or equal to one."
        assert isinstance(gamma, (float, int)), "Gamma must be a float."
        assert isinstance(tau, float), "Tau must be a float."
        assert tau > 0, "Tau must be greater than zero."
        assert isinstance(policy_freq, int), "Policy frequency must be an integer."
        assert (
            policy_freq >= 1
        ), "Policy frequency must be greater than or equal to one."
        assert (
            isinstance(actor_network, nn.Module) or actor_network is None
        ), "Actor network must be an nn.Module or None."
        assert (
            isinstance(critic_network, nn.Module) or critic_network is None
        ), "Critic network must be an nn.Module or None."
        if (actor_network is not None) != (critic_network is not None):  # XOR operation
            warnings.warn(
                "Actor and critic networks must both be supplied to use custom networks. Defaulting to net config."
            )
        assert isinstance(
            wrap, bool
        ), "Wrap models flag must be boolean value True or False."

        self.algo = "DDPG"
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.one_hot = one_hot
        self.max_action = max_action
        self.min_action = min_action
        self.net_config = net_config
        self.batch_size = batch_size
        self.lr_actor = lr_actor
        self.lr_critic = lr_critic
        self.learn_step = learn_step
        self.gamma = gamma
        self.tau = tau
        self.mut = mut
        self.policy_freq = policy_freq
        self.expl_noise = expl_noise
        self.actor_network = actor_network
        self.critic_network = critic_network
        self.device = device
        self.accelerator = accelerator

        self.index = index
        self.scores = []
        self.fitness = []
        self.steps = [0]
        self.learn_counter = 0

        if self.actor_network is not None and self.critic_network is not None:
            self.actor = actor_network
            self.critic = critic_network
            self.net_config = None
        else:
            # model
            assert isinstance(self.net_config, dict), "Net config must be a dictionary."
            assert (
                "arch" in self.net_config.keys()
            ), "Net config must contain arch: 'mlp' or 'cnn'."
            if self.min_action < 0:
                output_activation = "Tanh"
            else:
                output_activation = "Sigmoid"
            if self.net_config["arch"] == "mlp":  # Multi-layer Perceptron
                assert (
                    "h_size" in self.net_config.keys()
                ), "Net config must contain h_size: int."
                assert isinstance(
                    self.net_config["h_size"], list
                ), "Net config h_size must be a list."
                assert (
                    len(self.net_config["h_size"]) > 0
                ), "Net config h_size must contain at least one element."
                self.actor = EvolvableMLP(
                    num_inputs=state_dim[0],
                    num_outputs=action_dim,
                    hidden_size=self.net_config["h_size"],
                    mlp_output_activation=output_activation,
                    device=self.device,
                    accelerator=self.accelerator,
                )
                self.critic = EvolvableMLP(
                    num_inputs=state_dim[0] + action_dim,
                    num_outputs=1,
                    hidden_size=self.net_config["h_size"],
                    device=self.device,
                    accelerator=self.accelerator,
                )
            elif self.net_config["arch"] == "cnn":  # Convolutional Neural Network
                for key in ["c_size", "k_size", "s_size", "h_size"]:
                    assert (
                        key in self.net_config.keys()
                    ), f"Net config must contain {key}: int."
                    assert isinstance(
                        self.net_config[key], list
                    ), f"Net config {key} must be a list."
                    assert (
                        len(self.net_config[key]) > 0
                    ), f"Net config {key} must contain at least one element."
                assert (
                    "normalize" in self.net_config.keys()
                ), "Net config must contain normalize: True or False."
                assert isinstance(
                    self.net_config["normalize"], bool
                ), "Net config normalize must be boolean value True or False."
                self.actor = EvolvableCNN(
                    input_shape=state_dim,
                    num_actions=action_dim,
                    channel_size=self.net_config["c_size"],
                    kernel_size=self.net_config["k_size"],
                    stride_size=self.net_config["s_size"],
                    hidden_size=self.net_config["h_size"],
                    normalize=self.net_config["normalize"],
                    mlp_activation="ReLU",
                    mlp_output_activation=output_activation,
                    device=self.device,
                    accelerator=self.accelerator,
                )
                self.critic = EvolvableCNN(
                    input_shape=state_dim,
                    num_actions=action_dim,
                    channel_size=self.net_config["c_size"],
                    kernel_size=self.net_config["k_size"],
                    stride_size=self.net_config["s_size"],
                    hidden_size=self.net_config["h_size"],
                    normalize=self.net_config["normalize"],
                    mlp_activation="ReLU",
                    mlp_output_activation=None,
                    critic=True,
                    device=self.device,
                    accelerator=self.accelerator,
                )

        self.actor_target = copy.deepcopy(self.actor)
        self.critic_target = copy.deepcopy(self.critic)
        self.actor_target.load_state_dict(self.actor.state_dict())
        self.critic_target.load_state_dict(self.critic.state_dict())
        self.actor_optimizer_type = optim.Adam(
            self.actor.parameters(), lr=self.lr_actor
        )
        self.critic_optimizer_type = optim.Adam(
            self.critic.parameters(), lr=self.lr_critic
        )

        self.arch = (
            self.net_config["arch"] if self.net_config is not None else self.actor.arch
        )

        if self.accelerator is not None:
            self.actor_optimizer = self.actor_optimizer_type
            self.critic_optimizer = self.critic_optimizer_type
            if wrap:
                self.wrap_models()
        else:
            self.actor = self.actor.to(self.device)
            self.actor_target = self.actor_target.to(self.device)
            self.critic = self.critic.to(self.device)
            self.critic_target = self.critic_target.to(self.device)
            self.actor_optimizer = self.actor_optimizer_type
            self.critic_optimizer = self.critic_optimizer_type

        self.criterion = nn.MSELoss()

    def scale_to_action_space(self, action):
        """Scales actions to action space defined by self.min_action and self.max_action.

        :param action: Action to be scaled
        :type action: numpy.ndarray
        """
        return np.where(action > 0, action * self.max_action, action * -self.min_action)

    def getAction(self, state, epsilon=0):
        """Returns the next action to take in the environment.
        Epsilon is the probability of taking a random action, used for exploration.
        For epsilon-greedy behaviour, set epsilon to 0.

        :param state: Environment observation, or multiple observations in a batch
        :type state: numpy.ndarray[float]
        :param epsilon: Probablilty of taking a random action for exploration, defaults to 0
        :type epsilon: float, optional
        """
        state = torch.from_numpy(state).float()
        if self.accelerator is None:
            state = state.to(self.device)
        else:
            state = state.to(self.accelerator.device)

        if self.one_hot:
            state = (
                nn.functional.one_hot(state.long(), num_classes=self.state_dim[0])
                .float()
                .squeeze()
            )

        if len(state.size()) < 2:
            state = state.unsqueeze(0)

        # epsilon-greedy
        if random.random() < epsilon:
            action = (
                (self.max_action - self.min_action)
                * np.random.rand(state.size()[0], self.action_dim).astype("float32")
            ) + self.min_action
        else:
            self.actor.eval()
            with torch.no_grad():
                action_values = self.actor(state)
            self.actor.train()

            action = self.scale_to_action_space(action_values.cpu().data.numpy())
            action = (
                action
                + np.random.normal(0, self.expl_noise, size=self.action_dim).astype(
                    np.float32
                )
            ).clip(self.min_action, self.max_action)
        return action

    def learn(self, experiences, noise_clip=0.5, policy_noise=0.2):
        """Updates agent network parameters to learn from experiences.

        :param experience: List of batched states, actions, rewards, next_states, dones in that order.
        :type experience: list[torch.Tensor[float]]
        :param noise_clip: Maximum noise limit to apply to actions, defaults to 0.5
        :type noise_clip: float, optional
        :param policy_noise: Standard deviation of noise applied to policy, defaults to 0.2
        :type policy_noise: float, optional
        """
        states, actions, rewards, next_states, dones = experiences
        if self.accelerator is not None:
            states = states.to(self.accelerator.device)
            actions = actions.to(self.accelerator.device)
            rewards = rewards.to(self.accelerator.device)
            next_states = next_states.to(self.accelerator.device)
            dones = dones.to(self.accelerator.device)

        if self.one_hot:
            states = (
                nn.functional.one_hot(states.long(), num_classes=self.state_dim[0])
                .float()
                .squeeze()
            )
            next_states = (
                nn.functional.one_hot(next_states.long(), num_classes=self.state_dim[0])
                .float()
                .squeeze()
            )

        if self.arch == "mlp":
            input_combined = torch.cat([states, actions], 1)
            q_value = self.critic(input_combined)
        elif self.arch == "cnn":
            q_value = self.critic(states, actions)

        with torch.no_grad():
            next_actions = self.actor_target(next_states)
            # Scale actions
            next_actions = torch.where(
                next_actions > 0,
                next_actions * self.max_action,
                next_actions * -self.min_action,
            )
            noise = actions.data.normal_(0, policy_noise)
            noise = noise.clamp(-noise_clip, noise_clip)
            next_actions = next_actions + noise

            if self.arch == "mlp":
                next_input_combined = torch.cat([next_states, next_actions], 1)
                q_value_next_state = self.critic_target(next_input_combined)
            elif self.arch == "cnn":
                q_value_next_state = self.critic_target(next_states, next_actions)

        y_j = rewards + ((1 - dones) * self.gamma * q_value_next_state)

        critic_loss = self.criterion(q_value, y_j)

        # critic loss backprop
        self.critic_optimizer.zero_grad()
        if self.accelerator is not None:
            self.accelerator.backward(critic_loss)
        else:
            critic_loss.backward()
        self.critic_optimizer.step()

        # update actor and targets every policy_freq learn steps
        self.learn_counter += 1
        if self.learn_counter % self.policy_freq == 0:
            policy_actions = self.actor.forward(states)
            policy_actions = torch.where(
                policy_actions > 0,
                policy_actions * self.max_action,
                policy_actions * -self.min_action,
            )
            if self.arch == "mlp":
                input_combined = torch.cat([states, policy_actions], 1)
                actor_loss = -self.critic(input_combined).mean()
            elif self.arch == "cnn":
                actor_loss = -self.critic(states, policy_actions).mean()

            # actor loss backprop
            self.actor_optimizer.zero_grad()
            if self.accelerator is not None:
                self.accelerator.backward(actor_loss)
            else:
                actor_loss.backward()
            self.actor_optimizer.step()

            self.softUpdate(self.actor, self.actor_target)
            self.softUpdate(self.critic, self.critic_target)

            return actor_loss.item(), critic_loss.item()
        else:
            return None, critic_loss.item()

    def softUpdate(self, net, target):
        """Soft updates target network."""
        for eval_param, target_param in zip(net.parameters(), target.parameters()):
            target_param.data.copy_(
                self.tau * eval_param.data + (1.0 - self.tau) * target_param.data
            )

    def test(self, env, swap_channels=False, max_steps=500, loop=3):
        """Returns mean test score of agent in environment with epsilon-greedy policy.

        :param env: The environment to be tested in
        :type env: Gym-style environment
        :param swap_channels: Swap image channels dimension from last to first [H, W, C] -> [C, H, W], defaults to False
        :type swap_channels: bool, optional
        :param max_steps: Maximum number of testing steps, defaults to 500
        :type max_steps: int, optional
        :param loop: Number of testing loops/episodes to complete. The returned score is the mean. Defaults to 3
        :type loop: int, optional
        """
        with torch.no_grad():
            rewards = []
            for i in range(loop):
                state = env.reset()[0]
                score = 0
                for idx_step in range(max_steps):
                    if swap_channels:
                        if not hasattr(env, "num_envs"):
                            state = np.expand_dims(state, 0)
                        state = np.moveaxis(state, [3], [1])
                    action = self.getAction(state, epsilon=0)
                    if not hasattr(env, "num_envs"):
                        action = action[0]
                    state, reward, done, trunc, _ = env.step(action)
                    if hasattr(env, "num_envs"):
                        done = done[0]
                        trunc = trunc[0]
                        reward = reward[0]
                    score += reward
                    if done or trunc:
                        break
                rewards.append(score)
        mean_fit = np.mean(rewards)
        self.fitness.append(mean_fit)
        return mean_fit

    def clone(self, index=None, wrap=True):
        """Returns cloned agent identical to self.

        :param index: Index to keep track of agent for tournament selection and mutation, defaults to None
        :type index: int, optional
        """
        input_args = self.inspect_attributes(input_args_only=True)
        input_args["wrap"] = wrap

        if index is None:
            input_args["index"] = self.index

        clone = type(self)(**input_args)

        if self.accelerator is not None:
            self.unwrap_models()
        actor = self.actor.clone()
        actor_target = self.actor_target.clone()
        critic = self.critic.clone()
        critic_target = self.critic_target.clone()
        actor_optimizer = optim.Adam(actor.parameters(), lr=clone.lr_actor)
        critic_optimizer = optim.Adam(critic.parameters(), lr=clone.lr_critic)
        clone.actor_optimizer_type = actor_optimizer
        clone.critic_optimizer_type = critic_optimizer

        if self.accelerator is not None:
            if wrap:
                (
                    clone.actor,
                    clone.actor_target,
                    clone.critic,
                    clone.critic_target,
                    clone.actor_optimizer,
                    clone.critic_optimizer,
                ) = self.accelerator.prepare(
                    actor,
                    actor_target,
                    critic,
                    critic_target,
                    actor_optimizer,
                    critic_optimizer,
                )
            else:
                (
                    clone.actor,
                    clone.actor_target,
                    clone.critic,
                    clone.critic_target,
                    clone.actor_optimizer,
                    clone.critic_optimizer,
                ) = (
                    actor,
                    actor_target,
                    critic,
                    critic_target,
                    actor_optimizer,
                    critic_optimizer,
                )
        else:
            clone.actor = actor.to(self.device)
            clone.actor_target = actor_target.to(self.device)
            clone.critic = critic.to(self.device)
            clone.critic_target = critic_target.to(self.device)
            clone.actor_optimizer = actor_optimizer
            clone.critic_optimizer = critic_optimizer

        for attribute in self.inspect_attributes().keys():
            if hasattr(self, attribute) and hasattr(clone, attribute):
                attr, clone_attr = getattr(self, attribute), getattr(clone, attribute)
                if isinstance(attr, torch.Tensor) or isinstance(
                    clone_attr, torch.Tensor
                ):
                    if not torch.equal(attr, clone_attr):
                        setattr(
                            clone, attribute, copy.deepcopy(getattr(self, attribute))
                        )
                else:
                    if attr != clone_attr:
                        setattr(
                            clone, attribute, copy.deepcopy(getattr(self, attribute))
                        )
            else:
                setattr(clone, attribute, copy.deepcopy(getattr(self, attribute)))

        return clone

    def inspect_attributes(self, input_args_only=False):
        # Get all attributes of the current object
        attributes = inspect.getmembers(self, lambda a: not (inspect.isroutine(a)))
        guarded_attributes = [
            "actor",
            "critic",
            "actor_target",
            "critic_target",
            "actor_optimizer",
            "critic_optimizer",
            "actor_optimizer_type",
            "critic_optimizer_type",
        ]

        # Exclude private and built-in attributes
        attributes = [
            a for a in attributes if not (a[0].startswith("__") and a[0].endswith("__"))
        ]

        if input_args_only:
            constructor_params = inspect.signature(self.__init__).parameters.keys()
            attributes = {
                k: v
                for k, v in attributes
                if k not in guarded_attributes and k in constructor_params
            }
        else:
            # Remove the algo specific guarded variables
            attributes = {k: v for k, v in attributes if k not in guarded_attributes}

        return attributes

    def wrap_models(self):
        if self.accelerator is not None:
            (
                self.actor,
                self.actor_target,
                self.critic,
                self.critic_target,
                self.actor_optimizer,
                self.critic_optimizer,
            ) = self.accelerator.prepare(
                self.actor,
                self.actor_target,
                self.critic,
                self.critic_target,
                self.actor_optimizer_type,
                self.critic_optimizer_type,
            )

    def unwrap_models(self):
        if self.accelerator is not None:
            self.actor = self.accelerator.unwrap_model(self.actor)
            self.actor_target = self.accelerator.unwrap_model(self.actor_target)
            self.critic = self.accelerator.unwrap_model(self.critic)
            self.critic_target = self.accelerator.unwrap_model(self.critic_target)
            self.actor_optimizer = self.accelerator.unwrap_model(self.actor_optimizer)
            self.critic_optimizer = self.accelerator.unwrap_model(self.critic_optimizer)

    def saveCheckpoint(self, path):
        """Saves a checkpoint of agent properties and network weights to path.

        :param path: Location to save checkpoint at
        :type path: string
        """
        attribute_dict = self.inspect_attributes()

        network_info = {
            "actor_init_dict": self.actor.init_dict,
            "actor_state_dict": self.actor.state_dict(),
            "actor_target_init_dict": self.actor_target.init_dict,
            "actor_target_state_dict": self.actor_target.state_dict(),
            "critic_init_dict": self.critic.init_dict,
            "critic_state_dict": self.critic.state_dict(),
            "critic_target_init_dict": self.critic_target.init_dict,
            "critic_target_state_dict": self.critic_target.state_dict(),
            "actor_optimizer_state_dict": self.actor_optimizer.state_dict(),
            "critic_optimizer_state_dict": self.critic_optimizer.state_dict(),
        }

        attribute_dict.update(network_info)

        torch.save(
            attribute_dict,
            path,
            pickle_module=dill,
        )

    def loadCheckpoint(self, path):
        """Loads saved agent properties and network weights from checkpoint.

        :param path: Location to load checkpoint from
        :type path: string
        """
        network_info = [
            "actor_state_dict",
            "actor_target_state_dict",
            "actor_optimizer_state_dict",
            "actor_init_dict",
            "actor_target_init_dict",
            "critic_state_dict",
            "critic_target_state_dict",
            "critic_optimizer_state_dict",
            "critic_init_dict",
            "critic_target_init_dict",
            "net_config",
            "lr_actor",
            "lr_critic",
        ]

        checkpoint = torch.load(path, pickle_module=dill)
        self.net_config = checkpoint["net_config"]
        if self.net_config is not None:
            self.arch = checkpoint["net_config"]["arch"]
            if self.arch == "mlp":
                network_class = EvolvableMLP
            elif self.arch == "cnn":
                network_class = EvolvableCNN
        else:
            network_class = MakeEvolvable

        self.actor = network_class(**checkpoint["actor_init_dict"])
        self.actor_target = network_class(**checkpoint["actor_target_init_dict"])
        self.critic = network_class(**checkpoint["critic_init_dict"])
        self.critic_target = network_class(**checkpoint["critic_target_init_dict"])

        self.lr_actor = checkpoint["lr_actor"]
        self.lr_critic = checkpoint["lr_critic"]
        self.actor_optimizer = optim.Adam(self.actor.parameters(), lr=self.lr_actor)
        self.critic_optimizer = optim.Adam(self.critic.parameters(), lr=self.lr_critic)
        self.actor.load_state_dict(checkpoint["actor_state_dict"])
        self.actor_target.load_state_dict(checkpoint["actor_target_state_dict"])
        self.critic.load_state_dict(checkpoint["critic_state_dict"])
        self.critic_target.load_state_dict(checkpoint["critic_target_state_dict"])
        self.actor_optimizer.load_state_dict(checkpoint["actor_optimizer_state_dict"])
        self.critic_optimizer.load_state_dict(checkpoint["critic_optimizer_state_dict"])

        for attribute in checkpoint.keys():
            if attribute not in network_info:
                setattr(self, attribute, checkpoint[attribute])

    @classmethod
    def load(cls, path, device="cpu", accelerator=None):
        """Creates agent with properties and network weights loaded from path.

        :param path: Location to load checkpoint from
        :type path: string
        :param device: Device for accelerated computing, 'cpu' or 'cuda', defaults to 'cpu'
        :type device: str, optional
        :param accelerator: Accelerator for distributed computing, defaults to None
        :type accelerator: accelerate.Accelerator(), optional
        """
        checkpoint = torch.load(path, pickle_module=dill)
        checkpoint["actor_init_dict"]["device"] = device
        checkpoint["actor_target_init_dict"]["device"] = device
        checkpoint["critic_init_dict"]["device"] = device
        checkpoint["critic_target_init_dict"]["device"] = device

        actor_init_dict = checkpoint.pop("actor_init_dict")
        actor_target_init_dict = checkpoint.pop("actor_target_init_dict")
        actor_state_dict = checkpoint.pop("actor_state_dict")
        actor_target_state_dict = checkpoint.pop("actor_target_state_dict")
        actor_optimizer_state_dict = checkpoint.pop("actor_optimizer_state_dict")
        critic_init_dict = checkpoint.pop("critic_init_dict")
        critic_target_init_dict = checkpoint.pop("critic_target_init_dict")
        critic_state_dict = checkpoint.pop("critic_state_dict")
        critic_target_state_dict = checkpoint.pop("critic_target_state_dict")
        critic_optimizer_state_dict = checkpoint.pop("critic_optimizer_state_dict")

        checkpoint["device"] = device
        checkpoint["accelerator"] = accelerator

        constructor_params = inspect.signature(cls.__init__).parameters.keys()
        class_init_dict = {
            k: v for k, v in checkpoint.items() if k in constructor_params
        }

        if checkpoint["net_config"] is not None:
            agent = cls(**class_init_dict)
            agent.arch = checkpoint["net_config"]["arch"]
            if agent.arch == "mlp":
                agent.actor = EvolvableMLP(**actor_init_dict)
                agent.actor_target = EvolvableMLP(**actor_target_init_dict)
                agent.critic = EvolvableMLP(**critic_init_dict)
                agent.critic_target = EvolvableMLP(**critic_target_init_dict)
            elif agent.arch == "cnn":
                agent.actor = EvolvableCNN(**actor_init_dict)
                agent.actor_target = EvolvableCNN(**actor_target_init_dict)
                agent.critic = EvolvableCNN(**critic_init_dict)
                agent.critic_target = EvolvableCNN(**critic_target_init_dict)
        else:
            class_init_dict["actor_network"] = MakeEvolvable(**actor_init_dict)
            class_init_dict["critic_network"] = MakeEvolvable(**critic_init_dict)
            agent = cls(**class_init_dict)
            agent.actor_target = MakeEvolvable(**actor_target_init_dict)
            agent.critic_target = MakeEvolvable(**critic_target_init_dict)

        agent.actor_optimizer = optim.Adam(agent.actor.parameters(), lr=agent.lr_actor)
        agent.actor.load_state_dict(actor_state_dict)
        agent.actor_target.load_state_dict(actor_target_state_dict)
        agent.actor_optimizer.load_state_dict(actor_optimizer_state_dict)

        agent.critic_optimizer = optim.Adam(
            agent.critic.parameters(), lr=agent.lr_critic
        )
        agent.critic.load_state_dict(critic_state_dict)
        agent.critic_target.load_state_dict(critic_target_state_dict)
        agent.critic_optimizer.load_state_dict(critic_optimizer_state_dict)

        if accelerator is not None:
            agent.wrap_models()

        for attribute in agent.inspect_attributes().keys():
            setattr(agent, attribute, checkpoint[attribute])

        return agent
