# Upgrading from Legacy CGI to LocalAPI

## Overview

You currently have the legacy version of hass-sunpower installed that uses the old CGI endpoints (`/cgi-bin/dl_cgi`). This guide will help you upgrade to the LocalAPI version.

## Important: Backup First

Before upgrading, backup your current configuration:

1. **Export your current integration config**:
   - Go to **Settings** → **Devices & Services** → **SunPower**
   - Note down your current settings (host, update intervals, naming options)

2. **Backup entity customizations** (if any):
   - Check **Settings** → **Devices & Services** → **Entities**
   - Search for `sunpower` and note any customizations (friendly names, icons, etc.)

## Upgrade Steps

### Step 1: Remove Old Integration

1. **Delete the integration instance**:
   - Go to **Settings** → **Devices & Services**
   - Find **SunPower** integration
   - Click the **⋮** (three dots) → **Delete**
   - Confirm deletion

2. **Remove old integration files**:
   
   SSH into your Home Assistant or use Terminal add-on:
   ```bash
   # Backup the old version first (optional)
   cp -r /config/custom_components/sunpower /config/sunpower_backup_legacy
   
   # Remove old version
   rm -rf /config/custom_components/sunpower
   ```

### Step 2: Install LocalAPI Version

1. **Copy new integration files**:

   From your development machine:
   ```bash
   # Copy the entire sunpower directory to Home Assistant
   scp -r /Users/jimtooley/Documents/Projects/hass-sunpower/custom_components/sunpower \
         user@homeassistant:/config/custom_components/
   ```

   Or using File Editor add-on:
   - Create directory: `/config/custom_components/sunpower/`
   - Upload all files from your local `custom_components/sunpower/` directory
   - Ensure subdirectories are included (`translations/`)

2. **Verify file structure**:
   ```
   /config/custom_components/sunpower/
   ├── __init__.py
   ├── binary_sensor.py
   ├── config_flow.py
   ├── const.py
   ├── entity.py
   ├── manifest.json
   ├── sensor.py
   ├── strings.json
   ├── sunpower.py
   └── translations/
       └── en.json
   ```

### Step 3: Restart Home Assistant

- **Settings** → **System** → **Restart**
- Wait 1-2 minutes for full restart

### Step 4: Add LocalAPI Integration

1. **Add integration**:
   - **Settings** → **Devices & Services** → **+ Add Integration**
   - Search for **"SunPower"**
   - Click to configure

2. **Enter configuration**:
   - **Host**: `192.168.4.221` (same as before)
   - **Serial suffix**: Leave blank (uses hardcoded `A1651`)
   - **Use descriptive entity names**: ✅ (recommended - same as legacy)
   - **Use products in entity names**: ❌ (not recommended)

3. **Submit and wait**:
   - First setup may take 30-60 seconds
   - The PVS is slow to respond initially

### Step 5: Verify Migration

1. **Check devices**:
   - **Settings** → **Devices & Services** → **SunPower**
   - Should see: 1 PVS6, 2 Power Meters, 17 Inverters

2. **Check entity IDs**:
   - **Developer Tools** → **States**
   - Search for `sunpower`
   - Entity IDs should be similar to before (may have slight differences)

3. **Verify data**:
   - Click on a power sensor
   - Check **History** - should show recent data points
   - Values should match SunPower app

### Step 6: Restore Customizations

If you had customized entity names, icons, or other settings:

1. **Settings** → **Devices & Services** → **Entities**
2. Search for `sunpower`
3. Click each entity and restore:
   - Friendly names
   - Icons
   - Area assignments
   - Hidden status

### Step 7: Update Automations and Dashboards

1. **Check automations**:
   - **Settings** → **Automations & Scenes**
   - Search for any automations using SunPower entities
   - Update entity IDs if they changed

2. **Update Lovelace cards**:
   - Edit your dashboards
   - Update any cards referencing old entity IDs

3. **Update Energy Dashboard** (if configured):
   - **Settings** → **Dashboards** → **Energy**
   - Re-add solar production and consumption sensors if needed

## Key Differences: Legacy vs LocalAPI

| Feature | Legacy CGI | LocalAPI |
|---------|-----------|----------|
| **Protocol** | HTTP CGI | HTTP Varserver FCGI |
| **Authentication** | None | Basic Auth + Session Token |
| **Endpoint** | `/cgi-bin/dl_cgi?Command=DeviceList` | `/vars?match=...` |
| **Speed** | Slow (120s timeout) | Faster (30s timeout) |
| **Data Format** | Device list JSON | Variable key-value pairs |
| **Caching** | None | Server-side caching |
| **Configuration** | Host only | Host + Serial Suffix |
| **Entity IDs** | Same format | Same format (compatible) |

## What Changed

### New Features
- ✅ Faster response times with caching
- ✅ More efficient polling
- ✅ Session-based authentication
- ✅ Access to livedata aggregates

### Same Functionality
- ✅ Same entities created
- ✅ Same data fields
- ✅ Same update intervals
- ✅ Energy Dashboard compatible
- ✅ Entity ID format preserved

### Configuration Changes
- **New required field**: Serial suffix (last 5 of PVS serial)
  - Hardcoded as `A1651` in your version
  - Can leave blank in UI

## Troubleshooting

### "Cannot Connect" after upgrade

**Check**:
1. PVS is reachable: `ping 192.168.4.221`
2. LocalAPI is working: Run test script
   ```bash
   cd /Users/jimtooley/Documents/Projects/hass-sunpower
   source venv/bin/activate
   python test_localapi_simple.py 192.168.4.221
   ```

### Entity IDs changed

**Fix**:
1. Note the new entity IDs from **Developer Tools** → **States**
2. Update automations and dashboards manually
3. Or use **Settings** → **Devices & Services** → **Entities** → **Rename** to match old IDs

### Data shows "Unavailable"

**Fix**:
1. Check logs: **Settings** → **System** → **Logs**
2. Search for `sunpower` errors
3. Reload integration: **Settings** → **Devices & Services** → **SunPower** → **⋮** → **Reload**

### Want to rollback to legacy

**Restore backup**:
```bash
# Remove LocalAPI version
rm -rf /config/custom_components/sunpower

# Restore legacy backup
cp -r /config/sunpower_backup_legacy /config/custom_components/sunpower

# Restart Home Assistant
```

Then re-add the integration with just the host IP.

## Post-Upgrade Checklist

- [ ] Integration shows as "Connected" in Devices & Services
- [ ] All expected devices appear (1 PVS, 2 meters, 17 inverters)
- [ ] Entities show current values (not "Unavailable")
- [ ] History shows data updating every 120 seconds
- [ ] Energy Dashboard still works (if configured)
- [ ] Automations still trigger correctly
- [ ] Lovelace cards display data
- [ ] No errors in logs related to sunpower

## Performance Tuning

After upgrade, you can adjust polling intervals:

1. **Settings** → **Devices & Services** → **SunPower** → **Configure**
2. Adjust:
   - **Solar data update interval**: 120s (default) - can go as low as 60s
   - **Energy storage update interval**: 60s (not used for PV-only)

**Recommendation**: Keep at 120s or higher to avoid stressing the PVS.

## Support

If you encounter issues during upgrade:

1. **Enable debug logging**:
   Add to `configuration.yaml`:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.sunpower: debug
   ```

2. **Restart HA** and reproduce the issue

3. **Check logs** for detailed error messages

4. **Test LocalAPI directly** using the test scripts to verify PVS connectivity
