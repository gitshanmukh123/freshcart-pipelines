from __future__ import annotations

import pandas as pd

if "data_exporter" not in globals():
    try:
        from mage_ai.data_preparation.decorators import data_exporter
    except ImportError:
        def data_exporter(func):
            return func

if "test" not in globals():
    try:
        from mage_ai.data_preparation.decorators import test
    except ImportError:
        def test(func):
            return func


@data_exporter
def export_data(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    output_path = kwargs.get("output_path", "iris_predictions.csv")
    df.to_csv(output_path, index=False)
    print("Saved", len(df), "predictions to", output_path)
    return df


@test
def test_output(output: pd.DataFrame, *args) -> None:
    import os

    assert os.path.exists("iris_predictions.csv")
    assert len(output) == 30
