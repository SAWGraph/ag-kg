import argparse
from typing import Generator
import os
from multiprocessing import Pool
from functools import partial

import requests
from rdflib import Graph, Literal, URIRef, Namespace, XSD, OWL, TIME, RDF, RDFS, SOSA
from rdflib.namespace import DefinedNamespace
from rdflib.namespace._GEO import GEO
from shapely import set_precision, union_all
from shapely.wkt import loads
from shapely.geometry import Point, LinearRing, LineString, Polygon, MultiPolygon
from shapely.geometry.polygon import signed_area
from s2geometry import (
    S2CellId, S2RegionCoverer, S2Point, S2LatLng, S2Loop, S2Polyline, S2Polygon, S2Cell
)
from tqdm import tqdm


OUTPUT_FOLDER = "output"
SOIL_POST_REST_ENDPOINT = "https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest"

TOLERANCE = 1e-2
MINLEVEL = 13
MAXLEVEL = 13

KWG_ENDPOINT = "http://stko-kwg.geog.ucsb.edu/"
KWGR = Namespace(f"{KWG_ENDPOINT}lod/resource/")
AG = Namespace("http://w3id.org/sawgraph/v1/ag#")
DCTERMS = Namespace("http://purl.org/dc/terms/")
QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT = Namespace("https://qudt.org/vocab/unit/")


class KWG_ONT(DefinedNamespace):
    SoilMapUnit: URIRef
    SoilMapUnitObservation: URIRef
    SoilMapUnitObservationCollection: URIRef
    SoilSurveyArea: URIRef
    SoilMapUnitPolygon: URIRef
    SoilMapUnitS2OverlapObservation: URIRef

    soilSurveyArea: URIRef
    soilMapUnit: URIRef
    observedOverlapWith: URIRef

    soilMapUnitName: URIRef
    soilMapUnitSymbol: URIRef
    soilMapUnitKey: URIRef

    soilSurveyAreaSymbol: URIRef
    soilSurveyAreaName: URIRef
    soilSurveyAreaKey: URIRef

    soilMapUnitPolygonKey: URIRef

    _NS = Namespace(f"{KWG_ENDPOINT}lod/ontology/")


_PREFIX = {
    "kwgr": KWGR,
    "kwg-ont": KWG_ONT._NS,
    "ag": AG,
    "geo": Namespace("http://www.opengis.net/ont/geosparql#"),
    "geof": Namespace("http://www.opengis.net/def/function/geosparql/"),
    "sf": Namespace("http://www.opengis.net/ont/sf#"),
    "wd": Namespace("http://www.wikidata.org/entity/"),
    "wdt": Namespace("http://www.wikidata.org/prop/direct/"),
    "rdf": RDF,
    "rdfs": RDFS,
    "xsd": XSD,
    "owl": OWL,
    "time": TIME,
    "dbo": Namespace("http://dbpedia.org/ontology/"),
    "time": Namespace("http://www.w3.org/2006/time#"),
    "ssn": Namespace("http://www.w3.org/ns/ssn/"),
    "sosa": Namespace("http://www.w3.org/ns/sosa/"),
    "qudt": QUDT,
    "unit": UNIT,
    "dcterms": DCTERMS
}


class ResultTable(list[list]):
    def iter_records(self) -> Generator[dict[str, str], None, None]:
        if not self or not self[0]:
            return
        for row in self[1:]:
            yield {name: row[idx] for idx, name in enumerate(self.column_names())}

    def column_names(self) -> list[str]:
        return self[0] if self else []


class PolygonCount:
    def __init__(self, mukey: str, count: int) -> None:
        self.mukey = mukey
        self.count = count


def main(is_maine: bool = False, lkey_limit: int | None = None, mukey_limit: int | None = None) -> None:
    legend_keys = fetch_legend_keys(is_maine=is_maine)
    if lkey_limit is not None:
        legend_keys = legend_keys[:lkey_limit]

    total = len(legend_keys)
    print(f"There are {total} survey areas to triplify...")

    worker = partial(write_all_information, mukey_limit=mukey_limit)
    with Pool() as pool:
        _ = list(tqdm(pool.imap(worker, legend_keys), total=total))


