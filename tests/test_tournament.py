import copy

from agilerl.algorithms.cqn import CQN
from agilerl.algorithms.ddpg import DDPG
from agilerl.algorithms.dqn import DQN
from agilerl.algorithms.dqn_rainbow import RainbowDQN
from agilerl.algorithms.maddpg import MADDPG
from agilerl.algorithms.matd3 import MATD3
from agilerl.algorithms.ppo import PPO
from agilerl.algorithms.td3 import TD3
from agilerl.hpo.tournament import TournamentSelection
from agilerl.utils.utils import initialPopulation

# Shared HP dict that can be used by any algorithm
SHARED_INIT_HP = {
    "POPULATION_SIZE": 4,
    "DOUBLE": True,
    "BATCH_SIZE": 128,
    "LR": 1e-3,
    "LR_ACTOR": 1e-4,
    "LR_CRITIC": 1e-3,
    "GAMMA": 0.99,
    "LEARN_STEP": 1,
    "TAU": 1e-3,
    "BETA": 0.4,
    "PRIOR_EPS": 0.000001,
    "NUM_ATOMS": 51,
    "V_MIN": 0,
    "V_MAX": 200,
    "N_STEP": 3,
    "POLICY_FREQ": 10,
    "DISCRETE_ACTIONS": True,
    "GAE_LAMBDA": 0.95,
    "ACTION_STD_INIT": 0.6,
    "CLIP_COEF": 0.2,
    "ENT_COEF": 0.01,
    "VF_COEF": 0.5,
    "MAX_GRAD_NORM": 0.5,
    "TARGET_KL": None,
    "UPDATE_EPOCHS": 4,
    "MAX_ACTION": 1,
    "MIN_ACTION": -1,
    "N_AGENTS": 2,
    "AGENT_IDS": ["agent1", "agent2"],
    "CHANNELS_LAST": False,
}

SHARED_INIT_HP_MA = copy.deepcopy(SHARED_INIT_HP)
SHARED_INIT_HP_MA["MAX_ACTION"] = [(1,), (1,)]
SHARED_INIT_HP_MA["MIN_ACTION"] = [(-1,), (-1,)]


# Initializes the 'TournamentSelection' object with the given parameters.
def test_initialization_with_given_parameters():
    tournament_size = 5
    elitism = True
    population_size = 100
    evo_step = 10

    ts = TournamentSelection(tournament_size, elitism, population_size, evo_step)

    assert ts.tournament_size == tournament_size
    assert ts.elitism == elitism
    assert ts.population_size == population_size
    assert ts.evo_step == evo_step


### Single-agent algorithms ###
# Returns best agent and new population of agents following tournament selection.
def test_returns_best_agent_and_new_population():
    state_dim = [4]
    action_dim = 2
    one_hot = False
    net_config = {"arch": "mlp", "h_size": [8]}
    population_size = 4
    device = "cpu"
    population_size = 5

    # Initialize the class
    tournament_selection = TournamentSelection(3, True, population_size, 2)

    algo_classes = {
        "DQN": DQN,
        "Rainbow DQN": RainbowDQN,
        "DDPG": DDPG,
        "TD3": TD3,
        "PPO": PPO,
        "CQN": CQN,
    }

    for algo in algo_classes.keys():
        population = initialPopulation(
            algo=algo,
            state_dim=state_dim,
            action_dim=action_dim,
            one_hot=one_hot,
            net_config=net_config,
            INIT_HP=SHARED_INIT_HP,
            population_size=population_size,
            device=device,
        )

        population[0].fitness = [1, 2, 3]
        population[1].fitness = [4, 5, 6]
        population[2].fitness = [7, 8, 9]
        population[3].fitness = [10, 11, 12]
        population[4].fitness = [13, 14, 15]

        # Call the select method
        elite, new_population = tournament_selection.select(population)

        # Check if the elite agent is the best agent in the population
        assert elite.fitness == [13, 14, 15]
        assert elite.index == 4
        assert new_population[0].fitness == [13, 14, 15]
        assert new_population[0].index == 4

        # Check if the new population has the correct length
        assert len(new_population) == population_size


