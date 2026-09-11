import pytest

from jarvis.pc_functions import StorageInfo, bytes_to_gib, describe_storage


def test_bytes_to_gib() -> None:
    assert bytes_to_gib(5 * 1024**3) == 5.0


def test_bytes_to_gib_rejects_negative_values() -> None:
    with pytest.raises(ValueError):
        bytes_to_gib(-1)


def test_describe_storage_rounds_to_one_decimal_place() -> None:
    storage = StorageInfo(
        free_bytes=int(12.34 * 1024**3),
        total_bytes=int(256.78 * 1024**3),
    )
    assert describe_storage(storage) == (
        "Ich meine das Windows-Systemlaufwerk C:. Dort sind 12.3 Gigabyte "
        "von insgesamt 256.8 Gigabyte frei."
    )