def fetch_legend_keys(is_maine: bool = False) -> list[str]:
    query = "SELECT lkey FROM legend"
    if is_maine:
        query += " WHERE areasymbol LIKE 'ME%'"
    result_table = fetch_result_table(query=query)
    return [record["lkey"] for record in result_table.iter_records()]


def fetch_result_table(query: str) -> ResultTable:
    payload = {"QUERY": query, "FORMAT": "JSON+COLUMNNAME"}
    headers = {"Content-Type": "application/json; charset=utf-8"}

    response = requests.post(
        url=SOIL_POST_REST_ENDPOINT,
        headers=headers,
        json=payload,
        timeout=60
    )

    try:
        json_obj = response.json()
    except requests.exceptions.JSONDecodeError:
        snippet = (response.text or "")[:400]
        print(
            "Warning: received invalid JSON for query:\n"
            f"{query}\n"
            f"Status: {response.status_code}\n"
            f"Response snippet: {snippet}\n"
        )
        return ResultTable([[]])

    table = json_obj.get("Table")
    if not table:
        return ResultTable([[]])

    return ResultTable(table)


def write_all_information(lkey: str, mukey_limit: int | None = None) -> None:
    coverer = S2RegionCoverer()
    coverer.set_max_level(13)
    coverer.set_min_level(13)

    path = os.path.join(OUTPUT_FOLDER, lkey)
    os.makedirs(path, exist_ok=True)

    write_survey_area(lkey=lkey, path=path)

    path = os.path.join(path, "mapunits")
    write_map_units_and_polygons(lkey=lkey, path=path, coverer=coverer, mukey_limit=mukey_limit)


def write_survey_area(lkey: str, path: str) -> None:
    record = fetch_survey_area_record(lkey)
    graph = graphify_survey_area_record(record)
    for prefix in _PREFIX:
        graph.bind(prefix, _PREFIX[prefix])
    destination = os.path.join(path, f"soilSurveyArea.{lkey}.ttl")
    graph.serialize(destination=destination, format="ttl")


def fetch_survey_area_record(lkey: str) -> dict:
    result_table = fetch_result_table(query=f"SELECT * FROM legend WHERE lkey = '{lkey}'")
    record = next(result_table.iter_records(), {"lkey": lkey, "areasymbol": "", "areaname": ""})
    geometry = fetch_survey_area_geometry(lkey=lkey)
    record["geometry"] = geometry
    return record


def fetch_survey_area_geometry(lkey: str) -> Polygon | MultiPolygon | None:
    result_table = fetch_result_table(query=f"SELECT sapolygongeo FROM sapolygon WHERE lkey = '{lkey}'")
    geometries = [loads(r["sapolygongeo"]) for r in result_table.iter_records() if r.get("sapolygongeo")]
    if not geometries:
        return None
    return union_all(geometries, grid_size=1e-7)


def graphify_survey_area_record(record: dict) -> Graph:
    graph = Graph()

    lkey = record.get("lkey", "")
    areasymbol = record.get("areasymbol", "")
    areaname = record.get("areaname", "")

    area_iri = KWGR[f"soilSurveyArea.{lkey}"]
    graph.add((area_iri, RDF.type, KWG_ONT.SoilSurveyArea))
    graph.add((area_iri, RDFS.label, Literal(f"Soil survey area with legend key number {lkey}", datatype=XSD.string)))
    graph.add((area_iri, KWG_ONT.soilSurveyAreaSymbol, Literal(areasymbol, datatype=XSD.string)))
    graph.add((area_iri, KWG_ONT.soilSurveyAreaName, Literal(areaname, datatype=XSD.string)))
    graph.add((area_iri, KWG_ONT.soilSurveyAreaKey, Literal(lkey, datatype=XSD.integer)))

    geometry = record.get("geometry")
    if geometry is not None:
        geometry = set_precision(geometry=geometry, grid_size=1e-7)
        geom_type = geometry.geom_type
        geometry_iri = KWGR[f"geometry.{geom_type}.soilSurveyArea.{lkey}"]
        graph.add((area_iri, GEO.hasGeometry, geometry_iri))
        graph.add((area_iri, _PREFIX["geo"]["hasDefaultGeometry"], geometry_iri))
        graph.add((geometry_iri, RDF.type, GEO.Geometry))
        graph.add((geometry_iri, RDF.type, _PREFIX["sf"][geom_type]))
        graph.add((geometry_iri, RDFS.label, Literal(f"Geometry of soil survey area with legend key number {lkey}", datatype=XSD.string)))
        graph.add((geometry_iri, GEO.asWKT, Literal(geometry.wkt, datatype=GEO.wktLiteral)))

    return graph


