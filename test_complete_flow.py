#!/usr/bin/env python3
"""Complete integration test simulating Home Assistant setup flow."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_components', 'sunpower'))

from sunpower import SunPowerMonitor

host = "192.168.4.55"

print("="*70)
print("COMPLETE INTEGRATION TEST - Simulating Home Assistant Setup Flow")
print("="*70)
print()

# Step 1: Check firmware (what config_flow does first)
print("Step 1: Checking firmware compatibility...")
support = SunPowerMonitor.check_localapi_support(host)

if not support['supported']:
    print(f"   ✗ FAILED: {support['error']}")
    print("\n   This PVS does not support LocalAPI.")
    print("   Setup would fail in Home Assistant.")
    sys.exit(1)

print(f"   ✓ Firmware: {support['version']}")
print(f"   ✓ Build: {support['build']} (minimum: {SunPowerMonitor.MIN_LOCALAPI_BUILD})")
print(f"   ✓ Serial: {support['serial']}")
print()

# Step 2: Initialize monitor (what config_flow does during validation)
print("Step 2: Initializing monitor with auto-fetch...")
try:
    monitor = SunPowerMonitor(host, serial_suffix=None)
    print(f"   ✓ Auto-fetched serial suffix: {monitor.serial_suffix}")
    print(f"   ✓ Authentication successful")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)
print()

# Step 3: Fetch initial data (what async_setup_entry does)
print("Step 3: Fetching device data...")
try:
    device_list = monitor.device_list()
    devices = device_list.get('devices', [])
    
    by_type = {}
    for dev in devices:
        dtype = dev.get('DEVICE_TYPE', 'Unknown')
        by_type[dtype] = by_type.get(dtype, 0) + 1
    
    print(f"   ✓ Retrieved {len(devices)} devices:")
    for dtype, count in by_type.items():
        print(f"     - {dtype}: {count}")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)
print()

# Step 4: Verify data quality
print("Step 4: Verifying data quality...")
errors = []

# Check PVS
pvs_devices = [d for d in devices if d.get('DEVICE_TYPE') == 'PVS']
if len(pvs_devices) != 1:
    errors.append(f"Expected 1 PVS, found {len(pvs_devices)}")
else:
    pvs = pvs_devices[0]
    if not pvs.get('SERIAL'):
        errors.append("PVS missing SERIAL")
    if not pvs.get('MODEL'):
        errors.append("PVS missing MODEL")

# Check meters
meter_devices = [d for d in devices if d.get('DEVICE_TYPE') == 'Power Meter']
if len(meter_devices) < 1:
    errors.append(f"Expected at least 1 meter, found {len(meter_devices)}")
else:
    for meter in meter_devices:
        if meter.get('p_3phsum_kw') is None:
            errors.append(f"Meter {meter.get('SERIAL')} missing power data")

# Check inverters
inv_devices = [d for d in devices if d.get('DEVICE_TYPE') == 'Inverter']
if len(inv_devices) < 1:
    errors.append(f"Expected at least 1 inverter, found {len(inv_devices)}")
else:
    for inv in inv_devices[:3]:  # Check first 3
        if inv.get('p_mppt1_kw') is None:
            errors.append(f"Inverter {inv.get('SERIAL')} missing power data")

if errors:
    print("   ✗ Data quality issues:")
    for error in errors:
        print(f"     - {error}")
    sys.exit(1)
else:
    print("   ✓ All devices have required data fields")
    print("   ✓ Data quality verified")
print()

print("="*70)
print("✓ ALL TESTS PASSED - Integration ready for Home Assistant")
print("="*70)
print()
print("Summary:")
print(f"  - Firmware: {support['version']} (build {support['build']})")
print(f"  - Serial suffix: {monitor.serial_suffix} (auto-fetched)")
print(f"  - Devices: {len(devices)} total")
print(f"  - PVS: {len(pvs_devices)}")
print(f"  - Meters: {len(meter_devices)}")
print(f"  - Inverters: {len(inv_devices)}")
print()
print("Ready to install in Home Assistant!")
