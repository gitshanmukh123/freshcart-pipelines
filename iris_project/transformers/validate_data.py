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
    """Validate the raw Iris frame and return it unchanged."""
    missing_cells = int(df.isna().sum().sum())
    if missing_cells:
        raise ValueError(f"Iris data contains {missing_cells} missing cells")

    classes = sorted(df["target"].unique().tolist())
    if len(classes) != 3:
        raise ValueError(f"Iris data must contain exactly 3 classes, got {classes}")

    return df


@test
def test_output(output: pd.DataFrame, *args) -> None:
    assert output.shape == (150, 5)
    assert output["target"].nunique() == 3
    assert not output.isna().any().any()