# Returns best agent and new population of agents following tournament selection without elitism.
def test_returns_best_agent_and_new_population_without_elitism():
    state_dim = [4]
    action_dim = 2
    one_hot = False
    net_config = {"arch": "mlp", "h_size": [8]}
    population_size = 4
    device = "cpu"
    population_size = 5

    # Initialize the class
    tournament_selection = TournamentSelection(3, False, population_size, 2)

    algo_classes = {
        "DQN": DQN,
        "Rainbow DQN": RainbowDQN,
        "DDPG": DDPG,
        "TD3": TD3,
        "PPO": PPO,
        "CQN": CQN,
    }

    for algo in algo_classes.keys():
        population = initialPopulation(
            algo=algo,
            state_dim=state_dim,
            action_dim=action_dim,
            one_hot=one_hot,
            net_config=net_config,
            INIT_HP=SHARED_INIT_HP,
            population_size=population_size,
            device=device,
        )

        population[0].fitness = [1, 2, 3]
        population[1].fitness = [4, 5, 6]
        population[2].fitness = [7, 8, 9]
        population[3].fitness = [10, 11, 12]
        population[4].fitness = [13, 14, 15]

        # Call the select method
        elite, new_population = tournament_selection.select(population)

        # Check if the elite agent is the best agent in the population
        assert elite.fitness == [13, 14, 15]
        assert elite.index == 4

        # Check if the new population has the correct length
        assert len(new_population) == population_size


### Multi-agent algorithms ###
# Returns best agent and new population of agents following tournament selection.
def test_returns_best_agent_and_new_population_multi_agent():
    state_dim = [[4], [4]]
    action_dim = [2, 2]
    one_hot = False
    net_config = {"arch": "mlp", "h_size": [8]}
    population_size = 4
    device = "cpu"
    population_size = 5

    # Initialize the class
    tournament_selection = TournamentSelection(3, True, population_size, 2)

    algo_classes = {"MADDPG": MADDPG, "MATD3": MATD3}

    for algo in algo_classes.keys():
        population = initialPopulation(
            algo=algo,
            state_dim=state_dim,
            action_dim=action_dim,
            one_hot=one_hot,
            net_config=net_config,
            INIT_HP=SHARED_INIT_HP_MA,
            population_size=population_size,
            device=device,
        )

        population[0].fitness = [1, 2, 3]
        population[1].fitness = [4, 5, 6]
        population[2].fitness = [7, 8, 9]
        population[3].fitness = [10, 11, 12]
        population[4].fitness = [13, 14, 15]

        # Call the select method
        elite, new_population = tournament_selection.select(population)

        # Check if the elite agent is the best agent in the population
        assert elite.fitness == [13, 14, 15]
        assert elite.index == 4
        assert new_population[0].fitness == [13, 14, 15]
        assert new_population[0].index == 4

        # Check if the new population has the correct length
        assert len(new_population) == population_size


# Returns best agent and new population of agents following tournament selection without elitism.
def test_returns_best_agent_and_new_population_without_elitism_multi_agent():
    state_dim = [[4], [4]]
    action_dim = [2, 2]
    one_hot = False
    net_config = {"arch": "mlp", "h_size": [8]}
    population_size = 4
    device = "cpu"
    population_size = 5

    # Initialize the class
    tournament_selection = TournamentSelection(3, False, population_size, 2)

    algo_classes = {"MADDPG": MADDPG, "MATD3": MATD3}

    for algo in algo_classes.keys():
        population = initialPopulation(
            algo=algo,
            state_dim=state_dim,
            action_dim=action_dim,
            one_hot=one_hot,
            net_config=net_config,
            INIT_HP=SHARED_INIT_HP_MA,
            population_size=population_size,
            device=device,
        )

        population[0].fitness = [1, 2, 3]
        population[1].fitness = [4, 5, 6]
        population[2].fitness = [7, 8, 9]
        population[3].fitness = [10, 11, 12]
        population[4].fitness = [13, 14, 15]

        # Call the select method
        elite, new_population = tournament_selection.select(population)

        # Check if the elite agent is the best agent in the population
        assert elite.fitness == [13, 14, 15]
        assert elite.index == 4

        # Check if the new population has the correct length
        assert len(new_population) == population_size
