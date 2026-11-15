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
def train(df: pd.DataFrame, *args, **kwargs) -> dict:
    """Fit a decision tree and return the model, test predictions and accuracy."""
    from sklearn.metrics import accuracy_score
    from sklearn.tree import DecisionTreeClassifier

    max_depth = int(kwargs.get("max_depth", 3))
    accuracy_threshold = float(kwargs.get("accuracy_threshold", 0.90))

    feature_columns = [c for c in df.columns if c not in ("target", "split")]
    train_df = df[df["split"] == "train"]
    test_df = df[df["split"] == "test"]

    model = DecisionTreeClassifier(max_depth=max_depth, random_state=42)
    model.fit(train_df[feature_columns], train_df["target"])
    predictions = model.predict(test_df[feature_columns])
    accuracy = float(accuracy_score(test_df["target"], predictions))

    print(f"max_depth={max_depth} test_accuracy={accuracy:.4f}")

    return {
        "model": model,
        "feature_columns": feature_columns,
        "y_test": test_df["target"].reset_index(drop=True),
        "predictions": pd.Series(predictions, name="prediction"),
        "accuracy": accuracy,
        "accuracy_threshold": accuracy_threshold,
        "max_depth": max_depth,
    }


@test
def test_output(output: dict, *args) -> None:
    assert output["accuracy"] >= output["accuracy_threshold"], (
        f"test_accuracy {output['accuracy']:.4f} is below "
        f"{output['accuracy_threshold']:.2f} for max_depth={output['max_depth']}"
    )
    assert len(output["predictions"]) == 30
