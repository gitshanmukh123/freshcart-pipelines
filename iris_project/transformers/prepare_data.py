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
def transform(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    """Split Iris into stratified train and test partitions."""
    from sklearn.model_selection import train_test_split

    train, test = train_test_split(df, test_size=0.2, random_state=42)
    train = train.copy()
    test = test.copy()
    train["split"] = "train"
    test["split"] = "test"
    return pd.concat([train, test])


@test
def test_output(output: pd.DataFrame, *args) -> None:
    train_rows = int((output["split"] == "train").sum())
    test_rows = int((output["split"] == "test").sum())
    assert train_rows == 120, f"Expected 120 train rows, got {train_rows}"
    assert test_rows == 30, f"Expected 30 test rows, got {test_rows}"
    assert not output.isna().any().any()
