import numpy as np
import pytest
from agccActor import database


def test_getNextAgcExposureId(mock_opdb):
    mock_opdb.query_scalar.return_value = 101
    next_id = database.getNextAgcExposureId(db=mock_opdb)

    assert next_id == 101
    mock_opdb.query_scalar.assert_called_once_with(
        "SELECT MAX(agc_exposure_id) + 1 AS next_id FROM agc_exposure"
    )


def test_getNextAgcExposureId_empty_table(mock_opdb):
    """When the table is empty the query returns NULL; expect 0."""
    mock_opdb.query_scalar.return_value = None
    next_id = database.getNextAgcExposureId(db=mock_opdb)

    assert next_id == 0


def test_writeVisitToDB(mock_opdb):
    database.writeVisitToDB(12345, db=mock_opdb)
    mock_opdb.insert_kw.assert_called_once_with(
        "pfs_visit", pfs_visit_id=12345, pfs_visit_description=""
    )


def test_writeExposureToDB(mock_opdb):
    mock_opdb.query_series.side_effect = [
        {"altitude": 45.0, "azimuth": 180.0, "insrot": 0.0, "adc_pa": 10.0, "m2_pos3": 1.2},
        {"outside_temperature": 2.5, "outside_pressure": 600.0, "outside_humidity": 15.0},
    ]

    database.writeExposureToDB(12345, 101, 2.0, db=mock_opdb)

    assert mock_opdb.insert_kw.called
    args, kwargs = mock_opdb.insert_kw.call_args
    assert args[0] == "agc_exposure"
    assert kwargs["pfs_visit_id"] == 12345
    assert kwargs["agc_exposure_id"] == 101
    assert kwargs["agc_exptime"] == 2.0
    assert kwargs["altitude"] == 45.0
    assert kwargs["outside_temperature"] == 2.5


def test_writeExposureToDB_no_tel_status(mock_opdb):
    """Missing telescope status must raise RuntimeError."""
    mock_opdb.query_series.return_value = None

    with pytest.raises(RuntimeError, match="No telescope status"):
        database.writeExposureToDB(12345, 101, 2.0, db=mock_opdb)


def test_writeExposureToDB_no_obs_cond(mock_opdb):
    """Missing environmental conditions must raise RuntimeError."""
    mock_opdb.query_series.side_effect = [
        {"altitude": 45.0, "azimuth": 180.0, "insrot": 0.0, "adc_pa": 10.0, "m2_pos3": 1.2},
        None,
    ]

    with pytest.raises(RuntimeError, match="No environmental conditions"):
        database.writeExposureToDB(12345, 101, 2.0, db=mock_opdb)


def test_writeExposureToDB_db_insert_failure(mock_opdb):
    """A database insert error must propagate out of writeExposureToDB."""
    mock_opdb.query_series.side_effect = [
        {"altitude": 45.0, "azimuth": 180.0, "insrot": 0.0, "adc_pa": 10.0, "m2_pos3": 1.2},
        {"outside_temperature": 2.5, "outside_pressure": 600.0, "outside_humidity": 15.0},
    ]
    mock_opdb.insert_kw.side_effect = RuntimeError("DB write failed")

    with pytest.raises(RuntimeError, match="DB write failed"):
        database.writeExposureToDB(12345, 101, 2.0, db=mock_opdb)


def _spot_dtype():
    return np.dtype([
        ("image_moment_00_pix", "f4"),
        ("centroid_x_pix", "f4"),
        ("centroid_y_pix", "f4"),
        ("central_image_moment_20_pix", "f4"),
        ("central_image_moment_11_pix", "f4"),
        ("central_image_moment_02_pix", "f4"),
        ("peak_pixel_x_pix", "i2"),
        ("peak_pixel_y_pix", "i2"),
        ("peak_intensity", "f4"),
        ("background", "f4"),
        ("estimated_magnitude", "f4"),
        ("flags", "i2"),
    ])


def test_writeCentroidsToDB(mock_opdb):
    result = np.zeros(3, dtype=_spot_dtype())
    result["centroid_x_pix"] = [100.0, 200.0, 300.0]
    result["centroid_y_pix"] = [10.0, 20.0, 30.0]

    database.writeCentroidsToDB(result, 12345, 101, 1, db=mock_opdb)

    assert mock_opdb.insert_dataframe.called
    args, kwargs = mock_opdb.insert_dataframe.call_args
    assert args[0] == "agc_data"
    df = kwargs["df"]
    assert len(df) == 3
    assert list(df["agc_exposure_id"]) == [101, 101, 101]
    assert list(df["agc_camera_id"]) == [1, 1, 1]
    assert list(df["spot_id"]) == [0, 1, 2]