def write_map_units_and_polygons(
    lkey: str,
    path: str,
    coverer: S2RegionCoverer,
    mukey_limit: int | None = None
) -> None:
    polygon_counts = fetch_polygon_counts(lkey=lkey)
    if mukey_limit is not None:
        polygon_counts = polygon_counts[:mukey_limit]

    for polygon_count in polygon_counts:
        curr_path = os.path.join(path, polygon_count.mukey)
        os.makedirs(curr_path, exist_ok=True)
        write_mapunit(polygon_count, curr_path, coverer=coverer)


def fetch_polygon_counts(lkey: str) -> list[PolygonCount]:
    query = f"""
        SELECT
            mapunit.mukey,
            COUNT(mupolygon.mukey) AS polygon_count
        FROM
            mapunit
        JOIN
            mupolygon ON mapunit.mukey = mupolygon.mukey
        WHERE
            mapunit.lkey = {lkey}
        GROUP BY
            mapunit.mukey
    """
    result_table = fetch_result_table(query=query)
    return [
        PolygonCount(mukey=r["mukey"], count=int(r["polygon_count"]))
        for r in result_table.iter_records()
        if r.get("mukey") is not None
    ]


def write_mapunit(polygon_count: PolygonCount, path: str, coverer: S2RegionCoverer) -> None:
    record = fetch_mapunit_record(polygon_count)
    record["geometry"] = write_polygons_and_fetch_union(polygon_count=polygon_count, path=path)
    graph = graphify_mapunit_record(record=record, coverer=coverer)

    for prefix in _PREFIX:
        graph.bind(prefix, _PREFIX[prefix])

    destination = os.path.join(path, f"soilMapUnit.{polygon_count.mukey}.ttl")
    graph.serialize(destination=destination, format="ttl")


def write_polygons_and_fetch_union(polygon_count: PolygonCount, path: str) -> Polygon | MultiPolygon | None:
    mukey = polygon_count.mukey
    count = polygon_count.count
    offset = 0
    record_count = 1000

    polygons_path = os.path.join(path, "polygons")
    os.makedirs(polygons_path, exist_ok=True)

    geometries = []
    while offset < count:
        query = f"""
            SELECT 
                *
            FROM
                mupolygon
            WHERE
                mukey = '{mukey}'
            ORDER BY
                (SELECT NULL)
            OFFSET
                {offset} ROWS
            FETCH
                NEXT {record_count} ROWS ONLY
        """
        result_table = fetch_result_table(query=query)
        for record in result_table.iter_records():
            write_polygon_record(record, polygons_path)
            wkt = record.get("mupolygongeo")
            if not wkt:
                continue
            geometries.append(loads(wkt))
        offset += record_count

    if not geometries:
        return None
    return union_all(geometries=geometries, grid_size=1e-7)


def write_polygon_record(record: dict, path: str) -> None:
    graph = graphify_polygon_record(record=record)
    for prefix in _PREFIX:
        graph.bind(prefix, _PREFIX[prefix])

    mupolygonkey = record["mupolygonkey"]
    destination = os.path.join(path, f"soilMapUnitPolygon.{mupolygonkey}.ttl")
    graph.serialize(destination=destination, format="ttl")


