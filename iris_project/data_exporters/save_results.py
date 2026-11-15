from __future__ import annotations

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
def export_data(data: dict, *args, **kwargs) -> dict:
    """Write test predictions to iris_predictions.csv."""
    import pandas as pd

    output_path = kwargs.get("output_path", "iris_predictions.csv")
    frame = pd.DataFrame(
        {
            "prediction": data["predictions"].tolist(),
            "actual": data["y_test"].tolist(),
        }
    )
    frame.to_csv(output_path, index=False)
    return {"path": output_path, "rows": len(frame)}


@test
def test_output(output: dict, *args) -> None:
    import os

    assert os.path.exists(output["path"]), f"Missing {output['path']}"
    assert output["rows"] == 30
