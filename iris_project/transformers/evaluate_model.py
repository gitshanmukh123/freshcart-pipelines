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
def evaluate(data: dict, *args, **kwargs) -> dict:
    """Build a confusion matrix and a metrics table for the trained model."""
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

    labels = [0, 1, 2]
    y_true = data["y_test"]
    y_pred = data["predictions"]

    matrix = confusion_matrix(y_true, y_pred, labels=labels)
    matrix_frame = pd.DataFrame(
        matrix,
        index=[f"actual_{label}" for label in labels],
        columns=[f"predicted_{label}" for label in labels],
    )
    report = classification_report(
        y_true,
        y_pred,
        labels=labels,
        output_dict=True,
        zero_division=0,
    )
    metrics_frame = (
        pd.DataFrame(report)
        .transpose()
        .reset_index()
        .rename(columns={"index": "label"})
    )

    matrix_frame.to_csv(kwargs.get("matrix_path", "iris_confusion_matrix.csv"), index=True)
    metrics_frame.to_csv(kwargs.get("metrics_path", "iris_metrics.csv"), index=False)

    print(f"accuracy={accuracy_score(y_true, y_pred):.4f}")
    print(metrics_frame.to_string(index=False))

    return {
        "confusion_matrix": matrix_frame,
        "metrics": metrics_frame,
        "accuracy": float(accuracy_score(y_true, y_pred)),
    }


@test
def test_output(output: dict, *args) -> None:
    assert output["confusion_matrix"].shape == (3, 3)
    assert 0.0 <= output["accuracy"] <= 1.0