def graphify_polygon_record(record: dict) -> Graph:
    graph = Graph()

    mupolygonkey = record["mupolygonkey"]
    wkt = record["mupolygongeo"]
    mukey = record["mukey"]

    polygon_iri = KWGR[f"soilMapUnitPolygon.{mupolygonkey}"]
    graph.add((polygon_iri, RDF.type, KWG_ONT.SoilMapUnitPolygon))
    graph.add((polygon_iri, RDFS.label, Literal(f"Soil map unit polygon with key number {mupolygonkey}", datatype=XSD.string)))
    graph.add((polygon_iri, KWG_ONT.soilMapUnit, KWGR[f"soilMapUnit.{mukey}"]))
    graph.add((polygon_iri, KWG_ONT.soilMapUnitPolygonKey, Literal(mupolygonkey, datatype=XSD.integer)))

    geometry_iri = KWGR[f"geometry.polygon.soilMapUnitPolygon.{mupolygonkey}"]
    graph.add((polygon_iri, GEO.hasGeometry, geometry_iri))
    graph.add((polygon_iri, _PREFIX["geo"]["hasDefaultGeometry"], geometry_iri))
    graph.add((geometry_iri, RDF.type, GEO.Geometry))
    graph.add((geometry_iri, RDF.type, _PREFIX["sf"]["Polygon"]))
    graph.add((geometry_iri, RDFS.label, Literal(f"Geometry of soil map unit polygon with key number {mupolygonkey}", datatype=XSD.string)))
    graph.add((geometry_iri, GEO.asWKT, Literal(wkt, datatype=GEO.wktLiteral)))

    return graph


def fetch_mapunit_record(polygon_count: PolygonCount) -> dict:
    """Fetch mapunit attributes and horizon-level soil properties.

    Default behavior:
        - keep ALL components in the mapunit
        - keep only horizons that overlap the upper 0-30 cm depth interval
        - attach the 4 requested properties per horizon:
            om_r, cec7_r, ph1to1h2o_r, texture

    To retrieve all horizons later, see the commented SQL block below.
    """
    mukey = polygon_count.mukey

    # Default: topsoil query, keeping all components and all horizons that overlap 0-30 cm.
    # The overlap condition is:
    #     horizon top depth < 30 cm AND horizon bottom depth > 0 cm
    # This includes horizons such as 0-20 cm and 20-45 cm because the latter overlaps
    # the 0-30 cm interval from 20-30 cm.
    depth_filter = """
        AND hz.hzdept_r < 30
        AND hz.hzdepb_r > 0
    """

    # If later you want ALL horizons for every component, comment out the depth_filter
    # above and uncomment the line below:
    # depth_filter = ""

    query = f"""
        SELECT
            mu.mukey,
            mu.musym,
            mu.muname,
            mu.lkey,

            c.cokey,
            c.compname,
            c.comppct_r,

            hz.chkey,
            hz.hzname,
            hz.hzdept_r,
            hz.hzdepb_r,

            hz.om_r,
            hz.cec7_r,
            hz.ph1to1h2o_r,
            txg.texdesc AS texture
        FROM mapunit mu
        JOIN component c ON mu.mukey = c.mukey
        JOIN chorizon hz ON c.cokey = hz.cokey
        LEFT JOIN chtexturegrp txg ON hz.chkey = txg.chkey
        WHERE mu.mukey = '{mukey}'
        {depth_filter}
        ORDER BY c.comppct_r DESC, c.cokey, hz.hzdept_r, hz.hzdepb_r
    """

    result_table = fetch_result_table(query=query)
    # Keep rows separate. chtexturegrp may return multiple texture values for the same horizon;
    # those will become separate texture observations below.
    rows = list(result_table.iter_records())

    if not rows:
        return {"mukey": mukey, "musym": "", "muname": "", "lkey": "", "horizons": []}

    base = rows[0]
    return {
        "mukey": base.get("mukey", mukey),
        "musym": base.get("musym", ""),
        "muname": base.get("muname", ""),
        "lkey": base.get("lkey", ""),
        "horizons": rows,
    }


def _literal_for_value(value):
    """Return an rdflib Literal with a reasonable datatype for SDA values."""
    text = str(value).strip()
    if text == "":
        return Literal(value, datatype=XSD.string)
    try:
        integer_value = int(text)
        if text == str(integer_value):
            return Literal(integer_value, datatype=XSD.integer)
    except ValueError:
        pass
    try:
        decimal_value = float(text)
        return Literal(decimal_value, datatype=XSD.decimal)
    except ValueError:
        return Literal(value, datatype=XSD.string)




