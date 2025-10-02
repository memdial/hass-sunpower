"""SunPower PVS LocalAPI client and adapter to legacy schema."""

import os
import requests
import simplejson
from urllib.parse import urlencode

try:
    # Suppress TLS warnings when verify=False
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:  # pragma: no cover - optional
    pass


class ConnectionException(Exception):
    """Any failure to connect to sunpower PVS"""


class ParseException(Exception):
    """Any failure to connect to sunpower PVS"""


class SunPowerMonitor:
    """Client for SunPower PVS LocalAPI (Varserver FCGI), adapted to legacy schema."""

    # Optional hardcoded serial suffix fallback. Set this to your last 5 chars if you prefer to hardcode.
    # This value is only used if no serial suffix is supplied via constructor or environment variable.
    HARDCODED_SERIAL_SUFFIX = "A1651"
    
    # Minimum firmware build number that supports LocalAPI
    MIN_LOCALAPI_BUILD = 61840

    def __init__(self, host, serial_suffix: str | None = None):
        """Initialize LocalAPI client.

        - host: IP or hostname of the PVS
        - serial_suffix: last 5 characters of the PVS serial (password for ssm_owner)
        """
        self.host = host
        self.base = f"http://{host}"
        self.session = requests.Session()
        self.timeout = 30
        
        # Try to auto-fetch serial suffix from supervisor/info if not provided
        if not serial_suffix or not serial_suffix.strip():
            serial_suffix = self._fetch_serial_suffix()
        
        # Resolve serial suffix: provided -> auto-fetched -> env var -> hardcoded
        env_suffix = os.environ.get("SUNPOWER_SERIAL_SUFFIX", "").strip()
        hardcoded = self.HARDCODED_SERIAL_SUFFIX.strip()
        resolved = (serial_suffix or "").strip() or env_suffix or hardcoded
        
        if not resolved:
            raise ConnectionException(
                "Missing serial suffix. Provide last 5 of PVS serial via UI, env SUNPOWER_SERIAL_SUFFIX, or set HARDCODED_SERIAL_SUFFIX in sunpower.py",
            )
        
        self.serial_suffix = resolved
        self._login()
    
    def _fetch_serial_suffix(self) -> str:
        """Attempt to fetch serial number from supervisor/info endpoint.
        
        Returns last 5 characters of serial, or empty string if fetch fails.
        """
        try:
            resp = self.session.get(
                f"{self.base}/cgi-bin/dl_cgi/supervisor/info",
                timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                if "supervisor" in data and "SERIAL" in data["supervisor"]:
                    serial = data["supervisor"]["SERIAL"]
                    if len(serial) >= 5:
                        return serial[-5:]
        except Exception:
            pass  # Silently fail, will use fallback
        return ""
    
    @staticmethod
    def check_localapi_support(host: str, timeout: int = 30) -> dict:
        """Check if PVS supports LocalAPI by querying supervisor/info.
        
        Returns dict with:
        - supported: bool
        - build: int or None
        - version: str or None
        - serial: str or None
        - error: str or None
        """
        result = {
            "supported": False,
            "build": None,
            "version": None,
            "serial": None,
            "error": None
        }
        
        try:
            resp = requests.get(
                f"http://{host}/cgi-bin/dl_cgi/supervisor/info",
                timeout=timeout
            )
            
            if resp.status_code != 200:
                result["error"] = f"HTTP {resp.status_code}"
                return result
            
            data = resp.json()
            if "supervisor" not in data:
                result["error"] = "Invalid response format"
                return result
            
            supervisor = data["supervisor"]
            build = supervisor.get("BUILD")
            version = supervisor.get("SWVER")
            serial = supervisor.get("SERIAL")
            
            result["build"] = build
            result["version"] = version
            result["serial"] = serial
            
            # Check if firmware supports LocalAPI
            if build and build >= SunPowerMonitor.MIN_LOCALAPI_BUILD:
                result["supported"] = True
            else:
                result["error"] = f"Firmware build {build} is too old. LocalAPI requires build {SunPowerMonitor.MIN_LOCALAPI_BUILD}+"
            
            return result
            
        except requests.exceptions.RequestException as e:
            result["error"] = f"Connection failed: {e}"
            return result
        except Exception as e:
            result["error"] = f"Unexpected error: {e}"
            return result

    def _login(self):
        """Authenticate to LocalAPI, storing session token."""
        import base64
        
        # Build Basic auth header (lowercase "basic")
        token = base64.b64encode(f"ssm_owner:{self.serial_suffix}".encode("utf-8")).decode("ascii")
        auth_header = f"basic {token}"
        
        try:
            resp = self.session.get(
                f"{self.base}/auth?login",
                headers={"Authorization": auth_header},
                timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
            
            # Extract session token and store it for subsequent requests
            session_token = data.get("session")
            if not session_token:
                raise ParseException(f"No session token in response: {data}")
            
            # Store session token in session headers for all future requests
            self.session.headers.update({"Cookie": f"session={session_token}"})
            
        except requests.exceptions.RequestException as error:
            raise ConnectionException from error
        except simplejson.errors.JSONDecodeError as error:
            raise ParseException from error

    def _vars(self, *, names=None, match=None, cache=None, fmt_obj=True):
        """Query /vars endpoint.

        names: list of exact variable names
        match: substring match
        cache: cache id to create or query
        fmt_obj: if True, request fmt=obj to get object mapping
        """
        params = {}
        if names:
            params["name"] = ",".join(names)
        if match:
            params["match"] = match
        if cache:
            params["cache"] = cache
        if fmt_obj:
            params["fmt"] = "obj"
        
        try:
            resp = self.session.get(f"{self.base}/vars", params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return data
        except requests.exceptions.RequestException as error:
            raise ConnectionException from error
        except (simplejson.errors.JSONDecodeError, ValueError) as error:
            raise ParseException from error

    def _fetch_meters(self):
        # Fetch all meter variables and group by device index
        data = self._vars(match="meter", cache="mdata", fmt_obj=True)
        # Group by meter index (e.g., /sys/devices/meter/0/field -> meter 0)
        meters = {}
        for var_path, value in data.items():
            if "/sys/devices/meter/" in var_path:
                parts = var_path.split("/")
                if len(parts) >= 5:
                    meter_idx = parts[4]  # e.g., "0", "1"
                    field = parts[5] if len(parts) > 5 else None
                    if field:
                        meter_key = f"/sys/devices/meter/{meter_idx}"
                        if meter_key not in meters:
                            meters[meter_key] = {}
                        meters[meter_key][field] = value
        return meters

    def _fetch_inverters(self):
        # Fetch all inverter variables and group by device index
        data = self._vars(match="inverter", cache="idata", fmt_obj=True)
        inverters = {}
        for var_path, value in data.items():
            if "/sys/devices/inverter/" in var_path:
                parts = var_path.split("/")
                if len(parts) >= 5:
                    inv_idx = parts[4]
                    field = parts[5] if len(parts) > 5 else None
                    if field:
                        inv_key = f"/sys/devices/inverter/{inv_idx}"
                        if inv_key not in inverters:
                            inverters[inv_key] = {}
                        inverters[inv_key][field] = value
        return inverters

    def _fetch_sysinfo(self):
        # Use match instead of name query
        data = self._vars(match="info", cache="sysinfo", fmt_obj=True)
        return data

    @staticmethod
    def _key(obj, old_key, new_key, transform=None):
        if old_key in obj:
            val = obj[old_key]
            obj[new_key] = transform(val) if transform else val

    def device_list(self):
        """Return legacy-like DeviceList using LocalAPI vars.

        Structure: {"devices": [ {DEVICE_TYPE, SERIAL, MODEL, TYPE, DESCR, STATE, ...fields} ]}
        """
        devices = []

        # PVS device (minimal info)
        sysinfo = self._fetch_sysinfo()
        # Use actual serial number from PVS, not IP address
        pvs_serial = sysinfo.get("/sys/info/serialnum", f"PVS-{self.host}")
        pvs_model = sysinfo.get("/sys/info/model", "PVS")
        pvs_sw_version = sysinfo.get("/sys/info/sw_rev", "Unknown")
        devices.append(
            {
                "DEVICE_TYPE": "PVS",
                "SERIAL": pvs_serial,
                "MODEL": pvs_model,
                "TYPE": "PVS",
                "DESCR": f"{pvs_model} {pvs_serial}",
                "STATE": "working",
                "sw_ver": pvs_sw_version,
                # Legacy dl_* diagnostics unavailable via this minimal sysinfo; omit
            }
        )

        # Meter devices
        meters = self._fetch_meters()
        for path, m in meters.items():
            dev = {
                "DEVICE_TYPE": "Power Meter",
                "SERIAL": m.get("sn", "Unknown"),
                "MODEL": m.get("prodMdlNm", "Unknown"),
                "TYPE": "PVS-METER",
                "DESCR": f"Power Meter {m.get('sn', '')}",
                "STATE": "working",
            }
            # Field mappings
            dev["net_ltea_3phsum_kwh"] = m.get("netLtea3phsumKwh")
            dev["p_3phsum_kw"] = m.get("p3phsumKw")
            dev["q_3phsum_kvar"] = m.get("q3phsumKvar")
            dev["s_3phsum_kva"] = m.get("s3phsumKva")
            dev["tot_pf_rto"] = m.get("totPfRto")
            dev["v12_v"] = m.get("v12V")
            dev["v1n_v"] = m.get("v1nV")
            dev["v2n_v"] = m.get("v2nV")
            dev["freq_hz"] = m.get("freqHz")
            
            # Leg-specific fields
            if "i1A" in m:
                dev["i1_a"] = m.get("i1A")
            if "i2A" in m:
                dev["i2_a"] = m.get("i2A")
            if "p1Kw" in m:
                dev["p1_kw"] = m.get("p1Kw")
            if "p2Kw" in m:
                dev["p2_kw"] = m.get("p2Kw")
            
            # Grid/Home energy tracking (to_grid = negative, to_home = positive)
            if "negLtea3phsumKwh" in m:
                dev["neg_ltea_3phsum_kwh"] = m.get("negLtea3phsumKwh")
            if "posLtea3phsumKwh" in m:
                dev["pos_ltea_3phsum_kwh"] = m.get("posLtea3phsumKwh")
            
            devices.append(dev)

        # Inverter devices
        inverters = self._fetch_inverters()
        for path, inv in inverters.items():
            dev = {
                "DEVICE_TYPE": "Inverter",
                "SERIAL": inv.get("sn", "Unknown"),
                "MODEL": inv.get("prodMdlNm", "Unknown"),
                "TYPE": "MICRO-INVERTER",
                "DESCR": f"Inverter {inv.get('sn', '')}",
                "STATE": "working",
            }
            dev["ltea_3phsum_kwh"] = inv.get("ltea3phsumKwh")
            dev["p_mppt1_kw"] = inv.get("pMppt1Kw")
            dev["vln_3phavg_v"] = inv.get("vln3phavgV")
            dev["i_3phsum_a"] = inv.get("iMppt1A")  # best available analogue
            dev["v_mppt1_v"] = inv.get("vMppt1V")
            dev["t_htsnk_degc"] = inv.get("tHtsnkDegc")
            dev["freq_hz"] = inv.get("freqHz")
            # Optional MPPT sum if present
            if "pMpptsumKw" in inv:
                dev["p_mpptsum_kw"] = inv.get("pMpptsumKw")
            devices.append(dev)

        return {"devices": devices}

    def energy_storage_system_status(self):
        """Return minimal ESS-like structure using livedata if available.

        Structure expected by callers:
        { "ess_report": { "battery_status": [...], "ess_status": [...], "hub_plus_status": {...} } }
        If detailed vars are not available, return empty lists/dicts and let callers handle gracefully.
        """
        try:
            livedata = self._vars(match="livedata", cache="ldata", fmt_obj=True)
        except Exception:
            livedata = {}

        report = {
            "battery_status": [],
            "ess_status": [],
            "hub_plus_status": {},
        }

        # Populate minimal aggregate values if present
        if livedata:
            soc = livedata.get("/sys/livedata/soc")
            ess_p = livedata.get("/sys/livedata/ess_p")
            if soc is not None or ess_p is not None:
                report["ess_status"].append(
                    {
                        "serial_number": "ESS-AGG",
                        "ess_meter_reading": {
                            "agg_power": {"value": float(ess_p) if ess_p is not None else 0.0},
                            "meter_a": {"reading": {"current": {"value": 0}, "power": {"value": 0}, "voltage": {"value": 0}}},
                            "meter_b": {"reading": {"current": {"value": 0}, "power": {"value": 0}, "voltage": {"value": 0}}},
                        },
                        "enclosure_humidity": {"value": 0},
                        "enclosure_temperature": {"value": 0},
                    }
                )
                report["hub_plus_status"] = {
                    "serial_number": "HUBPLUS-AGG",
                    "grid_phase1_voltage": {"value": 0},
                    "grid_phase2_voltage": {"value": 0},
                    "hub_humidity": {"value": 0},
                    "hub_temperature": {"value": 0},
                    "inverter_connection_voltage": {"value": 0},
                    "load_phase1_voltage": {"value": 0},
                    "load_phase2_voltage": {"value": 0},
                }

        return {"ess_report": report}

    def network_status(self):
        """Return minimal network/system info via LocalAPI for config validation."""
        info = self._fetch_sysinfo()
        return info
