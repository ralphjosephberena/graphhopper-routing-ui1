# graphhopper_ui.py
import streamlit as st
import requests
import urllib.parse
import pandas as pd
from typing import Tuple, Dict

st.set_page_config(page_title="GraphHopper Routing UI", layout="wide")

# --- Helpers -----------------------------------------------------------------
GRAPHOPPER_GEOCODE = "https://graphhopper.com/api/1/geocode"
GRAPHOPPER_ROUTE = "https://graphhopper.com/api/1/route"

@st.cache_data(show_spinner=False)
def geocode_location(location: str, api_key: str) -> Tuple[int, dict]:
    """
    Geocode a location string using GraphHopper Geocoding API.
    Returns: (status_code, data)
    data contains: lat, lng, name, osm_value, state, country (when available)
    """
    params = {"q": location, "limit": "1", "key": api_key}
    url = GRAPHOPPER_GEOCODE + "?" + urllib.parse.urlencode(params)
    resp = requests.get(url, timeout=10)
    try:
        j = resp.json()
    except Exception:
        j = {}
    if resp.status_code != 200:
        return resp.status_code, {"error": j.get("message", "Unknown error")}
    hits = j.get("hits", [])
    if not hits:
        return 200, {"lat": None, "lng": None, "name": location, "osm_value": None}
    hit = hits[0]
    return 200, {
        "lat": hit["point"]["lat"],
        "lng": hit["point"]["lng"],
        "name": hit.get("name", location),
        "osm_value": hit.get("osm_value", ""),
        "state": hit.get("state", ""),
        "country": hit.get("country", ""),
        "raw": hit
    }

@st.cache_data(show_spinner=False)
def get_route(start: Tuple[float, float], end: Tuple[float, float], vehicle: str, api_key: str) -> Tuple[int, dict]:
    """
    Request routing from GraphHopper.
    start and end are (lat, lng).
    Returns (status_code, json_data)
    """
    # GraphHopper expects &point=lat,lng multiple times
    params = {"key": api_key, "vehicle": vehicle}
    base = GRAPHOPPER_ROUTE + "?" + urllib.parse.urlencode(params)
    op = f"&point={start[0]},{start[1]}"
    dp = f"&point={end[0]},{end[1]}"
    # ask for instructions and alternative attributes
    extra = "&instructions=true&calc_points=true&points_encoded=true"
    url = base + op + dp + extra
    resp = requests.get(url, timeout=15)
    try:
        j = resp.json()
    except Exception:
        j = {}
    return resp.status_code, j

# --- UI layout ---------------------------------------------------------------
st.title("GraphHopper Routing — Web UI")
st.markdown("Enter start and destination, pick a vehicle, and see directions and summary.")

# Sidebar: API key and options
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("GraphHopper API key", value="7fc6933f-2209-4248-8ca4-d11d6eacfd68", type="password")
    st.caption("Provide your GraphHopper API key. Default is prefilled from your script.")
    st.markdown("---")
    st.caption("Developer tip: keep your key secret for production.")

# Main input area
col1, col2 = st.columns([1, 1])
with col1:
    start_input = st.text_input("Starting location", value="Manila, Philippines")
with col2:
    end_input = st.text_input("Destination", value="Makati, Philippines")

vehicle = st.selectbox("Vehicle profile", options=["car", "bike", "foot"], index=0)

run_btn = st.button("Get Route")