def graphify_mapunit_record(record: dict, coverer: S2RegionCoverer) -> Graph:
    graph = Graph()

    musym = record.get("musym", "")
    muname = record.get("muname", "")
    mukey = record["mukey"]

    map_unit_iri = KWGR[f"soilMapUnit.{mukey}"]
    graph.add((map_unit_iri, RDF.type, KWG_ONT.SoilMapUnit))
    graph.add((map_unit_iri, RDFS.label, Literal(f"Soil map unit with key number {mukey}", datatype=XSD.string)))
    graph.add((map_unit_iri, KWG_ONT.soilMapUnitName, Literal(muname, datatype=XSD.string)))
    graph.add((map_unit_iri, KWG_ONT.soilMapUnitSymbol, Literal(musym, datatype=XSD.string)))
    graph.add((map_unit_iri, KWG_ONT.soilMapUnitKey, Literal(mukey, datatype=XSD.integer)))

    lkey = record.get("lkey", "")
    if lkey:
        graph.add((map_unit_iri, KWG_ONT.soilSurveyArea, KWGR[f"soilSurveyArea.{lkey}"]))

    # Horizon-level observations are grouped by horizon, not by map unit.
    # Mapunit-level retrieval remains possible through:
    #   SoilMapUnit -> ag:hasSoilComponent -> SoilComponent -> ag:hasSoilHorizon -> SoilHorizon
    #              -> sosa:isFeatureOfInterestOf -> SoilHorizonObservationCollection
    #              -> sosa:hasMember -> SoilHorizonObservation
    #
    # We therefore do NOT create kwg-ont:SoilMapUnitObservationCollection here.

    # Horizon/component vocabulary minted in the SAWGraph agriculture ontology namespace.
    # These keep the existing observation pattern, but preserve the SSURGO hierarchy:
    # mapunit -> component -> horizon -> observation.
    SOIL_COMPONENT_CLASS = AG.SoilComponent
    SOIL_HORIZON_CLASS = AG.SoilHorizon

    has_soil_component = AG.hasSoilComponent
    has_soil_horizon = AG.hasSoilHorizon
    horizon_of_component = AG.horizonOfComponent

    soil_component_key = AG.soilComponentKey
    soil_component_name = AG.soilComponentName
    component_area_percentage = AG.componentAreaPercentage

    soil_horizon_key = AG.soilHorizonKey
    soil_horizon_name = AG.soilHorizonName
    soil_horizon_top_cm = AG.soilHorizonTopDepthCm
    soil_horizon_bottom_cm = AG.soilHorizonBottomDepthCm

    # Only these 4 soil properties are emitted.
    # Keys are SDA column names; values are cleaner observable property local names.
    property_name_map = {
        "om_r": "organic_matter",
        "cec7_r": "cation_exchange_capacity_ph_7",
        "ph1to1h2o_r": "ph_1_to_1_water",
        "texture": "texture",
    }
    four_props = list(property_name_map.keys())

    for hz in record.get("horizons", []) or []:
        cokey = hz.get("cokey")
        compname = hz.get("compname", "")
        comppct_r = hz.get("comppct_r")

        chkey = hz.get("chkey")
        hzname = hz.get("hzname", "")
        hzdept_r = hz.get("hzdept_r")
        hzdepb_r = hz.get("hzdepb_r")

        component_iri = AG[f"soilComponent.{cokey}"] if cokey else None
        horizon_iri = AG[f"soilHorizon.{chkey}"] if chkey else None

        if component_iri is not None:
            graph.add((component_iri, RDF.type, SOIL_COMPONENT_CLASS))
            graph.add((component_iri, RDFS.label, Literal(
                f"Soil component {compname} in map unit {mukey}",
                datatype=XSD.string
            )))
            graph.add((map_unit_iri, has_soil_component, component_iri))
            graph.add((component_iri, soil_component_key, Literal(cokey, datatype=XSD.string)))
            if compname:
                graph.add((component_iri, soil_component_name, Literal(compname, datatype=XSD.string)))
            if comppct_r is not None:
                graph.add((component_iri, component_area_percentage, _literal_for_value(comppct_r)))

        if horizon_iri is not None:
            graph.add((horizon_iri, RDF.type, SOIL_HORIZON_CLASS))
            graph.add((horizon_iri, RDFS.label, Literal(
                f"Soil horizon {hzname} ({hzdept_r}-{hzdepb_r} cm) for component {compname} in map unit {mukey}",
                datatype=XSD.string
            )))
            graph.add((horizon_iri, soil_horizon_key, Literal(chkey, datatype=XSD.string)))
            if hzname:
                graph.add((horizon_iri, soil_horizon_name, Literal(hzname, datatype=XSD.string)))
            if hzdept_r is not None:
                graph.add((horizon_iri, soil_horizon_top_cm, _literal_for_value(hzdept_r)))
            if hzdepb_r is not None:
                graph.add((horizon_iri, soil_horizon_bottom_cm, _literal_for_value(hzdepb_r)))
            if component_iri is not None:
                graph.add((component_iri, has_soil_horizon, horizon_iri))
                graph.add((horizon_iri, horizon_of_component, component_iri))

        if horizon_iri is not None:
            # Horizon-specific observation collection.
            # The collection is the object directly about the horizon.
            # Individual observations are members of this collection 
            horizon_collection_iri = AG[
                f"soilHorizonObservationCollection.{mukey}.{cokey or 'unknownComponent'}.{chkey}"
            ]
            graph.add((horizon_iri, SOSA.isFeatureOfInterestOf, horizon_collection_iri))
            graph.add((horizon_collection_iri, RDF.type, AG.SoilHorizonObservationCollection))
            graph.add((horizon_collection_iri, SOSA.hasFeatureOfInterest, horizon_iri))
            graph.add((horizon_collection_iri, RDFS.label, Literal(
                f"Observation collection for soil horizon {hzname} ({hzdept_r}-{hzdepb_r} cm), component {compname}, map unit {mukey}",
                datatype=XSD.string
            )))
        else:
            horizon_collection_iri = None

        for key in four_props:
            value = hz.get(key)
            if value is None or str(value).strip() == "":
                continue

            property_name = property_name_map[key]
            component_suffix = cokey or "unknownComponent"
            horizon_suffix = chkey or f"{hzname}.{hzdept_r}.{hzdepb_r}"

            # One observation IRI per horizon + property.
            # If texture has multiple SDA rows for the same horizon, this creates one
            # texture observation with multiple sosa:hasSimpleResult values.
            observation_iri = AG[
                f"soilHorizonObservation.{mukey}.{component_suffix}.{horizon_suffix}.{property_name}"
            ]

            graph.add((observation_iri, RDF.type, AG.SoilHorizonObservation))
            graph.add((observation_iri, RDFS.label, Literal(
                f"Observation of {property_name} for horizon {hzname} ({hzdept_r}-{hzdepb_r} cm), component {compname}, map unit {mukey}",
                datatype=XSD.string
            )))
            graph.add((observation_iri, SOSA.observedProperty, AG[f"soilObservableProperty.{property_name}"]))

            if horizon_collection_iri is not None:
                graph.add((horizon_collection_iri, SOSA.hasMember, observation_iri))

            graph.add((observation_iri, SOSA.hasSimpleResult, _literal_for_value(value)))

    # KEEP original S2 overlap logic
    geometry = record.get("geometry")
    if geometry is not None:
        s2_object = s2_approximation(geometry=geometry)
        for cell_id in covering(geometry=geometry, coverer=coverer):
            id_int = cell_id.id()
            observation_iri = KWGR[f"soilMapUnitS2OverlapObservation.{id_int}.{mukey}"]
            graph.add((observation_iri, RDF.type, KWG_ONT.SoilMapUnitS2OverlapObservation))
            graph.add((observation_iri, RDFS.label, Literal(
                f"Observation of the area (in meters squared) of the overlap  of the S2 Cell having ID {id_int} with the soil map unit having key {mukey}",
                datatype=XSD.string
            )))

            cell_iri = fetch_cell_iri(cell_id=cell_id)
            graph.add((cell_iri, SOSA.isFeatureOfInterestOf, observation_iri))

            cell = S2Cell(cell_id)
            s2_polygon = S2Polygon(cell)
            overlap_fraction, _ = S2Polygon.GetOverlapFractions(s2_polygon, s2_object)
            s2_cell_area = cell.ApproxArea()
            earth_cell_area = s2_cell_area * (6.3781e6) * (6.3781e6)
            overlapping_area = overlap_fraction * earth_cell_area

            graph.add((observation_iri, SOSA.hasSimpleResult, Literal(overlapping_area, datatype=XSD.decimal)))
            graph.add((observation_iri, KWG_ONT.observedOverlapWith, map_unit_iri))
            graph.add((observation_iri, SOSA.observedProperty, KWGR["s2OverlapObservableProperty.soilMapUnitOverlapArea"]))

    return graph


