import torch
import losses
import util
import itertools


def train_sleep(generative_model, inference_network, num_samples,
                num_iterations, callback=None):
    optimizer = torch.optim.Adam(inference_network.parameters())
    for iteration in range(num_iterations):
        optimizer.zero_grad()
        sleep_loss = losses.get_sleep_loss(generative_model, inference_network,
                                           num_samples=num_samples)
        sleep_loss.backward()
        optimizer.step()
        if callback is not None:
            callback(iteration, sleep_loss.item(), generative_model,
                     inference_network, optimizer)

    return optimizer


class TrainSleepCallback():
    def __init__(self, logging_interval=10, saving_interval=10):
        self.sleep_loss_history = []
        self.logging_interval = logging_interval

    def __call__(self, iteration, sleep_loss, generative_model,
                 inference_network, optimizer):
        if iteration % self.logging_interval == 0:
            util.print_with_time('Iteration {}: loss = {:.3f}'.format(
                iteration, sleep_loss))
            self.sleep_loss_history.append(sleep_loss)


def train_wake_sleep(generative_model, inference_network,
                     true_generative_model, batch_size,
                     num_iterations, num_particles, callback=None):
    num_samples = batch_size * num_particles
    optimizer_phi = torch.optim.Adam(inference_network.parameters())
    optimizer_theta = torch.optim.Adam(generative_model.parameters())

    for iteration in range(num_iterations):
        # generate synthetic data
        obss = [true_generative_model.sample_obs() for _ in range(batch_size)]

        # wake theta
        optimizer_phi.zero_grad()
        optimizer_theta.zero_grad()
        wake_theta_loss, elbo = losses.get_wake_theta_loss(
            generative_model, inference_network, obss, num_particles)
        wake_theta_loss.backward()
        optimizer_theta.step()

        # sleep phi
        optimizer_phi.zero_grad()
        optimizer_theta.zero_grad()
        sleep_phi_loss = losses.get_sleep_loss(
            generative_model, inference_network, num_samples)
        sleep_phi_loss.backward()
        optimizer_phi.step()

        if callback is not None:
            callback(iteration, wake_theta_loss.item(), sleep_phi_loss.item(),
                     elbo.item(), generative_model, inference_network,
                     optimizer_theta, optimizer_phi)

    return optimizer_theta, optimizer_phi


class TrainWakeSleepCallback():
    def __init__(self, pcfg_path, model_folder, true_generative_model,
                 logging_interval=10, checkpoint_interval=100,
                 eval_interval=10):
        self.pcfg_path = pcfg_path
        self.model_folder = model_folder
        self.true_generative_model = true_generative_model
        self.logging_interval = logging_interval
        self.checkpoint_interval = checkpoint_interval
        self.eval_interval = eval_interval

        self.wake_theta_loss_history = []
        self.sleep_phi_loss_history = []
        self.elbo_history = []
        self.p_error_history = []
        self.q_error_to_true_history = []
        self.q_error_to_model_history = []

    def __call__(self, iteration, wake_theta_loss, sleep_phi_loss, elbo,
                 generative_model, inference_network, optimizer_theta,
                 optimizer_phi):
        if iteration % self.logging_interval == 0:
            util.print_with_time(
                'Iteration {} losses: theta = {:.3f}, phi = {:.3f}, elbo = '
                '{:.3f}'.format(iteration, wake_theta_loss, sleep_phi_loss,
                                elbo))
            self.wake_theta_loss_history.append(wake_theta_loss)
            self.sleep_phi_loss_history.append(sleep_phi_loss)
            self.elbo_history.append(elbo)

        if iteration % self.checkpoint_interval == 0:
            stats_filename = util.get_stats_filename(self.model_folder)
            util.save_object(self, stats_filename)
            util.save_models(generative_model, inference_network,
                             self.pcfg_path, self.model_folder)

        if iteration % self.eval_interval == 0:
            self.p_error_history.append(util.get_p_error(
                self.true_generative_model, generative_model))
            self.q_error_to_true_history.append(util.get_q_error(
                self.true_generative_model, inference_network))
            self.q_error_to_model_history.append(util.get_q_error(
                generative_model, inference_network))
            util.print_with_time(
                'Iteration {} p_error = {:.3f}, q_error_to_true = {:.3f}, '
                'q_error_to_model = {:.3f}'.format(
                    iteration, self.p_error_history[-1],
                    self.q_error_to_true_history[-1],
                    self.q_error_to_model_history[-1]))


