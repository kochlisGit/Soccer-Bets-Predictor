from wtforms import SelectField
from wtforms.validators import InputRequired
from flask_wtf import FlaskForm

import threading
import numpy as np
import pandas as pd
from abc import abstractmethod
from typing import Callable
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from database.repositories.model import ModelRepository
from gui.dialogs.model.utils import display_eval_metrics
from models.model import Model
from models.scikit.rf import RandomForest
from models.tf.nn import FCNet
from tuners.tuner import Tuner
from tuners.scikit.rf import RandomForestTuner
from tuners.tf.nn import FCNetTuner
from wtforms import SelectField, IntegerField


class TuningForm(FlaskForm):
    n_trials_selected = IntegerField("Number of trials", validators=[InputRequired()])
    selected_metric = SelectField('Metric', validators=[InputRequired()])
    selected_metric_target = SelectField("Metric target", validators=[InputRequired()])
    num_eval_samples_var = IntegerField("Number of evaluation samples", validators=[InputRequired()])
    def __init__(
            self,
            model_repository: ModelRepository,
            league_name: str,
            random_seed: int,
            matches_df: pd.DataFrame,
            one_hot: bool
    ):
        super().__init__()

        self._model_repository = model_repository
        self._league_name = league_name
        self._random_seed = random_seed
        self._matches_df = matches_df
        self._one_hot = one_hot

        self._metrics = ['Accuracy', 'F1', 'Precision', 'Recall']
        self._metric_targets = {'Home': 0, 'Draw': 1, 'Away': 2}
        self._best_params = None
        self._eval_metrics = None

        self.selected_metric.choices = self._metrics
        self.selected_metric_target.choices = [k for k in self._metric_targets.keys()]
        self.n_trials_selected.data = 20
        self.num_eval_samples_var.data = 200

    def _tune_fn(self):
        task_thread = threading.Thread(target=self._tune)
        task_thread.start()

    def _tune(self):
        metric_name = self.selected_metric.data
        metric_target = self._metric_targets[self.selected_metric_target.data]

        if metric_name == 'Accuracy':
            metric = lambda y_true, y_pred: accuracy_score(y_true=y_true, y_pred=y_pred)
        elif metric_name == 'F1':
            metric = lambda y_true, y_pred: f1_score(y_true=y_true, y_pred=y_pred, average=None)[metric_target]
        elif metric_name == 'Precision':
            metric = lambda y_true, y_pred: precision_score(
                y_true=y_true, y_pred=y_pred, average=None)[metric_target]
        elif metric_name == 'Recall':
            metric = lambda y_true, y_pred: recall_score(
                y_true=y_true, y_pred=y_pred, average=None)[metric_target]
        else:
            raise NotImplementedError(f'Error: Metric "{metric_name}" has not been implemented yet')

        tuner = self._construct_tuner(
            n_trials=self.n_trials_selected.data,
            metric=metric,
            matches_df=self._matches_df,
            num_eval_samples=self.num_eval_samples_var.data,
            random_seed=self._random_seed
        )
        self._best_params = tuner.tune()
        self._train(
            x_train=tuner.x_train,
            y_train=tuner.y_train,
            x_test=tuner.x_test,
            y_test=tuner.y_test,
            random_seed=self._random_seed,
            best_params=self._best_params
        )

    def _train(
            self,
            x_train: np.ndarray,
            y_train: np.ndarray,
            x_test: np.ndarray,
            y_test: np.ndarray,
            random_seed: int,
            best_params: dict
    ):
        model = self._construct_model(input_shape=x_train.shape[1:], random_seed=random_seed)
        self._build_model(model=model, best_params=best_params)
        self._eval_metrics = model.train(
            x_train=x_train,
            y_train=y_train,
            x_test=x_test,
            y_test=y_test,
            use_over_sampling=best_params['user_over_sampling']
        )
        self._model_repository.store_model(model=model, league_name=self._league_name)

    def submit_tuning(self):
        self._tune_fn()
        if self._eval_metrics is not None and self._best_params is not None:
            self._display_best_params(best_params=self._best_params)
            display_eval_metrics(self._eval_metrics)
            self._eval_metrics = None
            self._best_params = None

    @abstractmethod
    def _construct_tuner(
            self,
            n_trials: int,
            metric: Callable,
            matches_df: pd.DataFrame,
            num_eval_samples: int,
            random_seed: int = 0
    ) -> Tuner:
        pass

    @abstractmethod
    def _construct_model(self, input_shape: tuple, random_seed: int) -> Model:
        pass

    @abstractmethod
    def _build_model(self, model: Model, best_params: dict):
        pass

    @abstractmethod
    def _display_best_params(self, best_params: dict):
        pass

    def _dialog_result(self) -> None:
        return None


class TuningRFForm(TuningForm):
    def __init__(
            self,
            model_repository: ModelRepository,
            league_name: str,
            random_seed: int,
            matches_df: pd.DataFrame
    ):
        super().__init__(
            model_repository=model_repository,
            league_name=league_name,
            random_seed=random_seed,
            matches_df=matches_df,
            one_hot=False
        )

        self._text = None

    def _initialize(self):
        pass

    def _construct_tuner(
            self,
            n_trials: int,
            metric: Callable,
            matches_df: pd.DataFrame,
            num_eval_samples: int,
            random_seed: int = 0
    ) -> Tuner:
        return RandomForestTuner(
            n_trials=n_trials,
            metric=metric,
            matches_df=matches_df,
            num_eval_samples=num_eval_samples,
            random_seed=random_seed
        )

    def _construct_model(self, input_shape: tuple, random_seed: int) -> Model:
        return RandomForest(input_shape=input_shape, random_seed=random_seed)

    def _build_model(self, model: Model, best_params: dict):
        model.build_model(
            n_estimators=best_params['n_estimators'],
            max_features=best_params['max_features'],
            max_depth=best_params['max_depth'],
            min_samples_leaf=best_params['min_samples_leaf'],
            min_samples_split=best_params['min_samples_split'],
            bootstrap=best_params['bootstrap'],
            class_weight=best_params['class_weight'],
            is_calibrated=best_params['is_calibrated']
        )

    def _display_best_params(self, best_params: dict):
        s = '{'
        for param_name, param_value in best_params.items():
            s += f'\n\tParameter: {param_name} = {param_value}'
        s += '\n}'

        self._text['state'] = 'normal'
        self._text.delete(1.0, END)
        self._text.insert(INSERT, s)
        self._text['state'] = 'disabled'