def fetch_cell_iri(cell_id: S2CellId) -> URIRef:
    level = cell_id.level()
    id_str = cell_id.id()
    return KWGR[f"{'s2.level'}{level}.{id_str}"]


def s2_from_coords(
    geometry: tuple | Point | LinearRing | LineString | Polygon | MultiPolygon
) -> S2Point | S2Loop | S2Polyline | S2Polygon:
    if isinstance(geometry, tuple):
        return S2LatLng.FromDegrees(*geometry[::-1]).ToPoint()
    elif isinstance(geometry, Point):
        return S2LatLng.FromDegrees(*geometry.coords[0][::-1]).ToPoint()
    elif isinstance(geometry, LinearRing):
        s2_loop = S2Loop()
        s2_loop.Init(list(map(s2_from_coords, list(geometry.coords)[:-1])))
        return s2_loop
    elif isinstance(geometry, LineString):
        polyline = S2Polyline()
        polyline.InitFromS2Points(list(map(s2_from_coords, geometry.coords)))
        return polyline
    elif isinstance(geometry, (Polygon, MultiPolygon)):
        loops = map(s2_from_coords, map(orient, boundaries(geometry)))
        s2_polygon = S2Polygon()
        s2_polygon.InitNested(list(loops))
        return s2_polygon


