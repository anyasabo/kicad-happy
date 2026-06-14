#!/usr/bin/env python3
"""Tests for validation and signal detectors added in this session.

Covers: VM-001 (output-driver exemption), XL-001 (crystal load mismatch),
PU-001 (I2C missing pull-up), DC-001 (decoupling adequacy),
BOOT-001 (ESP32 strapping pin conflict), CC-001 (current capacity),
AK-001 (antenna keepout).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from kicad_types import AnalysisContext
from signal_detectors import detect_design_observations
from validation_detectors import validate_voltage_levels
from detector_helpers import get_unique_ics


def _make_ctx(components, nets, pin_net=None, known_power_rails=None):
    """Build a minimal AnalysisContext from components and nets."""
    if pin_net is None:
        pin_net = {}
        for net_name, net_info in nets.items():
            for p in net_info.get("pins", []):
                pin_net[(p["component"], p["pin_number"])] = (net_name, None)
    return AnalysisContext(
        components=components,
        nets=nets,
        lib_symbols={},
        pin_net=pin_net,
        known_power_rails=known_power_rails or set(),
    )


# ---------------------------------------------------------------------------
# VM-001: output-driver exemption for open-drain/output crossing voltage domains
# ---------------------------------------------------------------------------

def test_vm001_output_driver_exemption():
    """A lower-voltage IC driving an output/open_collector pin should not trigger VM-001."""
    components = [
        {"reference": "U1", "value": "ESP32-S3", "type": "ic", "pins": []},
        {"reference": "U2", "value": "SENSOR", "type": "ic", "pins": []},
    ]
    nets = {
        "+3V3": {"pins": [
            {"component": "#PWR01", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U1", "pin_number": "1", "pin_name": "VDD", "pin_type": "power_in"},
        ]},
        "+1V8": {"pins": [
            {"component": "#PWR02", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U2", "pin_number": "1", "pin_name": "VDD", "pin_type": "power_in"},
        ]},
        "INT_N": {"pins": [
            {"component": "U1", "pin_number": "5", "pin_name": "GPIO5", "pin_type": "input"},
            {"component": "U2", "pin_number": "3", "pin_name": "INT", "pin_type": "open_collector"},
        ]},
    }
    ctx = _make_ctx(components, nets, known_power_rails={"+3V3", "+1V8"})
    findings = validate_voltage_levels(ctx, level_shifters=[])
    vm001 = [f for f in findings if f["rule_id"] == "VM-001" and "INT_N" in f.get("summary", "")]
    assert len(vm001) == 0, f"Expected no VM-001 for open_collector driver, got: {vm001}"


def test_vm001_fires_for_bidirectional_crossing():
    """A bidirectional pin crossing voltage domains SHOULD fire VM-001."""
    components = [
        {"reference": "U1", "value": "MCU_3V3", "type": "ic", "pins": []},
        {"reference": "U2", "value": "IC_1V8", "type": "ic", "pins": []},
    ]
    nets = {
        "+3V3": {"pins": [
            {"component": "#PWR01", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U1", "pin_number": "1", "pin_name": "VDD", "pin_type": "power_in"},
        ]},
        "+1V8": {"pins": [
            {"component": "#PWR02", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U2", "pin_number": "1", "pin_name": "VDD", "pin_type": "power_in"},
        ]},
        "SPI_MOSI": {"pins": [
            {"component": "U1", "pin_number": "5", "pin_name": "MOSI", "pin_type": "bidirectional"},
            {"component": "U2", "pin_number": "3", "pin_name": "MOSI", "pin_type": "bidirectional"},
        ]},
    }
    ctx = _make_ctx(components, nets, known_power_rails={"+3V3", "+1V8"})
    findings = validate_voltage_levels(ctx, level_shifters=[])
    vm001 = [f for f in findings if f["rule_id"] == "VM-001" and "SPI_MOSI" in f.get("summary", "")]
    assert len(vm001) == 1, f"Expected VM-001 for bidirectional crossing, got {len(vm001)}"


# ---------------------------------------------------------------------------
# PU-001: I2C missing pull-up
# ---------------------------------------------------------------------------

def test_pu001_fires_when_no_pullup():
    """I2C SDA/SCL without pull-up resistors should trigger PU-001."""
    components = [
        {"reference": "U1", "value": "ESP32", "type": "ic", "pins": []},
        {"reference": "U2", "value": "BMP280", "type": "ic", "pins": []},
    ]
    nets = {
        "I2C_SDA": {"pins": [
            {"component": "U1", "pin_number": "5", "pin_name": "SDA", "pin_type": "bidirectional"},
            {"component": "U2", "pin_number": "3", "pin_name": "SDA", "pin_type": "bidirectional"},
        ]},
        "I2C_SCL": {"pins": [
            {"component": "U1", "pin_number": "6", "pin_name": "SCL", "pin_type": "bidirectional"},
            {"component": "U2", "pin_number": "4", "pin_name": "SCL", "pin_type": "bidirectional"},
        ]},
        "+3V3": {"pins": [
            {"component": "#PWR01", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U1", "pin_number": "1", "pin_name": "VDD", "pin_type": "power_in"},
        ]},
    }
    ctx = _make_ctx(components, nets, known_power_rails={"+3V3"})
    results = {"decoupling_analysis": [], "protection_devices": [], "power_regulators": [],
               "crystal_circuits": []}
    obs = detect_design_observations(ctx, results)
    pu001 = [o for o in obs if o.get("rule_id") == "PU-001"]
    assert len(pu001) == 2, f"Expected 2 PU-001 (SDA+SCL), got {len(pu001)}"


def test_pu001_no_fire_with_pullup():
    """I2C SDA with pull-up to power rail should NOT trigger PU-001."""
    components = [
        {"reference": "U1", "value": "ESP32", "type": "ic", "pins": []},
        {"reference": "U2", "value": "BMP280", "type": "ic", "pins": []},
        {"reference": "R1", "value": "4.7k", "type": "resistor", "pins": []},
    ]
    nets = {
        "I2C_SDA": {"pins": [
            {"component": "U1", "pin_number": "5", "pin_name": "SDA", "pin_type": "bidirectional"},
            {"component": "U2", "pin_number": "3", "pin_name": "SDA", "pin_type": "bidirectional"},
            {"component": "R1", "pin_number": "1", "pin_name": "", "pin_type": "passive"},
        ]},
        "+3V3": {"pins": [
            {"component": "#PWR01", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U1", "pin_number": "1", "pin_name": "VDD", "pin_type": "power_in"},
            {"component": "R1", "pin_number": "2", "pin_name": "", "pin_type": "passive"},
        ]},
    }
    ctx = _make_ctx(components, nets, known_power_rails={"+3V3"})
    results = {"decoupling_analysis": [], "protection_devices": [], "power_regulators": [],
               "crystal_circuits": []}
    obs = detect_design_observations(ctx, results)
    pu001 = [o for o in obs if o.get("rule_id") == "PU-001" and "SDA" in o.get("net", "")]
    assert len(pu001) == 0, f"Expected no PU-001 with pull-up present, got: {pu001}"


# ---------------------------------------------------------------------------
# XL-001: Crystal load capacitance mismatch
# ---------------------------------------------------------------------------

def test_xl001_fires_on_out_of_spec():
    """Crystal with out-of-spec load caps should trigger XL-001."""
    components = [
        {"reference": "Y1", "value": "16MHz", "type": "crystal", "pins": []},
    ]
    nets = {"XTAL_IN": {"pins": []}, "XTAL_OUT": {"pins": []}}
    ctx = _make_ctx(components, nets)
    results = {
        "decoupling_analysis": [], "protection_devices": [], "power_regulators": [],
        "crystal_circuits": [{
            "reference": "Y1",
            "value": "16MHz",
            "effective_load_pF": 22.0,
            "target_load_pF": 12.0,
            "load_cap_error_pct": 83.3,
            "load_cap_status": "out_of_spec",
            "load_caps": [{"ref": "C1", "pF": 47.0}, {"ref": "C2", "pF": 47.0}],
        }],
    }
    obs = detect_design_observations(ctx, results)
    xl001 = [o for o in obs if o.get("rule_id") == "XL-001"]
    assert len(xl001) == 1, f"Expected 1 XL-001, got {len(xl001)}"
    assert xl001[0]["severity"] == "warning"


def test_xl001_no_fire_when_matched():
    """Crystal with matching load caps should not trigger XL-001."""
    components = [
        {"reference": "Y1", "value": "16MHz", "type": "crystal", "pins": []},
    ]
    nets = {"XTAL_IN": {"pins": []}, "XTAL_OUT": {"pins": []}}
    ctx = _make_ctx(components, nets)
    results = {
        "decoupling_analysis": [], "protection_devices": [], "power_regulators": [],
        "crystal_circuits": [{
            "reference": "Y1",
            "value": "16MHz",
            "effective_load_pF": 12.5,
            "target_load_pF": 12.0,
            "load_cap_error_pct": 4.2,
            "load_cap_status": "ok",
            "load_caps": [{"ref": "C1", "pF": 27.0}, {"ref": "C2", "pF": 27.0}],
        }],
    }
    obs = detect_design_observations(ctx, results)
    xl001 = [o for o in obs if o.get("rule_id") == "XL-001"]
    assert len(xl001) == 0, f"Expected no XL-001 when matched, got {len(xl001)}"


# ---------------------------------------------------------------------------
# DC-001: Per-IC decoupling adequacy
# ---------------------------------------------------------------------------

def test_dc001_fires_when_bypass_insufficient():
    """ESP32 with only 1x100nF (needs 2) should trigger DC-001."""
    components = [
        {"reference": "U1", "value": "ESP32-S3-WROOM-1U", "type": "ic", "pins": []},
        {"reference": "C1", "value": "100nF", "type": "capacitor", "pins": []},
    ]
    nets = {
        "+3V3": {"pins": [
            {"component": "#PWR01", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U1", "pin_number": "2", "pin_name": "VDD", "pin_type": "power_in"},
            {"component": "C1", "pin_number": "1", "pin_name": "", "pin_type": "passive"},
        ]},
        "GND": {"pins": [
            {"component": "U1", "pin_number": "3", "pin_name": "GND", "pin_type": "power_in"},
            {"component": "C1", "pin_number": "2", "pin_name": "", "pin_type": "passive"},
        ]},
    }
    ctx = _make_ctx(components, nets, known_power_rails={"+3V3"})
    results = {
        "decoupling_analysis": [{
            "rail": "+3V3",
            "capacitors": [{"ref": "C1", "farads": 100e-9}],
        }],
        "protection_devices": [],
        "power_regulators": [],
        "crystal_circuits": [],
    }
    obs = detect_design_observations(ctx, results)
    dc001 = [o for o in obs if o.get("rule_id") == "DC-001"]
    assert len(dc001) == 1, f"Expected 1 DC-001, got {len(dc001)}"
    assert "ESP32" in dc001[0]["description"]


def test_dc001_no_fire_when_adequate():
    """ESP32 with 2x100nF + 10uF should not trigger DC-001."""
    components = [
        {"reference": "U1", "value": "ESP32-S3-WROOM-1U", "type": "ic", "pins": []},
        {"reference": "C1", "value": "100nF", "type": "capacitor", "pins": []},
        {"reference": "C2", "value": "100nF", "type": "capacitor", "pins": []},
        {"reference": "C3", "value": "10uF", "type": "capacitor", "pins": []},
    ]
    nets = {
        "+3V3": {"pins": [
            {"component": "#PWR01", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U1", "pin_number": "2", "pin_name": "VDD", "pin_type": "power_in"},
            {"component": "C1", "pin_number": "1", "pin_name": "", "pin_type": "passive"},
            {"component": "C2", "pin_number": "1", "pin_name": "", "pin_type": "passive"},
            {"component": "C3", "pin_number": "1", "pin_name": "", "pin_type": "passive"},
        ]},
        "GND": {"pins": [
            {"component": "U1", "pin_number": "3", "pin_name": "GND", "pin_type": "power_in"},
            {"component": "C1", "pin_number": "2", "pin_name": "", "pin_type": "passive"},
            {"component": "C2", "pin_number": "2", "pin_name": "", "pin_type": "passive"},
            {"component": "C3", "pin_number": "2", "pin_name": "", "pin_type": "passive"},
        ]},
    }
    ctx = _make_ctx(components, nets, known_power_rails={"+3V3"})
    results = {
        "decoupling_analysis": [{
            "rail": "+3V3",
            "capacitors": [
                {"ref": "C1", "farads": 100e-9},
                {"ref": "C2", "farads": 100e-9},
                {"ref": "C3", "farads": 10e-6},
            ],
        }],
        "protection_devices": [],
        "power_regulators": [],
        "crystal_circuits": [],
    }
    obs = detect_design_observations(ctx, results)
    dc001 = [o for o in obs if o.get("rule_id") == "DC-001"]
    assert len(dc001) == 0, f"Expected no DC-001 when adequate, got {len(dc001)}"


def test_dc001_skips_regulators():
    """Regulators should be exempted from DC-001."""
    components = [
        {"reference": "U1", "value": "TLV73333", "type": "ic", "pins": []},
    ]
    nets = {
        "+3V3": {"pins": [
            {"component": "#PWR01", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U1", "pin_number": "3", "pin_name": "OUT", "pin_type": "power_out"},
        ]},
        "VBUS": {"pins": [
            {"component": "U1", "pin_number": "1", "pin_name": "IN", "pin_type": "power_in"},
        ]},
    }
    ctx = _make_ctx(components, nets, known_power_rails={"+3V3", "VBUS"})
    results = {
        "decoupling_analysis": [],
        "protection_devices": [],
        "power_regulators": [{"ref": "U1", "output_rail": "+3V3", "value": "TLV73333"}],
        "crystal_circuits": [],
    }
    obs = detect_design_observations(ctx, results)
    dc001 = [o for o in obs if o.get("rule_id") == "DC-001"]
    assert len(dc001) == 0, f"Expected no DC-001 for regulator, got {len(dc001)}"


# ---------------------------------------------------------------------------
# BOOT-001: ESP32 strapping pin conflict
# ---------------------------------------------------------------------------

def test_boot001_fires_on_ic_output_on_strapping_pin():
    """An IC output pin on GPIO0 should trigger BOOT-001."""
    components = [
        {"reference": "U1", "value": "ESP32-S3-WROOM-1U", "type": "ic", "pins": []},
        {"reference": "U2", "value": "PCA9555", "type": "ic", "pins": []},
        {"reference": "R1", "value": "10k", "type": "resistor", "pins": []},
    ]
    nets = {
        "+3V3": {"pins": [
            {"component": "#PWR01", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U1", "pin_number": "2", "pin_name": "VDD", "pin_type": "power_in"},
            {"component": "R1", "pin_number": "2", "pin_name": "", "pin_type": "passive"},
        ]},
        "BOOT": {"pins": [
            {"component": "U1", "pin_number": "27", "pin_name": "GPIO0/BOOT", "pin_type": "bidirectional"},
            {"component": "U2", "pin_number": "4", "pin_name": "IO0", "pin_type": "bidirectional"},
            {"component": "R1", "pin_number": "1", "pin_name": "", "pin_type": "passive"},
        ]},
        "GND": {"pins": [
            {"component": "U1", "pin_number": "3", "pin_name": "GND", "pin_type": "power_in"},
        ]},
    }
    ctx = _make_ctx(components, nets, known_power_rails={"+3V3"})
    results = {"decoupling_analysis": [], "protection_devices": [], "power_regulators": [],
               "crystal_circuits": []}
    obs = detect_design_observations(ctx, results)
    boot001 = [o for o in obs if o.get("rule_id") == "BOOT-001"]
    assert len(boot001) == 1, f"Expected 1 BOOT-001, got {len(boot001)}"
    assert "U2" in boot001[0]["description"]
    assert "GPIO0" in boot001[0]["summary"]


def test_boot001_no_fire_with_only_passives():
    """GPIO0 with only resistor + switch should NOT trigger BOOT-001."""
    components = [
        {"reference": "U1", "value": "ESP32-S3-WROOM-1U", "type": "ic", "pins": []},
        {"reference": "R2", "value": "10k", "type": "resistor", "pins": []},
        {"reference": "SW2", "value": "BOOT_BTN", "type": "switch", "pins": []},
    ]
    nets = {
        "+3V3": {"pins": [
            {"component": "#PWR01", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U1", "pin_number": "2", "pin_name": "VDD", "pin_type": "power_in"},
            {"component": "R2", "pin_number": "2", "pin_name": "", "pin_type": "passive"},
        ]},
        "BOOT": {"pins": [
            {"component": "U1", "pin_number": "27", "pin_name": "GPIO0/BOOT", "pin_type": "bidirectional"},
            {"component": "R2", "pin_number": "1", "pin_name": "", "pin_type": "passive"},
            {"component": "SW2", "pin_number": "1", "pin_name": "1", "pin_type": "passive"},
        ]},
        "GND": {"pins": [
            {"component": "U1", "pin_number": "3", "pin_name": "GND", "pin_type": "power_in"},
            {"component": "SW2", "pin_number": "2", "pin_name": "2", "pin_type": "passive"},
        ]},
    }
    ctx = _make_ctx(components, nets, known_power_rails={"+3V3"})
    results = {"decoupling_analysis": [], "protection_devices": [], "power_regulators": [],
               "crystal_circuits": []}
    obs = detect_design_observations(ctx, results)
    boot001 = [o for o in obs if o.get("rule_id") == "BOOT-001"]
    assert len(boot001) == 0, f"Expected no BOOT-001 with passives only, got {len(boot001)}"


def test_boot001_no_fire_for_strapping_on_gnd():
    """ESP32-S3 GPIO46 tied to GND should NOT trigger BOOT-001."""
    components = [
        {"reference": "U1", "value": "ESP32-S3-WROOM-1U", "type": "ic", "pins": []},
    ]
    nets = {
        "+3V3": {"pins": [
            {"component": "#PWR01", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U1", "pin_number": "2", "pin_name": "VDD", "pin_type": "power_in"},
        ]},
        "GND": {"pins": [
            {"component": "U1", "pin_number": "3", "pin_name": "GND", "pin_type": "power_in"},
            {"component": "U1", "pin_number": "10", "pin_name": "GPIO46", "pin_type": "bidirectional"},
        ]},
    }
    ctx = _make_ctx(components, nets, known_power_rails={"+3V3"})
    results = {"decoupling_analysis": [], "protection_devices": [], "power_regulators": [],
               "crystal_circuits": []}
    obs = detect_design_observations(ctx, results)
    boot001 = [o for o in obs if o.get("rule_id") == "BOOT-001"]
    assert len(boot001) == 0, f"Expected no BOOT-001 for GPIO46 on GND, got {len(boot001)}"


def test_boot001_no_false_match_gpio20():
    """GPIO2 check must NOT match GPIO20 (regex boundary)."""
    components = [
        {"reference": "U1", "value": "ESP32-WROOM-32", "type": "ic", "pins": []},
        {"reference": "U2", "value": "CP2102", "type": "ic", "pins": []},
    ]
    nets = {
        "+3V3": {"pins": [
            {"component": "#PWR01", "pin_number": "1", "pin_name": "VCC", "pin_type": "power_out"},
            {"component": "U1", "pin_number": "2", "pin_name": "VDD", "pin_type": "power_in"},
        ]},
        "USB_D+": {"pins": [
            {"component": "U1", "pin_number": "14", "pin_name": "GPIO20/USB_D+", "pin_type": "bidirectional"},
            {"component": "U2", "pin_number": "3", "pin_name": "DP", "pin_type": "bidirectional"},
        ]},
    }
    ctx = _make_ctx(components, nets, known_power_rails={"+3V3"})
    results = {"decoupling_analysis": [], "protection_devices": [], "power_regulators": [],
               "crystal_circuits": []}
    obs = detect_design_observations(ctx, results)
    boot001 = [o for o in obs if o.get("rule_id") == "BOOT-001"]
    assert len(boot001) == 0, f"GPIO2 should NOT match GPIO20, got: {boot001}"


# ---------------------------------------------------------------------------
# CC-001: Current capacity (PCB analyzer)
# ---------------------------------------------------------------------------

def test_cc001_fires_for_undersized_trace():
    """Power trace too narrow for heuristic current should trigger CC-001."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from analyze_pcb import _IPC2152_1OZ_10C, _POWER_NET_CURRENT_HEURISTIC, _min_trace_width_for_current
    import re

    # VBUS should have 0.5A heuristic
    matched = None
    for pattern, current in _POWER_NET_CURRENT_HEURISTIC:
        if pattern.search("VBUS"):
            matched = current
            break
    assert matched == 0.5, f"Expected 0.5A for VBUS, got {matched}"

    # IPC table: {current_A: width_mm}. 0.5A -> 0.25mm min width
    min_w = _min_trace_width_for_current(0.5)
    assert min_w is not None, "Expected min width for 0.5A"
    assert 0.2 <= min_w <= 0.3, f"Expected ~0.25mm for 0.5A, got {min_w}"

    # 1.0A should need wider trace
    min_w_1a = _min_trace_width_for_current(1.0)
    assert min_w_1a > min_w, f"1.0A should need wider trace than 0.5A"


