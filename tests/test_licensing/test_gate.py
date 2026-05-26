from drama_shot_master import licensing
from drama_shot_master.licensing import manager


def test_requires_activation():
    S = manager.LicenseState
    assert manager.requires_activation(S.UNACTIVATED) is True
    assert manager.requires_activation(S.EXPIRED) is True
    assert manager.requires_activation(S.WRONG_MACHINE) is True
    assert manager.requires_activation(S.TAMPERED) is True
    assert manager.requires_activation(S.VALID) is False
