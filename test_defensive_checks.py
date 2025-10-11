#!/usr/bin/env python3
"""Test defensive checks in data transformation functions."""

import sys
import os
import time

# We'll copy the functions here to test them without HA dependencies
BATTERY_DEVICE_TYPE = "Battery"
ESS_DEVICE_TYPE = "ESS"
HUBPLUS_DEVICE_TYPE = "HubPlus"
PVS_DEVICE_TYPE = "PVS"
INVERTER_DEVICE_TYPE = "Inverter"
METER_DEVICE_TYPE = "Power Meter"
SUNVAULT_DEVICE_TYPE = "SunVault"

class MockLogger:
    def warning(self, msg):
        print(f"   [WARNING] {msg}")

_LOGGER = MockLogger()

# Copy the functions from __init__.py
def create_vmeter(data):
    # Create a virtual 'METER' that uses the sum of inverters
    kwh = 0.0
    kw = 0.0
    amps = 0.0
    freq = []
    volts = []
    state = "working"
    for _serial, inverter in data.get(INVERTER_DEVICE_TYPE, {}).items():
        if "STATE" in inverter and inverter["STATE"] != "working":
            state = inverter["STATE"]
        kwh += float(inverter.get("ltea_3phsum_kwh", "0"))
        kw += float(inverter.get("p_mppt1_kw", "0"))
        amps += float(inverter.get("i_3phsum_a", "0"))
        if "freq_hz" in inverter:
            freq.append(float(inverter["freq_hz"]))
        if "vln_3phavg_v" in inverter:
            volts.append(float(inverter["vln_3phavg_v"]))

    freq_avg = sum(freq) / len(freq) if len(freq) > 0 else None
    volts_avg = sum(volts) / len(volts) if len(volts) > 0 else None

    # Check if PVS device exists before trying to access it
    if PVS_DEVICE_TYPE not in data or not data[PVS_DEVICE_TYPE]:
        _LOGGER.warning("PVS device not found in data, skipping virtual meter creation")
        return data
    
    pvs_serial = next(iter(data[PVS_DEVICE_TYPE]))  # only one PVS
    vmeter_serial = f"{pvs_serial}pv"
    data.setdefault(METER_DEVICE_TYPE, {})[vmeter_serial] = {
        "SERIAL": vmeter_serial,
        "TYPE": "PVS-METER-P",
        "STATE": state,
        "MODEL": "Virtual",
        "DESCR": f"Power Meter {vmeter_serial}",
        "DEVICE_TYPE": "Power Meter",
        "interface": "virtual",
        "SWVER": "1.0",
        "HWVER": "Virtual",
        "origin": "virtual",
        "net_ltea_3phsum_kwh": kwh,
        "p_3phsum_kw": kw,
        "freq_hz": freq_avg,
        "i_a": amps,
        "v12_v": volts_avg,
    }
    return data

def convert_sunpower_data(sunpower_data):
    """Convert PVS data into indexable format data[device_type][serial]"""
    data = {}
    for device in sunpower_data["devices"]:
        data.setdefault(device["DEVICE_TYPE"], {})[device["SERIAL"]] = device

    create_vmeter(data)

    return data

print("="*70)
print("DEFENSIVE CHECKS TEST")
print("="*70)
print()

# Test 1: create_vmeter with missing PVS
print("Test 1: create_vmeter with missing PVS device...")
test_data = {
    "Inverter": {
        "INV001": {
            "SERIAL": "INV001",
            "STATE": "working",
            "ltea_3phsum_kwh": "100.5",
            "p_mppt1_kw": "5.2",
            "i_3phsum_a": "10.5",
            "freq_hz": "60.0",
            "vln_3phavg_v": "240.0"
        }
    }
    # No PVS device!
}

result = create_vmeter(test_data)
if result == test_data and "Power Meter" not in result:
    print("   ✓ PASS: Returns early without creating virtual meter")
else:
    print("   ✗ FAIL: Should return early without PVS")
    sys.exit(1)
print()

# Test 2: create_vmeter with empty PVS
print("Test 2: create_vmeter with empty PVS device dict...")
test_data = {
    "PVS": {},  # Empty!
    "Inverter": {
        "INV001": {
            "SERIAL": "INV001",
            "STATE": "working",
            "ltea_3phsum_kwh": "100.5",
            "p_mppt1_kw": "5.2",
            "i_3phsum_a": "10.5",
        }
    }
}

result = create_vmeter(test_data)
if result == test_data and "Power Meter" not in result:
    print("   ✓ PASS: Returns early with empty PVS")
else:
    print("   ✗ FAIL: Should return early with empty PVS")
    sys.exit(1)
print()

# Test 3: create_vmeter with valid PVS
print("Test 3: create_vmeter with valid PVS device...")
test_data = {
    "PVS": {
        "PVS123": {
            "SERIAL": "PVS123",
            "MODEL": "PVS6",
            "STATE": "working"
        }
    },
    "Inverter": {
        "INV001": {
            "SERIAL": "INV001",
            "STATE": "working",
            "ltea_3phsum_kwh": "100.5",
            "p_mppt1_kw": "5.2",
            "i_3phsum_a": "10.5",
            "freq_hz": "60.0",
            "vln_3phavg_v": "240.0"
        }
    }
}

result = create_vmeter(test_data)
if "Power Meter" in result and "PVS123pv" in result["Power Meter"]:
    vmeter = result["Power Meter"]["PVS123pv"]
    if vmeter["net_ltea_3phsum_kwh"] == 100.5 and vmeter["p_3phsum_kw"] == 5.2:
        print("   ✓ PASS: Virtual meter created with correct data")
    else:
        print("   ✗ FAIL: Virtual meter has incorrect data")
        sys.exit(1)
else:
    print("   ✗ FAIL: Virtual meter not created")
    sys.exit(1)
print()

# Test 4: convert_sunpower_data with valid data
print("Test 5: convert_sunpower_data with valid device list...")
sunpower_data = {
    "devices": [
        {"SERIAL": "PVS123", "DEVICE_TYPE": "PVS", "MODEL": "PVS6"},
        {"SERIAL": "INV001", "DEVICE_TYPE": "Inverter", "STATE": "working", "ltea_3phsum_kwh": "100.5", "p_mppt1_kw": "5.2", "i_3phsum_a": "10.5"}
    ]
}

result = convert_sunpower_data(sunpower_data)
if "PVS" in result and "Inverter" in result and "Power Meter" in result:
    print("   ✓ PASS: Converts device list and creates virtual meter")
else:
    print("   ✗ FAIL: Should convert device list properly")
    print(f"   Result keys: {result.keys()}")
    sys.exit(1)
print()

print("="*70)
print("✓ ALL DEFENSIVE CHECKS TESTS PASSED")
print("="*70)
print()
print("The integration will handle missing device data gracefully.")
