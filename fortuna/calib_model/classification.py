from fortuna.calib_model.base import CalibModel
from fortuna.calib_model.predictive.classification import ClassificationPredictive
from fortuna.prob_output_layer.classification import ClassificationProbOutputLayer
from fortuna.model.model_manager.classification import ClassificationModelManager
from fortuna.likelihood.classification import ClassificationLikelihood
from fortuna.typing import Status, Outputs, Targets
from flax import linen as nn
from fortuna.data import DataLoader
from fortuna.calib_model.config.base import Config
from fortuna.loss.classification.focal_loss import focal_loss_fn
from typing import Optional, Callable
import numpy as np
import jax.numpy as jnp


class CalibClassifier(CalibModel):
    def __init__(
            self,
            model: nn.Module,
            seed: int = 0):
        r"""
        A calibration classifier class.

        Parameters
        ----------
        model : nn.Module
            A model describing the deterministic relation between inputs and outputs. The outputs must correspond to
            the logits of a softmax probability vector. The output dimension must be the same as the number of classes.
            Let :math:`x` be input variables and :math:`w` the random model parameters. Then the model is described by
            a function :math:`f(w, x)`, where each component of :math:`f` corresponds to one of the classes.
        seed: int
            A random seed.

        Attributes
        ----------
        model : nn.Module
            See `model` in `Parameters`.
        model_manager : ClassificationModelManager
            This object orchestrates the model's forward pass.
        prob_output_layer : ClassificationProbOutputLayer
            This object characterizes the distribution of target variable given the outputs. It is defined
            by :math:`p(y|o)=\text{Categorical}(y|p=softmax(o))`,
            where :math:`o` denotes the outputs and :math:`y` denotes a target variable.
        likelihood : ClassificationLikelihood
            The likelihood function. This is defined by
            :math:`p(y|w, \phi, x) = \text{Categorical}(y|p=\text{softmax}(g(\phi, f(w, x)))`.
        predictive : ClassificationPredictive
            This denotes the predictive distribution, that is :math:`p(y|x, \mathcal{D})`.
        """
        self.model_manager = ClassificationModelManager(model)
        self.prob_output_layer = ClassificationProbOutputLayer()
        self.likelihood = ClassificationLikelihood(
                model_manager=self.model_manager,
                prob_output_layer=self.prob_output_layer,
                output_calib_manager=None
            )
        self.predictive = ClassificationPredictive(
            likelihood=self.likelihood
        )
        super().__init__(seed=seed)

    def _check_output_dim(self, data_loader: DataLoader):
        if data_loader.size == 0:
            raise ValueError(
                """`data_loader` is either empty or incorrectly constructed."""
            )
        data_output_dim = len(np.unique(data_loader.to_array_targets()))
        for x, y in data_loader:
            input_shape = x.shape[1:]
            break
        model_manager_output_dim = self._get_output_dim(input_shape)
        if model_manager_output_dim != data_output_dim:
            raise ValueError(
                f"""The outputs dimension of `model` must correspond to the number of different classes
            in the target variables of `_data_loader`. However, {model_manager_output_dim} and {data_output_dim} were 
            found, respectively."""
            )

    def calibrate(
        self,
        calib_data_loader: DataLoader,
        val_data_loader: Optional[DataLoader] = None,
        loss_fn: Callable[[Outputs, Targets], jnp.ndarray] = focal_loss_fn,
        config: Config = Config()
    ) -> Status:
        """
        Calibrate the calibration classifier.

        Parameters
        ----------
        calib_data_loader : DataLoader
            A calibration data loader.
        val_data_loader : DataLoader
            A validation data loader.
        loss_fn: Callable[[Outputs, Targets], jnp.ndarray]
            The loss function to use for calibration.
        config : Config
            An object to configure the calibration.

        Returns
        -------
        Status
            A calibration status object. It provides information about the calibration.
        """
        self._check_output_dim(calib_data_loader)
        if val_data_loader is not None:
            self._check_output_dim(val_data_loader)
        return self._calibrate(
            calib_data_loader=calib_data_loader,
            uncertainty_fn=config.monitor.uncertainty_fn if config.monitor.uncertainty_fn is not None
            else self.prob_output_layer.mean,
            val_data_loader=val_data_loader,
            loss_fn=loss_fn,
            config=config,
        )