#!/usr/bin/env python3
import re
import sys
import time
from pathlib import Path

import requests

KWG_ENDPOINT = "https://stko-kwg.geog.ucsb.edu/graphdb/repositories/KWG"
OUT_DIR = Path.home() / "Desktop" / "kwg_maine_cropland_by_county"
OUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS_TTL = {"Accept": "text/turtle"}
HEADERS_JSON = {"Accept": "application/sparql-results+json"}

# If KWG SSL chain fails on your machine, keep verify=False.
# If SSL works, set VERIFY_SSL=True.
VERIFY_SSL = False


def safe_filename(s: str) -> str:
    """Turn a label into a safe filename."""
    s = s.strip().lower()
    s = s.replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown_county"


def run_select(query: str) -> dict:
    """Run a SELECT query and return JSON results."""
    resp = requests.post(
        KWG_ENDPOINT,
        data={"query": query},
        headers=HEADERS_JSON,
        verify=VERIFY_SSL,
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()


def run_construct(query: str) -> str:
    """Run a CONSTRUCT query and return Turtle text."""
    resp = requests.post(
        KWG_ENDPOINT,
        data={"query": query},
        headers=HEADERS_TTL,
        verify=VERIFY_SSL,
        timeout=600,
    )
    resp.raise_for_status()
    return resp.text


def get_maine_counties():
    # Counties are modeled as admin regions that are administrativePartOf Maine (USA.23)
    # Labels look like "Androscoggin County, Maine"
    q = """
PREFIX kwg-ont: <http://stko-kwg.geog.ucsb.edu/lod/ontology/>
PREFIX kwgr: <http://stko-kwg.geog.ucsb.edu/lod/resource/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?county ?label
WHERE {
  ?county kwg-ont:administrativePartOf kwgr:administrativeRegion.USA.23 ;
          rdfs:label ?label .
  FILTER(CONTAINS(STR(?county), "administrativeRegion.USA.23"))
}
ORDER BY ?label
"""
    data = run_select(q)
    bindings = data["results"]["bindings"]
    counties = []
    for b in bindings:
        county_iri = b["county"]["value"]
        label = b["label"]["value"]
        counties.append((county_iri, label))
    return counties


def construct_for_county(county_iri: str) -> str:
    # CONSTRUCT, parameterized by the county IRI
    return f"""
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX kwg-ont: <http://stko-kwg.geog.ucsb.edu/lod/ontology/>
PREFIX kwgr: <http://stko-kwg.geog.ucsb.edu/lod/resource/>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

CONSTRUCT {{
    ?s2Cell sosa:isFeatureOfInterestOf ?croplandObsCollection .
    ?croplandObsCollection rdf:type kwg-ont:CroplandS2OverlapObservationCollection .
    ?croplandObsCollection rdfs:label ?label .
    ?croplandObsCollection sosa:phenomenonTime ?kwgrInstant .
    ?croplandObsCollection sosa:hasMember ?CroplandS2OverlapObservation .
    ?CroplandS2OverlapObservation rdf:type kwg-ont:CroplandS2OverlapObservation .
    ?CroplandS2OverlapObservation rdfs:label ?description .
    ?CroplandS2OverlapObservation sosa:observedProperty ?observedProperty .
    ?CroplandS2OverlapObservation sosa:hasSimpleResult ?sosaSimpleResult .
}}
WHERE {{
    <{county_iri}> kwg-ont:sfContains ?s2Cell .
    ?s2Cell sosa:isFeatureOfInterestOf ?croplandObsCollection .
    ?croplandObsCollection rdf:type kwg-ont:CroplandS2OverlapObservationCollection .
    ?croplandObsCollection rdfs:label ?label .
    ?croplandObsCollection sosa:phenomenonTime ?kwgrInstant .
    ?croplandObsCollection sosa:hasMember ?CroplandS2OverlapObservation .
    ?CroplandS2OverlapObservation rdf:type kwg-ont:CroplandS2OverlapObservation .
    ?CroplandS2OverlapObservation rdfs:label ?description .
    ?CroplandS2OverlapObservation sosa:observedProperty ?observedProperty .
    ?CroplandS2OverlapObservation sosa:hasSimpleResult ?sosaSimpleResult .
}}
"""


def extract_fips_from_iri(county_iri: str) -> str:
    # Example: .../administrativeRegion.USA.23001 -> "23001"
    m = re.search(r"administrativeRegion\.USA\.(\d+)$", county_iri)
    return m.group(1) if m else "unknown"


def main():
    print(f"Output directory: {OUT_DIR}")
    print("Fetching Maine counties...")
    counties = get_maine_counties()
    print(f"Found {len(counties)} counties.")

    
    for i, (county_iri, label) in enumerate(counties, start=1):
        fips = extract_fips_from_iri(county_iri)
        fname = f"cropland_{safe_filename(label)}_{fips}.ttl"
        out_path = OUT_DIR / fname

        print(f"[{i}/{len(counties)}] Exporting {label} ({county_iri}) -> {out_path.name}")

        q = construct_for_county(county_iri)

        try:
            ttl_text = run_construct(q)
        except requests.HTTPError as e:
            # Print server response for debugging
            print(f"  ERROR: HTTP {e.response.status_code}")
            print(e.response.text[:1000])
            continue
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        # If server returned HTML error page, don't save as TTL
        if ttl_text.lstrip().lower().startswith("<!doctype html") or "<html" in ttl_text[:200].lower():
            print("  ERROR: Looks like HTML (not Turtle). Not saving.")
            continue

        out_path.write_text(ttl_text, encoding="utf-8")
        print(f"  Saved {out_path.stat().st_size / 1024:.1f} KB")

    
        time.sleep(0.3)

    print("Done.")


if __name__ == "__main__":
    # to export just one county by FIPS:
    #   python export_kwg_cropland_by_county.py 23001
    if len(sys.argv) == 2:
        target_fips = sys.argv[1].strip()
        counties = get_maine_counties()
        match = [(iri, lbl) for iri, lbl in counties if extract_fips_from_iri(iri) == target_fips]
        if not match:
            print(f"No county found for FIPS {target_fips}")
            sys.exit(1)
        county_iri, label = match[0]
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUT_DIR / f"cropland_{safe_filename(label)}_{target_fips}.ttl"
        ttl_text = run_construct(construct_for_county(county_iri))
        out_path.write_text(ttl_text, encoding="utf-8")
        print(f"Saved {out_path}")
    else:
        main()

