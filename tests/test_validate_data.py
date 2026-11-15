import pandas as pd
import pytest
from sklearn.datasets import load_iris

from iris_project.transformers.validate_data import transform as validate_transform


def test_validates_and_returns_same_frame():
    df = load_iris(as_frame=True).frame
    out = validate_transform(df)
    pd.testing.assert_frame_equal(out, df)


def test_rejects_missing_values():
    df = load_iris(as_frame=True).frame.copy()
    df.loc[0, "sepal length (cm)"] = None
    with pytest.raises(ValueError, match="missing"):
        validate_transform(df)


def test_rejects_wrong_number_of_classes():
    df = load_iris(as_frame=True).frame.copy()
    df["target"] = 0
    with pytest.raises(ValueError, match="3 classes"):
        validate_transform(df)
