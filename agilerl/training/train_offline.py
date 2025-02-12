import os
import warnings
from datetime import datetime

import numpy as np
import wandb
from torch.utils.data import DataLoader
from tqdm import trange

from agilerl.components.replay_data import ReplayDataset
from agilerl.components.sampler import Sampler
from agilerl.utils.minari_utils import MinariToAgileBuffer


def train_offline(
    env,
    env_name,
    dataset,
    algo,
    pop,
    memory,
    INIT_HP=None,
    MUT_P=None,
    swap_channels=False,
    n_episodes=2000,
    max_steps=500,
    evo_epochs=5,
    evo_loop=1,
    target=200.0,
    tournament=None,
    mutation=None,
    checkpoint=None,
    checkpoint_path=None,
    save_elite=False,
    elite_path=None,
    wb=False,
    verbose=True,
    accelerator=None,
    minari_dataset_id=None,
    remote=False,
    wandb_api_key=None,
):
    """The general offline RL training function. Returns trained population of agents and their fitnesses.

    :param env: The environment to train in
    :type env: Gym-style environment
    :param env_name: Environment name
    :type env_name: str
    :param dataset: Offline RL dataset
    :type dataset: h5py-style dataset
    :param algo: RL algorithm name
    :type algo: str
    :param pop: Population of agents
    :type pop: list[object]
    :param memory: Experience Replay Buffer
    :type memory: object
    :param INIT_HP: Dictionary containing initial hyperparameters, defaults to None
    :type INIT_HP: dict, optional
    :param MUT_P: Dictionary containing mutation parameters, defaults to None
    :type MUT_P: dict, optional
    :param swap_channels: Swap image channels dimension from last to first
        [H, W, C] -> [C, H, W], defaults to False
    :type swap_channels: bool, optional
    :param n_episodes: Maximum number of training episodes, defaults to 2000
    :type n_episodes: int, optional
    :param max_steps: Maximum number of steps in environment per episode, defaults to
        500
    :type max_steps: int, optional
    :param evo_epochs: Evolution frequency (episodes), defaults to 5
    :type evo_epochs: int, optional
    :param evo_loop: Number of evaluation episodes, defaults to 1
    :type evo_loop: int, optional
    :param target: Target score for early stopping, defaults to 200.
    :type target: float, optional
    :param tournament: Tournament selection object, defaults to None
    :type tournament: object, optional
    :param mutation: Mutation object, defaults to None
    :type mutation: object, optional
    :param checkpoint: Checkpoint frequency (episodes), defaults to None
    :type checkpoint: int, optional
    :param checkpoint_path: Location to save checkpoint, defaults to None
    :type checkpoint_path: str, optional
    :param save_elite: Boolean flag indicating whether to save elite member at the end
        of training, defaults to False
    :type save_elite: bool, optional
    :param elite_path: Location to save elite agent, defaults to None
    :type elite_path: str, optional
    :param wb: Weights & Biases tracking, defaults to False
    :type wb: bool, optional
    :param verbose: Display training stats, defaults to True
    :type verbose: bool, optional
    :param accelerator: Accelerator for distributed computing, defaults to None
    :type accelerator: accelerate.Accelerator(), optional
    :param wandb_api_key: API key for Weights & Biases, defaults to None
    :type wandb_api_key: str, optional
    """
    assert isinstance(
        algo, str
    ), "'algo' must be the name of the algorithm as a string."
    assert isinstance(n_episodes, int), "Number of episodes must be an integer."
    assert isinstance(max_steps, int), "Number of steps must be an integer."
    assert isinstance(evo_epochs, int), "Evolution frequency must be an integer."
    if target is not None:
        assert isinstance(
            target, (float, int)
        ), "Target score must be a float or an integer."
    if checkpoint is not None:
        assert isinstance(checkpoint, int), "Checkpoint must be an integer."
    assert isinstance(
        wb, bool
    ), "'wb' must be a boolean flag, indicating whether to record run with W&B"
    assert isinstance(verbose, bool), "Verbose must be a boolean."
    if save_elite is False and elite_path is not None:
        warnings.warn(
            "'save_elite' set to False but 'elite_path' has been defined, elite will not\
                      be saved unless 'save_elite' is set to True."
        )
    if checkpoint is None and checkpoint_path is not None:
        warnings.warn(
            "'checkpoint' set to None but 'checkpoint_path' has been defined, checkpoint will not\
                      be saved unless 'checkpoint' is defined."
        )

    if wb:
        if not hasattr(wandb, "api"):
            if wandb_api_key is not None:
                wandb.login(key=wandb_api_key)
            else:
                warnings.warn("Must login to wandb with API key.")

        if accelerator is not None:
            accelerator.wait_for_everyone()
            if accelerator.is_main_process:
                wandb.init(
                    # set the wandb project where this run will be logged
                    project="AgileRL",
                    name="{}-EvoHPO-{}-{}".format(
                        env_name, algo, datetime.now().strftime("%m%d%Y%H%M%S")
                    ),
                    # track hyperparameters and run metadata
                    config={
                        "algo": f"Evo HPO {algo}",
                        "env": env_name,
                        "batch_size": INIT_HP["BATCH_SIZE"] if INIT_HP else None,
                        "lr": INIT_HP["LR"] if INIT_HP else None,
                        "gamma": INIT_HP["GAMMA"] if INIT_HP else None,
                        "memory_size": INIT_HP["MEMORY_SIZE"] if INIT_HP else None,
                        "learn_step": INIT_HP["LEARN_STEP"] if INIT_HP else None,
                        "tau": INIT_HP["TAU"] if INIT_HP else None,
                        "pop_size": INIT_HP["POP_SIZE"] if INIT_HP else None,
                        "no_mut": MUT_P["NO_MUT"] if MUT_P else None,
                        "arch_mut": MUT_P["ARCH_MUT"] if MUT_P else None,
                        "params_mut": MUT_P["PARAMS_MUT"] if MUT_P else None,
                        "act_mut": MUT_P["ACT_MUT"] if MUT_P else None,
                        "rl_hp_mut": MUT_P["RL_HP_MUT"] if MUT_P else None,
                    },
                )
            accelerator.wait_for_everyone()
        else:
            wandb.init(
                # set the wandb project where this run will be logged
                project="AgileRL",
                name="{}-EvoHPO-{}-{}".format(
                    env_name, algo, datetime.now().strftime("%m%d%Y%H%M%S")
                ),
                # track hyperparameters and run metadata
                config={
                    "algo": f"Evo HPO {algo}",
                    "env": env_name,
                    "batch_size": INIT_HP["BATCH_SIZE"] if INIT_HP else None,
                    "lr": INIT_HP["LR"] if INIT_HP else None,
                    "gamma": INIT_HP["GAMMA"] if INIT_HP else None,
                    "memory_size": INIT_HP["MEMORY_SIZE"] if INIT_HP else None,
                    "learn_step": INIT_HP["LEARN_STEP"] if INIT_HP else None,
                    "tau": INIT_HP["TAU"] if INIT_HP else None,
                    "pop_size": INIT_HP["POP_SIZE"] if INIT_HP else None,
                    "no_mut": MUT_P["NO_MUT"] if MUT_P else None,
                    "arch_mut": MUT_P["ARCH_MUT"] if MUT_P else None,
                    "params_mut": MUT_P["PARAMS_MUT"] if MUT_P else None,
                    "act_mut": MUT_P["ACT_MUT"] if MUT_P else None,
                    "rl_hp_mut": MUT_P["RL_HP_MUT"] if MUT_P else None,
                },
            )

    if accelerator is not None:
        accel_temp_models_path = f"models/{env_name}"
        if accelerator.is_main_process:
            if not os.path.exists(accel_temp_models_path):
                os.makedirs(accel_temp_models_path)

    save_path = (
        checkpoint_path.split(".pt")[0]
        if checkpoint_path is not None
        else "{}-EvoHPO-{}-{}".format(
            env_name, algo, datetime.now().strftime("%m%d%Y%H%M%S")
        )
    )

    if accelerator is not None:
        if accelerator.is_main_process:
            print("Filling replay buffer with dataset...")
        accelerator.wait_for_everyone()
    else:
        print("Filling replay buffer with dataset...")

    if minari_dataset_id:
        print(f"Loading Minari Dataset with dataset_id {minari_dataset_id} in Buffer")

        memory = MinariToAgileBuffer(minari_dataset_id, memory, accelerator, remote)

        print(f"Minari Dataset with dataset_id {minari_dataset_id} loaded in Buffer")

    else:
        print("Loading buffer...")
        print(dataset["rewards"])
        dataset_length = dataset["rewards"].shape[0]
        # for i in range(dataset_length):
        #     state = dataset['observations'][i]
        #     next_state = dataset['next_observations'][i]
        #     if swap_channels:
        #         state = np.moveaxis(state, [3], [1])
        #         next_state = np.moveaxis(next_state, [3], [1])
        #     action = dataset['actions'][i]
        #     reward = dataset['rewards'][i]
        #     done = bool(dataset['terminals'][i])
        #     memory.save2memory(state, action, next_state, reward, done)
        for i in range(dataset_length - 1):
            state = dataset["observations"][i]
            next_state = dataset["observations"][i + 1]
            if swap_channels:
                state = np.moveaxis(state, [-1], [-3])
                next_state = np.moveaxis(next_state, [-1], [-3])
            action = dataset["actions"][i]
            reward = dataset["rewards"][i]
            done = bool(dataset["terminals"][i])
            memory.save2memory(state, action, reward, next_state, done)
        if accelerator is not None:
            if accelerator.is_main_process:
                print("Loaded buffer.")
            accelerator.wait_for_everyone()
        else:
            print("Loaded buffer.")

    if accelerator is not None:
        # Create dataloader from replay buffer
        replay_dataset = ReplayDataset(memory, pop[0].batch_size)
        replay_dataloader = DataLoader(replay_dataset, batch_size=None)
        replay_dataloader = accelerator.prepare(replay_dataloader)
        sampler = Sampler(
            distributed=True, dataset=replay_dataset, dataloader=replay_dataloader
        )
    else:
        sampler = Sampler(distributed=False, memory=memory)

    if accelerator is not None:
        print(f"\nDistributed training on {accelerator.device}...")
    else:
        print("\nTraining...")

    bar_format = "{l_bar}{bar:10}| {n:4}/{total_fmt} [{elapsed:>7}<{remaining:>7}, {rate_fmt}{postfix}]"
    if accelerator is not None:
        pbar = trange(
            n_episodes,
            unit="ep",
            bar_format=bar_format,
            ascii=True,
            disable=not accelerator.is_local_main_process,
        )
    else:
        pbar = trange(n_episodes, unit="ep", bar_format=bar_format, ascii=True)

    pop_loss = [[] for _ in pop]
    pop_fitnesses = []
    total_steps = 0

    # Pre-training mutation
    if accelerator is None:
        if mutation is not None:
            pop = mutation.mutation(pop, pre_training_mut=True)

    # RL training loop
    for idx_epi in pbar:
        if accelerator is not None:
            accelerator.wait_for_everyone()
        for agent_idx, agent in enumerate(pop):  # Loop through population
            for idx_step in range(max_steps):
                experiences = sampler.sample(agent.batch_size)  # Sample replay buffer
                # Learn according to agent's RL algorithm
                loss = agent.learn(experiences)

            pop_loss[agent_idx].append(loss)
            agent.steps[-1] += max_steps
            total_steps += max_steps

        # Now evolve if necessary
        if (idx_epi + 1) % evo_epochs == 0:
            # Evaluate population
            fitnesses = [
                agent.test(
                    env, swap_channels=swap_channels, max_steps=max_steps, loop=evo_loop
                )
                for agent in pop
            ]
            pop_fitnesses.append(fitnesses)

            wandb_dict = {
                "global_step": (
                    total_steps * accelerator.state.num_processes
                    if accelerator is not None and accelerator.is_main_process
                    else total_steps
                ),
                "eval/mean_fitness": np.mean(fitnesses),
                "eval/best_fitness": np.max(fitnesses),
            }

            agent_loss_dict = {
                f"train/agent_{index}_loss": loss[-1]
                for index, loss in enumerate(pop_loss)
            }

            wandb_dict.update(agent_loss_dict)

            if wb:
                if accelerator is not None:
                    accelerator.wait_for_everyone()
                    if accelerator.is_main_process:
                        wandb.log(wandb_dict)
                    accelerator.wait_for_everyone()
                else:
                    wandb.log(wandb_dict)

            # Update step counter
            for agent in pop:
                agent.steps.append(agent.steps[-1])

            # Early stop if consistently reaches target
            if (
                np.all(
                    np.greater([np.mean(agent.fitness[-100:]) for agent in pop], target)
                )
                and idx_epi >= 100
            ):
                if wb:
                    wandb.finish()
                return pop, pop_fitnesses

            # Tournament selection and population mutation
            if tournament and mutation is not None:
                if accelerator is not None:
                    accelerator.wait_for_everyone()
                    for model in pop:
                        model.unwrap_models()
                    accelerator.wait_for_everyone()
                    if accelerator.is_main_process:
                        elite, pop = tournament.select(pop)
                        pop = mutation.mutation(pop)
                        for pop_i, model in enumerate(pop):
                            model.saveCheckpoint(
                                f"{accel_temp_models_path}/{algo}_{pop_i}.pt"
                            )
                    accelerator.wait_for_everyone()
                    if not accelerator.is_main_process:
                        for pop_i, model in enumerate(pop):
                            model.loadCheckpoint(
                                f"{accel_temp_models_path}/{algo}_{pop_i}.pt"
                            )
                    accelerator.wait_for_everyone()
                    for model in pop:
                        model.wrap_models()
                else:
                    elite, pop = tournament.select(pop)
                    pop = mutation.mutation(pop)

                if save_elite and (idx_epi + 1 == n_episodes):
                    elite_save_path = (
                        elite_path.split(".pt")[0]
                        if elite_path is not None
                        else "{}-elite_{}-{}".format(
                            env_name, algo, datetime.now().strftime("%m%d%Y%H%M%S")
                        )
                    )
                    elite.saveCheckpoint(f"{elite_save_path}.pt")

            if verbose:
                fitness = ["%.2f" % fitness for fitness in fitnesses]
                avg_fitness = ["%.2f" % np.mean(agent.fitness[-100:]) for agent in pop]
                avg_score = ["%.2f" % np.mean(agent.scores[-100:]) for agent in pop]
                agents = [agent.index for agent in pop]
                num_steps = [agent.steps[-1] for agent in pop]
                muts = [agent.mut for agent in pop]
                pbar.update(0)

                print(
                    f"""
                    --- Epoch {idx_epi + 1} ---
                    Fitness:\t\t{fitness}
                    100 fitness avgs:\t{avg_fitness}
                    100 score avgs:\t{avg_score}
                    Agents:\t\t{agents}
                    Steps:\t\t{num_steps}
                    Mutations:\t\t{muts}
                    """,
                    end="\r",
                )

        if checkpoint is not None:
            if (idx_epi + 1) % checkpoint == 0:
                if accelerator is not None:
                    accelerator.wait_for_everyone()
                    for model in pop:
                        model.unwrap_models()
                    accelerator.wait_for_everyone()
                    if accelerator.is_main_process:
                        for i, agent in enumerate(pop):
                            agent.saveCheckpoint(f"{save_path}_{i}_{idx_epi+1}.pt")
                        print("Saved checkpoint.")
                    accelerator.wait_for_everyone()
                    for model in pop:
                        model.wrap_models()
                    accelerator.wait_for_everyone()
                else:
                    for i, agent in enumerate(pop):
                        agent.saveCheckpoint(f"{save_path}_{i}_{idx_epi+1}.pt")
                    print("Saved checkpoint.")

    if wb:
        if accelerator is not None:
            accelerator.wait_for_everyone()
            if accelerator.is_main_process:
                wandb.finish()
            accelerator.wait_for_everyone()
        else:
            wandb.finish()

    return pop, pop_fitnesses