def s2_approximation(
    geometry: S2Point | LinearRing | LineString | Polygon | MultiPolygon,
    tolerance: float = TOLERANCE
) -> S2Point | S2Loop | S2Polyline | S2Polygon:
    return s2_from_coords(geometry.segmentize(tolerance))


def orient(
    geometry: LinearRing | Polygon | MultiPolygon,
    sign: float = 1.0
) -> LinearRing | Polygon | MultiPolygon:
    sign = float(sign)
    if isinstance(geometry, LinearRing):
        return geometry if signed_area(geometry) / sign >= 0 else geometry.reverse()
    elif isinstance(geometry, Polygon):
        exterior = orient(geometry.exterior, sign)
        oppositely_orient = partial(orient, sign=-sign)
        interiors = list(map(oppositely_orient, geometry.interiors))
        return Polygon(exterior, interiors)
    elif isinstance(geometry, MultiPolygon):
        orient_with_sign = partial(orient, sign=sign)
        return MultiPolygon(list(map(orient_with_sign, geometry.geoms)))


def boundaries(geometry: Polygon | MultiPolygon) -> Generator[LinearRing, None, None]:
    polygons = [geometry] if isinstance(geometry, Polygon) else geometry.geoms
    for polygon in polygons:
        yield polygon.exterior
        for interior in polygon.interiors:
            yield interior


def covering(
    geometry: Polygon | MultiPolygon,
    coverer: S2RegionCoverer,
    tolerance: float = TOLERANCE
) -> list[S2CellId]:
    s2_obj = s2_approximation(geometry, tolerance)
    return coverer.GetCovering(s2_obj)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.set_start_method("spawn", force=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--maine", action="store_true", help="filter to Maine (areasymbol LIKE 'ME%')")
    parser.add_argument("--test", action="store_true", help="use with limits for quick test runs")
    parser.add_argument("--lkey_limit", type=int, default=None)
    parser.add_argument("--mukey_limit", type=int, default=None)
    args = parser.parse_args()

    if args.maine:
        print("Maine filter is on...")
    if args.test:
        print("Test mode is on... (using limits if provided)")

    main(is_maine=args.maine, lkey_limit=args.lkey_limit, mukey_limit=args.mukey_limit)