# --- Action when button pressed ---------------------------------------------
if run_btn:
    if api_key.strip() == "":
        st.error("Please provide a GraphHopper API key in the sidebar.")
    elif start_input.strip() == "" or end_input.strip() == "":
        st.error("Please provide both starting location and destination.")
    else:
        with st.spinner("Geocoding start..."):
            s_status, s_data = geocode_location(start_input, api_key)
        with st.spinner("Geocoding destination..."):
            d_status, d_data = geocode_location(end_input, api_key)

        if s_status != 200 or d_status != 200:
            st.error(f"Geocoding failed: start_status={s_status}, dest_status={d_status}")
            st.json({"start_resp": s_data, "dest_resp": d_data})
        elif s_data.get("lat") is None or d_data.get("lat") is None:
            st.warning("One of the geocoding queries returned no results.")
            st.json({"start": s_data, "dest": d_data})
        else:
            start_coords = (s_data["lat"], s_data["lng"])
            dest_coords = (d_data["lat"], d_data["lng"])

            with st.spinner("Requesting route..."):
                r_status, r_json = get_route(start_coords, dest_coords, vehicle, api_key)

            if r_status != 200:
                st.error(f"Routing failed (status {r_status}). See response below.")
                st.json(r_json)
            else:
                # Extract primary path (first path)
                paths = r_json.get("paths", [])
                if not paths:
                    st.error("No paths returned by the Routing API.")
                    st.json(r_json)
                else:
                    path = paths[0]

                    # Distance and time
                    distance_m = path.get("distance", 0.0)  # in meters
                    distance_km = distance_m / 1000.0
                    # Convert to miles
                    distance_miles = distance_km / 1.609344
                    time_ms = path.get("time", 0)
                    # derive hours, minutes, seconds
                    total_seconds = int(time_ms / 1000)
                    hrs = total_seconds // 3600
                    mins = (total_seconds % 3600) // 60
                    secs = total_seconds % 60

                    st.subheader("Route summary")
                    c1, c2, c3 = st.columns([1, 1, 1])
                    c1.metric("Distance (km)", f"{distance_km:.2f}")
                    c2.metric("Distance (miles)", f"{distance_miles:.2f}")
                    c3.metric("Duration (hh:mm:ss)", f"{hrs:02d}:{mins:02d}:{secs:02d}")

                    # Show start and dest info
                    st.markdown("**From → To**")
                    st.write(f"- **From:** {s_data.get('name')} ({start_coords[0]}, {start_coords[1]})")
                    st.write(f"- **To:** {d_data.get('name')} ({dest_coords[0]}, {dest_coords[1]})")
                    st.write("---")

                    # Show step-by-step instructions
                    instr = path.get("instructions", [])
                    if instr:
                        st.subheader("Turn-by-turn instructions")
                        for i, ins in enumerate(instr):
                            txt = ins.get("text", "(no text)")
                            dist = ins.get("distance", 0.0) / 1000.0  # km
                            # time for that instruction (ms -> sec)
                            ins_time_ms = ins.get("time", 0)
                            tsec = int(ins_time_ms / 1000)
                            th = tsec // 3600
                            tm = (tsec % 3600) // 60
                            ts = tsec % 60
                            with st.expander(f"{i+1}. {txt} — {dist:.2f} km"):
                                st.write(f"Distance: {dist:.3f} km / {(dist/1.609344):.3f} miles")
                                st.write(f"Estimated time: {th:02d}:{tm:02d}:{ts:02d}")
                                st.json(ins)

                    else:
                        st.info("No step-by-step instructions available in the response.")
                        st.json(path)

                    # Simple map showing start and end markers
                    try:
                        st.subheader("Map (Start & Destination)")
                        df_map = pd.DataFrame(
                            [{"lat": start_coords[0], "lon": start_coords[1], "label": "Start"},
                             {"lat": dest_coords[0], "lon": dest_coords[1], "label": "Destination"}]
                        )
                        # st.map expects columns named 'lat' and 'lon' OR a DataFrame with numeric columns
                        st.map(df_map.rename(columns={"lat": "lat", "lon": "lon"})[["lat", "lon"]])
                        # also show a small table with labels
                        st.table(df_map)
                    except Exception as e:
                        st.warning(f"Could not render map: {e}")

                    # Show raw response and allow download
                    st.subheader("Raw routing JSON")
                    st.download_button("Download JSON", data=str(r_json), file_name="graphhopper_route.json")
                    st.json(r_json)