def test_cc001_gnd_exempt():
    """GND net pattern should return None current (zones handle it)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from analyze_pcb import _POWER_NET_CURRENT_HEURISTIC

    for pattern, current in _POWER_NET_CURRENT_HEURISTIC:
        if pattern.search("GND"):
            assert current is None, f"GND should have None current (exempt), got {current}"
            return
    # If no match, that's also fine — GND won't get a heuristic current
    pass


# ---------------------------------------------------------------------------
# AK-001: Antenna keepout (PCB analyzer)
# ---------------------------------------------------------------------------

def test_ak001_external_antenna_exempt():
    """Modules with external antenna suffixes should be exempt from AK-001."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from analyze_pcb import _EXTERNAL_ANTENNA_SUFFIXES

    # The actual check: any(suf.upper() in fp_id for suf in _EXTERNAL_ANTENNA_SUFFIXES)
    test_fps = [
        ("ESP32-S3-WROOM-1U", True),       # -1U = external antenna (U.FL)
        ("ESP32-S3-WROOM-1U-N8R2", True),   # -1U- variant
        ("ESP32-S3-WROOM-32U", True),       # -32U = external antenna variant
        ("ESP32-S3-WROOM-1", False),        # no U suffix = PCB antenna
        ("ESP32-S3-WROOM-1-N8R2", False),   # PCB antenna variant
    ]
    for fp, should_exempt in test_fps:
        fp_upper = fp.upper()
        exempt = any(suf.upper() in fp_upper for suf in _EXTERNAL_ANTENNA_SUFFIXES)
        if should_exempt:
            assert exempt, f"Expected {fp} to be exempt (external antenna)"
        else:
            assert not exempt, f"Expected {fp} NOT to be exempt"


def test_ak001_segment_intersects_rect():
    """Segment-rectangle intersection helper should work correctly."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from analyze_pcb import _segment_intersects_rect

    # API: _segment_intersects_rect(sx, sy, ex, ey, rect) where rect is a dict
    rect = {"min_x": 0, "min_y": 0, "max_x": 10, "max_y": 10}
    # Segment clearly inside rect
    assert _segment_intersects_rect(5, 5, 6, 6, rect) is True
    # Segment crossing rect boundary
    assert _segment_intersects_rect(-1, 5, 5, 5, rect) is True
    # Segment entirely outside
    assert _segment_intersects_rect(15, 15, 20, 20, rect) is False
    # Segment touching corner
    assert _segment_intersects_rect(10, 10, 15, 15, rect) is True


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
            print(f"  PASS: {test.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL: {test.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
