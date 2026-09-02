from fpga_lab.peripherals.manifest import parse_manifest


def test_required_terminals_preset_can_drop_optional_pins():
    spec = parse_manifest({
        "id": "demo",
        "label": "Demo",
        "category": "output",
        "simulation": {"class": "gpio_sampled"},
        "terminals": [
            {"name": "a", "direction": "output", "required": True},
            {"name": "b", "direction": "output", "required": False},
        ],
        "properties": {
            "mode": {
                "type": "enum",
                "values": ["small", "full"],
                "default": "small",
                "presets": {
                    "small": {"required_terminals": ["a"]},
                    "full": {"required_terminals": ["a", "b"]},
                },
            }
        },
        "visual": {"renderer": "lamp", "size": [10, 10]},
    })
    assert spec.required_terminals({"mode": "small"}) == ("a",)
    assert spec.required_terminals({"mode": "full"}) == ("a", "b")
    assert spec.required_terminals({}) == ("a",)