def train_wake_wake(generative_model, inference_network,
                    true_generative_model, batch_size,
                    num_iterations, num_particles, callback=None):
    optimizer_phi = torch.optim.Adam(inference_network.parameters())
    optimizer_theta = torch.optim.Adam(generative_model.parameters())

    for iteration in range(num_iterations):
        # generate synthetic data
        obss = [true_generative_model.sample_obs() for _ in range(batch_size)]

        log_weight, log_q = losses.get_log_weight_and_log_q(
            generative_model, inference_network, obss, num_particles)

        # wake theta
        optimizer_phi.zero_grad()
        optimizer_theta.zero_grad()
        wake_theta_loss, elbo = losses.get_wake_theta_loss_from_log_weight(
            log_weight)
        wake_theta_loss.backward(retain_graph=True)
        optimizer_theta.step()

        # wake phi
        optimizer_phi.zero_grad()
        optimizer_theta.zero_grad()
        wake_phi_loss = losses.get_wake_phi_loss_from_log_weight_and_log_q(
            log_weight, log_q)
        wake_phi_loss.backward()
        optimizer_phi.step()

        if callback is not None:
            callback(iteration, wake_theta_loss.item(), wake_phi_loss.item(),
                     elbo.item(), generative_model, inference_network,
                     optimizer_theta, optimizer_phi)

    return optimizer_theta, optimizer_phi


class TrainWakeWakeCallback():
    def __init__(self, pcfg_path, model_folder, true_generative_model,
                 logging_interval=10, checkpoint_interval=100,
                 eval_interval=10):
        self.pcfg_path = pcfg_path
        self.model_folder = model_folder
        self.true_generative_model = true_generative_model
        self.logging_interval = logging_interval
        self.checkpoint_interval = checkpoint_interval
        self.eval_interval = eval_interval

        self.wake_theta_loss_history = []
        self.wake_phi_loss_history = []
        self.elbo_history = []
        self.p_error_history = []
        self.q_error_to_true_history = []
        self.q_error_to_model_history = []

    def __call__(self, iteration, wake_theta_loss, wake_phi_loss, elbo,
                 generative_model, inference_network, optimizer_theta,
                 optimizer_phi):
        if iteration % self.logging_interval == 0:
            util.print_with_time(
                'Iteration {} losses: theta = {:.3f}, phi = {:.3f}, elbo = '
                '{:.3f}'.format(iteration, wake_theta_loss, wake_phi_loss,
                                elbo))
            self.wake_theta_loss_history.append(wake_theta_loss)
            self.wake_phi_loss_history.append(wake_phi_loss)
            self.elbo_history.append(elbo)

        if iteration % self.checkpoint_interval == 0:
            stats_filename = util.get_stats_filename(self.model_folder)
            util.save_object(self, stats_filename)
            util.save_models(generative_model, inference_network,
                             self.pcfg_path, self.model_folder)

        if iteration % self.eval_interval == 0:
            self.p_error_history.append(util.get_p_error(
                self.true_generative_model, generative_model))
            self.q_error_to_true_history.append(util.get_q_error(
                self.true_generative_model, inference_network))
            self.q_error_to_model_history.append(util.get_q_error(
                generative_model, inference_network))
            util.print_with_time(
                'Iteration {} p_error = {:.3f}, q_error_to_true = {:.3f}, '
                'q_error_to_model = {:.3f}'.format(
                    iteration, self.p_error_history[-1],
                    self.q_error_to_true_history[-1],
                    self.q_error_to_model_history[-1]))


def train_iwae(algorithm, generative_model, inference_network,
               true_generative_model, batch_size, num_iterations,
               num_particles, callback=None):
    """Train using IWAE objective.

    Args:
        algorithm: reinforce or vimco
    """

    parameters = itertools.chain.from_iterable(
        [x.parameters() for x in [generative_model, inference_network]])
    optimizer = torch.optim.Adam(parameters)

    for iteration in range(num_iterations):
        # generate synthetic data
        obss = [true_generative_model.sample_obs() for _ in range(batch_size)]

        # wake theta
        optimizer.zero_grad()
        if algorithm == 'vimco':
            loss, elbo = losses.get_vimco_loss(
                generative_model, inference_network, obss, num_particles)
        elif algorithm == 'reinforce':
            loss, elbo = losses.get_reinforce_loss(
                generative_model, inference_network, obss, num_particles)
        loss.backward()
        optimizer.step()

        if callback is not None:
            callback(iteration, loss.item(), elbo.item(), generative_model,
                     inference_network, optimizer)

    return optimizer


