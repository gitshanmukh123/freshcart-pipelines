from __future__ import annotations

import pandas as pd

if "data_loader" not in globals():
    try:
        from mage_ai.data_preparation.decorators import data_loader
    except ImportError:
        def data_loader(func):
            return func

if "test" not in globals():
    try:
        from mage_ai.data_preparation.decorators import test
    except ImportError:
        def test(func):
            return func


@data_loader
def load_data(*args, **kwargs) -> pd.DataFrame:
    """Load the sklearn Iris dataset as a pandas DataFrame."""
    from sklearn.datasets import load_iris

    return load_iris(as_frame=True).frame


@test
def test_output(output: pd.DataFrame, *args) -> None:
    assert output.shape == (150, 5), f"Unexpected Iris shape: {output.shape}"
    assert output["target"].nunique() == 3
    assert not output.isna().any().any()
