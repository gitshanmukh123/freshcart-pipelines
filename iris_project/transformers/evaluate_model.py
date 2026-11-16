from __future__ import annotations

import pandas as pd

if "transformer" not in globals():
    try:
        from mage_ai.data_preparation.decorators import transformer
    except ImportError:
        def transformer(func):
            return func

if "test" not in globals():
    try:
        from mage_ai.data_preparation.decorators import test
    except ImportError:
        def test(func):
            return func


@transformer
def evaluate(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    y_true = df["target"]
    y_pred = df["predicted"]

    print("Confusion matrix:")
    print(pd.crosstab(y_true, y_pred, rownames=["actual"], colnames=["predicted"]))

    metrics = pd.DataFrame(
        {
            "metric": ["accuracy", "precision", "recall", "f1_score"],
            "value": [
                round(accuracy_score(y_true, y_pred), 3),
                round(precision_score(y_true, y_pred, average="macro"), 3),
                round(recall_score(y_true, y_pred, average="macro"), 3),
                round(f1_score(y_true, y_pred, average="macro"), 3),
            ],
        }
    )
    print(metrics.to_string(index=False))
    return metrics


@test
def test_output(output: pd.DataFrame, *args) -> None:
    assert len(output) == 4
    assert set(output["metric"]) == {"accuracy", "precision", "recall", "f1_score"}
