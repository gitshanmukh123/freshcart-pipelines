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


FEATURES = [
    "sepal length (cm)",
    "sepal width (cm)",
    "petal length (cm)",
    "petal width (cm)",
]
ACCURACY_THRESHOLD = 0.8


@transformer
def train(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    import joblib
    from sklearn.tree import DecisionTreeClassifier

    max_depth = int(kwargs.get("max_depth", 3))
    threshold = float(kwargs.get("accuracy_threshold", ACCURACY_THRESHOLD))

    train_df = df[df["split"] == "train"]
    test_df = df[df["split"] == "test"].copy()

    model = DecisionTreeClassifier(max_depth=max_depth, random_state=42)
    model.fit(train_df[FEATURES], train_df["target"])

    test_df["predicted"] = model.predict(test_df[FEATURES])
    accuracy = (test_df["predicted"] == test_df["target"]).mean()
    print("max_depth =", max_depth, "| Test accuracy =", round(accuracy, 3))

    joblib.dump(model, kwargs.get("model_path", "iris_model.pkl"))
    test_df.attrs["accuracy_threshold"] = threshold
    return test_df


@test
def test_accuracy(output: pd.DataFrame, *args) -> None:
    accuracy = (output["predicted"] == output["target"]).mean()
    assert accuracy >= ACCURACY_THRESHOLD, "Model accuracy is below 80%"