class TrainIwaeCallback():
    def __init__(self, pcfg_path, model_folder, true_generative_model,
                 logging_interval=10, checkpoint_interval=100,
                 eval_interval=10):
        self.pcfg_path = pcfg_path
        self.model_folder = model_folder
        self.true_generative_model = true_generative_model
        self.logging_interval = logging_interval
        self.checkpoint_interval = checkpoint_interval
        self.eval_interval = eval_interval

        self.loss_history = []
        self.elbo_history = []
        self.p_error_history = []
        self.q_error_to_true_history = []
        self.q_error_to_model_history = []

    def __call__(self, iteration, loss, elbo, generative_model,
                 inference_network, optimizer):
        if iteration % self.logging_interval == 0:
            util.print_with_time(
                'Iteration {} loss = {:.3f}, elbo = {:.3f}'.format(
                    iteration, loss, elbo))
            self.loss_history.append(loss)
            self.elbo_history.append(elbo)

        if iteration % self.checkpoint_interval == 0:
            stats_filename = util.get_stats_filename(self.model_folder)
            util.save_object(self, stats_filename)
            util.save_models(generative_model, inference_network,
                             self.pcfg_path, self.model_folder)

        if iteration % self.eval_interval == 0:
            self.p_error_history.append(util.get_p_error(
                self.true_generative_model, generative_model))
            self.q_error_to_true_history.append(util.get_q_error(
                self.true_generative_model, inference_network))
            self.q_error_to_model_history.append(util.get_q_error(
                generative_model, inference_network))
            util.print_with_time(
                'Iteration {} p_error = {:.3f}, q_error_to_true = {:.3f}, '
                'q_error_to_model = {:.3f}'.format(
                    iteration, self.p_error_history[-1],
                    self.q_error_to_true_history[-1],
                    self.q_error_to_model_history[-1]))


def train_relax(generative_model, inference_network, control_variate,
                true_generative_model, batch_size, num_iterations,
                num_particles, callback=None):
    """Train using RELAX."""

    num_q_params = sum([param.nelement()
                        for param in inference_network.parameters()])
    iwae_optimizer = torch.optim.Adam(itertools.chain(
        generative_model.parameters(), inference_network.parameters()))
    control_variate_optimizer = torch.optim.Adam(control_variate.parameters())

    for iteration in range(num_iterations):
        # generate synthetic data
        obss = [true_generative_model.sample_obs() for _ in range(batch_size)]

        # optimize theta and phi
        iwae_optimizer.zero_grad()
        control_variate_optimizer.zero_grad()
        loss, elbo = losses.get_relax_loss(
            generative_model, inference_network, control_variate, obss,
            num_particles)
        if torch.isnan(loss):
            import pdb
            pdb.set_trace()
        loss.backward(create_graph=True)
        iwae_optimizer.step()

        # optimize rho
        control_variate_optimizer.zero_grad()
        torch.autograd.backward(
            [2 * q_param.grad / num_q_params
             for q_param in inference_network.parameters()],
            [q_param.grad.detach()
             for q_param in inference_network.parameters()]
        )
        control_variate_optimizer.step()

        if callback is not None:
            callback(iteration, loss.item(), elbo.item(), generative_model,
                     inference_network, control_variate)

    return iwae_optimizer, control_variate_optimizer


class TrainRelaxCallback():
    def __init__(self, pcfg_path, model_folder, true_generative_model,
                 logging_interval=10, checkpoint_interval=100,
                 eval_interval=10):
        self.pcfg_path = pcfg_path
        self.model_folder = model_folder
        self.true_generative_model = true_generative_model
        self.logging_interval = logging_interval
        self.checkpoint_interval = checkpoint_interval
        self.eval_interval = eval_interval

        self.loss_history = []
        self.elbo_history = []
        self.p_error_history = []
        self.q_error_to_true_history = []
        self.q_error_to_model_history = []

    def __call__(self, iteration, loss, elbo, generative_model,
                 inference_network, control_variate):
        if iteration % self.logging_interval == 0:
            util.print_with_time(
                'Iteration {} loss = {:.3f}, elbo = {:.3f}'.format(
                    iteration, loss, elbo))
            self.loss_history.append(loss)
            self.elbo_history.append(elbo)

        if iteration % self.checkpoint_interval == 0:
            stats_filename = util.get_stats_filename(self.model_folder)
            util.save_object(self, stats_filename)
            util.save_models(generative_model, inference_network,
                             self.pcfg_path, self.model_folder)
            util.save_control_variate(control_variate, self.model_folder)

        if iteration % self.eval_interval == 0:
            self.p_error_history.append(util.get_p_error(
                self.true_generative_model, generative_model))
            self.q_error_to_true_history.append(util.get_q_error(
                self.true_generative_model, inference_network))
            self.q_error_to_model_history.append(util.get_q_error(
                generative_model, inference_network))
            util.print_with_time(
                'Iteration {} p_error = {:.3f}, q_error_to_true = {:.3f}, '
                'q_error_to_model = {:.3f}'.format(
                    iteration, self.p_error_history[-1],
                    self.q_error_to_true_history[-1],
                    self.q_error_to_model_history[-1]))
