import webclaw


def test_public_sdk_does_not_expose_retired_lead_features():
    methods = {"lead", "lead_batch", "get_lead_batch", "wait_for_lead_batch"}
    for client in (webclaw.Webclaw, webclaw.AsyncWebclaw):
        assert methods.isdisjoint(dir(client))
    assert not any(name.startswith("Lead") for name in dir(webclaw))