def test_writeCentroidsToDB_empty_result(mock_opdb):
    """Zero-row result should still call insert_dataframe with an empty frame."""
    result = np.zeros(0, dtype=_spot_dtype())

    database.writeCentroidsToDB(result, 12345, 101, 1, db=mock_opdb)

    assert mock_opdb.insert_dataframe.called
    _, kwargs = mock_opdb.insert_dataframe.call_args
    assert len(kwargs["df"]) == 0


def test_writeCentroidsToDB_column_mapping(mock_opdb):
    """All expected columns must be present in the DataFrame sent to the DB."""
    result = np.zeros(2, dtype=_spot_dtype())
    result["centroid_x_pix"] = [150.0, 250.0]

    database.writeCentroidsToDB(result, 99, 42, 3, db=mock_opdb)

    _, kwargs = mock_opdb.insert_dataframe.call_args
    df = kwargs["df"]
    expected_cols = {
        "agc_exposure_id", "agc_camera_id", "spot_id",
        "centroid_x_pix", "centroid_y_pix", "image_moment_00_pix",
    }
    assert expected_cols.issubset(set(df.columns))
    assert (df["centroid_x_pix"] == [150.0, 250.0]).all()



# ---------------------------------------------------------------------------
# Versions written to agc_exposure
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_versions(monkeypatch):
    """Stand in for ``pfs.utils.versions.getVersion``; returns the products it knows and its calls."""
    products = {"ics_agccActor": "2.3.0", "pfs_instdata": "1.8.121-2-gabc1234"}
    calls = []

    def getVersion(product):
        calls.append(product)
        try:
            return products[product]
        except KeyError:
            raise RuntimeError(f"Could not determine version for product: {product}") from None

    monkeypatch.setattr(database.versions, "getVersion", getVersion)
    database.getProductVersion.cache_clear()
    yield products, calls
    database.getProductVersion.cache_clear()


def test_getProductVersion(fake_versions):
    assert database.getProductVersion("ics_agccActor") == "2.3.0"
    assert database.getProductVersion("pfs_instdata") == "1.8.121-2-gabc1234"


def test_getProductVersion_lookup_failure(fake_versions):
    """A failing lookup is reported as unknown and never raised."""
    assert database.getProductVersion("ics_notAnActor") == "unknown"


def test_getProductVersion_is_never_the_legacy_literal(fake_versions):
    """A version that reads "git" would mark new exposures as old ones: it is recorded as unknown."""
    products, _ = fake_versions
    products["ics_agccActor"] = "git"
    assert database.getProductVersion("ics_agccActor") == "unknown"
    # Negative control: a version that only contains it is kept.
    products["pfs_instdata"] = "git-1.8.121"
    assert database.getProductVersion("pfs_instdata") == "git-1.8.121"


def test_getProductVersion_looked_up_once(fake_versions):
    """Found or not, a product is looked up once per process."""
    _, calls = fake_versions
    for _ in range(3):
        assert database.getProductVersion("ics_agccActor") == "2.3.0"
        assert database.getProductVersion("ics_notAnActor") == "unknown"
    assert calls == ["ics_agccActor", "ics_notAnActor"]


def test_writeExposureToDB_writes_versions(mock_opdb, fake_versions):
    """The exposure row carries the actor and pfs_instdata versions."""
    mock_opdb.query_series.side_effect = [
        {"altitude": 45.0, "azimuth": 180.0, "insrot": 0.0, "adc_pa": 10.0, "m2_pos3": 1.2},
        {"outside_temperature": 2.5, "outside_pressure": 600.0, "outside_humidity": 15.0},
    ]

    database.writeExposureToDB(12345, 101, 2.0, db=mock_opdb)

    _, kwargs = mock_opdb.insert_kw.call_args
    assert kwargs["version_actor"] == "2.3.0"
    assert kwargs["version_instdata"] == "1.8.121-2-gabc1234"
    # Negative control: rows from before the versions were recorded hold the literal "git",
    # which is how readers tell the two apart.
    assert kwargs["version_actor"] != "git"
    assert kwargs["version_instdata"] != "git"
