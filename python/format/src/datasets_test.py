from etils import epath
from format.src import datasets
from format.src import errors
import pytest


# End-to-end tests on real data. The data is in `tests/end-to-end/*.json`.
@pytest.mark.parametrize(
    ["filename", "error"],
    [
        # Metadata.
        [
            "metadata_missing_property_name.json",
            'Property "https://schema.org/name" is mandatory, but does not exist.',
        ],
        [
            "metadata_bad_type.json",
            'Node should have an attribute `"@type" in',
        ],
        # Distribution.
        [
            "distribution_missing_property_content_url.json",
            'Property "https://schema.org/contentUrl" is mandatory, but does not exist.',
        ],
        [
            "distribution_bad_type.json",
            'Node should have an attribute `"@type" in',
        ],
        # Record set.
        [
            "recordset_missing_property_name.json",
            'Property "https://schema.org/name" is mandatory, but does not exist.',
        ],
        [
            "recordset_bad_type.json",
            'Node should have an attribute `"@type" in',
        ],
        # ML field.
        [
            "mlfield_missing_property_name.json",
            'Property "https://schema.org/name" is mandatory, but does not exist.',
        ],
        [
            "mlfield_bad_type.json",
            'Node should have an attribute `"@type" in',
        ],
    ],
)
def test_check_graph(filename, error):
    base_path = epath.Path(__file__).parent / "tests/graphs"
    with pytest.raises(errors.ValidationError, match=error):
        datasets.Dataset(base_path / filename)
